# Architecture Review - Consolidated Findings

**Reviewed:** 2026-05-31
**Documents Reviewed:** 15
**Status:** COMPLETE

---

## Executive Summary

The architecture documentation is highly accurate overall, with 863 verified claims across 15 documents. However, 41 incorrect claims were identified (2 HIGH, 10 MEDIUM, 29 LOW), along with 22 bugs (2 HIGH, 8 MEDIUM, 12 LOW). The most critical issues include wrong return types for `propose_trend_memory`, incorrect degradation behavior documentation, a missing `experiments` field on `PipelineRootConfig`, and several tasks missing `max_retries`. The documentation should prioritize fixing HIGH-severity bugs and correcting the misleading degradation behavior table.

---

## Aggregate Statistics

| Document | Verified | Incorrect | Bugs | Improvements | Stale |
|----------|----------|-----------|------|--------------|-------|
| models.md | 42 | 6 | 6 (0H, 1M, 5L) | 7 | 0 |
| schemas.md | 58 | 6 | 3 (1H, 1M, 1L) | 7 | 0 |
| adapters.md | 48 | 3 | 1 (0H, 1M, 0L) | 5 | 3 |
| utils.md | 42 | 0 | 0 | 5 | 1 |
| llm_providers.md | 32 | 6 | 0 | 6 | 2 |
| search_providers.md | 28 | 3 | 0 | 7 | 2 |
| subagent.md | 35 | 4 | 0 | 9 | 2 |
| pipeline.md | 38 | 6 | 1 (0H, 1M, 0L) | 5 | 2 |
| tasks.md | 35 | 5 | 3 (0H, 2M, 1L) | 6 | 2 |
| prompts.md | 22 | 3 | 1 (0H, 0M, 1L) | 5 | 2 |
| infrastructure.md | 68 | 2 | 3 (0H, 0M, 3L) | 5 | 1 |
| config.md | 92 | 0 | 1 (0H, 1M, 0L) | 7 | 1 |
| overview.md | 138 | 0 | 1 (0H, 0M, 1L) | 5 | 0 |
| routes.md | 47 | 2 | 1 (0H, 0M, 1L) | 4 | 1 |
| services.md | 38 | 3 | 1 (1H, 0M, 0L) | 5 | 2 |
| **TOTAL** | **863** | **41** | **22 (2H, 8M, 12L)** | **82** | **17** |

---

## Bugs by Severity

### HIGH Severity
| # | Document | Description | Location | Evidence |
|---|----------|-------------|----------|----------|
| 1 | services.md | `propose_trend_memory` return type is `SubagentResponse`, not `list[TrendMemory]` — callers expecting list will fail at runtime | `services/trend_memory.py:217` | Returns `SubagentResponse(synthesis=..., used_fallback=..., fallback_stages=[])` |
| 2 | schemas.md | `PipelineRootConfig.experiments` field undocumented — functional field used by A/B experiment system | `schemas/pipeline.py:167` | `experiments: dict = Field(default_factory=dict)` exists, referenced in `pipeline.yaml:265-292` |

### MEDIUM Severity
| # | Document | Description | Location | Evidence |
|---|----------|-------------|----------|----------|
| 1 | pipeline.md | "research disabled: Article goes directly to `writing`" — actually routes through `_finalize()` which goes to REVIEW/DONE | `tasks/pipeline.py:260-267` | `_finalize()` with `skip_next="finalize"` routes to REVIEW or DONE, not WRITING |
| 2 | pipeline.md | "write disabled: Article goes directly to `editing`" — actually routes through `_finalize()` which goes to REVIEW/DONE | `tasks/pipeline.py:260-267` | Same as above |
| 3 | models.md | Missing `ArticleVersion` model documentation — 8 fields + unique constraint not documented | `models/pipeline.py:63-91` | Has `article_id`, `version_number`, `final_article`, `original_ai_article`, `source_fields`, `change_reason`, `changed_by`, `created_at` + unique constraint |
| 4 | schemas.md | `RawItem` schema undocumented — used by all adapters | `schemas/item.py:9-19` | 10 fields: `source_id`, `external_id`, `title`, `url`, `author`, `published_at`, `text_content`, `raw_score`, `raw_metadata`, `topics` |
| 5 | tasks.md | Stage transitions table incomplete — missing SELECTING, WRITTEN stages and PENDING→RESEARCHING | `constants.py:53-63` | Missing: PENDING→RESEARCHING, SELECTING→SELECTED, WRITTEN→EDITING |
| 6 | services.md | `chat_structured` signature outdated — missing `max_validation_retries` and `stage` params, includes non-existent `**kwargs` | `services/llm/base.py:217-227` | Actual params: `max_validation_retries: int = 2, stage: str = ""`, returns `T` (TypeVar) |
| 7 | services.md | Content extractor "raw HTML with boilerplate removal" fallback claim is false | `services/content_extractor.py:123` | Returns `ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)` — no raw HTML extraction |
| 8 | search_providers.md | YAML example shows completely different structure than actual `providers.yaml` | `providers.yaml:127-150` | Doc shows nested `default:` + `providers:` dict; actual is flat list with separate `default_search_provider:` key |

