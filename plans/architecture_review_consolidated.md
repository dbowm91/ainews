# Architecture Review: Consolidated Findings

**Created:** 2026-05-29
**Status:** COMPLETE
**Purpose:** Aggregated findings from all 15 architecture document reviews (7 subagents)

---

## Summary

| Category | HIGH | MEDIUM | LOW | Total |
|----------|------|--------|-----|-------|
| Incorrect Claims | 6 | 8 | 7 | 21 |
| Bugs Found | 2 | 4 | 7 | 13 |
| Stale Content | 4 | 3 | 3 | 10 |
| Improvements | 5 | 14 | 20 | 39 |

---

## HIGH Priority Findings (Action Required)

### BUG-1: Missing Article import in routes/admin/api/replay.py
- **File:** `routes/admin/api/replay.py:21`
- **Issue:** `get_pipeline_history()` uses `Article` without importing it. Will cause `NameError` at runtime.
- **Fix:** Add `from models import Article` at module level or inside the function.
- **Source:** review_routes.md

### BUG-2: ResponseCache.get_or_set() leaks pubsub connections
- **File:** `services/cache.py:172-183`
- **Issue:** When `set(nx=True)` fails, a `pubsub` object is created and subscribed but `pubsub.close()` is never called — only `unsubscribe()`. Leaks Redis pubsub connections.
- **Fix:** Add `pubsub.close()` in the finally block (compare with `ModelLimiter.acquire()` at `services/limiter.py:81-85`).
- **Source:** review_services.md

### CLAIM-1: overview.md claims "PostgreSQL (prod)" but no PostgreSQL exists
- **File:** `architecture/overview.md:49`
- **Issue:** Tech stack lists "SQLite (WAL) / PostgreSQL (prod)" but no PostgreSQL configuration, driver, or connection string exists anywhere in the codebase.
- **Fix:** Remove PostgreSQL reference or mark as "planned".
- **Source:** review_overview.md

### CLAIM-2: routes.md claims GET /articles list endpoint exists but it doesn't
- **File:** `architecture/routes.md:107,305`
- **Issue:** Documentation claims `GET /articles` returns a list of articles. No such endpoint exists.
- **Fix:** Remove the claim or implement the endpoint.
- **Source:** review_routes.md

### CLAIM-3: services.md ModelLimiter interface is entirely wrong
- **File:** `architecture/services.md:182-198`
- **Issue:** All three method signatures are wrong:
  - `acquire(slots=1, timeout=30)` → actual: `acquire(provider_id, model, max_concurrent, timeout=300)`
  - `release(slots=1)` → actual: `release(provider_id, model, timeout=300)`
  - `get_active()` → actual: `get_active(provider_id, model)`
- **Fix:** Update all signatures to match the provider/model-aware interface.
- **Source:** review_services.md

### CLAIM-4: search-providers.md has wrong Google env var names
- **File:** `architecture/search-providers.md:86-87`
- **Issue:** Doc says `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX`. Actual is `GOOGLE_API_KEY`/`GOOGLE_CSE_ID` (in `providers.yaml:137-138`).
- **Fix:** Update env var names.
- **Source:** review_search_providers.md

### CLAIM-5: subagent.md claims 9 tools but 14 exist
- **File:** `architecture/subagent.md:42-52`
- **Issue:** 5 tools missing from documentation: `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`.
- **Fix:** Add missing tools to documentation.
- **Source:** review_subagent.md

### CLAIM-6: subagent.md pipeline.yaml config example has wrong tool names
- **File:** `architecture/subagent.md:256-263`
- **Issue:** References `article_lookup` and `article_search` which don't exist. Should be `get_article_by_id` and `search_articles`.
- **Fix:** Update tool names in example.
- **Source:** review_subagent.md

---

## MEDIUM Priority Findings

