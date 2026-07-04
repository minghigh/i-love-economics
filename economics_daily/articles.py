from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, datetime, time, timezone

from bs4 import BeautifulSoup

from .io import BEIJING
from .models import SourceArticle

MIN_CONTENT_LENGTH = 80


def _text(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)


def _guid(link: str, fallback: str) -> str:
    match = re.search(r"/s/([^/?]+)", link or "")
    return match.group(1) if match else fallback


def load_articles(target_date: date, db_path: str | None = None) -> list[SourceArticle]:
    db = db_path or os.environ.get("WE_MP_RSS_DB_PATH", "/we-mp-rss-data/db.db")
    start = datetime.combine(target_date, time.min, BEIJING).timestamp()
    end = datetime.combine(target_date, time.max, BEIJING).timestamp()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              a.id,
              a.mp_id,
              COALESCE(f.mp_name, a.mp_id) AS source,
              a.title,
              a.url,
              a.publish_time,
              COALESCE(NULLIF(a.content_html, ''), a.content, '') AS content_html
            FROM articles a
            LEFT JOIN feeds f ON f.id = a.mp_id
            WHERE a.publish_time BETWEEN ? AND ?
              AND COALESCE(NULLIF(a.content_html, ''), a.content, '') != ''
            ORDER BY a.publish_time DESC
            """,
            (int(start), int(end)),
        ).fetchall()
    finally:
        conn.close()

    articles: list[SourceArticle] = []
    for row in rows:
        html = row["content_html"] or ""
        text = _text(html)
        title = row["title"] or ""
        if not title or len(text) < MIN_CONTENT_LENGTH:
            continue
        link = row["url"] or row["id"]
        articles.append(
            SourceArticle(
                id=_guid(link, row["id"]),
                title=title,
                source=row["source"] or row["mp_id"],
                link=link,
                published_at=datetime.fromtimestamp(row["publish_time"], timezone.utc).astimezone(BEIJING),
                content_html=html,
                content_text=text,
            )
        )
    return articles
