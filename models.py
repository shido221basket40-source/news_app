import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_app.db')
        return sqlite3.connect(db_path)


def is_postgres():
    return bool(DATABASE_URL)


def pq(sql):
    """SQLiteの ? をPostgreSQLの %s に変換する"""
    if is_postgres():
        return sql.replace('?', '%s')
    return sql


def _upsert(key, on_conflict):
    """INSERT OR REPLACE (SQLite) / INSERT ... ON CONFLICT DO UPDATE (PostgreSQL)"""
    if is_postgres():
        return f"INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
    return "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)"


def init_db():
    conn = get_conn()
    c = conn.cursor()
    if is_postgres():
        c.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                title TEXT, source TEXT, link TEXT UNIQUE,
                is_read BOOLEAN DEFAULT FALSE,
                is_saved BOOLEAN DEFAULT FALSE,
                summary TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at BIGINT NOT NULL,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_genres (
                email TEXT PRIMARY KEY,
                genre1 TEXT DEFAULT '',
                genre2 TEXT DEFAULT ''
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, source TEXT, link TEXT UNIQUE,
                is_read INTEGER DEFAULT 0,
                is_saved INTEGER DEFAULT 0,
                summary TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 既存DBへのカラム追加（初回のみ成功、以後は無視）
        try:
            c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL")
        except Exception:
            pass
        c.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                used INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_genres (
                email TEXT PRIMARY KEY,
                genre1 TEXT DEFAULT '',
                genre2 TEXT DEFAULT ''
            )
        """)
    conn.commit()
    conn.close()
