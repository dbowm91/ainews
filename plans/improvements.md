# ainews improvement implementation plan

This file is intended as a handoff plan for a smaller implementation model. It assumes the current `ainews` codebase already contains the Flask/Celery/newsletter pipeline described in `README.md`, with the stronger implementation surface visible in `app.py`, `tasks/`, `services/`, `routes/`, `models/`, and `schemas/`.

The goal is not to rebuild the application. The goal is to add high-leverage, realistic improvements around editorial quality, source intelligence, pipeline operability, search, and observability while preserving the current architecture.

## Ground rules for implementation agents

Follow `AGENTS.md` first. In particular, keep production behavior fail-closed for security-sensitive checks, add tests for every behavior change, preserve clean layering where practical, and avoid broad rewrites unless explicitly called out here.

Do not change the public article-generation tone or prompts unless a task explicitly requires it. Most tasks below should be implemented as incremental services, models, admin/API endpoints, and tests.

Do not add autonomous write-capable subagent tools early. New subagent tools should be read-only unless an admin route or explicit human approval path exists.

When modifying Celery tasks, preserve `acks_late=True`, `task_reject_on_worker_lost=True`, retry behavior, task signature verification where currently used, and database rollback discipline.

When adding new database fields or tables, create migrations if this repo uses Flask-Migrate/Alembic for the affected deployment path. If migration scaffolding is not present or not straightforward, document the manual migration SQL in the PR and add model-level tests.

Before finishing any phase, run the local test suite and lint/type checks that are standard for this repo, typically:

```bash
python -m pytest
ruff check . --exclude .venv
mypy .
```

If some existing mypy errors are known legacy issues, report them without expanding their surface.

## Current relevant architecture summary

The public app is a Flask site with public feeds, article pages, tag/topic routes, RSS, sitemap, newsletter subscribe/unsubscribe/verify, short URLs, and share/newsletter click tracking.

The publishing pipeline is Celery-based and currently follows roughly:

```text
crawl -> extract -> select -> research -> write -> edit -> review|done
```

Important existing components:

- `tasks/crawl.py`: source crawl orchestration, Redis source locks, dedupe, dispatch to extraction.
- `tasks/extract.py`: content extraction, article creation, duplicate detection, citation creation, dispatch to selection.
- `tasks/select.py`: LLM selector with score/confidence and review routing.
- `tasks/research.py`: web search, web synthesis subagent, related articles, topic notes, trend memory, structured research brief, quality gate.
- `tasks/write.py`: structured draft generation, trend memory injection, degenerate draft gate.
- `tasks/edit.py`: contextualization subagent, final article generation, article versioning, validation, tag assignment, trend-memory proposal, webhook trigger.
- `services/llm/`: provider abstraction and circuit-breaker fallback.
- `services/search/`: web search providers, SQLite FTS, hybrid FTS/vector provider.
- `services/subagent/`: subagent runner, tool registry, tool middleware, and current context/search tools.
- `services/metrics.py`: Redis-backed counters/gauges/histograms plus Prometheus exposition.
- `routes/admin/api/`: health, pipeline, search analytics, config/source/article/webhook APIs.
- `models/`: article, citation, pipeline, newsletter, article metrics, topic notes, trend memory, webhooks, audit, search query, auth.

## Priority overview

Implement in this order unless there is a strong reason to split work differently:

1. Claim/citation verification and persisted quality reports.
2. Source intelligence and topic/source gap analysis.
3. Pipeline rescue/replay operator tooling.
4. Hybrid search exposure and embedding lifecycle cleanup.
5. Cost-aware LLM telemetry and routing policy groundwork.
6. Alerting on top of existing metrics/health checks.
7. Documentation cleanup.

The first phase is the most important. It directly reduces the main risk of an autonomous publishing system: plausible but insufficiently grounded output.

---

## Phase 1: Persisted editorial quality reports and citation verification

### Objective

Add a first-class quality-verification layer after the edit stage and before automatic publication. The system should persist structured quality findings, route questionable articles to review, and expose reports to admin/review surfaces.

### Existing basis

`services/quality.py` already defines `QualityScore`, lightweight quality signals, an LLM quality assessor, and primitive hallucination heuristics. `services/article_validation.py` already validates final article structure. `schemas/llm_responses.py` already models `ResearchBrief`, `KeyClaim`, `DirectQuote`, `ExternalSource`, `CondensedArticle`, and citations. `tasks/edit.py` currently performs structural validation and routes to review, but final grounding/claim verification is not persisted as an editorial artifact.

