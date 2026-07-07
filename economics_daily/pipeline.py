from __future__ import annotations

import html
import os
import re
import shutil
from difflib import SequenceMatcher
from datetime import date
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .articles import load_articles
from .io import read_json, read_text, run_dir, write_json, write_text
from .llm import ChatClient, deepseek_client, local_client, parse_json_response, prompt
from .models import SourceArticle, Topic
from .search import search_queries

AI_DISCLOSURE = "本文由 AI 辅助生成，用于经济学学习与讨论；事实表述经检索核实，经济学分析供参考。"


def article_payload(articles: Iterable[SourceArticle], max_chars: int = 1200) -> list[dict]:
    return [
        {
            "id": a.id,
            "title": a.title,
            "source": a.source,
            "link": a.link,
            "published_at": a.published_at.isoformat(),
            "excerpt": a.content_text[:max_chars],
        }
        for a in articles
    ]


def validate_topic(raw: dict) -> Topic:
    required = ["title", "pass", "score", "economic_question", "core_concept", "reason", "source_ids"]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"topic missing fields: {', '.join(missing)}")
    reader_score = raw.get("reader_score")
    return Topic(
        title=str(raw["title"]),
        pass_=bool(raw["pass"]),
        score=max(1, min(10, int(raw["score"]))),
        economic_question=str(raw["economic_question"]),
        core_concept=str(raw["core_concept"]),
        reason=str(raw["reason"]),
        source_ids=[str(item) for item in raw["source_ids"]],
        related_concepts=[str(item) for item in raw.get("related_concepts", [])],
        reader_score=max(1, min(10, int(reader_score))) if reader_score is not None else None,
        reader_note=str(raw.get("reader_note") or ""),
    )


def screen_articles(articles: list[SourceArticle], client: ChatClient) -> list[Topic]:
    if not articles:
        return []
    batch_size = int(os.environ.get("SCREEN_BATCH_SIZE", "20"))
    topics: list[Topic] = []
    for start in range(0, len(articles), batch_size):
        topics.extend(_screen_batch(articles[start : start + batch_size], client))
    return topics


def _screen_batch(articles: list[SourceArticle], client: ChatClient) -> list[Topic]:
    body = prompt("01_screen_articles.md", articles_json=article_payload(articles))
    last_error: Exception | None = None
    for _ in range(2):
        try:
            raw = parse_json_response(client.complete(body))
            items = raw.get("topics", raw) if isinstance(raw, dict) else raw
            return [validate_topic(item) for item in items]
        except Exception as exc:  # noqa: BLE001 - retry boundary for model output
            last_error = exc
    raise ValueError(f"screening failed after retry: {last_error}")


def group_topics(topics: list[Topic], client: ChatClient) -> list[Topic]:
    passed = [topic for topic in topics if topic.pass_]
    if len(passed) <= 1:
        return passed
    body = prompt("02_group_topics.md", topics_json=[topic.to_json() for topic in passed])
    try:
        raw = parse_json_response(client.complete(body))
        items = raw.get("topics", raw) if isinstance(raw, dict) else raw
        return [validate_topic(item) for item in items]
    except Exception:
        return passed


def dedupe_topics(topics: list[Topic]) -> list[Topic]:
    kept: list[Topic] = []
    for topic in topics:
        replaced = False
        for index, item in enumerate(kept):
            if is_duplicate_topic(topic, item):
                if topic.score > item.score:
                    kept[index] = topic
                replaced = True
                break
        if not replaced:
            kept.append(topic)
    return kept


def rank_topics(topics: list[Topic], client: ChatClient) -> list[Topic]:
    if not topics:
        return []
    batch_size = int(os.environ.get("RANK_BATCH_SIZE", "50"))
    deduped = dedupe_topics(topics)
    if len(deduped) <= batch_size:
        return _rank_batch(deduped, client)
    survivors: list[Topic] = []
    for start in range(0, len(deduped), batch_size):
        survivors.extend(topic for topic in _rank_batch(deduped[start : start + batch_size], client) if topic.pass_)
    return dedupe_topics(survivors)


