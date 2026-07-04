from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from economics_daily.articles import load_articles
from economics_daily.io import parse_target_date
from economics_daily.pipeline import render_wechat_html, safe_filename, validate_topic


class PipelineTest(unittest.TestCase):
    def test_loads_yesterday_articles_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "db.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE feeds (id TEXT PRIMARY KEY, mp_name TEXT);
                CREATE TABLE articles (
                  id TEXT PRIMARY KEY,
                  mp_id TEXT,
                  title TEXT,
                  url TEXT,
                  publish_time INTEGER,
                  content TEXT,
                  content_html TEXT
                );
                INSERT INTO feeds VALUES ('mp1', '测试公众号');
                """
            )
            published = int(datetime(2026, 7, 4, 12, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())
            conn.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "a1",
                    "mp1",
                    "价格战为什么停不下来",
                    "https://mp.weixin.qq.com/s/abc",
                    published,
                    "",
                    "<p>这是一篇关于价格战和商家补贴的长文章，包含足够多的正文用于测试筛选逻辑。</p>" * 4,
                ),
            )
            conn.commit()
            conn.close()

            articles = load_articles(parse_target_date("2026-07-04"), str(db))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].id, "abc")
        self.assertEqual(articles[0].source, "测试公众号")

    def test_validate_topic_and_html_rendering(self) -> None:
        topic = validate_topic(
            {
                "title": "为什么价格战停不下来？",
                "pass": True,
                "score": 11,
                "economic_question": "企业为何继续降价？",
                "core_concept": "囚徒困境",
                "reason": "有明确激励结构",
                "source_ids": ["abc"],
            }
        )
        self.assertEqual(topic.score, 10)
        self.assertIn("<h2", render_wechat_html("# 标题\n\n正文"))
        self.assertEqual(safe_filename('囚徒/困境'), "囚徒-困境")


if __name__ == "__main__":
    unittest.main()
