import feedparser
import sqlite3
import time
import random
import os
from models import DB_PATH

class NewsManager:
    @staticmethod
    def fetch_and_store():
        feed = feedparser.parse("https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 既存の未読記事をクリア
        c.execute("DELETE FROM articles")
        
        # ランダムに3件選定
        samples = random.sample(feed.entries, min(len(feed.entries), 10))
        for entry in samples[:3]:
            raw_title = entry.title
            if " - " in raw_title:
                title, source = raw_title.rsplit(" - ", 1)
            else:
                title, source = raw_title, "不明"
            
            try:
                c.execute("INSERT INTO articles (title, source, link) VALUES (?, ?, ?)",
                          (title, source, entry.link))
            except sqlite3.IntegrityError:
                pass
        
        # ここから下のインデントがズレていた可能性があります
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_fetch', ?)", (int(time.time()),))
        conn.commit()
        conn.close()