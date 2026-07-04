# Daily Workflow

Date: 2026-07-05

## Daily Run

Run on `10.88.255.251`.

```bash
cd /home/daofu/github/i-love-economics
docker compose run --rm daily --date yesterday
```

The default target is yesterday's Beijing natural day.

Example:

If run on `2026-07-05`, it processes articles published from `2026-07-04 00:00:00` to `2026-07-04 23:59:59` Beijing time.

## Output Directory

Each run writes to:

```text
data/runs/YYYY-MM-DD/
  index.html
  screening.json
  topics.json
  candidates/
    01/
      article.md
      article.html
      cover.png
      sources.json
      fact_check.json
      knowledge-card.patch.md
    02/
      article.md
      article.html
      cover.png
      sources.json
      fact_check.json
      knowledge-card.patch.md
  rejected_topics.json
  run.log
```

## Review

Open:

```text
data/runs/YYYY-MM-DD/index.html
```

Use it to review:

- Candidate title.
- Score.
- Core economics question.
- Core concept.
- Fact-check status.
- Cover image.
- Source list.
- Links to `article.html` and `article.md`.

`index.html` is only a preview and management entry. It does not support editing.

## Publish

For the article you choose to publish:

1. Open `article.html`.
2. Copy the article into the WeChat official account editor.
3. Upload `cover.png` as the article cover.
4. Check sources and risky fact-check notes.
5. Make final edits in the WeChat editor if needed.
6. Publish manually.

The system never publishes automatically.

## After Publishing

Apply the knowledge-card patch only for published articles.

```bash
docker compose run --rm apply-card data/runs/YYYY-MM-DD/candidates/01
```

This creates or updates the matching file under:

```text
docs/concepts/
```

Do not apply cards for unpublished candidates.

## Rerun A Day

If the run directory already exists, the daily command should exit without overwriting it.

Use `--force` only when you intentionally want to regenerate that day.

```bash
docker compose run --rm daily --date 2026-07-04 --force
```

Use this when some articles published yesterday only received full content later.

## Rewrite One Candidate

Rewrite a single candidate without rerunning the whole day:

```bash
docker compose run --rm rewrite data/runs/YYYY-MM-DD/candidates/02
```

The rewrite command should back up existing article files before replacing them:

```text
article.prev.md
article.prev.html
```

## Expected Manual Decisions

Every day, the user decides:

- Which candidate articles are worth publishing.
- Whether a fact-check warning is acceptable after manual review.
- Whether to apply the knowledge-card patch after publishing.

The system decides:

- Which yesterday articles are worth screening.
- Which topics become up to 3 complete candidates.
- Which extra topics remain as rejected or backup summaries.