### LOW Severity
| # | Document | Description | Location | Evidence |
|---|----------|-------------|----------|----------|
| 1 | models.md | TopicNote `topic` field missing `index=True` in doc | `models/context.py:12` | Actual: `index=True` |
| 2 | models.md | TrendMemory `topic` field missing `nullable=False, index=True` in doc | `models/context.py:31` | Actual: `nullable=False, index=True` |
| 3 | models.md | AdminUser `password_hash` missing `nullable=False` in doc | `models/auth.py:36` | Actual: `nullable=False` |
| 4 | models.md | AdminUser `backup_codes` missing `nullable=True` in doc | `models/auth.py:39` | Actual: `nullable=True` |
| 5 | models.md | TrendMemory `last_accessed_at` missing `nullable=True, index=True, onupdate=` in doc | `models/context.py:40-44` | Actual has `nullable=True, index=True, onupdate=...` |
| 6 | models.md | Missing `Citation` model documentation | `models/article.py:86-100` | Fields: `article_id`, `url`, `title`, `author`, `context`, `position` |
| 7 | models.md | Missing `Tag` model documentation | `models/tag.py:24-33` | Fields: `name`, `slug`, `created_at` |
| 8 | models.md | Missing `AuditLog` model documentation | `models/audit.py:8-24` | Fields: `action`, `category`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at` |
| 9 | models.md | Missing `ApiToken` model documentation | `models/auth.py:8-28` | Fields: `token_hash`, `token_prefix`, `name`, `created_at`, `last_used_at`, `expires_at` |
| 10 | models.md | Missing `ShareConfig` model documentation | `models/share.py:6-18` | Fields: `platform_key`, `label`, `url_template`, `icon_name`, `active`, `sort_order` |
| 11 | schemas.md | `WebhookCreate` and `WebhookResponse` schemas undocumented | `schemas/webhook.py:10-27` | Used by webhook API routes |
| 12 | tasks.md | `generate_daily_newsletters` lacks `max_retries` — could retry indefinitely | `tasks/newsletter.py:476-487` | Has `autoretry_for` but no `max_retries` parameter |
| 13 | tasks.md | `retry_stuck` lacks `max_retries` | `tasks/retry.py:67-77` | Has `autoretry_for` but no `max_retries` |
| 14 | tasks.md | `publish_scheduled_articles` lacks `max_retries` | `tasks/scheduler.py:10` | Has `autoretry_for` but no `max_retries` |
| 15 | prompts.md | `escape_prompt_data` backward-compat alias `_escape_prompt_data` documented as canonical name | `services/subagent/__init__.py:54` | `_escape_prompt_data = escape_prompt_data` is re-export |
| 16 | infrastructure.md | `traced_llm_call`/`traced_stage` shown as standalone functions, actually context managers | `services/logging_utils.py:251,278` | Used as `with traced_llm_call(...):` |
| 17 | infrastructure.md | `shutdown(wait=False, cancel_futures=True)` pattern not consistently used | `services/subagent/config.py:11` | Executor created but no explicit shutdown |
| 18 | infrastructure.md | Missing documentation for subagent config executor | `services/subagent/config.py:11` | Bounded pool not mentioned |
| 19 | infrastructure.md | Missing documentation for LLM batch executor | `services/llm/base.py:396` | Bounded pool for parallelism |
| 20 | infrastructure.md | Missing documentation for timeout executor | `services/timeout.py:29-49` | Cross-platform timeout support |
| 21 | config.md | `reload_beat_schedule()` requires `celery_app` parameter — doc implies no-arg call | `config.py:206` | `reload_beat_schedule(cls, celery_app)` |
| 22 | routes.md | Missing `/newsletter/preview` POST endpoint documentation | `routes/admin/api/newsletters.py:221` | Endpoint exists with `@require_auth` and `@validate_csrf_json` |
| 23 | overview.md | Subagent system location confusion (package vs module) | `overview.md:636` | Both `services/subagent/` and `services.subagent` are correct |

---

## Key Findings Per Document

### models.md
1. **6 models lack detailed field documentation** — ArticleVersion, Citation, Tag, AuditLog, ApiToken, ShareConfig listed in inventory but not documented
2. **Minor attribute omissions** — `index=True` and `nullable=` missing from TrendMemory, TopicNote, AdminUser field definitions
3. **No file path or relationship errors** — All verified claims are accurate

### schemas.md
1. **CRITICAL: `PipelineRootConfig.experiments` field undocumented** — functional field used by A/B experiment system
2. **`RawItem` schema missing** — used by all adapters to return crawled items
3. **StageConfig correctly identified as stub** — only has `tools: list[str]`

### adapters.md
1. **WebAdapter unbounded fetch** — `_scrape_listing` returns all URLs across all pages with no `max_items` cap
2. **3 incorrect claims are documentation errors** — wrong function signature, wrong delay behavior description
3. **Layering is correct** — All adapters import from `utils.url` (not `services.url`)

### utils.md
1. **No incorrect claims or bugs** — All factual claims match actual code
2. **Duplicate exception clause** in `sanitize_html()` — dead code at line 159
3. **`services/url.py` duplication documented** — re-exports from `utils/url.py` with config support

### llm_providers.md
1. **`health_check()` incorrectly listed as abstract** — it's concrete on `BaseProvider`
2. **`record_provider_success()` signature incomplete** — missing `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `article_id`
3. **`extract_json` function name has typo** — doc says `_extract_json()`, actual is `extract_json()`

