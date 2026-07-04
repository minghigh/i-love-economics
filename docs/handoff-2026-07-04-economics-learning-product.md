# Handoff: i-love-economics

Date: 2026-07-04

## Context

The user has an existing project that collects many WeChat official account articles every day:

- Source repo: `/Users/daofu/Documents/workspace/wechat_official_account_article_summary`
- New target project: `/Users/daofu/Documents/workspace/i-love-economics`

The user wants to explore a new learning product, likely split into this new project, that uses fresh news/articles as material for learning economics.

This is currently a discussion/research/design phase, not an implementation task.

## Chosen Direction

The user chose option C:

> A mixed learning system: first explain real-world news through economics, then gradually accumulate concept cards into a personal economics knowledge base.

Recommended first version:

1. Read daily article/news summaries.
2. Select 3-5 items that are suitable for economics interpretation.
3. Explain each item through one or more economics concepts.
4. Save the concepts and examples so they can become a long-term knowledge base.

Do not start with a full course system. Start with a daily economics interpretation flow and let the knowledge base emerge from actual usage.

## Product Hypothesis

The product is for personal learning:

- The user likes economics.
- The user wants to understand real life through economics.
- News is the daily trigger.
- Economics concepts are the learning lens.
- The value is not just summarization, but explanation: "why does this happen, what incentives/constraints/tradeoffs are visible here?"

## MVP Shape

For each selected article/news item, output:

1. `现实事件`: what happened.
2. `经济学概念`: the relevant concept, such as opportunity cost, incentives, externalities, information asymmetry, supply and demand, expectations, game theory, principal-agent, sunk cost, marginal analysis.
3. `经济学解释`: use the concept to explain the real event.
4. `反问`: one question that makes the learner think.
5. `知识卡片`: a reusable concept note, either newly created or linked to an existing one.

## Key Questions To Research Next

1. Should the daily output be article-first or concept-first?
   - Default: article-first for the first version.

2. What counts as a "good economics interpretation"?
   - It should explain behavior, incentives, constraints, tradeoffs, or market structure.
   - It should avoid generic commentary that could fit any article.

3. How should concepts be stored?
   - Minimal first version: Markdown files under `docs/concepts/`.
   - Avoid building a database until retrieval/editing needs are real.

4. How should source articles enter this project?
   - Minimal first version: import/export JSON or Markdown from the existing WeChat project.
   - Avoid coupling this new project directly to the old project's database at the beginning.

5. What is the daily learning loop?
   - Pick articles.
   - Generate interpretations.
   - Review/save concept cards.
   - Optionally revisit old cards when a new article matches them.

## Suggested Skills

Use these in the next session:

1. `/grill-with-docs`
   - Best next step. The idea belongs to a repo and should be sharpened into durable docs before implementation.

2. `/prototype`
   - Use only if a question needs runnable exploration, such as comparing output formats or testing a small article-to-concept pipeline.

3. `/to-prd`
   - Use after the discussion stabilizes and the user wants a product requirements document.

4. `/to-issues`
   - Use only after a PRD exists and the work should be split into buildable slices.

5. `/teach`
   - Consider later if the project becomes a stateful learning workspace for economics concepts, not just a software product.

## Suggested First Discussion

Start by asking the user:

> 你每天打开这个产品时，最想先看到的是「今天这几件事可以用哪些经济学解释」，还是「今天学一个经济学概念，并用新闻举例」？

Recommended default:

Start with "today's events through economics", because it fits the user's existing article flow and keeps the first product loop simple.

## Constraints

- Keep the first version small.
- Do not build a full LMS, spaced repetition system, graph database, or plugin architecture yet.
- Do not tightly couple the new project to the old repo until the learning format is proven.
- Favor plain Markdown/JSON artifacts first.

## Current Status

No code has been written in `i-love-economics` yet.

This handoff is the first artifact.
