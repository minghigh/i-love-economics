# Product Decisions

Date: 2026-07-05

## Product Shape

This project generates daily WeChat official account article drafts for learning economics from real news.

The first version is not a course, LMS, database product, or web app. It is a daily article generation pipeline.

## Daily Output

- Review articles published yesterday, based on Beijing time.
- Select events that can be explained clearly through economics.
- If no event is good enough, output nothing.
- Generate up to 3 complete candidate articles per day.
- Extra good-but-not-top-3 topics go into a rejected/candidate summary, not full drafts.

## Topic Rules

A topic is worth writing only if it has:

- A real behavior or decision to explain.
- A clear economics concept behind it.
- A reader-facing insight, preferably counterintuitive or clarifying.

Events can be merged into one article only when they share the same economics question. Otherwise, keep them as separate candidates.

Ranking priority:

1. Strength of the economics explanation.
2. Reader relatability.
3. Counterintuitive conclusion.
4. Freshness and popularity.

Exclude:

- Pure entertainment gossip unless platform, attention, or fan-economy mechanisms are clear.
- Pure emotion or stance-only events.
- Policy summaries without incentive or constraint changes.
- Short-term market moves unless explaining behavior, not predicting prices.
- Events with too little information or disputed facts.

## Article Format

Each complete candidate is a publishable WeChat article.

Article structure:

1. Title focused on a real-world question.
2. Opening: what happened yesterday.
3. Surface interpretation: how people may commonly understand it.
4. Economics explanation: one core concept.
5. Counterintuitive or memorable conclusion.
6. Real-world extension.
7. A non-classroom-style knowledge card.
8. Reference sources.

The title should be reality-first, not concept-first.

Example:

- Prefer: `为什么大家都知道价格战伤利润，却还是停不下来？`
- Avoid: `囚徒困境：价格战背后的经济学`

The main article should not begin with "today we learn concept X". The explicit concept goes near the end.

## Concept Rules

- One article has one core economics concept.
- It can lightly mention 1-2 related concepts.
- One knowledge card corresponds to one concept, not one article.
- Daily runs only generate `knowledge-card.patch.md`.
- Concept docs are updated only after the user decides to publish an article.

## Sources

First version uses the existing `we-mp-rss` SQLite data from the old WeChat project.

The new project runs independently, but mounts the old Docker volume read-only.

Do:

- Read articles from the `we-mp-rss` SQLite database.
- Use articles published yesterday by Beijing natural day.
- Allow reruns for yesterday when full content arrived late.
- Keep reference sources in each draft.

Do not:

- Connect directly to the old project's MySQL.
- Depend on the old project's API.
- Copy large original passages into the output article.

DeepSeek may receive relevant original excerpts plus structured material, but original text is only a fact source, not material to rewrite.

Excerpt rule:

- Main source: up to 3000-5000 Chinese characters.
- Supporting source: up to 1000-2000 Chinese characters each.
- Keep event details, numbers, direct claims, and background.
- Remove ads, QR prompts, unrelated sections, and repeated disclaimers.

## Model Roles

Local model through `local-llm-gateway`:

- Understand and screen articles.
- Group events into economics questions.
- Produce scores and reasons.
- Generate cover text.

Screening runs in small batches because a normal day can contain hundreds of articles.

DeepSeek:

- Write complete WeChat articles.
- Generate final Markdown and HTML text.
- Run fact checks after writing.

There is no fallback from DeepSeek writing to local-model writing. If writing fails, mark the candidate as failed and continue.

Prompts must be visible as repo files:

```text
prompts/
  01_screen_articles.md
  02_group_topics.md
  03_write_wechat_article.md
  04_make_knowledge_card.md
  05_make_cover_text.md
  06_fact_check_article.md
```

## Screening Output

The local screening model should return JSON with minimal validation.

Required fields:

```json
{
  "title": "...",
  "pass": true,
  "score": 8,
  "economic_question": "...",
  "core_concept": "...",
  "reason": "...",
  "source_ids": ["..."]
}
```

If JSON parsing or validation fails, retry once. If it still fails, log the batch as failed.

## Fact Check

After DeepSeek writes an article, DeepSeek checks facts once.

The check compares article claims with the provided source excerpts. If the model/API has built-in search, it may use it. This project will not add a separate search API in version one.

Fact check does not block file generation. It marks the candidate as:

- `passed`
- `risky`
- `failed`

Risk details should include the claim, problem type, and suggested fix.

The system does not automatically rewrite risky claims.

## Cover And Layout

Version one creates a local text-only cover image, no AI image generation.

Cover includes:

- Main title.
- Date.
- Column name: `用经济学看昨天`.

Do not use news images, article images, people, logos, or generated illustrations in version one.

The article HTML is optimized for copying into the WeChat editor:

- Inline styles.
- Simple HTML tags.
- No external CSS or JavaScript.
- Comfortable reading layout with short paragraphs and clear section rhythm.

No in-article images in version one.

## Deployment

Run this project on `10.88.255.251`.

Use an independent Docker Compose project. Mount the old `we-mp-rss-data` volume read-only.

Use filesystem storage, not a database.

Use host cron to run the daily job. Do not build a scheduler service yet.

Use `.env` for secrets and endpoints.

## First-Version Non-Goals

- No Web UI.
- No rich editor.
- No auto publish.
- No search API integration.
- No database.
- No image generation model.
- No direct old-project API dependency.
- No automatic concept-card updates from unpublished candidates.
