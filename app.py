"""
CSUBot - Flask Backend with V1 Auth
- SQLite user store, no flat files
- bcrypt cost 12
- Email-only identity, no username
- Roles: student (chat), staff (RAG/FAQ), admin (approve accounts)
- Form POST login, not JSON
- Client-stored server-signed session cookie (NOT server-side store)
- session.clear() on login (session fixation prevention)
- POST /logout only
- HttpOnly + Secure + SameSite=Lax cookie flags
- 8-hour fixed session lifetime, no sliding window
- Brute-force lockout: 5 failures / 900s by email OR ip (blunt, documented)
- Compound index on login_attempts(email, attempted_at)

Run with:
  gunicorn --bind 0.0.0.0:5000 --timeout 120 --worker-class gthread app:app
"""

import html
import json
import os
import sqlite3
import tempfile
import hashlib
import time
import requests
import bcrypt
from flask import (Flask, request, Response, stream_with_context,
                   session, redirect, url_for, jsonify,
                   send_from_directory)
from rag import build_system_prompt, refresh_knowledge
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

# ── Configuration ─────────────────────────────────────────────
OLLAMA_HOST      = 'http://127.0.0.1:11434'
DEFAULT_MODEL    = 'qwen3:1.7b'
RATE_LIMIT       = 200          # max chat requests per IP per hour
RATE_WINDOW      = 3600         # seconds
ALLOWED_ROLES    = {'user', 'assistant', 'system'}
ACCOUNT_ROLES    = {'student', 'staff', 'admin'}
SIGNUP_ROLES     = {'student', 'staff'}
MAX_MSG_LEN      = 4000
ROOT             = os.path.dirname(__file__)
DB_PATH          = os.path.join(ROOT, 'csubot.db')
KNOWLEDGE_DIR    = os.path.join(ROOT, 'knowledge')
KNOWLEDGE_FILES  = (
    'about.md', 'library.md', 'dining.md', 'calendar.md', 'campus.md'
)
SECRET_KEY       = os.environ.get('CSUBOT_SECRET', 'CHANGE_THIS_IN_PRODUCTION')
SESSION_HOURS    = 8            # fixed lifetime, no sliding window
MAX_FAILED_LOGIN = 5
LOCKOUT_SECONDS  = 900          # 15 minutes
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 8-hour fixed session lifetime
app.permanent_session_lifetime = timedelta(hours=SESSION_HOURS)

# Cookie security flags
app.config.update(
    SESSION_COOKIE_HTTPONLY = True,
    SESSION_COOKIE_SECURE   = False,   # False for local HTTP; True in production
    SESSION_COOKIE_SAMESITE = 'Lax',
    SESSION_COOKIE_NAME     = 'csubot_session',
)

CORS(app,
     origins=['https://cs.csub.edu', 'http://localhost'],
     supports_credentials=True)

