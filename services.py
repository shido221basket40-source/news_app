import feedparser
import sqlite3
import time
import random
import os
from models import DB_PATH

RSS_FEEDS = [
    "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtcGhHZ0pRVWlnQVAB?hl=ja&gl=JP&ceid=JP:ja",  # テクノロジー
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtcGhHZ0pRVWlnQVAB?hl=ja&gl=JP&ceid=JP:ja",  # スポーツ
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtcGhHZ0pRVWlnQVAB?hl=ja&gl=JP&ceid=JP:ja",  # エンタメ
]

class NewsManager:
    @staticmethod
    def fetch_and_store():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # 古い記事を削除（7日以上前）
        c.execute("DELETE FROM articles WHERE fetched_at < datetime('now', '-7 days')")
        
        inserted = 0
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    raw_title = entry.title
                    if " - " in raw_title:
                        title, source = raw_title.rsplit(" - ", 1)
                    else:
                        title, source = raw_title, "不明"
                    # 公開日時を取得
                    pub_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed)
                    try:
                        if pub_date:
                            c.execute("INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?, ?, ?, ?)",
                                      (title, source, entry.link, pub_date))
                        else:
                            c.execute("INSERT OR IGNORE INTO articles (title, source, link) VALUES (?, ?, ?)",
                                      (title, source, entry.link))
                        inserted += c.rowcount
                    except sqlite3.IntegrityError:
                        pass
            except Exception as e:
                pass

        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_fetch', ?)", (int(time.time()),))
        conn.commit()
        conn.close()
