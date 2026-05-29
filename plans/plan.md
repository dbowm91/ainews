# AINews Consolidated Implementation Plan

**Status:** ACTIVE
**Last Updated:** 2026-05-29
**Source:** Consolidated from 15 architecture review files + improvements.md

---

## Overview

This plan consolidates findings from architecture reviews across all modules and the improvements roadmap. Items are organized into waves that can be executed in parallel by sub-agents.

**Previous work (2026-05-28):** Phases 1-8 of the original plan (bug fixes, doc corrections, signature fixes) are COMPLETE. This plan adds remaining bug fixes, documentation gaps, and future feature work.

---

## Wave 1: Remaining Bug Fixes (Parallel)

These are actual code bugs that should be fixed before documentation work. Each item can be assigned to a separate sub-agent.

| ID | Item | File | Priority | Verified |
|----|------|------|----------|----------|
| W1-1 | `SSRFSafeRedirectHandler.__call__` returns original request instead of redirect-modified request | `adapters/session.py:54` | MEDIUM | YES |
| W1-2 | `ProcessItemTask.topics` lacks `max_length` validator — API callers can submit unbounded lists | `schemas/tasks.py:99` | MEDIUM | YES |
| W1-3 | `overview.md` stale tool count: says "9 built-in tools" but actual is 14 | `architecture/overview.md:585` | LOW | YES |

**W1-1 details:** The `__call__` method validates the redirect URL via `validate_url_safe(location)` but then returns the original `request` object unchanged. Should return a new `PreparedRequest` with the redirect URL set, or `None` to skip. Compare with how `requests` library redirect handlers work.

**W1-2 details:** `ProcessItemTask.topics` at `schemas/tasks.py:99` is a `list[str]` with no `max_length` constraint. Other schemas like `SelectArticleTask` have `validate_topics` validators. Add a similar validator or `max_length` constraint.

**W1-3 details:** Update `architecture/overview.md:585` from "Tool registry (9 built-in tools)" to "Tool registry (14 built-in tools)".

---

## Wave 2: Documentation Corrections (Parallel)

All documentation items can be addressed in parallel. Group by target file.

### Group 2A: Models Documentation (`architecture/models.md`)

| ID | Item | Verified |
|----|------|----------|
| W2A-1 | Document `QualityReport` model (exists in `models/quality.py:10-51`) with all fields: `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings`, `meta` | YES |
| W2A-2 | Document `Webhook` model fields: `failure_count`, `last_triggered_at`, `last_success_at`, `last_failure_at`, `last_error` | YES |
| W2A-3 | Document `WebhookEvent` model (`models/webhook.py:32-49`) | YES |
| W2A-4 | Document `ArticleMetric` fields: `page_loads`, `newsletter_clicks`, `share_button_clicks`, `share_link_views`, `updated_at` | YES |
| W2A-5 | Document `models/utils.py` functions: `slugify`, `encode_short_url`, `decode_short_url` | YES |
| W2A-6 | Add missing index documentation for `Source.source_type`, `Source.active`, `TrendMemory.last_accessed_at`, `AuditLog` composite index, `ArticleVersion` unique constraint | YES |

### Group 2B: Schemas Documentation (`architecture/schemas.md`)