# ── Database ──────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_column(conn, table, name, spec):
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
    if name not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT    NOT NULL,
                ip           TEXT    NOT NULL,
                success      INTEGER NOT NULL DEFAULT 0,
                attempted_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_login_attempts_email_time
                ON login_attempts (email, attempted_at);

            CREATE TABLE IF NOT EXISTS faqs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                question   TEXT    NOT NULL,
                answer     TEXT    NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
        """)
        _ensure_column(conn, 'users', 'role', "TEXT NOT NULL DEFAULT 'student'")
        _ensure_column(conn, 'users', 'status', "TEXT NOT NULL DEFAULT 'approved'")

init_db()

# ── Helpers ───────────────────────────────────────────────────
def read_html(name):
    with open(os.path.join(ROOT, name), encoding='utf-8') as f:
        return f.read()

def show_box(html_text, placeholder, message, open_style='display:block;'):
    if not message:
        return html_text
    needle = f'style="display:none;">{placeholder}'
    return html_text.replace(
        needle,
        f'style="{open_style}">{html.escape(message)}'
    )

def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM users WHERE LOWER(email) = ?',
            (email.lower(),)
        ).fetchone()

def get_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()

def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return get_user_by_id(user_id)

def redirect_for_user(user):
    if not user or user['status'] != 'approved':
        return redirect(url_for('pending_page'))
    if user['role'] == 'admin':
        return redirect(url_for('admin_page'))
    if user['role'] == 'staff':
        return redirect(url_for('staff_page'))
    return redirect(url_for('index'))

def record_attempt(email, ip, success):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO login_attempts (email, ip, success) VALUES (?, ?, ?)',
            (email.lower(), ip, 1 if success else 0)
        )

def is_locked_out(email, ip):
    """
    Blunt lockout: triggers on email OR ip.
    Known tradeoff: shared NAT (campus Wi-Fi, lab) can punish innocent users.
    Acceptable at current scale. Fix later by splitting into separate counters
    with a higher threshold for IP-only lockout.
    """
    cutoff = int(time.time()) - LOCKOUT_SECONDS
    with get_db() as conn:
        failed = conn.execute("""
            SELECT COUNT(*) FROM login_attempts
            WHERE (LOWER(email) = ? OR ip = ?)
              AND success = 0
              AND attempted_at > ?
        """, (email.lower(), ip, cutoff)).fetchone()[0]
    return failed >= MAX_FAILED_LOGIN

def count_recent_failures(email, ip):
    cutoff = int(time.time()) - LOCKOUT_SECONDS
    with get_db() as conn:
        return conn.execute("""
            SELECT COUNT(*) FROM login_attempts
            WHERE (LOWER(email) = ? OR ip = ?)
              AND success = 0
              AND attempted_at > ?
        """, (email.lower(), ip, cutoff)).fetchone()[0]

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.method == 'POST':
                return jsonify({'error': 'Unauthorized. Please log in.'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def approved_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user = current_user()
            if not user:
                session.clear()
                return redirect(url_for('login_page'))
            if user['status'] != 'approved':
                if request.is_json:
                    return jsonify({'error': 'Account pending approval.'}), 403
                return redirect(url_for('pending_page'))
            if roles and user['role'] not in roles:
                if request.is_json:
                    return jsonify({'error': 'Forbidden.'}), 403
                return redirect_for_user(user)
            return f(*args, **kwargs)
        return decorated
    return decorator

def role_nav(user):
    links = []
    if user['role'] == 'admin':
        links.append('<a class="config-btn" href="/admin">Approve users</a>')
    if user['role'] == 'staff':
        links.append('<a class="config-btn" href="/staff">Knowledge</a>')
    return ''.join(links)

# ── Rate limiting (chat only) ─────────────────────────────────
RATE_DIR = os.path.join(tempfile.gettempdir(), 'csubot_rl')
os.makedirs(RATE_DIR, exist_ok=True)

def is_rate_limited(ip):
    cache_file = os.path.join(RATE_DIR, hashlib.md5(ip.encode()).hexdigest() + '.json')
    now = time.time()
    log = []
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                log = [t for t in json.load(f).get('r', []) if now - t < RATE_WINDOW]
        except Exception:
            log = []
    if len(log) >= RATE_LIMIT:
        return True
    log.append(now)
    with open(cache_file, 'w') as f:
        json.dump({'r': log}, f)
    return False

# ── Auth routes ───────────────────────────────────────────────
@app.route('/login', methods=['GET'])
def login_page():
    user = current_user()
    if user:
        return redirect_for_user(user)
    page = read_html('login.html')
    page = show_box(page, '__ERROR__', request.args.get('error', ''))
    page = show_box(page, '__NOTICE__', request.args.get('notice', ''))
    return page


@app.route('/login', methods=['POST'])
def login():
    # Form POST — read from request.form, not JSON
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    ip       = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not email or not password:
        return redirect(url_for('login_page', error='Email and password are required.'))

    if is_locked_out(email, ip):
        return redirect(url_for('login_page',
            error='Too many failed attempts. Try again in 15 minutes.'))

    user = get_user_by_email(email)

    # Always run bcrypt regardless of whether user exists.
    # Prevents timing attack that reveals whether an email is registered.
    dummy_hash  = b'$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    stored_hash = user['password_hash'].encode() if user else dummy_hash

    password_ok = False
    try:
        password_ok = bcrypt.checkpw(password.encode(), stored_hash)
    except Exception:
        password_ok = False

    if not user or not password_ok:
        record_attempt(email, ip, success=False)
        remaining = max(0, MAX_FAILED_LOGIN - count_recent_failures(email, ip))
        msg = 'Invalid credentials.'
        if remaining <= 2:
            msg += f' {remaining} attempt(s) remaining before lockout.'
        return redirect(url_for('login_page', error=msg))

    if user['status'] == 'denied':
        return redirect(url_for('login_page',
            error='This account was not approved. Contact an admin.'))

    # ── Success ───────────────────────────────────────────────
    record_attempt(email, ip, success=True)

    # Clear existing session before writing new one.
    # Prevents session fixation: destroys any pre-existing session ID
    # and forces the browser to accept a fresh one.
    # Note: this is client-cookie invalidation only — Flask does not
    # maintain a server-side session store. A stolen cookie remains
    # valid until the 8-hour lifetime expires.
    session.clear()
    session.permanent  = True       # activates 8-hour fixed lifetime
    session['user_id'] = user['id']
    session['email']   = user['email']

    return redirect_for_user(user)


@app.route('/signup', methods=['GET'])
def signup_page():
    if current_user():
        return redirect_for_user(current_user())
    return show_box(read_html('signup.html'), '__ERROR__', request.args.get('error', ''))


@app.route('/signup', methods=['POST'])
def signup():
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    role     = request.form.get('role', 'student').strip().lower()

    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        return redirect(url_for('signup_page', error='Enter a valid email address.'))
    if len(password) < 8:
        return redirect(url_for('signup_page', error='Password must be at least 8 characters.'))
    if role not in SIGNUP_ROLES:
        return redirect(url_for('signup_page', error='Choose Student or Staff.'))

    password_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=12)
    ).decode()
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO users (email, password_hash, role, status) VALUES (?, ?, ?, ?)',
                (email, password_hash, role, 'pending')
            )
    except sqlite3.IntegrityError:
        return redirect(url_for('signup_page', error='That email is already registered.'))

    return redirect(url_for('login_page',
        notice='Request submitted. An admin must approve your account before you can sign in.'))


@app.route('/pending')
@login_required
def pending_page():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for('login_page'))
    if user['status'] == 'approved':
        return redirect_for_user(user)
    if user['status'] == 'denied':
        status_msg = (
            'This account was not approved. Contact an admin if you think '
            'that is a mistake.'
        )
    else:
        status_msg = (
            'Your account is waiting for an admin to approve it. '
            'You cannot use chat or staff tools yet.'
        )
    page = read_html('pending.html')
    return (
        page
        .replace('__STATUS_MSG__', html.escape(status_msg))
        .replace('__EMAIL__', html.escape(user['email']))
        .replace('__ROLE__', html.escape(user['role']))
    )


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Clears session data from the client-side cookie.
    # Does not revoke server-side — no server store exists.
    session.clear()
    return redirect(url_for('login_page'))


def _account_rows(users, pending=False):
    if not users:
        return '<p class="empty">None.</p>'
    rows = [
        '<table class="accounts"><thead><tr>'
        '<th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>'
    ]
    for u in users:
        actions = ''
        if pending:
            actions = (
                '<div class="row-actions">'
                f'<form method="POST" action="/admin/approve">'
                f'<input type="hidden" name="user_id" value="{int(u["id"])}"/>'
                f'<button class="btn-ok" type="submit">Approve</button></form>'
                f'<form method="POST" action="/admin/deny">'
                f'<input type="hidden" name="user_id" value="{int(u["id"])}"/>'
                f'<button class="btn-no" type="submit">Deny</button></form>'
                '</div>'
            )
        rows.append(
            '<tr>'
            f'<td>{html.escape(u["email"])}</td>'
            f'<td>{html.escape(u["role"])}</td>'
            f'<td>{html.escape(u["status"])}</td>'
            f'<td>{actions}</td>'
            '</tr>'
        )
    rows.append('</tbody></table>')
    return ''.join(rows)


@app.route('/admin')
@approved_required('admin')
def admin_page():
    with get_db() as conn:
        pending = conn.execute(
            "SELECT * FROM users WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        everyone = conn.execute(
            'SELECT * FROM users ORDER BY created_at'
        ).fetchall()
    page = read_html('admin.html')
    flash = request.args.get('flash', '')
    return (
        page
        .replace('__FLASH__', html.escape(flash) if flash else '')
        .replace('__PENDING__', _account_rows(pending, pending=True))
        .replace('__ALL__', _account_rows(everyone, pending=False))
    )


def _set_status(user_id, status):
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET status = ? WHERE id = ? AND role != ?',
            (status, user_id, 'admin')
        )


@app.route('/admin/approve', methods=['POST'])
@approved_required('admin')
def admin_approve():
    try:
        user_id = int(request.form.get('user_id', '0'))
    except ValueError:
        user_id = 0
    _set_status(user_id, 'approved')
    return redirect(url_for('admin_page', flash='Account approved.'))


@app.route('/admin/deny', methods=['POST'])
@approved_required('admin')
def admin_deny():
    try:
        user_id = int(request.form.get('user_id', '0'))
    except ValueError:
        user_id = 0
    _set_status(user_id, 'denied')
    return redirect(url_for('admin_page', flash='Account denied.'))


def _safe_knowledge_file(name):
    if name not in KNOWLEDGE_FILES:
        return None
    path = os.path.realpath(os.path.join(KNOWLEDGE_DIR, name))
    root = os.path.realpath(KNOWLEDGE_DIR)
    if not path.startswith(root + os.sep):
        return None
    return path


@app.route('/staff')
@approved_required('staff')
def staff_page():
    filename = request.args.get('file', 'library.md')
    if filename not in KNOWLEDGE_FILES:
        filename = 'library.md'
    path = _safe_knowledge_file(filename)
    content = ''
    if path and os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            content = f.read()

    links = []
    for name in KNOWLEDGE_FILES:
        active = ' active' if name == filename else ''
        links.append(
            f'<a class="{active.strip()}" href="/staff?file={html.escape(name)}">'
            f'{html.escape(name)}</a>'
        )

    with get_db() as conn:
        faqs = conn.execute(
            'SELECT id, question, answer FROM faqs ORDER BY id DESC'
        ).fetchall()
    faq_html = []
    if not faqs:
        faq_html.append('<p class="empty">No FAQs yet.</p>')
    for faq in faqs:
        faq_html.append(
            '<div class="faq-item">'
            f'<form method="POST" action="/staff/faq/update">'
            f'<input type="hidden" name="faq_id" value="{int(faq["id"])}"/>'
            f'<input type="text" name="question" value="{html.escape(faq["question"], quote=True)}" required/>'
            f'<textarea name="answer" rows="3" required>{html.escape(faq["answer"])}</textarea>'
            f'<button class="submit-btn" type="submit">Save FAQ</button></form>'
            f'<form method="POST" action="/staff/faq/delete" style="display:inline;">'
            f'<input type="hidden" name="faq_id" value="{int(faq["id"])}"/>'
            f'<button class="submit-btn danger" type="submit">Delete</button></form>'
            '</div>'
        )

    page = read_html('staff.html')
    flash = request.args.get('flash', '')
    return (
        page
        .replace('__FLASH__', html.escape(flash) if flash else '')
        .replace('__FILE_LINKS__', ''.join(links))
        .replace('__FILENAME__', html.escape(filename))
        .replace('__FILE_CONTENT__', html.escape(content))
        .replace('__FAQS__', ''.join(faq_html))
    )


@app.route('/staff/save-file', methods=['POST'])
@approved_required('staff')
def staff_save_file():
    filename = request.form.get('filename', '')
    path = _safe_knowledge_file(filename)
    if not path:
        return redirect(url_for('staff_page', flash='Invalid file.'))
    content = request.form.get('content', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    refresh_knowledge()
    return redirect(url_for('staff_page', file=filename, flash=f'Saved {filename}.'))


@app.route('/staff/faq/add', methods=['POST'])
@approved_required('staff')
def staff_faq_add():
    question = request.form.get('question', '').strip()
    answer = request.form.get('answer', '').strip()
    if question and answer:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO faqs (question, answer) VALUES (?, ?)',
                (question[:500], answer[:4000])
            )
    return redirect(url_for('staff_page', flash='FAQ added.'))


@app.route('/staff/faq/update', methods=['POST'])
@approved_required('staff')
def staff_faq_update():
    try:
        faq_id = int(request.form.get('faq_id', '0'))
    except ValueError:
        faq_id = 0
    question = request.form.get('question', '').strip()
    answer = request.form.get('answer', '').strip()
    if faq_id and question and answer:
        with get_db() as conn:
            conn.execute(
                'UPDATE faqs SET question = ?, answer = ?, updated_at = strftime("%s","now") WHERE id = ?',
                (question[:500], answer[:4000], faq_id)
            )
    return redirect(url_for('staff_page', flash='FAQ updated.'))


@app.route('/staff/faq/delete', methods=['POST'])
@approved_required('staff')
def staff_faq_delete():
    try:
        faq_id = int(request.form.get('faq_id', '0'))
    except ValueError:
        faq_id = 0
    if faq_id:
        with get_db() as conn:
            conn.execute('DELETE FROM faqs WHERE id = ?', (faq_id,))
    return redirect(url_for('staff_page', flash='FAQ deleted.'))


# ── App routes ────────────────────────────────────────────────
@app.route('/')
@approved_required('student', 'staff', 'admin')
def index():
    user = current_user()
    page = read_html('index.html')
    return page.replace('__ROLE_NAV__', role_nav(user))


@app.route('/csubot.css')
def stylesheet():
    return send_from_directory(ROOT, 'csubot.css')


@app.route('/panel.css')
def panel_stylesheet():
    return send_from_directory(ROOT, 'panel.css')


@app.route('/csubot.js')
def script():
    return send_from_directory(ROOT, 'csubot.js')


@app.route('/chat', methods=['POST'])
@approved_required('student', 'staff', 'admin')
def chat():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if is_rate_limited(ip):
        return jsonify({'error': 'Rate limit exceeded. Please wait before sending more messages.'}), 429

    body = request.get_json(silent=True)
    if not body or 'messages' not in body or not isinstance(body['messages'], list):
        return jsonify({'error': 'Invalid request.'}), 400

    messages = []
    for m in body['messages']:
        role    = m.get('role', 'user')
        content = str(m.get('content', ''))
        # Never accept a client-supplied system prompt.
        if role == 'system':
            continue
        if role not in ALLOWED_ROLES:
            role = 'user'
        messages.append({'role': role, 'content': content[:MAX_MSG_LEN]})

    if not messages:
        return jsonify({'error': 'No valid messages.'}), 400

    user_query = next(
        (m['content'] for m in reversed(messages) if m['role'] == 'user'),
        ''
    )
    messages = [
        {'role': 'system', 'content': build_system_prompt(user_query)}
    ] + messages

    payload = {
        'model': DEFAULT_MODEL,
        'messages': messages,
        'stream': True,
        'think': False,
        'options': {'temperature': 0.2},
    }

    def generate():
        try:
            with requests.post(
                f'{OLLAMA_HOST}/api/chat',
                json=payload, stream=True, timeout=120
            ) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
        except requests.exceptions.ConnectionError:
            yield json.dumps({'error': 'Could not connect to AI engine.'}).encode()
        except requests.exceptions.Timeout:
            yield json.dumps({'error': 'AI engine timed out.'}).encode()
        except Exception as e:
            yield json.dumps({'error': str(e)}).encode()

    return Response(stream_with_context(generate()), content_type='application/x-ndjson')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': DEFAULT_MODEL}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