def _rank_batch(topics: list[Topic], client: ChatClient) -> list[Topic]:
    body = prompt("02_rank_topics.md", topics_json=[topic.to_json() for topic in topics])
    try:
        raw = parse_json_response(client.complete(body))
        items = raw.get("topics", raw) if isinstance(raw, dict) else raw
        ranked = [validate_topic(item) for item in items]
    except Exception:
        return topics
    ranked_ids = {",".join(topic.source_ids) for topic in ranked}
    for topic in topics:
        key = ",".join(topic.source_ids)
        if key not in ranked_ids:
            ranked.append(Topic(topic.title, False, min(topic.score, 6), topic.economic_question, topic.core_concept, topic.reason, topic.source_ids, topic.related_concepts))
    return ranked


def _topic_key(topic: Topic) -> str:
    return ",".join(topic.source_ids)


def score_reader_appeal(topics: list[Topic], client: ChatClient) -> list[Topic]:
    candidates = [topic for topic in topics if topic.pass_]
    if not candidates:
        return topics
    batch_size = int(os.environ.get("APPEAL_BATCH_SIZE", "40"))
    appeal_by_key: dict[str, tuple[int, str]] = {}
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        body = prompt("02_score_reader_appeal.md", topics_json=[topic.to_json() for topic in chunk])
        try:
            raw = parse_json_response(client.complete(body))
            items = raw.get("topics", raw) if isinstance(raw, dict) else raw
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = ",".join(str(value) for value in item.get("source_ids", []))
                if not key or item.get("reader_score") is None:
                    continue
                appeal_by_key[key] = (max(1, min(10, int(item["reader_score"]))), str(item.get("reader_note") or ""))
        except Exception:
            continue
    merged: list[Topic] = []
    for topic in topics:
        appeal = appeal_by_key.get(_topic_key(topic))
        if appeal is None:
            merged.append(topic)
            continue
        merged.append(
            Topic(
                topic.title,
                topic.pass_,
                topic.score,
                topic.economic_question,
                topic.core_concept,
                topic.reason,
                topic.source_ids,
                topic.related_concepts,
                reader_score=appeal[0],
                reader_note=appeal[1],
            )
        )
    return merged


def reader_ok(topic: Topic) -> bool:
    if topic.reader_score is None:
        return True
    return topic.reader_score >= int(os.environ.get("MIN_READER_SCORE", "8"))


def select_sort_key(topic: Topic) -> tuple[int, int]:
    reader = topic.reader_score if topic.reader_score is not None else 0
    return (reader, topic.score)


def select_topics(topics: list[Topic], limit: int) -> tuple[list[Topic], list[Topic]]:
    min_score = int(os.environ.get("MIN_TOPIC_SCORE", "9"))
    passed = [topic for topic in topics if topic.pass_ and topic.score >= min_score and reader_ok(topic)]
    rejected = [topic for topic in topics if topic not in passed]
    passed.sort(key=select_sort_key, reverse=True)
    selected: list[Topic] = []
    for topic in passed:
        if any(is_duplicate_topic(topic, item) for item in selected):
            rejected.append(topic)
        elif len(selected) < limit:
            selected.append(topic)
        else:
            rejected.append(topic)
    return selected, rejected


def topic_status(topic: dict, selected_titles: set[str]) -> str:
    if topic["title"] in selected_titles:
        return "selected"
    min_score = int(os.environ.get("MIN_TOPIC_SCORE", "9"))
    min_reader = int(os.environ.get("MIN_READER_SCORE", "8"))
    reader_score = topic.get("reader_score")
    reader_ok = reader_score is None or int(reader_score) >= min_reader
    if topic.get("pass") and int(topic.get("score", 0)) >= min_score and reader_ok:
        return "backup"
    return "rejected"