### CLAIM-7: pipeline.md selector routing mismatch
- **File:** `architecture/pipeline.md:77`
- **Issue:** Doc says `selected=True, score < min_score` routes to `review` or `discard`. Code routes ALL such cases to `SKIPPED`.
- **Fix:** Update documentation to reflect actual behavior (routes to `skipped`).
- **Source:** review_pipeline.md

### CLAIM-8: pipeline.md write validation incomplete
- **File:** `architecture/pipeline.md:101`
- **Issue:** Doc says "If body < 500 chars, marks for review" but `_is_degenerate_write()` also checks empty `key_points` and empty `citations`.
- **Fix:** Document all three conditions.
- **Source:** review_pipeline.md

### CLAIM-9: tasks.md task signatures show hardcoded max_retries=3
- **File:** `architecture/tasks.md:69,80,109,119,130,141,153`
- **Issue:** All task signatures show `max_retries=3` but code uses `CELERY_TASK_MAX_RETRIES` (configurable).
- **Fix:** Note that max_retries is configurable via env var.
- **Source:** review_tasks.md

### CLAIM-10: schemas.md SendEmailTask has email validator (doc says it doesn't)
- **File:** `architecture/schemas.md:358`
- **Issue:** Doc claims no email validator on SendEmailTask. Code has `validate_email` at `schemas/tasks.py:65-70`.
- **Fix:** Remove the incorrect note.
- **Source:** review_schemas.md

### CLAIM-11: search-providers.md config section name wrong
- **File:** `architecture/search-providers.md:147-161`
- **Issue:** Doc shows config under `search:` key. Actual is `search_providers:` (plural).
- **Fix:** Update section name.
- **Source:** review_search_providers.md

### CLAIM-12: infrastructure.md and config.md code sample references non-existent function
- **File:** `architecture/infrastructure.md:441-443`, `architecture/config.md:438-443`
- **Issue:** Code sample shows `from celery_support import get_current_app` but this function doesn't exist. Actual code uses `flask.current_app`.
- **Fix:** Update code sample to use actual implementation.
- **Source:** review_infrastructure.md, review_config.md

### CLAIM-13: llm-providers.md record_provider_success signature incomplete
- **File:** `architecture/llm-providers.md:273-279`
- **Issue:** Doc shows simplified signature. Missing `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id` params.
- **Fix:** Document full signature.
- **Source:** review_llm_providers.md

### CLAIM-14: prompts.md template resolution references non-existent "subagent.py"
- **File:** `architecture/prompts.md:167`
- **Issue:** Doc says templates are in `subagent.py`. Actual location is `services/subagent/prompt_templates.py`.
- **Fix:** Update file reference.
- **Source:** review_prompts.md

### BUG-3: services.md ConfigCache._import_class allows arbitrary schemas.* imports
- **File:** `services/config_cache.py:58-73`
- **Issue:** Allows importing any class from any `schemas.*` module based on a string stored in Redis. Potential security concern.
- **Priority:** MEDIUM
- **Source:** review_services.md

### BUG-4: ModelLimiter cleanup_stale_slots() could release slots for still-running tasks
- **File:** `services/limiter.py:141-161`
- **Issue:** Deletes limiter keys with TTL 0-60s if count > 0. Could release slots for tasks near TTL expiry.
- **Priority:** MEDIUM
- **Source:** review_services.md

### IMP-1: Missing models: QualityReport, Webhook fields, ArticleMetric fields
- **Files:** `models/quality.py`, `models/webhook.py`, `models/newsletter.py`
- **Issue:** Several models and their fields are undocumented.
- **Source:** review_models.md

### IMP-2: Missing schema files: admin.py, llm.py
- **Files:** `schemas/admin.py`, `schemas/llm.py`
- **Issue:** Two schema files with 11 total schemas not documented.
- **Source:** review_schemas.md

### IMP-3: routes.md missing 6 API files and 12+ endpoints
- **Files:** `routes/admin/api/alerts.py`, `quality.py`, `replay.py`, `source_intelligence.py`, `topic_gap.py`, `newsletter.py`
- **Issue:** Significant undocumented API surface.
- **Source:** review_routes.md