### search_providers.md
1. **YAML example structurally wrong** — shows nested format, actual is flat list with separate key
2. **`BaseSearchProvider` has no abstract `search()` method** — method only on concrete classes
3. **DeepSeek correctly noted as NOT a search provider** — only regex pattern in `trend_detector.py`

### subagent.md
1. **YAML config example has non-existent fields** — `tool_timeout` and `default_model` don't exist
2. **Schema location contradicted** — line 140 says `runner.py`, line 204 says `schemas/pipeline.py`
3. **14 tools all verified** — complete and accurate tool list

### pipeline.md
1. **CRITICAL: Degradation behavior table wrong** — disabled stages route through `_finalize()`, not directly to next stage
2. **Newsletter idempotency key TTL wrong** — 2 days, not 10 minutes (lock TTL is 10 min)
3. **A/B experiment distribution verified** — 70% control, 15% variant_a, 15% variant_b

### tasks.md
1. **Multiple tasks lack `max_retries`** — `generate_daily_newsletters`, `retry_stuck`, `publish_scheduled_articles`, cleanup tasks
2. **Stage transitions table incomplete** — missing SELECTING, WRITTEN, and PENDING→RESEARCHING
3. **"Normal flow" misleading** — review is not always in the path; articles can go edit→done directly

### prompts.md
1. **Prompt file count wrong** — 9 files exist, doc says 7 (missing 2 subagent templates)
2. **`_escape_prompt_data` is backward-compat alias** — canonical is `escape_prompt_data` in `utils/text.py`
3. **Template resolution order correct** — stage_config.task_template → _SUBAGENT_TASK_TEMPLATES fallback

### infrastructure.md
1. **3 ThreadPoolExecutors undocumented** — subagent config, LLM batch, timeout utility
2. **`traced_llm_call`/`traced_stage` are context managers** — not standalone functions as doc implies
3. **Redis DB allocation verified** — DB 0=Celery, DB 1=config cache, DB 15=limiter

### config.md
1. **`reload_beat_schedule()` requires `celery_app` param** — doc implies no-arg call
2. **`StageConfig` correctly identified as stub** — only has `tools` field
3. **All 14 providers verified** in providers.yaml

### overview.md
1. **Highly accurate** — 138 verified claims, 0 incorrect
2. **Layering rules all verified** — including documented violations
3. **Subagent location note is correct** — package at `services/subagent/`

### routes.md
1. **Newsletter endpoint misnamed** — `/newsletters/performance` should be `/newsletters/stats`
2. **Missing `/newsletter/preview` POST endpoint** — exists but undocumented
3. **47 admin routes and 35+ API endpoints verified** — all correct

### services.md
1. **CRITICAL: Wrong return type for `propose_trend_memory`** — `SubagentResponse`, not `list[TrendMemory]`
2. **Content extractor "raw HTML" fallback claim is false** — returns EMPTY status
3. **File inventory ~50% incomplete** — lists ~30 modules, actual ~60

---

## Cross-Document Contradictions