def render_topics_review(base: Path) -> None:
    ranked = read_json(base / "ranked.json") if (base / "ranked.json").exists() else []
    if not ranked and (base / "screening.json").exists():
        ranked = read_json(base / "screening.json")
    selected = read_json(base / "topics.json") if (base / "topics.json").exists() else []
    selected_titles = {str(topic.get("title", "")) for topic in selected}
    if not isinstance(ranked, list):
        ranked = []

    items = sorted(
        ranked,
        key=lambda item: (
            -int(item.get("reader_score") or 0),
            -int(item.get("score", 0)),
            str(item.get("title", "")),
        ),
    )
    passed = [item for item in items if item.get("pass")]
    score9 = sum(1 for item in passed if int(item.get("score", 0)) >= 9)
    score8 = sum(1 for item in passed if int(item.get("score", 0)) == 8)
    reader9 = sum(1 for item in passed if int(item.get("reader_score") or 0) >= 9)

    rows = []
    for item in items:
        title = str(item.get("title", "未命名"))
        score = int(item.get("score", 0))
        reader_score = item.get("reader_score")
        reader_display = str(reader_score) if reader_score is not None else "—"
        status = topic_status(item, selected_titles)
        status_label = {"selected": "已选", "backup": "备选", "rejected": "未选"}.get(status, "未选")
        row_class = status
        reader_note = html.escape(str(item.get("reader_note") or ""))
        rows.append(
            f"""
            <tr class="{row_class}">
              <td>{score}</td>
              <td>{reader_display}</td>
              <td>{"是" if item.get("pass") else "否"}</td>
              <td><span class="tag {status}">{status_label}</span></td>
              <td>{html.escape(title)}</td>
              <td>{html.escape(str(item.get("core_concept", "")))}</td>
              <td>{html.escape(str(item.get("economic_question", "")))}</td>
              <td class="note">{reader_note}</td>
            </tr>
            """
        )

    page = f"""<!doctype html>
<meta charset="utf-8">
<title>选题评分 - {html.escape(base.name)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;line-height:1.6;color:#222;background:#fafafa}}
.meta{{background:white;border:1px solid #ddd;border-radius:8px;padding:18px;margin:0 0 18px;max-width:1200px}}
table{{width:100%;max-width:1200px;border-collapse:collapse;background:white;border:1px solid #ddd}}
th,td{{border-bottom:1px solid #eee;padding:10px 12px;text-align:left;vertical-align:top;font-size:14px}}
th{{background:#f8fafc;position:sticky;top:0}}
tr.selected{{background:#ecfdf5}}
tr.backup{{background:#fffbeb}}
tr.rejected{{color:#666}}
.tag{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px}}
.tag.selected{{background:#dcfce7;color:#166534}}
.tag.backup{{background:#fef3c7;color:#92400e}}
.tag.rejected{{background:#f3f4f6;color:#6b7280}}
.note{{color:#666;font-size:13px;max-width:220px}}
a{{color:#2563eb}}
</style>
<p><a href="index.html">← 返回候选文章</a></p>
<h1>选题评分 · {html.escape(base.name)}</h1>
<div class="meta">
  <p><b>合计</b> {len(items)} 个选题 · <b>pass</b> {len(passed)} · <b>机制9分+</b> {score9} · <b>机制8分</b> {score8} · <b>读者9分+</b> {reader9} · <b>已生成文章</b> {len(selected)}</p>
  <p>先按机制质量筛选，再按<b>读者吸引力</b>（贴近生活、热点、有趣）选前 {len(selected)} 篇。</p>
</div>
<table>
  <thead>
    <tr><th>机制分</th><th>读者分</th><th>pass</th><th>状态</th><th>标题</th><th>概念</th><th>经济学问题</th><th>读者吸引力说明</th></tr>
  </thead>
  <tbody>
    {"".join(rows) if rows else "<tr><td colspan='8'>暂无选题数据</td></tr>"}
  </tbody>
</table>
"""
    write_text(base / "topics.html", page)


def is_duplicate_topic(left: Topic, right: Topic) -> bool:
    title_ratio = SequenceMatcher(None, left.title, right.title).ratio()
    question_ratio = SequenceMatcher(None, left.economic_question, right.economic_question).ratio()
    return max(title_ratio, question_ratio) >= 0.55


