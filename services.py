import feedparser
import time
import os
import urllib.request
import json
from models import get_conn, is_postgres, ph

GNEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

class NewsManager:
    @staticmethod
    def fetch_and_store():
        conn = get_conn()
        c = conn.cursor()
        if is_postgres():
            c.execute("DELETE FROM articles WHERE fetched_at < NOW() - INTERVAL '30 days'")
        else:
            c.execute("DELETE FROM articles WHERE fetched_at < datetime('now', '-30 days')")

        if GNEWS_API_KEY:
            NewsManager._fetch_from_gnews(c)
        NewsManager._fetch_from_rss(c)

        p = ph()
        c.execute(f"INSERT INTO settings (key, value) VALUES ({p}, {p}) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value" if is_postgres()
                  else f"INSERT OR REPLACE INTO settings (key, value) VALUES ({p}, {p})",
                  ('last_fetch', str(int(time.time()))))
        conn.commit()
        conn.close()

    @staticmethod
    def fetch_by_date(c, days=7):
        if not GNEWS_API_KEY:
            return
        import datetime
        from_date = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        try:
            url = (f"https://gnews.io/api/v4/top-headlines"
                   f"?country=jp&lang=ja&max=10&from={from_date}&token={GNEWS_API_KEY}")
            req = urllib.request.Request(url, headers={"User-Agent": "NewsApp/1.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())
            NewsManager._insert_articles(c, data.get("articles", []))
        except Exception:
            pass

    @staticmethod
    def _fetch_from_gnews(c):
        try:
            url = (f"https://gnews.io/api/v4/top-headlines"
                   f"?country=jp&lang=ja&max=10&token={GNEWS_API_KEY}")
            req = urllib.request.Request(url, headers={"User-Agent": "NewsApp/1.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())
            NewsManager._insert_articles(c, data.get("articles", []))
        except Exception:
            pass

    @staticmethod
    def _insert_articles(c, articles):
        p = ph()
        for article in articles:
            title = (article.get("title") or "").strip()
            source = (article.get("source") or {}).get("name", "不明")
            link = article.get("url", "")
            pub = article.get("publishedAt", "")
            pub_date = pub.replace("T", " ").replace("Z", "") if pub else time.strftime('%Y-%m-%d %H:%M:%S')
            if not title or not link:
                continue
            try:
                if is_postgres():
                    c.execute("INSERT INTO articles (title, source, link, fetched_at) VALUES (%s,%s,%s,%s) ON CONFLICT (link) DO NOTHING",
                              (title, source, link, pub_date))
                else:
                    c.execute("INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?,?,?,?)",
                              (title, source, link, pub_date))
            except Exception:
                pass

    @staticmethod
    def _fetch_from_rss(c):
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            feed = feedparser.parse("https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja")
            for entry in feed.entries:
                raw_title = entry.title
                title, source = raw_title.rsplit(" - ", 1) if " - " in raw_title else (raw_title, "不明")
                link = entry.link
                pub_date = time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed) if hasattr(entry, 'published_parsed') and entry.published_parsed else now_str
                try:
                    if is_postgres():
                        c.execute("INSERT INTO articles (title, source, link, fetched_at) VALUES (%s,%s,%s,%s) ON CONFLICT (link) DO NOTHING",
                                  (title.strip(), source.strip(), link, pub_date))
                    else:
                        c.execute("INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?,?,?,?)",
                                  (title.strip(), source.strip(), link, pub_date))
                except Exception:
                    pass
        except Exception:
            pass