### IMP-4: services.md architecture tree missing ~30 files
- **File:** `architecture/services.md:8-41`
- **Issue:** Many service files exist but are not in the architecture tree.
- **Source:** review_services.md

---

## LOW Priority Findings

### CLAIM-15: models.md Newsletter↔Subscriber relationship direction is wrong
- **Source:** review_models.md

### CLAIM-16: utils.md format_date() omits singular "1 hour ago"
- **Source:** review_utils.md

### CLAIM-17: llm-providers.md health_check() is inherited from BaseProvider, not BaseLLMProvider
- **Source:** review_llm_providers.md

### CLAIM-18: tasks.md _should_route_to_review() documented as public but is private
- **Source:** review_tasks.md

### CLAIM-19: adapters.md _classify_topics parameter naming misleading
- **Source:** review_adapters.md

### CLAIM-20: overview.md version claims may be stale
- **Source:** review_overview.md

### CLAIM-21: pipeline.md newsletter lock idempotency TTL undocumented
- **Source:** review_pipeline.md

### BUG-5: subagent.md run_subagent() has duplicated finalization logic
- **Source:** review_subagent.md

### BUG-6: subagent.md _retry_with_backoff lacks jitter
- **Source:** review_subagent.md

### BUG-7: services.md race condition in ResponseCache.get() L1 check
- **Source:** review_services.md

### BUG-8: services.md trend_memory timezone mixing
- **Source:** review_services.md

### STALE-1: prompts.md subagent task templates comment implies more exist
- **Source:** review_prompts.md

### STALE-2: tasks.md local _degrade_and_advance claim is stale
- **Source:** review_tasks.md

### STALE-3: config.md missing celery_support.py from Key Files
- **Source:** review_config.md

---

## Cross-Document Inconsistencies

1. **Redis DB allocation:** infrastructure.md and overview.md both document DB 0, 1, 15. Config.md mentions `CELERY_RESULT_BACKEND` uses DB 1 (shared with config cache). Not冲突 but should be clarified.

2. **Pipeline.yaml config examples:** pipeline.md, subagent.md, and config.md all show pipeline.yaml examples that differ from actual config values (temperature, tool names).

3. **Tool count discrepancy:** subagent.md claims 9 tools, actual is 14. This affects pipeline.yaml configuration examples.

4. **ModelLimiter interface:** services.md shows a simplified interface, but AGENTS.md and the actual code show a provider/model-aware interface. The AGENTS.md version is correct.

---

## Recommended Action Plan

### Immediate (HIGH priority)
1. Fix `routes/admin/api/replay.py` missing Article import (BUG-1)
2. Fix `services/cache.py` pubsub leak (BUG-2)
3. Remove PostgreSQL claim from overview.md (CLAIM-1)
4. Remove fake GET /articles endpoint from routes.md (CLAIM-2)
5. Update services.md ModelLimiter interface (CLAIM-3)
6. Fix search-providers.md Google env vars (CLAIM-4)
7. Update subagent.md tool count and names (CLAIM-5, CLAIM-6)

### Short-term (MEDIUM priority)
8. Update pipeline.md selector routing documentation (CLAIM-7)
9. Update pipeline.md write validation docs (CLAIM-8)
10. Note configurable max_retries in tasks.md (CLAIM-9)
11. Fix schemas.md SendEmailTask note (CLAIM-10)
12. Fix search-providers.md config section name (CLAIM-11)
13. Fix code samples in infrastructure.md and config.md (CLAIM-12)
14. Document full record_provider_success signature (CLAIM-13)
15. Fix prompts.md template resolution reference (CLAIM-14)
16. Document missing models, schemas, routes, and services files

### Future (LOW priority)
17. Fix minor documentation inaccuracies
18. Document additional utility functions and patterns
19. Add missing template and file documentation