def source_excerpt(article: SourceArticle, main: bool) -> str:
    limit = 5000 if main else 2000
    text = article.content_text
    return text[:limit]


def sources_for(topic: Topic, articles: list[SourceArticle]) -> list[dict]:
    by_id = {article.id: article for article in articles}
    found = [by_id[item] for item in topic.source_ids if item in by_id]
    return [
        {
            "id": article.id,
            "title": article.title,
            "source": article.source,
            "link": article.link,
            "published_at": article.published_at.isoformat(),
            "excerpt": source_excerpt(article, i == 0),
        }
        for i, article in enumerate(found)
    ]


def build_event_brief(cdir: Path, topic: Topic, sources: list[dict], client: ChatClient) -> dict:
    claims_prompt = prompt("07_extract_claims.md", selected_topic=topic.to_json(), sources=sources)
    try:
        claims = parse_json_response(client.complete(claims_prompt, temperature=0))
    except Exception as exc:  # noqa: BLE001
        claims = {"claims": [], "search_queries": [], "error": str(exc)}
    write_json(cdir / "claims.json", claims)

    queries = claims.get("search_queries", []) if isinstance(claims, dict) else []
    if not isinstance(queries, list):
        queries = []
    search_evidence = search_queries([str(item) for item in queries])
    write_json(cdir / "search_evidence.json", search_evidence)

    verify_prompt = prompt(
        "08_verify_claims_with_search.md",
        claims=claims,
        search_evidence=search_evidence,
        sources=sources,
    )
    try:
        event_brief = parse_json_response(client.complete(verify_prompt, temperature=0))
    except Exception as exc:  # noqa: BLE001
        event_brief = {
            "event_summary": "",
            "verified_facts": [],
            "source_errors": [],
            "disputed_or_unverified": [],
            "do_not_assert": [],
            "verification_status": "failed",
            "error": str(exc),
        }
    if event_brief.get("verification_status") == "passed":
        if not search_evidence or all(not item.get("results") for item in search_evidence):
            event_brief["verification_status"] = "risky"
    write_json(cdir / "event_brief.json", event_brief)
    return event_brief


def post_write_fact_check(article: str, event_brief: dict, client: ChatClient) -> dict:
    check_prompt = prompt("06_fact_check_article.md", article=article, event_brief=event_brief)
    try:
        return parse_json_response(client.complete(check_prompt, temperature=0))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "issues": [{"claim": "", "problem": str(exc), "suggestion": "人工检查"}]}


def write_candidate_content(cdir: Path, topic: Topic, sources: list[dict], client: ChatClient) -> None:
    event_brief = build_event_brief(cdir, topic, sources, client)
    article_prompt = prompt(
        "03_write_wechat_article.md",
        selected_topic=topic.to_json(),
        event_brief=event_brief,
        sources=sources,
    )
    article = client.complete(article_prompt, temperature=0.6)
    write_text(cdir / "article.md", article)
    write_text(cdir / "article.html", render_wechat_html(article))
    write_cover(cdir / "cover.png", topic.title, footer=topic.core_concept)
    card_prompt = prompt("04_make_knowledge_card.md", article=article, selected_topic=topic.to_json(), sources=sources)
    write_text(cdir / "knowledge-card.patch.md", client.complete(card_prompt, temperature=0.2))
    write_json(cdir / "fact_check.json", post_write_fact_check(article, event_brief, client))


def write_candidate(base: Path, index: int, topic: Topic, sources: list[dict], client: ChatClient) -> None:
    cdir = base / "candidates" / f"{index:02d}"
    cdir.mkdir(parents=True, exist_ok=True)
    write_json(cdir / "topic.json", topic.to_json())
    write_json(cdir / "sources.json", sources)
    write_candidate_content(cdir, topic, sources, client)


