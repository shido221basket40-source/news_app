import feedparser
import time
import os
import urllib.request
import json
import logging

from models import get_conn, is_postgres, pq

logger = logging.getLogger(__name__)

GNEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


class NewsManager:

    @staticmethod
    def fetch_and_store():
        conn = get_conn()
        c = conn.cursor()

        # 30日以上前の記事を削除
        if is_postgres():
            c.execute("DELETE FROM articles WHERE fetched_at < NOW() - INTERVAL '30 days'")
        else:
            c.execute("DELETE FROM articles WHERE fetched_at < datetime('now', '-30 days')")

        if GNEWS_API_KEY:
            NewsManager._fetch_from_gnews(c)
        NewsManager._fetch_from_rss(c)

        # 最終取得時刻を更新
        if is_postgres():
            c.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                ('last_fetch', str(int(time.time())))
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ('last_fetch', str(int(time.time())))
            )

        conn.commit()
        conn.close()

    @staticmethod
    def _fetch_from_gnews(c):
        url = (
            f"https://gnews.io/api/v4/top-headlines"
            f"?country=jp&lang=ja&max=10&token={GNEWS_API_KEY}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NewsApp/1.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode())
            NewsManager._insert_articles(c, data.get("articles", []))
        except Exception as e:
            logger.warning("GNews取得失敗: %s", e)

    @staticmethod
    def _insert_articles(c, articles):
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
                    c.execute(
                        "INSERT INTO articles (title, source, link, fetched_at) VALUES (%s, %s, %s, %s) ON CONFLICT (link) DO NOTHING",
                        (title, source, link, pub_date)
                    )
                else:
                    c.execute(
                        "INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?, ?, ?, ?)",
                        (title, source, link, pub_date)
                    )
            except Exception as e:
                logger.warning("記事INSERT失敗 (link=%s): %s", link, e)

    @staticmethod
    def _fetch_from_rss(c):
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            feed = feedparser.parse("https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja")
            for entry in feed.entries:
                raw_title = entry.title
                if " - " in raw_title:
                    title, source = raw_title.rsplit(" - ", 1)
                else:
                    title, source = raw_title, "不明"

                link = entry.link
                pub_date = (
                    time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed)
                    if hasattr(entry, 'published_parsed') and entry.published_parsed
                    else now_str
                )

                try:
                    if is_postgres():
                        c.execute(
                            "INSERT INTO articles (title, source, link, fetched_at) VALUES (%s, %s, %s, %s) ON CONFLICT (link) DO NOTHING",
                            (title.strip(), source.strip(), link, pub_date)
                        )
                    else:
                        c.execute(
                            "INSERT OR IGNORE INTO articles (title, source, link, fetched_at) VALUES (?, ?, ?, ?)",
                            (title.strip(), source.strip(), link, pub_date)
                        )
                except Exception as e:
                    logger.warning("RSS記事INSERT失敗 (link=%s): %s", link, e)

        except Exception as e:
            logger.warning("RSSフィード取得失敗: %s", e)