### Files likely to modify or add

- Add `models/quality.py` or extend an existing appropriate model module.
- Update `models/__init__.py` exports.
- Add `services/quality_report.py` or extend `services/quality.py` if the new code remains cohesive.
- Update `tasks/edit.py` after `article.final_article` is produced and before `_post_finalize_article()`.
- Add admin API route under `routes/admin/api/quality.py` or extend an existing article/review route.
- Register route import in `routes/admin/api/__init__.py` if adding a new module.
- Update templates/admin review page if there is a review template surface.
- Add tests under `tests/` for service logic, model persistence, and edit-stage routing.

### Data model

Create a durable quality report model. Suggested fields:

```python
class QualityReport(db.Model):
    __tablename__ = "quality_reports"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False, index=True)
    article_version_id = db.Column(db.Integer, db.ForeignKey("article_versions.id"), nullable=True, index=True)
    stage = db.Column(db.String(32), nullable=False, default="edit")
    overall_score = db.Column(db.Float, nullable=False, default=0.0)
    groundedness = db.Column(db.Float, nullable=True)
    coherence = db.Column(db.Float, nullable=True)
    completeness = db.Column(db.Float, nullable=True)
    safety = db.Column(db.Float, nullable=True)
    citation_score = db.Column(db.Float, nullable=True)
    claim_score = db.Column(db.Float, nullable=True)
    passed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    needs_review = db.Column(db.Boolean, nullable=False, default=True, index=True)
    findings = db.Column(db.JSON, nullable=False, default=list)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

If `metadata` is reserved or conventionally avoided in this repo, use `meta` or `metadata_json` consistently.

Findings should be a list of objects like:

```json
{
  "severity": "error|warning|info",
  "code": "unsupported_claim|missing_citation|unknown_citation_url|quote_mismatch|stale_date|unsafe_content|schema_error",
  "message": "Human readable finding",
  "field": "body|citations|key_points|headline|research_brief",
  "evidence": {"claim": "...", "source": "..."}
}
```

### Service behavior

Implement a deterministic quality-report builder that takes an `Article` and returns a typed result or a `QualityReport` instance ready to persist.

Suggested API:

```python
def build_quality_report(article: Article) -> QualityReportResult: ...
def persist_quality_report(article: Article, result: QualityReportResult) -> QualityReport: ...
def article_passes_quality(result: QualityReportResult, thresholds: QualityThresholds | None = None) -> bool: ...
```

Core checks:

1. Parse `article.final_article` as JSON. Reuse or call `validate_final_article()` so schema failures appear in the report.
2. Parse `article.research_brief` as `ResearchBrief` where possible.
3. Verify final article citations:
   - every final citation must have a URL unless it is explicitly marked as internal/db/original source;
   - every external citation URL should appear in `research_brief.external_sources`, `research_brief.key_claims.source`, original article URL, or existing `Citation` rows;
   - duplicate citation URLs should be normalized before scoring;
   - invalid or unsafe URL schemes should be findings.
4. Verify claims heuristically:
   - extract sentence-like claims from `body`, `tldr`, `why_it_matters`, `what_to_watch`, and `key_points`;
   - flag numeric/date/entity-heavy claims if no overlapping key claim/source text exists;
   - do not attempt perfect entailment; use conservative warnings, not automatic failures, except for obvious unsupported high-risk claims.
5. Verify direct quotes:
   - if final article includes quoted text, check whether the quote appears in `ResearchBrief.direct_quotes` or source text if available;
   - unknown quotes should be at least warning severity.
6. Compute scores:
   - combine existing `lightweight_quality_signals()` with citation/claim checks;
   - default thresholds can be conservative: fail on schema errors, empty/unknown citations, severe unsupported claims, or safety score below threshold.

### Edit-stage integration

In `tasks/edit.py`, after `article.final_article` is assigned and before `_handle_validation_and_routing()` or before `_post_finalize_article()`, run quality report generation.

Recommended flow:

```text
editor LLM returns final article
sanitize final article
create article version
assign tags
run structural validation
build and persist quality report
if quality report fails: route to review with last_error summary
else continue to publish/done or review rules already present
```

Avoid double-routing. If existing structural validation routes to review, still create a quality report if enough data exists.

### Admin/API exposure

Add endpoints:

```text
GET /api/v1/articles/<id>/quality
GET /api/v1/quality/recent?passed=false&limit=50
```

Return latest report and findings. Include score fields and a compact findings list.

If there is an article review page, display:

- pass/fail badge;
- overall score;
- citation score;
- claim score;
- findings grouped by severity;
- links to relevant citations where safe.

### Tests

Add tests covering:

- valid final article with matching citation passes;
- final citation URL not present in research/original citations creates warning or failure according to threshold;
- invalid final article JSON creates schema finding and fails;
- unsupported numeric/date-heavy claim creates finding;
- quote not in `direct_quotes` creates finding;
- edit task routes to review when quality report fails;
- API endpoint requires auth and returns expected report shape.

### Acceptance criteria

- Quality reports are persisted for newly edited articles.
- Failed quality reports route the article to `review` and set a concise `last_error`.
- Admin/API can retrieve latest quality report by article.
- Existing tests pass; new tests cover the major paths.
- The pipeline continues to publish articles that pass existing validation and the new quality gate.

---

## Phase 2: Source intelligence and source performance dashboard API

### Objective

Add source-level operational intelligence so operators can see which sources are high-signal, noisy, broken, duplicated, stale, or expensive.

### Existing basis

Sources already track health fields such as active state, consecutive failures, last success, disabled time, and last error. Crawl tasks log fetched/new counts and update source crawl state. Article records link back to sources and store pipeline status, impact score, timestamps, category/topics, and metrics.

### Files likely to modify or add

- Add `services/source_intelligence.py`.
- Add admin API route `routes/admin/api/source_intelligence.py` or extend `routes/admin/api/pipeline.py` / `sources.py`.
- Add tests for aggregation logic.
- Optionally add admin template enhancements after API is in place.

### Service behavior

Implement aggregation over a configurable time window:

```python
def get_source_performance(days: int = 7, limit: int | None = None) -> list[SourcePerformance]: ...
def get_topic_coverage(days: int = 7) -> dict: ...
def get_source_recommendations(days: int = 30) -> list[SourceRecommendation]: ...
```

Metrics per source:

- fetched count if available from `PipelineLog` or source stats;
- articles created;
- selected count;
- review count;
- published/done count;
- skipped count;
- failed count;
- average impact score;
- p50/p95 crawl-to-publish latency if timestamps allow;
- duplicate citation additions if measurable;
- extraction failure rate if stored;
- consecutive failure count and last error;
- last successful crawl;
- topic distribution.

If fetched counts are only available in logs and not cleanly queryable, start with article-derived metrics and source health. Do not overfit parsing freeform logs unless necessary.

Suggested output shape:

```json
{
  "source_key": "...",
  "name": "...",
  "active": true,
  "health": "ok|degraded|failing|inactive",
  "articles_created": 42,
  "published": 12,
  "review": 4,
  "skipped": 20,
  "failed": 1,
  "selection_rate": 0.38,
  "publish_rate": 0.29,
  "avg_impact_score": 62.1,
  "last_success_at": "...",
  "last_error": "...",
  "topics": {"ai": 12, "security": 6},
  "recommendations": ["high_noise", "low_recent_yield"]
}
```

### Admin/API exposure

Add:

```text
GET /api/v1/sources/performance?days=7
GET /api/v1/topics/coverage?days=30
GET /api/v1/sources/recommendations?days=30
```

Require auth. Clamp `days` to a safe range, for example 1 to 90.

### Tests

Create small in-memory DB fixtures with several sources and articles in different statuses. Test rates, sorting, clamping, and health labels.

### Acceptance criteria

- Operators can retrieve source performance via authenticated API.
- Metrics are computed from DB state without requiring live Celery/Redis.
- Failing/noisy/high-value source labels are deterministic and tested.

---

## Phase 3: Topic gap and source recommendation tool

### Objective

Use existing search analytics, topic config, source/article data, and trend memory to identify under-covered topics and candidate source gaps.

### Existing basis

`SearchQuery` exists and search analytics already exposes top and zero-result queries. Topic notes and trend memory exist. Topics are loaded from config. Articles have category/topics.

### Files likely to modify or add

- Add `services/topic_gap.py`.
- Add API route `routes/admin/api/topic_gap.py`.
- Optionally add read-only subagent tool after service is tested.
- Tests for gap scoring.

### Service behavior

Compute topic gaps from:

- zero-result search queries;
- topic article volume in last N days;
- topic publication velocity;
- topic average impact score;
- trend memory importance by topic;
- source coverage per topic;
- subscriber preferences by topic if easily queryable.

Output:

```json
{
  "topic": "security",
  "article_count_7d": 3,
  "article_count_30d": 8,
  "zero_result_queries": ["..."],
  "trend_memory_count": 4,
  "active_sources": 2,
  "gap_score": 0.72,
  "reason": "High search demand and trend memory, low recent publication volume."
}
```

Add a read-only subagent tool only after the service is stable:

```text
get_topic_gap_report(topics?: list[str], days?: int)
```

Register it in `services/subagent/tools.py` through a service-layer helper rather than direct DB logic, if practical.

### Acceptance criteria

- Authenticated API returns topic gap report.
- Gap score is deterministic and documented.
- Tests cover low-volume/high-demand, high-volume/low-demand, and no-data cases.

---

## Phase 4: Pipeline rescue/replay console API

### Objective

Allow an operator to re-run an article from a specific stage, inspect previous outputs, and avoid manual DB surgery when the pipeline produces bad or stuck states.

### Existing basis

There are pipeline stats, backlog, dead-letter stats, task status endpoints, `ArticleVersion`, review routing, retry-stuck tasks, and individual stage tasks. The missing piece is stage-level replay and operator-oriented history.

### Files likely to modify or add

- Add `services/pipeline_replay.py`.
- Add `routes/admin/api/replay.py` or extend `routes/admin/api/pipeline.py`.
- Possibly add fields to `ArticleVersion` only if necessary; prefer using existing version model first.
- Tests for status transitions and task dispatch.

### API design

Add endpoints:

```text
GET /api/v1/articles/<id>/pipeline/history
POST /api/v1/articles/<id>/pipeline/replay
POST /api/v1/articles/<id>/pipeline/restore-version
```

Replay request shape:

```json
{
  "stage": "select|research|write|edit",
  "provider_id": null,
  "model": null,
  "reason": "manual_replay_after_quality_failure"
}
```

Initial implementation may ignore provider/model override if the current pipeline does not support it cleanly. If ignored, return a warning field rather than silently pretending override worked.

Behavior:

- Verify article exists.
- Validate stage name.
- Create an article version before destructive modifications.
- Set pipeline status to the correct pre-stage status.
- Clear only downstream fields that must be regenerated.
- Dispatch the relevant task with `run_id` if available or create a new `PipelineRun` for manual replay.
- Audit-log the action if audit infrastructure is available.

Suggested field clearing:

- replay `select`: clear selector result, research brief, draft, final article, selected/published timestamps downstream.
- replay `research`: preserve selector result, clear research brief, draft, final article.
- replay `write`: preserve selector/research, clear draft/final.
- replay `edit`: preserve draft/research, clear final only.

Be conservative. Do not delete citations unless the task explicitly regenerates them.

### Acceptance criteria

- Authenticated replay endpoint dispatches correct task and updates status.
- Invalid stage returns 400.
- Replay creates an audit trail or article version record.
- Tests cover each replay stage and downstream field clearing.

---

## Phase 5: Expose and use hybrid search deliberately

### Objective

Make the existing hybrid search implementation an explicit feature for public/admin search and internal related-article retrieval.

### Existing basis

`services/search/hybrid.py` implements `hybrid_search()` with SQLite FTS and vector similarity, but the compatibility `search()` method delegates to FTS-only behavior.

### Files likely to modify or add

- `services/search/hybrid.py`
- `services/article.py` or related article service files.
- Public feed/search route if it currently handles `q`.
- Admin search API route.
- `tasks/embeddings.py`
- Tests for search behavior.

### Implementation steps

1. Add a clear service wrapper:

```python
def search_articles(query: str, *, mode: str = "fts", category: str | None = None, page: int = 1, per_page: int = 20) -> SearchPage: ...
```

2. Support `mode=fts|hybrid`.
3. Add safe fallback: if sentence-transformers unavailable or embeddings missing, hybrid mode should return FTS results plus a response flag like `vector_available=false`.
4. Add optional result metadata for admin: `fts_rank`, `vector_score`, `combined_score`.
5. Update public search carefully. Public pages should not expose confusing score internals unless useful.
6. Update related article retrieval to optionally use hybrid mode when embeddings exist.

### Embedding lifecycle

Currently embeddings can be backfilled by a scheduled task. Add incremental embedding generation when an article is finalized or published, but do not block publication if embedding generation fails.

Suggested behavior in `tasks/edit.py` after successful publish:

```python
try:
    enqueue or compute embedding for article.final_article
