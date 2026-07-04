# PRD: Daily Economics WeChat Articles

Date: 2026-07-05

## Problem Statement

The user reads many WeChat official account articles every day and wants to turn yesterday's useful news, events, and business signals into publishable WeChat articles that explain the world through economics.

The current gap is not article collection. The user already has a separate WeChat article collection system. The gap is converting that article pool into a small number of high-quality economics explanations that are ready to review, publish, and later reuse as a personal economics knowledge base.

The user does not want a full course system, a learning-management product, or a complicated editorial platform in the first version. The first version must produce daily candidate articles with visible prompts, clear sources, fact-check signals, cover images, and simple manual publishing flow.

## Solution

Build an independent Dockerized daily pipeline that runs on `10.88.255.251`.

Each run reads yesterday's published articles from the existing `we-mp-rss` SQLite Docker volume, screens them with the local LLM gateway, groups related events only when they share the same economics question, and generates up to 3 complete publishable WeChat article candidates using DeepSeek.

Each candidate includes:

- A Markdown draft.
- A WeChat-copyable HTML draft.
- A local text-only cover image.
- Source metadata.
- A DeepSeek fact-check result.
- A knowledge-card patch that can be applied after publishing.

The user reviews candidates through a generated `index.html`, manually chooses what to publish, copies the selected article into the WeChat official account editor, uploads the cover image, and applies the knowledge-card patch only after publication.

## User Stories

1. As the article author, I want the system to review yesterday's WeChat article pool, so that I do not have to manually scan every source each morning.
2. As the article author, I want the system to ignore days with no good economics topic, so that I do not publish weak articles just to maintain output.
3. As the article author, I want up to 3 complete candidate articles per day, so that I can choose the strongest publishable article without reviewing an unbounded list.
4. As the article author, I want additional good-but-not-top-3 topics saved as summaries, so that potentially useful ideas are not lost.
5. As the article author, I want each topic to be selected because it explains real behavior, incentives, constraints, or tradeoffs, so that the output is economics interpretation rather than generic commentary.
6. As the article author, I want events merged only when they share the same economics question, so that each article has one clear argument.
7. As the article author, I want topic ranking to prioritize explanatory strength over raw popularity, so that the article teaches something meaningful.
8. As the article author, I want pure gossip, stance-only events, weak policy summaries, unsupported market moves, and disputed facts filtered out, so that review time is not wasted.
9. As the article author, I want titles to focus on real-world questions, so that WeChat readers are pulled in by a concrete problem.
10. As the article author, I want the economics concept introduced naturally inside the article and explicitly summarized near the end, so that the article does not feel like a classroom note.
11. As the article author, I want each article to have one core economics concept, so that readers remember one idea clearly.
12. As the article author, I want related concepts mentioned only lightly, so that the article stays readable.
13. As the article author, I want a reusable knowledge-card patch per article, so that published articles gradually build a personal economics knowledge base.
14. As the article author, I want knowledge cards applied only after publication, so that rejected drafts do not pollute the knowledge base.
15. As the article author, I want source titles, accounts, dates, and links retained, so that I can verify and cite the material.
16. As the article author, I want the generated article to summarize facts in its own words instead of copying large original passages, so that the value is interpretation rather than rewriting.
17. As the article author, I want DeepSeek to receive relevant source excerpts plus structured topic material, so that it has enough context to write accurately.
18. As the article author, I want original excerpts trimmed to relevant parts, so that prompts stay focused and costs stay controlled.
19. As the article author, I want local LLM screening to produce structured JSON, so that the pipeline can rank and validate topics reliably.
20. As the article author, I want broken model JSON retried once and then logged, so that one malformed response does not silently corrupt the run.
21. As the article author, I want DeepSeek to write final drafts, so that the prose quality is high enough for a public WeChat article.
22. As the article author, I want no automatic fallback from DeepSeek writing to local-model writing, so that draft quality does not become inconsistent.
23. As the article author, I want DeepSeek to fact-check the written draft once, so that risky claims are visible before publication.
24. As the article author, I want fact-check issues to be marked without blocking file generation, so that I can still decide manually.
25. As the article author, I want no separate search API in version one, so that fact checking stays simple.
26. As the article author, I want all prompts visible in repository files, so that I can inspect and edit the system behavior directly.
27. As the article author, I want a local text-only cover image, so that every candidate has a WeChat cover without needing image generation.
28. As the article author, I want no news photos, logos, people, or generated illustrations in version one, so that copyright and image quality issues do not slow the MVP.
29. As the article author, I want WeChat-copyable HTML with inline styles, so that copying into the official account editor keeps readable formatting.
30. As the article author, I want no in-article images in version one, so that the article pipeline remains reliable.
31. As the article author, I want an `index.html` for each run, so that candidate review is easy without building a web app.
32. As the article author, I want the index page to show score, concept, question, cover, sources, and fact-check status, so that I can quickly decide what to publish.
33. As the article author, I want the index page to avoid editing features, so that the first version does not become a web editor project.
34. As the article author, I want a rerun to avoid overwriting by default, so that reviewed or modified drafts are not lost accidentally.
35. As the article author, I want a force rerun option, so that late-arriving full content can be included intentionally.
36. As the article author, I want a command to rewrite one candidate, so that I can regenerate a single draft without rerunning the whole day.
37. As the article author, I want previous rewritten files backed up, so that I can recover the prior draft.
38. As the article author, I want the project deployed independently from the old WeChat project, so that this product can evolve without changing the collection system.
39. As the article author, I want the old `we-mp-rss` SQLite volume mounted read-only, so that this project can use source data without risking the collector.
40. As the article author, I want filesystem outputs instead of a database, so that runs are transparent and easy to debug.
41. As the article author, I want host cron to trigger the daily run, so that no scheduler service is needed yet.
42. As the article author, I want `.env` to hold endpoints and secrets, so that deployment stays simple.
43. As the article author, I want the daily workflow documented, so that running, reviewing, publishing, applying cards, rerunning, and rewriting are clear.

