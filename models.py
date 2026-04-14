import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "")

def get_conn():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        import sqlite3
        return sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_app.db'))

def is_postgres():
    return bool(DATABASE_URL)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    if is_postgres():
        c.execute('''CREATE TABLE IF NOT EXISTS articles
                     (id SERIAL PRIMARY KEY,
                      title TEXT, source TEXT, link TEXT UNIQUE,
                      is_read BOOLEAN DEFAULT FALSE, is_saved BOOLEAN DEFAULT FALSE,
                      summary TEXT, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id SERIAL PRIMARY KEY,
                      email TEXT UNIQUE NOT NULL,
                      password_hash TEXT DEFAULT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS otp_codes
                     (id SERIAL PRIMARY KEY,
                      email TEXT NOT NULL, code TEXT NOT NULL,
                      expires_at BIGINT NOT NULL, used BOOLEAN DEFAULT FALSE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_genres
                     (email TEXT PRIMARY KEY,
                      genre1 TEXT DEFAULT '',
                      genre2 TEXT DEFAULT '')''')
    else:
        import sqlite3
        c.execute('''CREATE TABLE IF NOT EXISTS articles
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      title TEXT, source TEXT, link TEXT UNIQUE,
                      is_read BOOLEAN DEFAULT 0, is_saved BOOLEAN DEFAULT 0,
                      summary TEXT, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      email TEXT UNIQUE NOT NULL,
                      password_hash TEXT DEFAULT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        try:
            c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL")
        except:
            pass
        c.execute('''CREATE TABLE IF NOT EXISTS otp_codes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      email TEXT NOT NULL, code TEXT NOT NULL,
                      expires_at INTEGER NOT NULL, used BOOLEAN DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_genres
                     (email TEXT PRIMARY KEY,
                      genre1 TEXT DEFAULT '',
                      genre2 TEXT DEFAULT '')''')
    conn.commit()
    conn.close()

# SQLiteとPostgres両方で使えるプレースホルダー変換
def ph(n=1):
    """PostgreSQLは%s、SQLiteは?"""
    if is_postgres():
        return '%s'
    return '?'