def render_wechat_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out = ['<meta charset="utf-8">', '<section style="font-size:16px;line-height:1.85;color:#222;">']
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if re.fullmatch(r"[-*_]{3,}", text):
            out.append('<section style="margin:1.8em 0;border-top:1px solid #e5e7eb;height:0;line-height:0;"></section>')
        elif text.startswith("#"):
            title = render_inline(text.lstrip("#").strip())
            out.append(f'<h2 style="font-size:18px;line-height:1.5;margin:1.7em 0 .8em;color:#111;">{title}</h2>')
        elif re.match(r"^[-*]\s+", text):
            out.append(f'<p style="margin:0 0 .7em;padding-left:1em;">• {render_inline(text[2:].strip())}</p>')
        else:
            out.append(f'<p style="margin:0 0 1em;">{render_inline(text)}</p>')
    out.append(f'<p style="margin:2em 0 0;font-size:12px;line-height:1.7;color:#888;">{AI_DISCLOSURE}</p>')
    out.append("</section>")
    return "\n".join(out)


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r'<strong style="color:#8a1c1c;background:#fff3d8;padding:0 .12em;">\1</strong>', escaped)


def write_cover(path: Path, title: str, column: str = "用经济学看昨天", footer: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (900, 500), "#16141a")
    draw = ImageDraw.Draw(image)
    try:
        serif = first_existing_font(
            [
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-SemiBold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                "/System/Library/Fonts/Supplemental/Songti.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            ]
        )
        sans = first_existing_font(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            ]
        )
        title_font, wrapped_title = fit_cover_title(draw, title, serif, 730, 188)
        small_font = ImageFont.truetype(sans, 34)
        footer_font = ImageFont.truetype(sans, 28)
        tiny_font = ImageFont.truetype(sans, 20)
    except OSError:
        title_font = ImageFont.load_default()
        wrapped_title = wrap_title(title, 12)
        small_font = ImageFont.load_default()
        footer_font = ImageFont.load_default()
        tiny_font = ImageFont.load_default()
    for y in range(500):
        t = y / 499
        r = int(34 + 112 * t)
        g = int(20 + 8 * t)
        b = int(28 + 6 * t)
        draw.line((0, y, 900, y), fill=(r, g, b))
    for x in range(900):
        t = x / 899
        draw.line((x, 0, x, 500), fill=(int(12 + 45 * t), 14, int(24 + 18 * t)), width=1)

    draw.ellipse((560, -120, 1040, 360), fill="#a3262d")
    draw.ellipse((610, -70, 980, 300), outline="#d9a441", width=4)
    draw.rectangle((46, 44, 854, 456), outline="#f0c76a", width=4)
    draw.rectangle((70, 70, 830, 430), outline="#71343b", width=2)

    draw.rounded_rectangle((92, 74, 360, 134), radius=0, fill="#f0c76a")
    draw.text((112, 82), column, fill="#351018", font=small_font)
    draw.text((92, 152), "DAILY ECONOMICS", fill="#f0c76a", font=tiny_font)

    draw.multiline_text((90, 178), wrapped_title, fill="#fff8e7", font=title_font, spacing=0)
    draw.rectangle((90, 396, 520, 400), fill="#f0c76a")
    draw.text((90, 416), footer or "经济学视角", fill="#fff8e7", font=footer_font)
    image.save(path)


def first_existing_font(paths: list[str]) -> str:
    for path in paths:
        if Path(path).exists():
            return path
    return paths[-1]


def wrap_title(title: str, width: int) -> str:
    return "\n".join(title[i : i + width] for i in range(0, len(title), width))


def wrap_title_pixels(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> str:
    lines: list[str] = []
    line = ""
    for char in title:
        candidate = line + char
        if char in "，。！？；：、" or draw.textlength(candidate, font=font) <= max_width:
            line = candidate
            continue
        lines.append(line)
        if len(lines) == max_lines:
            lines[-1] = lines[-1].rstrip("，。！？；：、") + "..."
            return "\n".join(lines)
        line = char
    if line:
        lines.append(line)
    return "\n".join(lines)


def fit_cover_title(draw: ImageDraw.ImageDraw, title: str, font_path: str, max_width: int, max_height: int) -> tuple[ImageFont.FreeTypeFont, str]:
    for size in range(78, 43, -2):
        font = ImageFont.truetype(font_path, size)
        wrapped = wrap_title_pixels(draw, title, font, max_width, 4)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=0)
        if bbox[2] <= max_width and bbox[3] - bbox[1] <= max_height:
            return font, wrapped
    font = ImageFont.truetype(font_path, 44)
    return font, wrap_title_pixels(draw, title, font, max_width, 4)