except Exception:
    logger.warning(...)
```

Prefer a small Celery task such as `generate_article_embedding(article_id)` rather than computing inline if sentence-transformer latency is meaningful.

### Acceptance criteria

- Public/admin search can request hybrid mode without breaking FTS mode.
- Hybrid mode gracefully falls back when embeddings are unavailable.
- New/edited published articles get embeddings without waiting for nightly backfill.
- Tests cover FTS fallback and hybrid scoring path with mocked embeddings.

---

## Phase 6: Cost-aware LLM telemetry groundwork

### Objective

Improve LLM telemetry so future routing can account for actual token usage, latency, failure rate, and approximate cost by role/stage/model.

### Existing basis

`services/llm/__init__.py` records provider success/failure and token/call metrics. `services/cost_tracker.py` estimates cost from aggregate token counters using a blended input/output ratio. Provider fallback and circuit breakers already exist.

### Files likely to modify or add

- `services/llm/base.py` and provider adapters if token usage is parsed there.
- `services/llm/__init__.py`
- `services/cost_tracker.py`
- `services/metrics.py` only if label format cannot support this already.
- Admin costs endpoint in `routes/admin/api/pipeline.py` or split to `routes/admin/api/costs.py`.
- Tests with mocked provider responses.

### Implementation steps

1. Extend provider result normalization to capture:
   - input tokens;
   - output tokens;
   - total tokens;
   - cached tokens if available;
   - latency milliseconds;
   - provider ID;
   - model;
   - role/stage;
   - article ID if available at call site.
2. Record separate metrics:

```text
llm.input_tokens{provider=...,model=...,stage=...}
llm.output_tokens{provider=...,model=...,stage=...}
llm.calls{provider=...,model=...,stage=...,status=success|failure}
llm.latency_ms histogram by provider/model/stage
```

3. Update `cost_tracker` to use input/output rates when available; keep blended fallback for legacy counters.
4. Add `GET /api/v1/costs?days=...&group_by=stage|model|provider` if feasible. If historical metrics are not retained beyond Redis TTL, document current-window limitations.

### Acceptance criteria

- Cost summary no longer depends exclusively on blended total-token estimates when input/output counters exist.
- Stage-level cost breakdown is available.
- Existing metrics consumers still work.

---

## Phase 7: Read-only subagent tool expansion

### Objective

Give research/edit/review subagents better read-only context without adding mutation risk.

### Existing basis

Current subagent tools include topic notes, related articles, trend memory, article lookup/search, source health, and web search.

### Add these tools after their services exist

- `get_source_performance(source_key?: str, days?: int)` backed by `services/source_intelligence.py`.
- `get_topic_gap_report(topics?: list[str], days?: int)` backed by `services/topic_gap.py`.
- `get_quality_report(article_id: int)` backed by the Phase 1 quality report service.
- `find_dedupe_candidates(title: str, url?: str, limit?: int)` backed by existing duplicate logic or a new service wrapper.
- `estimate_stage_cost(stage: str, model?: str)` backed by cost summary data.

### Constraints

Do not let tools directly mutate `Article`, `Source`, `TrendMemory`, `TopicNote`, or config files. All mutation remains admin/API/manual.

Try to avoid growing `services/subagent/tools.py` with more direct DB imports. Add service-layer helpers and keep tool functions thin.

### Acceptance criteria

- Tools are read-only.
- Tools are registered through the existing registry path.
- Tests validate tool output and error handling.
- Tool descriptions are concise and stage-aware.

---

## Phase 8: Alerting layer over metrics and health

### Objective

Convert existing health/metrics into actionable alert evaluations.

### Existing basis

`services/metrics.py` supports counters, gauges, histograms, and Prometheus output. Admin health endpoints expose app, DB, Redis, Celery, limiter, circuit breakers, cache, DNS cache, worker state, and task state.

### Files likely to modify or add

- Add `services/alerts.py`.
- Add `routes/admin/api/alerts.py`.
- Optionally integrate with existing webhook system for alert dispatch.
- Tests for alert rule evaluation.

### Alert rules

Initial deterministic rules:

- Celery has no workers.
- Redis unavailable.
- LLM circuit breaker open for primary provider/model.
- pipeline backlog above threshold.
- stuck article count above threshold.
- source consecutive failures above threshold.
- crawl produced zero new articles for N runs or N hours.
- quality gate failure rate above threshold.
- newsletter delivery failures above threshold.
- estimated cost above threshold for current window.

Suggested model:

```python
@dataclass
class Alert:
    code: str
    severity: Literal["info", "warning", "critical"]
    title: str
    message: str
    source: str
    created_at: datetime
    metadata: dict
