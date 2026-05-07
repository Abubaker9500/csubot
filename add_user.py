"""
CSUBot - Admin User Provisioning Script
Email is the only identity. No username field.

Usage:
  python3 add_user.py add <email> <password>
  python3 add_user.py list
  python3 add_user.py delete <email>
"""

import sys
import sqlite3
import bcrypt
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), 'csubot.db')

def valid_email(email):
    return re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) is not None

def add_user(email, password):
    if not valid_email(email):
        print(f"Error: '{email}' is not a valid email address.")
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    password_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=12)
    ).decode()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                'INSERT INTO users (email, password_hash) VALUES (?, ?)',
                (email.strip().lower(), password_hash)
            )
        print(f"✅ User '{email}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: Email '{email}' already exists.")
        sys.exit(1)

def list_users():
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute(
            'SELECT id, email, created_at FROM users ORDER BY created_at'
        ).fetchall()
    if not users:
        print("No users found.")
        return
    print(f"\n{'ID':<5} {'Email':<35} {'Created (unix)'}")
    print("-" * 55)
    for u in users:
        print(f"{u[0]:<5} {u[1]:<35} {u[2]}")

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

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'add':
        if len(sys.argv) != 4:
            print("Usage: python3 add_user.py add <email> <password>")
            sys.exit(1)
        add_user(sys.argv[2], sys.argv[3])

    elif command == 'list':
        list_users()

    elif command == 'delete':
        if len(sys.argv) != 3:
            print("Usage: python3 add_user.py delete <email>")
            sys.exit(1)
        delete_user(sys.argv[2])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
