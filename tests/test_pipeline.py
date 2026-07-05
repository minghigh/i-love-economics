from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from economics_daily.articles import load_articles
from economics_daily.io import parse_target_date
from economics_daily.models import SourceArticle
from economics_daily.pipeline import render_home, render_wechat_html, safe_filename, screen_articles, select_topics, validate_topic, write_cover
from economics_daily.wechat import _json_payload, add_day_drafts, build_draft_article


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
        rendered = render_wechat_html("# 标题\n\n**正文**\n\n---")
        self.assertIn('<meta charset="utf-8">', rendered)
        self.assertIn("<h2", rendered)
        self.assertIn('<strong style="color:#8a1c1c;background:#fff3d8;padding:0 .12em;">正文</strong>', rendered)
        self.assertIn("border-top:1px solid #e5e7eb", rendered)
        self.assertNotIn("<p style=\"margin:0 0 1em;\">---</p>", rendered)
        self.assertIn("本文由 AI 辅助生成", rendered)
        self.assertIn("font-size:12px", rendered)
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

    def test_select_topics_rejects_weak_topics_instead_of_filling_quota(self) -> None:
        topics = [
            validate_topic(
                {
                    "title": "有细节的强选题",
                    "pass": True,
                    "score": 8,
                    "economic_question": "为什么值得写？",
                    "core_concept": "激励",
                    "reason": "有机制",
                    "source_ids": ["a"],
                }
            ),
            validate_topic(
                {
                    "title": "只有常识短评的弱选题",
                    "pass": True,
                    "score": 7,
                    "economic_question": "为什么不够？",
                    "core_concept": "成本",
                    "reason": "事实细节不足",
                    "source_ids": ["b"],
                }
            ),
        ]
        selected, rejected = select_topics(topics, 3)
        self.assertEqual([topic.title for topic in selected], ["有细节的强选题"])
        self.assertEqual([topic.title for topic in rejected], ["只有常识短评的弱选题"])

    def test_render_home_lists_daily_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            run = root / "runs" / "2026-07-04"
            candidate = run / "candidates" / "01"
            candidate.mkdir(parents=True)
            (run / "articles.json").write_text('[{"title":"原文"}]', encoding="utf-8")
            (run / "topics.json").write_text('[{"title":"候选标题"}]', encoding="utf-8")
            (candidate / "fact_check.json").write_text('{"status":"passed"}', encoding="utf-8")

            render_home(root)

            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("2026-07-04", page)
            self.assertIn("候选标题", page)
            self.assertIn('href="runs/2026-07-04/index.html"', page)

    def test_cover_generation_handles_long_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cover.png"
            write_cover(path, "World Cup arrived but television sales still collapsed", column="Daily", footer="Concept")
            self.assertGreater(path.stat().st_size, 1000)

    def test_builds_wechat_draft_payload_from_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cdir = Path(tmp)
            (cdir / "topic.json").write_text(
                '{"title":"这是一个非常非常非常非常长的标题","economic_question":"这是一个非常非常非常非常长的摘要","reason":"理由"}',
                encoding="utf-8",
            )
            (cdir / "sources.json").write_text('[{"link":"https://example.com"}]', encoding="utf-8")
            (cdir / "article.html").write_text('<meta charset="utf-8">\n<section>正文</section>', encoding="utf-8")
            (cdir / "cover.png").write_bytes(b"cover")

            article = build_draft_article(cdir, "thumb")

        self.assertEqual(article["title"], "这是一个非常非常非常非常长的标题")
        self.assertEqual(article["thumb_media_id"], "thumb")
        self.assertLessEqual(len(article["digest"].encode("utf-8")), 54)
        self.assertEqual(article["content"], "<section>正文</section>")

    def test_wechat_json_payload_keeps_chinese_readable(self) -> None:
        payload = _json_payload({"title": "日本为何开始从废旧空调中提取稀土？"})
        self.assertIn("日本为何".encode("utf-8"), payload)
        self.assertNotIn(b"\\u65e5", payload)

    def test_draft_day_skips_existing_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp)
            existing = day / "candidates" / "01"
            fresh = day / "candidates" / "02"
            existing.mkdir(parents=True)
            fresh.mkdir(parents=True)
            (existing / "wechat-draft.json").write_text("{}", encoding="utf-8")
            with patch("economics_daily.wechat.add_draft", return_value=fresh / "wechat-draft.json") as add_draft:
                paths = add_day_drafts(day)

        self.assertEqual(paths, [existing / "wechat-draft.json", fresh / "wechat-draft.json"])
        add_draft.assert_called_once_with(fresh)


if __name__ == "__main__":
    unittest.main()