| ID | Item | Verified |
|----|------|----------|
| W2B-1 | Fix `SendEmailTask` claim — it DOES have an email validator (`schemas/tasks.py:65-70`). Remove "No email format validator" claim | YES |
| W2B-2 | Add `schemas/admin.py` to file inventory: `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams` | YES |
| W2B-3 | Add `schemas/llm.py` to file inventory: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig` | YES |
| W2B-4 | Document `ReviewConfig` schema (`schemas/pipeline.py:35-41`): `enabled: bool = False`, `auto_publish_threshold: Optional[int]` | YES |
| W2B-5 | Update `llm_responses.py` file inventory to list all 15 schemas (currently lists 11) | YES |

### Group 2C: Routes Documentation (`architecture/routes.md`)

| ID | Item | Verified |
|----|------|----------|
| W2C-1 | Add 6 missing API files to structure: `alerts.py`, `quality.py`, `replay.py`, `source_intelligence.py`, `topic_gap.py`, `newsletter.py` | YES |
| W2C-2 | Document undocumented endpoints: `/api/v1/alerts`, `/api/v1/sources/performance`, `/api/v1/topics/coverage`, `/api/v1/newsletters/performance`, `/api/v1/articles/<id>/quality`, `/api/v1/articles/<id>/pipeline/history`, `/api/v1/articles/<id>/pipeline/replay` | YES |
| W2C-3 | Fix unsubscribe route to show two handlers (`unsubscribe` GET + `unsubscribe_confirm` POST) | YES |

### Group 2D: Services Documentation (`architecture/services.md`)

| ID | Item | Verified |
|----|------|----------|
| W2D-1 | Add ~30 missing service files to architecture tree (`provider_base.py`, `degradation.py`, `prompts.py`, `tracing.py`, `redis_utils.py`, `subagent/`, `cost_tracker.py`, `quality_report.py`, `source_intelligence.py`, `topic_gap.py`, `pipeline_replay.py`, `alerts.py`, etc.) | YES |
| W2D-2 | Document `BaseProvider` and `ProviderManager` classes | YES |
| W2D-3 | Document `RedisCircuitBreaker` as default return from `get_breaker()` | YES |
| W2D-4 | Document `BaseLLMProvider.__init__(provider_id, config)` signature | YES |
| W2D-5 | Document `_retry_with_backoff()` method | YES |
| W2D-6 | Document `ResponseCache` and `ConfigCache` classes/methods | YES |

### Group 2E: Pipeline Documentation (`architecture/pipeline.md`)

| ID | Item | Verified |
|----|------|----------|
| W2E-1 | Update researcher temperature example from 0.4 to 0.0 | YES |
| W2E-2 | Document all write validation conditions: body length + empty `key_points` + empty `citations` | YES |
| W2E-3 | Document `build_quality_report()` routing in edit stage (`tasks/edit.py:378-419`) | YES |

### Group 2F: Subagent Documentation (`architecture/subagent.md`)

| ID | Item | Verified |
|----|------|----------|
| W2F-1 | Fix tool function signatures to match actual implementations (add `exclude_id`, `min_importance`, `max_age_days` params; note return types) | YES |
| W2F-2 | Update pipeline.yaml config example tool names: `article_lookup` → `get_article_by_id`, `article_search` → `search_articles` | YES |
| W2F-3 | Document `ToolSelector` and `StageAwareToolSelector` from `services/tool_selection.py` | YES |
| W2F-4 | Document `SubagentStageConfig` schema fields from `schemas/pipeline.py:93-105` | YES |

### Group 2G: Other Documentation

| ID | File | Item | Verified |
|----|------|------|----------|
| W2G-1 | `architecture/search-providers.md` | Fix config section name: `search:` → `search_providers:` | YES |
| W2G-2 | `architecture/search-providers.md` | Document SSRF protection in `services/search/session.py` | YES |
| W2G-3 | `architecture/llm-providers.md` | Document full `record_provider_success()` signature (add `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id`) | YES |
| W2G-4 | `architecture/llm-providers.md` | Document `chat_structured_batch()` and `BatchError` | YES |
| W2G-5 | `architecture/tasks.md` | Update task signatures to show `max_retries=CELERY_TASK_MAX_RETRIES` (configurable) | YES |
| W2G-6 | `architecture/tasks.md` | Document edit stage quality report gate as routing path to `review` | YES |
| W2G-7 | `architecture/prompts.md` | Fix template resolution reference from "subagent.py" to `services/subagent/prompt_templates.py` | YES |
| W2G-8 | `architecture/prompts.md` | Document 2 additional prompt template files: `prompts/subagent_research_synthesis.txt` and `prompts/subagent_edit_contextualization.txt` | YES |
| W2G-9 | `architecture/config.md` | Fix `config_utils.py` code sample to show actual `flask.current_app` usage | YES |
| W2G-10 | `architecture/infrastructure.md` | Fix `config_utils.py` code sample (same as W2G-9) | YES |
| W2G-11 | `architecture/overview.md` | Update beat schedule to clarify UTC timezone (Celery uses UTC, `NewsletterConfig.timezone` is display-only) | YES |
| W2G-12 | `architecture/utils.md` | Document `parse_date()` timezone handling (naive datetimes get `timezone.utc` appended) | YES |

---

## Wave 3: Feature Enhancements (Sequential — from improvements.md)

These phases have dependencies and should be executed in order. Each phase can have parallel sub-tasks within it.

### Phase 3.1: Persisted Quality Reports and Citation Verification

**Status:** PARTIALLY COMPLETE — `QualityReport` model exists (`models/quality.py`), quality report gate exists in `tasks/edit.py:378-419`, `build_quality_report` and `persist_quality_report` exist in `services/quality_report.py`. Admin API exists at `routes/admin/api/quality.py`.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.1-1 | Verify `services/quality.py` has complete citation verification logic | `services/quality.py` |
| W3.1-2 | Ensure API endpoints (`GET /api/v1/articles/<id>/quality`, `GET /api/v1/quality/recent`) work correctly | `routes/admin/api/quality.py` |
| W3.1-3 | Add tests for quality report builder, persistence, and edit-stage routing | `tests/` |
| W3.1-4 | Verify acceptance criteria: failed quality reports route to `review` with concise `last_error` | Integration test |

### Phase 3.2: Source Intelligence and Performance Dashboard API

**Status:** PARTIALLY COMPLETE — `services/source_intelligence.py` exists, `routes/admin/api/source_intelligence.py` exists.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.2-1 | Verify `get_source_performance()`, `get_topic_coverage()`, `get_source_recommendations()` implementations | `services/source_intelligence.py` |
| W3.2-2 | Verify API endpoints: `GET /api/v1/sources/performance`, `GET /api/v1/topics/coverage`, `GET /api/v1/sources/recommendations` | `routes/admin/api/source_intelligence.py` |
| W3.2-3 | Add tests for aggregation logic | `tests/` |

### Phase 3.3: Topic Gap and Source Recommendation Tool

**Status:** PARTIALLY COMPLETE — `services/topic_gap.py` exists, `routes/admin/api/topic_gap.py` exists.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.3-1 | Verify `get_topic_gap_report()` service implementation | `services/topic_gap.py` |
| W3.3-2 | Verify read-only subagent tool `get_topic_gap_report` is registered | `services/subagent/tools.py:451` |
| W3.3-3 | Add tests for gap scoring | `tests/` |

### Phase 3.4: Pipeline Rescue/Replay Console API

**Status:** PARTIALLY COMPLETE — `routes/admin/api/replay.py` exists.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.4-1 | Verify `GET /api/v1/articles/<id>/pipeline/history` endpoint | `routes/admin/api/replay.py` |
| W3.4-2 | Verify `POST /api/v1/articles/<id>/pipeline/replay` endpoint with stage, provider_id, model, reason | `routes/admin/api/replay.py` |
| W3.4-3 | Verify `POST /api/v1/articles/<id>/pipeline/restore-version` endpoint | `routes/admin/api/replay.py` |
| W3.4-4 | Add tests for replay stage dispatch and downstream field clearing | `tests/` |

### Phase 3.5: Hybrid Search Exposure

**Status:** PARTIALLY COMPLETE — `services/search/hybrid.py` exists with `search_articles()` (line 329).

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.5-1 | Add `search_articles(query, mode="fts|hybrid", ...)` service wrapper | `services/search/hybrid.py` or `services/article.py` |
| W3.5-2 | Ensure graceful fallback when sentence-transformers unavailable | `services/search/hybrid.py` |
| W3.5-3 | Add incremental embedding generation on article finalization | `tasks/edit.py` |
| W3.5-4 | Update public/admin search to support hybrid mode | `routes/public/feeds.py`, `routes/admin/api/search.py` |
| W3.5-5 | Add tests for FTS fallback and hybrid scoring | `tests/` |

### Phase 3.6: Cost-Aware LLM Telemetry

**Status:** NOT STARTED — `services/cost_tracker.py` exists with basic cost estimation.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.6-1 | Extend provider result normalization to capture `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms` | `services/llm/base.py`, `services/llm/__init__.py` |
| W3.6-2 | Add separate metrics: `llm.input_tokens`, `llm.output_tokens`, `llm.calls`, `llm.latency_ms` | `services/metrics.py` |
| W3.6-3 | Update `cost_tracker` to use input/output rates when available | `services/cost_tracker.py` |
| W3.6-4 | Add `GET /api/v1/costs` endpoint | `routes/admin/api/pipeline.py` or new `routes/admin/api/costs.py` |
| W3.6-5 | Add tests with mocked provider responses | `tests/` |

### Phase 3.7: Read-Only Subagent Tool Expansion

**Status:** PARTIALLY COMPLETE — 5 tools already registered (get_topic_gap_report, get_source_performance, get_quality_report, find_dedupe_candidates, estimate_stage_cost).

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.7-1 | Verify all 14 tools are registered and functional | `services/subagent/tools.py` |
| W3.7-2 | Ensure all tools are read-only (no mutation of Article, Source, TrendMemory, etc.) | `services/subagent/tools.py` |
| W3.7-3 | Add tests for tool output and error handling | `tests/` |

### Phase 3.8: Alerting Layer

**Status:** NOT STARTED — `routes/admin/api/alerts.py` exists but may be a stub.

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.8-1 | Implement `services/alerts.py` with deterministic alert rules | New file |
| W3.8-2 | Implement `GET /api/v1/alerts` endpoint | `routes/admin/api/alerts.py` |
| W3.8-3 | Alert rules: no workers, Redis unavailable, circuit breaker open, backlog threshold, stuck articles, source failures, quality gate failures, cost threshold | `services/alerts.py` |
| W3.8-4 | Add tests for alert rule evaluation | `tests/` |

### Phase 3.9: Newsletter Intelligence

**Status:** NOT STARTED

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.9-1 | Add `GET /api/v1/newsletters/performance` endpoint | `routes/admin/api/newsletter.py` |
| W3.9-2 | Metrics: sent, failed, retry, click count, top clicked articles, click-through by topic | `routes/admin/api/newsletter.py` |
| W3.9-3 | Add tests for metrics aggregation | `tests/` |

### Phase 3.10: Documentation Cleanup

**Remaining work:**

| ID | Item | Files |
|----|------|-------|
| W3.10-1 | Update README.md: fix placeholder clone URLs, document features accurately | `README.md` |
| W3.10-2 | Create `docs/pipeline.md`: stage descriptions, state transitions, review routing, retry behavior, replay/rescue | New file |
| W3.10-3 | Create `docs/subagents.md`: subagent config, tools, how to add tools, read-only constraints | New file |
| W3.10-4 | Create `docs/search.md`: FTS, hybrid vector search, embedding generation/backfill, public/admin search | New file |
| W3.10-5 | Create `docs/operations.md`: health endpoints, metrics, alerts, backups, Celery workers, Redis DB allocation | New file |
| W3.10-6 | Create `docs/quality.md`: quality report model, scoring, citation verification, review workflow | New file |

---

## Execution Strategy

### Parallelization Map

```
Wave 1 (Bug Fixes)     ──┬── W1-1, W1-2, W1-3 can run in parallel
                          │
