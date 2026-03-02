import sqlite3
from datetime import datetime
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            email TEXT NOT NULL,
            expire_at TEXT,
            traffic_limit_gb INTEGER DEFAULT 50,
            created_at TEXT DEFAULT (datetime('now')),
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );
    """)
    conn.commit()
    conn.close()


# ---------- Users ----------

def upsert_user(telegram_id: int, username: str = None, first_name: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (telegram_id, username, first_name))
    conn.commit()
    conn.close()


def get_user(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return row


def count_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    result = cur.fetchone()[0]
    conn.close()
    return result


def count_new_users_today():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')")
    result = cur.fetchone()[0]
    conn.close()
    return result


# ---------- Subscriptions ----------

def add_subscription(telegram_id: int, client_id: str, email: str,
                     expire_at: str, traffic_limit_gb: int = 50):
    conn = get_connection()
    cur = conn.cursor()
    # Deactivate old subscriptions
    cur.execute(
        "UPDATE subscriptions SET is_active=0 WHERE telegram_id=?",
        (telegram_id,)
    )
    cur.execute("""
        INSERT INTO subscriptions (telegram_id, client_id, email, expire_at, traffic_limit_gb)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, client_id, email, expire_at, traffic_limit_gb))
    conn.commit()
    conn.close()


def get_active_subscription(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM subscriptions
        WHERE telegram_id=? AND is_active=1
        ORDER BY created_at DESC LIMIT 1
    """, (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return row


def count_active_subscriptions():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active=1")
    result = cur.fetchone()[0]
    conn.close()
    return result


def deactivate_subscription(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE subscriptions SET is_active=0 WHERE telegram_id=?",
        (telegram_id,)
    )
    conn.commit()
    conn.close()