| # | Document A | Document B | Claim A | Claim B | Resolution |
|---|-----------|-----------|---------|---------|------------|
| 1 | subagent.md:140 | subagent.md:204 | Chain schemas in `runner.py` | Chain schemas in `schemas/pipeline.py` | Schemas are in `schemas/pipeline.py:108-118` — line 140 is incorrect |
| 2 | tasks.md:66 | tasks.md (multiple lines) | "All pipeline tasks use `max_retries=CELERY_TASK_MAX_RETRIES`" | Multiple tasks lack this parameter | Statement is incorrect — not all tasks have `max_retries` |
| 3 | pipeline.md:272-274 | pipeline.md (code evidence) | "research/write disabled: Article goes directly to next stage" | Routes through `_finalize()` to REVIEW/DONE | Code evidence is correct; documentation is wrong |

---

## Recommended Pruning Actions

| # | Document | Action | Reason | Priority |
|---|----------|--------|--------|----------|
| 1 | subagent.md | rewrite | YAML config example (lines 287-301) has non-existent fields `tool_timeout` and `default_model` | P1 |
| 2 | pipeline.md | rewrite | Degradation behavior table (lines 272-274) incorrectly describes disabled stage routing | P1 |
| 3 | schemas.md | update | Add `experiments: dict` field to `PipelineRootConfig` documentation | P1 |
| 4 | schemas.md | update | Add `RawItem` schema documentation | P1 |
| 5 | services.md | update | Fix `propose_trend_memory` return type to `SubagentResponse` | P1 |
| 6 | search_providers.md | rewrite | YAML example (lines 227-241) shows completely different structure | P1 |
| 7 | tasks.md | update | Fix stage transitions table to include SELECTING, WRITTEN, PENDING→RESEARCHING | P1 |
| 8 | tasks.md | update | Add `max_retries=CELERY_TASK_MAX_RETRIES` to `generate_daily_newsletters`, `retry_stuck`, `publish_scheduled_articles` | P1 |
| 9 | services.md | update | Fix `chat_structured` signature — add `max_validation_retries`, `stage` params, remove `**kwargs` | P1 |
| 10 | routes.md | update | Fix `/newsletters/performance` → `/newsletters/stats` | P1 |
| 11 | prompts.md | update | Update prompt file count from 7 to 9 | P2 |
| 12 | services.md | update | Remove false "raw HTML with boilerplate removal" fallback claim | P2 |
| 13 | services.md | update | Complete file inventory (~30 missing modules) | P2 |
| 14 | subagent.md | update | Fix schema location contradiction (line 140) | P2 |
| 15 | models.md | update | Document ArticleVersion, Citation, Tag, AuditLog, ApiToken, ShareConfig models | P2 |
| 16 | infrastructure.md | update | Show `traced_llm_call`/`traced_stage` as context managers | P2 |
| 17 | config.md | update | Document `reload_beat_schedule()` requires `celery_app` parameter | P2 |
| 18 | pipeline.md | update | Document idempotency key TTL (2 days) separately from lock TTL (10 min) | P2 |
| 19 | models.md | update | Add `index=True`, `nullable=` attributes to TrendMemory, TopicNote, AdminUser fields | P3 |
| 20 | schemas.md | update | Add `WebhookCreate` and `WebhookResponse` schema documentation | P3 |
| 21 | infrastructure.md | update | Document subagent config, LLM batch, and timeout ThreadPoolExecutors | P3 |
| 22 | llm_providers.md | update | Fix `extract_json` function name (remove underscore prefix) | P3 |
| 23 | overview.md | update | Document `services/subagent/` package structure in module index | P2 |
| 24 | tasks.md | update | Clarify "normal flow" doesn't always include review | P2 |
| 25 | llm_providers.md | update | Document `chat_structured_batch()`, `BatchError`, `ToolCall`, `ToolResult`, `ToolCallingResponse` | P2 |

---

## Summary

- **Total verified claims:** 863
- **Total incorrect claims:** 41 (HIGH: 2, MEDIUM: 10, LOW: 29)
- **Total bugs:** 22 (HIGH: 2, MEDIUM: 8, LOW: 12)
- **Total improvements:** 82
- **Total stale items:** 17
- **Cross-document contradictions:** 3
- **Recommended pruning actions:** 25

### Top Priority Fixes (P1)
1. Fix `propose_trend_memory` return type documentation (services.md)
2. Fix degradation behavior table (pipeline.md)
3. Document `PipelineRootConfig.experiments` field (schemas.md)
4. Fix YAML config example in subagent.md
5. Fix YAML example in search_providers.md
6. Add `max_retries` to newsletter/retry/scheduler tasks (tasks.md)
7. Fix `chat_structured` signature (services.md)
8. Fix `/newsletters/performance` → `/newsletters/stats` (routes.md)
9. Add `RawItem` schema documentation (schemas.md)
10. Fix stage transitions table (tasks.md)