def format_brief_errors(event_brief: dict) -> str:
    errors = event_brief.get("source_errors") or []
    items = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        source_claim = html.escape(str(item.get("source_claim") or ""))
        correction = html.escape(str(item.get("correction") or ""))
        items.append(f"<li><b>原文</b> {source_claim} → <b>纠正</b> {correction}</li>")
    return "".join(items)


def render_index(base: Path) -> None:
    ranked_count = len(read_json(base / "ranked.json")) if (base / "ranked.json").exists() else 0
    candidates = []
    for cdir in sorted((base / "candidates").glob("*")):
        topic = read_json(cdir / "topic.json")
        check = read_json(cdir / "fact_check.json")
        sources = read_json(cdir / "sources.json")
        event_brief = read_json(cdir / "event_brief.json") if (cdir / "event_brief.json").exists() else {}
        brief_status = str(event_brief.get("verification_status") or "unknown")
        article_status = str(check.get("status") or ("passed" if check.get("ok") else "risky"))
        candidates.append((cdir.name, topic, brief_status, article_status, sources, check, event_brief))
    rows = []
    for name, topic, brief_status, article_status, sources, check, event_brief in candidates:
        issues = check.get("issues") or []
        issue_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in issues)
        brief_error_html = format_brief_errors(event_brief)
        rows.append(
            f"""
            <article class="card">
              <img src="candidates/{name}/cover.png" alt="cover">
              <h2>{html.escape(topic["title"])}</h2>
              <p><b>分数</b> {topic["score"]} · <b>概念</b> {html.escape(topic["core_concept"])} · <b>事实底稿</b> <span class="{brief_status}">{brief_status}</span> · <b>文章校验</b> <span class="{article_status}">{article_status}</span></p>
              <p>{html.escape(topic["economic_question"])}</p>
              <p><b>来源</b> {"; ".join(html.escape(s["title"]) for s in sources)}</p>
              <p><a href="candidates/{name}/article.html">article.html</a> · <a href="candidates/{name}/article.md">article.md</a> · <a href="candidates/{name}/event_brief.json">event_brief.json</a></p>
              <ul>{brief_error_html}{issue_html}</ul>
            </article>
            """
        )
    page = f"""<!doctype html>
<meta charset="utf-8">
<title>用经济学看昨天</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;line-height:1.6;color:#222;background:#fafafa}}
.card{{background:white;border:1px solid #ddd;border-radius:8px;padding:18px;margin:0 0 18px;max-width:900px}}
img{{width:260px;max-width:100%;display:block;border:1px solid #eee}}
.passed{{color:#15803d}}.risky{{color:#b45309}}.failed{{color:#b91c1c}}
a{{color:#2563eb}}
</style>
<h1>用经济学看昨天</h1>
<p><a href="topics.html">查看全部选题评分（{ranked_count} 个）</a></p>
{"".join(rows) if rows else "<p>今天没有生成候选文章。</p>"}
"""
    write_text(base / "index.html", page)


