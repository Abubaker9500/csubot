"""
CSUBot - Flask Backend with V1 Auth
- SQLite user store, no flat files
- bcrypt cost 12
- Email-only identity, no username
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

import json
import os
import sqlite3
import tempfile
import hashlib
import time
import requests
import bcrypt
from flask import (Flask, request, Response, stream_with_context,
                   session, redirect, url_for, jsonify, render_template_string)
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

# ── Configuration ─────────────────────────────────────────────
OLLAMA_HOST      = 'http://127.0.0.1:11434'
DEFAULT_MODEL    = 'qwen3:8b'
RATE_LIMIT       = 20           # max chat requests per IP per hour
RATE_WINDOW      = 3600         # seconds
ALLOWED_ROLES    = {'user', 'assistant', 'system'}
MAX_MSG_LEN      = 4000
DB_PATH          = os.path.join(os.path.dirname(__file__), 'csubot.db')
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
    SESSION_COOKIE_SECURE   = True,    # HTTPS only
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
        """)

init_db()

# ── Helpers ───────────────────────────────────────────────────
def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM users WHERE LOWER(email) = ?',
            (email.lower(),)
        ).fetchone()

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
    if 'user_id' in session:
        return redirect(url_for('index'))
    error = request.args.get('error', '')
    with open(os.path.join(os.path.dirname(__file__), 'login.html')) as f:
        html = f.read()
    if error:
        html = html.replace(
            'style="display:none;">__ERROR__',
            f'style="display:block;">{error}'
        )
    return html


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

    return redirect(url_for('index'))


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Clears session data from the client-side cookie.
    # Does not revoke server-side — no server store exists.
    session.clear()
    return redirect(url_for('login_page'))


# ── App routes ────────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    with open(os.path.join(os.path.dirname(__file__), 'index.html')) as f:
        return f.read()


@app.route('/chat', methods=['POST'])
@login_required
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
        if role not in ALLOWED_ROLES:
            role = 'user'
        messages.append({'role': role, 'content': content[:MAX_MSG_LEN]})

    if not messages:
        return jsonify({'error': 'No valid messages.'}), 400

    payload = {'model': DEFAULT_MODEL, 'messages': messages, 'stream': True}

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
    app.run(host='0.0.0.0', port=5000, debug=False)
