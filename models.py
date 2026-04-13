import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_app.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
    # 既存テーブルにpassword_hashカラムがなければ追加
    try:
        c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL")
    except:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS otp_codes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL, code TEXT NOT NULL,
                  expires_at INTEGER NOT NULL, used BOOLEAN DEFAULT 0)''')
    # ジャンル設定テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS user_genres
                 (email TEXT PRIMARY KEY,
                  genre1 TEXT DEFAULT \'\',
                  genre2 TEXT DEFAULT \'\')'''
    )
    conn.commit()
    conn.close()