def render_home(data_dir: Path = Path("data")) -> None:
    runs = []
    for rdir in sorted((data_dir / "runs").glob("*"), reverse=True):
        if not rdir.is_dir():
            continue
        topics = read_json(rdir / "topics.json") if (rdir / "topics.json").exists() else []
        articles = read_json(rdir / "articles.json") if (rdir / "articles.json").exists() else []
        statuses = []
        for cdir in sorted((rdir / "candidates").glob("*")):
            check = read_json(cdir / "fact_check.json") if (cdir / "fact_check.json").exists() else {}
            statuses.append(str(check.get("status") or ("passed" if check.get("ok") else "risky")))
        runs.append((rdir.name, topics, articles, statuses))

    rows = []
    for day, topics, articles, statuses in runs:
        passed = statuses.count("passed")
        titles = "".join(f"<li>{html.escape(str(topic.get('title', '未命名选题')))}</li>" for topic in topics)
        rows.append(
            f"""
            <article class="card">
              <h2><a href="runs/{day}/index.html">{day}</a></h2>
              <p>{len(articles)} 篇原文 · {len(topics)} 个候选 · {passed}/{len(statuses)} 事实校验通过</p>
              <ol>{titles}</ol>
            </article>
            """
        )

    page = f"""<!doctype html>
<meta charset="utf-8">
<title>每日文章情况</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:32px;line-height:1.6;color:#222;background:#fafafa}}
.card{{background:white;border:1px solid #ddd;border-radius:8px;padding:18px;margin:0 0 18px;max-width:900px}}
h1,h2{{line-height:1.3}} a{{color:#2563eb}}
</style>
<h1>每日文章情况</h1>
{"".join(rows) if rows else "<p>还没有生成日报。</p>"}
"""
    write_text(data_dir / "index.html", page)


def run_daily(target_date: date, force: bool, limit: int) -> None:
    base = run_dir(target_date)
    if base.exists():
        if not force:
            raise SystemExit(f"{base} already exists; use --force to regenerate")
        shutil.rmtree(base)
    base.mkdir(parents=True)
    articles = load_articles(target_date)
    write_json(base / "articles.json", article_payload(articles, max_chars=400))
    log_lines = [f"loaded {len(articles)} articles"]
    try:
        screened = screen_articles(articles, local_client())
        grouped = group_topics(dedupe_topics(screened), local_client())
        ranked = rank_topics(grouped, local_client())
        ranked = score_reader_appeal(ranked, local_client())
    except Exception as exc:  # noqa: BLE001
        write_json(base / "screening.json", {"error": str(exc), "topics": []})
        render_index(base)
        render_topics_review(base)
        render_home()
        return
    selected, rejected = select_topics(ranked, limit)
    write_json(base / "screening.json", [topic.to_json() for topic in screened])
    write_json(base / "grouped.json", [topic.to_json() for topic in grouped])
    write_json(base / "ranked.json", [topic.to_json() for topic in ranked])
    write_json(base / "topics.json", [topic.to_json() for topic in selected])
    write_json(base / "rejected_topics.json", [topic.to_json() for topic in rejected])
    for i, topic in enumerate(selected, start=1):
        write_candidate(base, i, topic, sources_for(topic, articles), deepseek_client())
    render_index(base)
    render_topics_review(base)
    log_lines.append(f"generated {len(selected)} candidates")
    write_text(base / "run.log", "\n".join(log_lines) + "\n")
    render_home()


def backup_candidate_files(candidate_dir: Path, names: list[str]) -> None:
    for name in names:
        path = candidate_dir / name
        if path.exists():
            path.replace(candidate_dir / f"{path.stem}.prev{path.suffix}")


def rewrite_candidate(candidate_dir: Path) -> None:
    topic = validate_topic(read_json(candidate_dir / "topic.json"))
    sources = read_json(candidate_dir / "sources.json")
    backup_candidate_files(
        candidate_dir,
        ["article.md", "article.html", "claims.json", "search_evidence.json", "event_brief.json", "fact_check.json"],
    )
    write_candidate_content(candidate_dir, topic, sources, deepseek_client())


def apply_card(candidate_dir: Path) -> Path:
    topic = validate_topic(read_json(candidate_dir / "topic.json"))
    patch = read_text(candidate_dir / "knowledge-card.patch.md")
    concepts = Path("docs") / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    path = concepts / f"{safe_filename(topic.core_concept)}.md"
    old = path.read_text(encoding="utf-8") if path.exists() else f"# {topic.core_concept}\n\n"
    write_text(path, old.rstrip() + "\n\n" + patch.strip() + "\n")
    return path


def safe_filename(value: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "-", value).strip() or "concept"