Wave 2 (Doc Fixes)     ──┼── Groups 2A-2G can all run in parallel
                          │   Each group targets different architecture/*.md files
                          │
Wave 3 (Features)      ──┴── Phases 3.1-3.10 run sequentially
                             But within each phase, sub-tasks can parallelize
```

### Recommended Sub-Agent Distribution

**Batch 1 (Wave 1 + Wave 2 Groups):**
- Agent A: W1-1 (SSRF handler bug) + W1-2 (schema validator) + W1-3 (tool count)
- Agent B: Group 2A (models.md)
- Agent C: Group 2B (schemas.md)
- Agent D: Group 2C (routes.md)
- Agent E: Group 2D (services.md)

**Batch 2 (Wave 2 Groups continued):**
- Agent F: Group 2E (pipeline.md)
- Agent G: Group 2F (subagent.md)
- Agent H: Group 2G (all other docs)

**Batch 3 (Wave 3 early phases):**
- Agent I: Phase 3.1 (quality reports) — verify existing implementation
- Agent J: Phase 3.2 (source intelligence) — verify existing implementation
- Agent K: Phase 3.3 (topic gap) — verify existing implementation
- Agent L: Phase 3.4 (pipeline replay) — verify existing implementation

---

## Notes

- **Previously completed work:** Phases 1-8 of the original plan (bug fixes, doc corrections, signature fixes) were completed on 2026-05-28. See git history for details.
- **APIAdapter/WebAdapter close() Design:** These adapters intentionally have no-op `close()` because they share the global session. RSSAdapter owns its own session and closes it properly. This is BY DESIGN.
- **utils/url.py and services/url.py Duplication:** Intentional for layering — `utils/url.py` is for adapters, `services/url.py` is for services with config support.
- **DeepSeek is NOT a search provider:** DeepSeek is only a regex pattern in `services/trend_detector.py` and `adapters/base.py`. Do NOT list it as a search provider.
- **SubagentConfig has no top-level `enabled` field:** The `enabled` field is on `SubagentStageConfig`, not `SubagentConfig`.
- **Config cache is two-tier:** L1 (in-memory, 500 entries) + L2 (Redis, DB 1).
- **Limiter uses Redis DB 15:** Not DB 0 or DB 2.
- **PipelineLog uses `meta` not `metadata`:** Due to SQLAlchemy reserved name restriction.
- **Tool count is 14:** 12 context tools + 2 search tools (verified in `services/subagent/tools.py:306-603`).
- **QualityReport already exists:** `models/quality.py` with full field set, gate in `tasks/edit.py:378-419`.
- **Many features partially implemented:** Phases 3.1-3.4, 3.7 have existing code — verify and complete rather than build from scratch.

---

*Plan consolidated: 2026-05-29*
*All claims verified against codebase on 2026-05-29*
