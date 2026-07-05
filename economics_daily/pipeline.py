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

AI_DISCLOSURE = "本文由 AI 辅助生成，用于经济学学习与讨论；事实信息以参考来源为准。"


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
    return Topic(
        title=str(raw["title"]),
        pass_=bool(raw["pass"]),
        score=max(1, min(10, int(raw["score"]))),
        economic_question=str(raw["economic_question"]),
        core_concept=str(raw["core_concept"]),
        reason=str(raw["reason"]),
        source_ids=[str(item) for item in raw["source_ids"]],
        related_concepts=[str(item) for item in raw.get("related_concepts", [])],
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


def select_topics(topics: list[Topic], limit: int) -> tuple[list[Topic], list[Topic]]:
    passed = [topic for topic in topics if topic.pass_]
    passed.sort(key=lambda topic: topic.score, reverse=True)
    selected: list[Topic] = []
    rejected: list[Topic] = []
    for topic in passed:
        if any(is_duplicate_topic(topic, item) for item in selected):
            rejected.append(topic)
        elif len(selected) < limit:
            selected.append(topic)
        else:
            rejected.append(topic)
    return selected, rejected


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


def write_candidate(base: Path, index: int, topic: Topic, sources: list[dict], client: ChatClient) -> None:
    cdir = base / "candidates" / f"{index:02d}"
    cdir.mkdir(parents=True, exist_ok=True)
    write_json(cdir / "topic.json", topic.to_json())
    write_json(cdir / "sources.json", sources)
    article_prompt = prompt("03_write_wechat_article.md", selected_topic=topic.to_json(), sources=sources)
    article = client.complete(article_prompt, temperature=0.6)
    write_text(cdir / "article.md", article)
    write_text(cdir / "article.html", render_wechat_html(article))
    write_cover(cdir / "cover.png", topic.title)
    card_prompt = prompt("04_make_knowledge_card.md", article=article, selected_topic=topic.to_json(), sources=sources)
    write_text(cdir / "knowledge-card.patch.md", client.complete(card_prompt, temperature=0.2))
    check_prompt = prompt("06_fact_check_article.md", article=article, sources=sources)
    try:
        fact_check = parse_json_response(client.complete(check_prompt, temperature=0))
    except Exception as exc:  # noqa: BLE001
        fact_check = {"status": "failed", "issues": [{"claim": "", "problem": str(exc), "suggestion": "人工检查"}]}
    write_json(cdir / "fact_check.json", fact_check)


def render_wechat_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out = ['<meta charset="utf-8">', '<section style="font-size:16px;line-height:1.85;color:#222;">']
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
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
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def write_cover(path: Path, title: str, column: str = "用经济学看昨天", footer: str = "资源稀缺性 · 替代性资源开发") -> None:
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
    draw.text((90, 416), footer, fill="#fff8e7", font=footer_font)
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


def render_index(base: Path) -> None:
    candidates = []
    for cdir in sorted((base / "candidates").glob("*")):
        topic = read_json(cdir / "topic.json")
        check = read_json(cdir / "fact_check.json")
        sources = read_json(cdir / "sources.json")
        status = check.get("status") or ("passed" if check.get("ok") else "risky")
        candidates.append((cdir.name, topic, status, sources, check))
    rows = []
    for name, topic, status, sources, check in candidates:
        issues = check.get("issues") or []
        issue_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in issues)
        rows.append(
            f"""
            <article class="card">
              <img src="candidates/{name}/cover.png" alt="cover">
              <h2>{html.escape(topic["title"])}</h2>
              <p><b>分数</b> {topic["score"]} · <b>概念</b> {html.escape(topic["core_concept"])} · <b>事实校验</b> <span class="{status}">{status}</span></p>
              <p>{html.escape(topic["economic_question"])}</p>
              <p><b>来源</b> {"; ".join(html.escape(s["title"]) for s in sources)}</p>
              <p><a href="candidates/{name}/article.html">article.html</a> · <a href="candidates/{name}/article.md">article.md</a></p>
              <ul>{issue_html}</ul>
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
        grouped = group_topics(screened, local_client())
    except Exception as exc:  # noqa: BLE001
        write_json(base / "screening.json", {"error": str(exc), "topics": []})
        render_index(base)
        render_home()
        return
    selected, rejected = select_topics(grouped, limit)
    write_json(base / "screening.json", [topic.to_json() for topic in screened])
    write_json(base / "topics.json", [topic.to_json() for topic in selected])
    write_json(base / "rejected_topics.json", [topic.to_json() for topic in rejected])
    for i, topic in enumerate(selected, start=1):
        write_candidate(base, i, topic, sources_for(topic, articles), deepseek_client())
    render_index(base)
    log_lines.append(f"generated {len(selected)} candidates")
    write_text(base / "run.log", "\n".join(log_lines) + "\n")
    render_home()


def rewrite_candidate(candidate_dir: Path) -> None:
    topic = validate_topic(read_json(candidate_dir / "topic.json"))
    sources = read_json(candidate_dir / "sources.json")
    for name in ["article.md", "article.html"]:
        path = candidate_dir / name
        if path.exists():
            path.replace(candidate_dir / name.replace("article.", "article.prev."))
    article = deepseek_client().complete(prompt("03_write_wechat_article.md", selected_topic=topic.to_json(), sources=sources), temperature=0.6)
    write_text(candidate_dir / "article.md", article)
    write_text(candidate_dir / "article.html", render_wechat_html(article))
    write_cover(candidate_dir / "cover.png", topic.title)


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
