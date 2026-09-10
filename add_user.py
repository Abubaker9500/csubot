"""
CSUBot - Admin User Provisioning Script
Email is the only identity. No username field.

Usage:
  python3 add_user.py add <email> <password> [student|staff|admin]
  python3 add_user.py list
  python3 add_user.py delete <email>
  python3 add_user.py promote <email> <student|staff|admin>
"""

import sys
import sqlite3
import bcrypt
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), 'csubot.db')
ACCOUNT_ROLES = ('student', 'staff', 'admin')


def _ensure_column(conn, table, name, spec):
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
    if name not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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


def valid_email(email):
    return re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) is not None


def add_user(email, password, role='student'):
    if not valid_email(email):
        print(f"Error: '{email}' is not a valid email address.")
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    role = role.lower()
    if role not in ACCOUNT_ROLES:
        print(f"Error: role must be one of {', '.join(ACCOUNT_ROLES)}.")
        sys.exit(1)

    password_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=12)
    ).decode()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                'INSERT INTO users (email, password_hash, role, status) VALUES (?, ?, ?, ?)',
                (email.strip().lower(), password_hash, role, 'approved')
            )
        print(f"✅ User '{email}' added as approved {role}.")
    except sqlite3.IntegrityError:
        print(f"Error: Email '{email}' already exists.")
        sys.exit(1)


def list_users():
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute(
            'SELECT id, email, role, status, created_at FROM users ORDER BY created_at'
        ).fetchall()
    if not users:
        print("No users found.")
        return
    print(f"\n{'ID':<5} {'Email':<35} {'Role':<10} {'Status':<12} {'Created'}")
    print("-" * 80)
    for u in users:
        print(f"{u[0]:<5} {u[1]:<35} {u[2]:<10} {u[3]:<12} {u[4]}")


def delete_user(email):
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute(
            'DELETE FROM users WHERE LOWER(email) = ?',
            (email.strip().lower(),)
        )
    if result.rowcount:
        print(f"✅ User '{email}' deleted.")
    else:
        print(f"Error: User '{email}' not found.")


def promote_user(email, role):
    role = role.lower()
    if role not in ACCOUNT_ROLES:
        print(f"Error: role must be one of {', '.join(ACCOUNT_ROLES)}.")
        sys.exit(1)
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute(
            'UPDATE users SET role = ?, status = ? WHERE LOWER(email) = ?',
            (role, 'approved', email.strip().lower())
        )
    if result.rowcount:
        print(f"✅ User '{email}' is now an approved {role}.")
    else:
        print(f"Error: User '{email}' not found.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    init_db()

    if command == 'add':
        if len(sys.argv) not in (4, 5):
            print("Usage: python3 add_user.py add <email> <password> [student|staff|admin]")
            sys.exit(1)
        role = sys.argv[4] if len(sys.argv) == 5 else 'student'
        add_user(sys.argv[2], sys.argv[3], role)

    elif command == 'list':
        list_users()

    elif command == 'delete':
        if len(sys.argv) != 3:
            print("Usage: python3 add_user.py delete <email>")
            sys.exit(1)
        delete_user(sys.argv[2])

    elif command == 'promote':
        if len(sys.argv) != 4:
            print("Usage: python3 add_user.py promote <email> <student|staff|admin>")
            sys.exit(1)
        promote_user(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
