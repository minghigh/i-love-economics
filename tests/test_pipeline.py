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
from economics_daily.models import SourceArticle
from economics_daily.pipeline import render_wechat_html, safe_filename, screen_articles, select_topics, validate_topic


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, temperature: float = 0.2) -> str:
        self.calls += 1
        return '{"topics":[{"title":"选题","pass":true,"score":8,"economic_question":"问题","core_concept":"概念","reason":"理由","source_ids":["a"]}]}'


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

    def test_screening_batches_articles(self) -> None:
        old = os.environ.get("SCREEN_BATCH_SIZE")
        os.environ["SCREEN_BATCH_SIZE"] = "2"
        try:
            client = FakeClient()
            articles = [
                SourceArticle(str(i), "标题", "来源", "link", datetime.now(ZoneInfo("Asia/Shanghai")), "", "正文" * 50)
                for i in range(5)
            ]
            topics = screen_articles(articles, client)  # type: ignore[arg-type]
        finally:
            if old is None:
                os.environ.pop("SCREEN_BATCH_SIZE", None)
            else:
                os.environ["SCREEN_BATCH_SIZE"] = old
        self.assertEqual(client.calls, 3)
        self.assertEqual(len(topics), 3)

    def test_select_topics_skips_near_duplicate_events(self) -> None:
        topics = [
            validate_topic(
                {
                    "title": "日本为何开始从废旧空调中提取稀土？",
                    "pass": True,
                    "score": 9,
                    "economic_question": "日本为何开始回收空调稀土？",
                    "core_concept": "资源稀缺性",
                    "reason": "理由",
                    "source_ids": ["a"],
                }
            ),
            validate_topic(
                {
                    "title": "日本从废旧空调中提取稀土：资源短缺下的激励与行为分析",
                    "pass": True,
                    "score": 9,
                    "economic_question": "日本为何开始回收空调稀土？",
                    "core_concept": "资源稀缺性",
                    "reason": "理由",
                    "source_ids": ["b"],
                }
            ),
            validate_topic(
                {
                    "title": "世界杯来了，电视却卖不动了",
                    "pass": True,
                    "score": 9,
                    "economic_question": "智能电视为什么伤害消费者体验？",
                    "core_concept": "消费者剩余",
                    "reason": "理由",
                    "source_ids": ["c"],
                }
            ),
        ]
        selected, rejected = select_topics(topics, 3)
        self.assertEqual([topic.title for topic in selected], [topics[0].title, topics[2].title])
        self.assertEqual([topic.title for topic in rejected], [topics[1].title])


if __name__ == "__main__":
    unittest.main()