## Implementation Decisions

- The product is an independent daily article generation pipeline, not a web application.
- The pipeline runs on `10.88.255.251`.
- Deployment uses an independent Docker Compose project.
- The old `we-mp-rss` Docker volume is mounted read-only.
- The system reads the `we-mp-rss` SQLite database directly.
- The system does not read the old project's MySQL database.
- The system does not call the old project's API.
- The daily target date is yesterday by Beijing natural day.
- The run can be forced to regenerate a day when full content arrives late.
- Each run writes to a date-scoped filesystem directory.
- Existing run directories are not overwritten unless the user explicitly forces a rerun.
- Daily generation produces up to 3 complete candidates.
- Extra topics are saved as summaries, not full drafts.
- Candidate artifacts include Markdown, WeChat-copyable HTML, cover image, sources, fact check, and knowledge-card patch.
- The review surface is a generated static `index.html`.
- The index page is a preview and management entry, not an editor.
- The user manually publishes through the WeChat official account editor.
- The system never auto-publishes.
- Concept docs are updated only after publication through an explicit apply-card command.
- A rewrite command regenerates one candidate and backs up previous article files.
- Prompts are stored as visible Markdown files in the repository.
- Local LLM is used for article understanding, screening, grouping, scoring, and cover text.
- DeepSeek is used for final article writing and fact checking.
- DeepSeek writing failure does not fall back to local-model writing.
- Screening output is validated as minimal structured JSON.
- Invalid screening JSON is retried once, then logged as failed.
- DeepSeek fact checking compares draft claims with provided source excerpts.
- If the DeepSeek interface has built-in search, it may use it; the project will not integrate a separate search API in version one.
- Fact-check risks are shown to the user but do not prevent candidate files from being created.
- Cover images are text-only local images with title, date, and the column name `用经济学看昨天`.
- The first version does not use AI image generation.
- The first version does not include images inside the article body.
- Article HTML uses simple tags and inline styles for WeChat editor copying.
- The first version stores all outputs on the filesystem, not in a database.
- The first version uses host cron instead of a scheduler service.

## Testing Decisions

The highest useful test seam is the daily command behavior. Tests should exercise the pipeline from source articles to generated run artifacts while replacing external LLM calls with fake clients.

Good tests assert externally visible behavior:

- Given a small SQLite fixture with yesterday's articles, the daily command creates a run directory with expected artifacts.
- Given no passing topics, the daily command records no complete candidates.
- Given more than 3 passing topics, the daily command creates only 3 full candidates and records the rest as summaries.
- Given malformed screening JSON, the pipeline retries once and logs failure if still invalid.
- Given an existing run directory, the daily command does not overwrite it unless forced.
- Given a candidate path, the rewrite command backs up previous article files and writes replacements.
- Given a published candidate, the apply-card command creates or updates the matching concept doc.
- Given fact-check issues, the generated index shows a risky status and issue details.

Modules to test:

- The SQLite article reader with a small temporary database.
- The daily pipeline orchestration with fake local and DeepSeek clients.
- The screening JSON parser and validator.
- The run artifact writer.
- The static index generator.
- The WeChat HTML renderer.
- The cover generator.
- The fact-check result renderer.
- The apply-card command.
- The rewrite command.

No current test suite exists in this repo. Keep the first tests small and runnable through the Dockerized project or the same command environment.

## Out of Scope

- A full course system.
- A learning management system.
- A web UI.
- A browser-based editor.
- Automatic publishing to WeChat.
- Separate search API integration.
- Database storage for runs.
- Direct dependency on the old project's API or MySQL.
- AI image generation.
- Article body images.
- Multi-user workflows.
- Authentication.
- Scheduler service.
- Complex prompt registry or prompt versioning system.
- Automatic concept-card updates for unpublished candidates.
- Automatic rewriting of risky fact-check claims.

## Further Notes

The first version optimizes for a reliable daily habit: run the job, review candidates, publish manually, then apply the concept card for the published article.

The first version should stay boring. Files, Docker, visible prompts, and static HTML are enough. Add a web UI only after the daily file-based workflow proves painful in real use.
