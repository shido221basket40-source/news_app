import feedparser
import sqlite3
import time
import os
import urllib.request
import json
from models import DB_PATH

GNEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

class NewsManager:
    @staticmethod
    def fetch_and_store():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # 30日以上前の記事を削除
        c.execute("DELETE FROM articles WHERE fetched_at < datetime('now', '-30 days')")

        if GNEWS_API_KEY:
            NewsManager._fetch_from_gnews(c)

        # フォールバック：Google News RSS
        NewsManager._fetch_from_rss(c)

        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_fetch', ?)", (int(time.time()),))
        conn.commit()
        conn.close()

    @staticmethod
    def _fetch_from_gnews(c):
        try:
            # 日本のトップヘッドライン（最大10件）
            url = (
                "https://gnews.io/api/v4/top-headlines"
                "?country=jp&lang=ja&max=10"
                f"&apikey={GNEWS_API_KEY}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "NewsApp/1.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())

            for article in data.get("articles", []):
                title = (article.get("title") or "").strip()
                source = (article.get("source") or {}).get("name", "不明")
                link = article.get("url", "")
                pub = article.get("publishedAt", "")
                if pub:
                    # "2024-04-13T10:00:00Z" → "2024-04-13 10:00:00"
                    pub_date = pub.replace("T", " ").replace("Z", "")
                else:
                    pub_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

                if not title or not link:
                    continue
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?, ?, ?, ?)",
                        (title, source, link, pub_date)
                    )
                except Exception:
                    pass
        except Exception as e:
            pass

    @staticmethod
    def _fetch_from_rss(c):
        feeds = [
            "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja",
        ]
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    raw_title = entry.title
                    if " - " in raw_title:
                        title, source = raw_title.rsplit(" - ", 1)
                    else:
                        title, source = raw_title, "不明"
                    link = entry.link
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed)
                    else:
                        pub_date = now_str
                    try:
                        c.execute(
                            "INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?, ?, ?, ?)",
                            (title.strip(), source.strip(), link, pub_date)
                        )
                    except Exception:
                        pass
            except Exception:
                pass