```

Start with stateless evaluation from current DB/metrics. Persisting alert history can be a later step.

### API

```text
GET /api/v1/alerts
```

Return active alerts grouped by severity.

### Acceptance criteria

- Alert service can run without Celery workers.
- API requires auth.
- Tests cover healthy, warning, and critical states.

---

## Phase 9: Newsletter intelligence refinements

### Objective

Improve newsletter usefulness and operator visibility without overhauling the mailer.

### Existing basis

Newsletter schemas, subscriber preferences, scheduled generation, verification/welcome/unsubscribe flows, and click tracking already exist.

### Suggested incremental tasks

1. Add newsletter performance endpoint:

```text
GET /api/v1/newsletters/performance?days=30
```

Metrics:

- sent count;
- failed count;
- retry count;
- click count;
- top clicked articles;
- click-through by topic/newsletter type;
- subscriber count by newsletter type/topic preference.

2. Add subject-line A/B test support only if newsletter model already stores enough delivery metadata. If not, defer.
3. Add digest archive page for past newsletters if newsletters are already persisted with article associations.
4. Add per-topic cadence config only after performance data is visible.

### Acceptance criteria

- Operators can inspect newsletter performance.
- No changes break subscribe/unsubscribe/verification flows.
- Tests cover metrics aggregation.

---

## Phase 10: Documentation cleanup

### Objective

Make the repo easier for future agents and humans to work with.

### Files to update or add

- `README.md`
- `docs/pipeline.md`
- `docs/subagents.md`
- `docs/search.md`
- `docs/operations.md`
- Possibly `docs/quality.md` after Phase 1.

### README updates

Fix placeholder clone URLs. The current README uses `github.com/yourorg/ainews.git`; update to the actual repo path if this is intended for private/internal use, or use a neutral placeholder consistently.

Document current major features more accurately:

- multi-provider LLM pipeline;
- subagents/tool calling;
- quality gates/review routing;
- trend memory/topic notes;
- webhooks;
- hybrid search/embeddings if Phase 5 is complete;
- metrics/health/cost endpoints;
- admin API tokens and 2FA if externally relevant.

### New docs

`docs/pipeline.md` should describe every stage, state transitions, review routing, retry behavior, and how to replay/rescue articles.

`docs/subagents.md` should describe subagent config, current tools, how to add a tool, and constraints around read-only tools.

`docs/search.md` should describe FTS, hybrid vector search, embedding generation/backfill, and public/admin search behavior.

`docs/operations.md` should describe health endpoints, metrics, alerts, backups, Celery workers, Redis DB allocation, and common failure recovery.

`docs/quality.md` should describe the quality report model, scoring, citation verification rules, and review workflow.

### Acceptance criteria

- README no longer undersells or misstates the architecture.
- New docs match actual code paths and endpoint prefixes.
- Any newly added endpoint or service in this plan has at least a short operational note.

---

## Suggested small-model implementation order

A smaller model should not attempt all phases in one pass. Use this sequence:

1. Phase 1 model/service/tests only, no UI. Add `QualityReport`, quality report builder, and tests.
2. Wire Phase 1 into `tasks/edit.py` and add API endpoint.
3. Phase 2 source intelligence service/API/tests.
4. Phase 3 topic gap service/API/tests.
5. Phase 4 pipeline replay API/tests.
6. Phase 5 hybrid search wrapper and embedding lifecycle.
7. Phase 6 token/cost telemetry.
8. Phase 7 read-only subagent tools.
9. Phase 8 alerts.
10. Documentation.

Each pass should keep the diff small enough to review. If a pass requires schema migration, do that pass alone.

## Definition of done for the full initiative

- Articles have persisted quality reports and failed reports route to review.
- Operators can inspect source performance and topic gaps through authenticated APIs.
- Operators can replay a failed/stale article from a specific pipeline stage.
- Hybrid search is intentionally exposed and safely falls back to FTS.
- LLM cost telemetry separates input/output tokens when provider data allows.
- Alerts expose actionable current system failures/degradations.
- Subagent tools are expanded with read-only operational context.
- Documentation reflects the actual pipeline and operational controls.
- Existing public routes, newsletter subscription, RSS feeds, Celery pipeline, and admin auth continue to work.
