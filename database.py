import sqlite3
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
            trial_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            client_id TEXT NOT NULL,
            email TEXT NOT NULL,
            plan_id TEXT DEFAULT '1m',
            expire_at TEXT,
            traffic_limit_gb INTEGER DEFAULT 50,
            created_at TEXT DEFAULT (datetime('now')),
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT DEFAULT 'RUB',
            method TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            provider_payment_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Migration: add columns if they don't exist (safe for existing DBs)
        -- trial_used
        CREATE TEMP TABLE IF NOT EXISTS _dummy_check (x);
    """)
    # Safe migrations for existing databases
    _safe_add_column(cur, "users", "trial_used", "INTEGER DEFAULT 0")
    _safe_add_column(cur, "subscriptions", "plan_id", "TEXT DEFAULT '1m'")
    conn.commit()
    conn.close()


def _safe_add_column(cur, table: str, column: str, definition: str):
    """Add column only if it doesn't already exist."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        pass  # column already exists


# ────────── Users ───────────────────────────────────────────────────────────────────────────

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


def get_user_by_id(telegram_id: int):
    """Alias for get_user for compatibility."""
    return get_user(telegram_id)


def is_trial_used(telegram_id: int) -> bool:
    user = get_user(telegram_id)
    if not user:
        return False
    return bool(user["trial_used"])


def set_trial_used(telegram_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET trial_used=1 WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()


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


# ────────── Subscriptions ─────────────────────────────────────────────────────────────

def add_subscription(telegram_id: int, client_id: str, email: str,
                     expire_at: str, traffic_limit_gb: int = 50,
                     plan_id: str = "1m"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE subscriptions SET is_active=0 WHERE telegram_id=?",
        (telegram_id,)
    )
    cur.execute("""
        INSERT INTO subscriptions (telegram_id, client_id, email, expire_at, traffic_limit_gb, plan_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (telegram_id, client_id, email, expire_at, traffic_limit_gb, plan_id))
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


# ────────── Payments ───────────────────────────────────────────────────────────────────────

def create_payment(telegram_id: int, plan_id: str, amount: int,
                   currency: str, method: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (telegram_id, plan_id, amount, currency, method)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, plan_id, amount, currency, method))
    payment_id = cur.lastrowid
    conn.commit()
    conn.close()
    return payment_id


def confirm_payment(payment_id: int, provider_payment_id: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE payments
        SET status='paid', provider_payment_id=?, updated_at=datetime('now')
        WHERE id=?
    """, (provider_payment_id, payment_id))
    conn.commit()
    conn.close()


def update_payment_status(payment_id: int, status: str, provider_payment_id: str = None):
    """Update payment status (pending, paid, failed, etc.)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE payments
        SET status=?, provider_payment_id=?, updated_at=datetime('now')
        WHERE id=?
    """, (status, provider_payment_id, payment_id))
    conn.commit()
    conn.close()


def get_payment(payment_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
    row = cur.fetchone()
    conn.close()
    return row


def count_total_revenue():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid' AND currency='RUB'")
    result = cur.fetchone()[0]
    conn.close()
    return result


def count_paid_today():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM payments
        WHERE status='paid' AND date(updated_at) = date('now')
    """)
    result = cur.fetchone()[0]
    conn.close()
    return result


def get_expired_subscriptions():
    """Get all active subscriptions that have expired."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM subscriptions
        WHERE is_active=1 AND datetime(expire_at) < datetime('now')
    """)
    rows = cur.fetchall()
    conn.close()
    return rows
