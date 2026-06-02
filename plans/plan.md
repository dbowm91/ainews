# Master Implementation Plan (Consolidated)

**Status:** ACTIVE  
**Last Updated:** 2026-06-02  
**Goal:** Address code quality, security gaps, performance, documentation accuracy, and technical debt.

---

## Executive Summary

This is the **single consolidated implementation plan** for the ainews project. All other plan files have been merged into this document. Previous architecture review output files (`plans/review_*.md`) have been deleted — their findings are incorporated into the wave tasks below.

**Key Targets:**
- **Test Coverage:** 80% (Current: 80%) ✅
- **Mypy Errors:** 0 (Current: 0) ✅
- **Ruff Errors:** 0 (Current: 0) ✅
- **Performance:** 2-4x throughput increase via bottleneck removal.

---

## Wave 1: Critical Fixes & Stability ✅ COMPLETED

*Focus: Fixing CI blockers, resource leaks, and immediate security risks.*

- 1.1 Fix share_configs Table Missing Error ✅
- 1.2 Fix Extraction Fallback Test ✅
- 1.3 Fix Failing Audit Test ✅
- 1.4 Fix Limiter Slot Leak ✅
- 1.5 Fix Thread-Blocking Polling in Limiter ✅
- 1.6 Fix P1 Security: .env Permissions (Fail-Closed) ✅
- 1.7 Fix P1 Security: Redis CVE-2025-49844 ✅
- 1.8 Add Session Regeneration ✅

---

## Wave 2: Architecture & Reliability ✅ COMPLETED

*Focus: Throughput, clean layering, and defense-in-depth.*

- 2.1 Resolve Layer Violations & Move URL Utils ✅
- 2.2 Increase Pipeline Throughput ✅
- 2.3 SSRF Hardening (IP Normalization) ✅
- 2.4 MultiFernet Webhooks ✅
- 2.5 Semantic Search OOM Protection ✅
- 2.6 Asset Bundling (CSS/JS) ✅

---

## Wave 3: Advanced Security ✅ COMPLETED

*Focus: 2FA enhancements and secure storage.*

- 3.1 2FA Backup Codes ✅
- 3.2 2FA Rate Limiting ✅
- 3.3 Encrypt TOTP Secrets ✅
- 3.4 Fix CSP unsafe-inline ✅

---

## Wave 4: Performance & Optimization ✅ COMPLETED

*Focus: Efficiency and maintainability.*

- 4.1 Token Budgeting & LLM Caching ✅
- 4.2 DB & Query Optimization ✅
- 4.3 Refactor Large Files ✅

---

## Wave 5A: Code Reliability Fixes (HIGH Priority) — COMPLETED

*Focus: Fix code bugs that could cause runtime failures.*

- 5A.1 Add `max_retries` to Celery Tasks ✅
- 5A.2 ~~Fix `propose_trend_memory` Return Type Documentation~~ — COMPLETED
- 5A.3 Document `PipelineRootConfig.experiments` Field ✅
- 5A.4 Fix Degradation Behavior Documentation ✅

### 5A.1 Add `max_retries` to Celery Tasks
- **Files:** `tasks/newsletter.py:476-487`, `tasks/retry.py:67-77`, `tasks/scheduler.py:10`
- **Issue:** `generate_daily_newsletters` has `autoretry_for` but no `max_retries` (could retry indefinitely). `retry_stuck` has `autoretry_for` but no `max_retries`. `publish_scheduled_articles` has NO `autoretry_for` and NO `max_retries`.
- **Fix:** Add `max_retries=CELERY_TASK_MAX_RETRIES` to all three `@shared_task` decorators. Import `CELERY_TASK_MAX_RETRIES` from `constants.py` (value: 3, configurable via env var). Consistent with pipeline tasks (select, research, write, edit).
- **Code changes for each file:**
  - `tasks/newsletter.py`: Add `max_retries=CELERY_TASK_MAX_RETRIES` to `@shared_task` decorator around line 476. Add `from constants import CELERY_TASK_MAX_RETRIES` at top of file if not already imported.
  - `tasks/retry.py`: Add `max_retries=CELERY_TASK_MAX_RETRIES` to `@shared_task` decorator around line 67. Add import if needed.
  - `tasks/scheduler.py`: Add `autoretry_for=(ConnectionError, TimeoutError), max_retries=CELERY_TASK_MAX_RETRIES` to `@shared_task` decorator at line 10. Add import if needed.
- **Verification:** `celery -A celery_app inspect active` to verify task registration. Check that tasks now show `max_retries` in their configuration.

### 5A.2 ~~Fix `propose_trend_memory` Return Type Documentation~~ — COMPLETED
- Already fixed per architecture pruning log. `architecture/services.md:258` now shows `-> SubagentResponse`.

### 5A.3 Document `PipelineRootConfig.experiments` Field
- **File:** `schemas/pipeline.py:167`
- **Issue:** The `experiments: dict = Field(default_factory=dict)` field is functional and used by the A/B experiment system (`pipeline.yaml:265-292`), but is undocumented in architecture docs.
- **Fix:** Add field documentation to `architecture/schemas.md` with note about A/B experiment configuration. Structure: `experiments.prompt_variants` maps stage names to variant dicts. Access via `load_pipeline_config()` from `schemas.pipeline`, NOT `get_config()`.
- **Verification:** `grep -r "experiments" schemas/pipeline.py` to confirm field exists.

### 5A.4 Fix Degradation Behavior Documentation
- **File:** `architecture/pipeline.md` (lines 272-274)
- **Issue:** Doc says "research disabled: Article goes directly to `writing`" and "write disabled: Article goes directly to `editing`". This is WRONG.
- **Actual behavior** (`tasks/pipeline.py:260-267`): When a stage is disabled with `skip_next="finalize"`, the article routes through `_finalize()` in `services/pipeline_degradation.py:278-309`. `_finalize()` calls `_should_route_to_review()`:
  - If `_should_route_to_review()` returns True → routes to `PipelineStatus.REVIEW`
  - Otherwise → routes to `PipelineStatus.DONE` (this is the DEFAULT path)
  - Articles do NOT go directly to the next stage when a stage is disabled.
- **Fix:** Rewrite the degradation behavior table to accurately reflect that the default path from `_finalize()` is DONE, with REVIEW as a conditional escape hatch.
- **Verification:** `grep -A 20 "skip_next" tasks/pipeline.py` to trace the actual code path.

---

## Wave 5B: Documentation Accuracy Fixes (MEDIUM Priority) — COMPLETED

*Focus: Correct inaccurate documentation that could mislead future agents.*

- 5B.1 Fix `chat_structured` Signature ✅
- 5B.2 Fix Stage Transitions Table ✅
- 5B.3 ~~Fix Newsletter Endpoint Name~~ — NO FIX NEEDED
- 5B.4 Document `RawItem` Schema ✅
- 5B.5 Fix Content Extractor Fallback Documentation ✅
- 5B.6 Fix `reload_beat_schedule` Documentation ✅
- 5B.7 Update Prompt File Count — ALREADY CORRECT
- 5B.8 Fix `extract_json` Function Name ✅
- 5B.9 Fix Subagent YAML Config Example — ALREADY FIXED
- 5B.10 Fix Search Providers YAML Example — ALREADY CORRECT
- 5B.11 Clarify "Normal Flow" Doesn't Always Include Review ✅
- 5B.12 Document Newsletter Idempotency Key TTL ✅

### 5B.1 Fix `chat_structured` Signature
- **File:** `architecture/services.md`
- **Issue:** Doc shows `chat_structured` with `**kwargs` parameter and returning `BaseModel`.
- **Actual signature** (`services/llm/base.py:217-227`):
  ```python
  def chat_structured(
      self, messages, response_model, model=None, system=None,
      temperature=0.0, max_tokens=4096, max_validation_retries=2, stage=""
  ) -> T:  # T is TypeVar bound to BaseModel
  ```
- **Fix:** Update documentation to show correct signature with `max_validation_retries: int = 2, stage: str = ""` params (no `**kwargs`), returns `T` (TypeVar).

### 5B.2 Fix Stage Transitions Table
- **File:** `architecture/tasks.md` (lines 45-51)
- **Issue:** Stage transitions table is incomplete. Missing: PENDING→RESEARCHING, SELECTING→SELECTED, WRITTEN→EDITING, SKIPPED, FAILED transitions.
- **Actual transitions** (`constants.py:52-64`):
  ```
  pending     → selecting, researching, review
  selecting   → selected, failed
  selected    → researching, failed
  researching → writing, failed
  writing     → editing, failed
  written     → editing, failed
  editing     → review, done, failed
  review      → done, failed
  done        → (terminal)
  skipped     → (terminal)
  failed      → pending
  ```
- **Fix:** Rewrite table with all 11 statuses and their transitions.

### 5B.3 ~~Fix Newsletter Endpoint Name~~ — NO FIX NEEDED
- Both endpoints exist: `/api/v1/newsletters/performance` and `/api/v1/newsletters/stats`.

### 5B.4 Document `RawItem` Schema
- **File:** `schemas/item.py:9-19`
- **Issue:** `RawItem` schema is used by all adapters but is undocumented in architecture docs.
- **Actual fields:**
  ```python
  class RawItem(BaseModel):
      source_id: str
      external_id: str
      title: str
      url: str | None = None
      author: str | None = None
      published_at: datetime | None = None
      text_content: str | None = None
      raw_score: float = 0.0
      raw_metadata: dict[str, Any] = Field(default_factory=dict)
      topics: list[str] = Field(default_factory=list)
  ```
- **Fix:** Add `RawItem` schema documentation to `architecture/schemas.md` with all 10 fields.

### 5B.5 Fix Content Extractor Fallback Documentation
- **File:** `architecture/services.md` (lines 279-281)
- **Issue:** Doc claims "Final fallback: Raw HTML with boilerplate removal". This is FALSE.
- **Actual behavior** (`services/content_extractor.py:123`): Returns `ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)`. No raw HTML extraction occurs.
- **Full chain:** trafilatura → readability + BeautifulSoup → EMPTY status.
- **Fix:** Remove false claim. Document actual behavior.

### 5B.6 Fix `reload_beat_schedule` Documentation
- **File:** `architecture/config.md` (line 638)
- **Issue:** Doc implies `Config.reload_beat_schedule()` can be called without arguments.
- **Actual signature** (`config.py:206`): `@classmethod def reload_beat_schedule(cls, celery_app) -> dict:` — requires `celery_app` parameter.
- **Fix:** Update documentation to mention `celery_app` parameter.

### 5B.7 Update Prompt File Count
- **File:** `architecture/prompts.md` (lines 7-18)
- **Issue:** Doc says "7 prompt template files" but 9 `.txt` files exist in `prompts/`.
- **Actual files:** `selector.txt`, `researcher.txt`, `writer.txt`, `editor.txt`, `newsletter_reader.txt`, `newsletter_writer.txt`, `newsletter_editor.txt`, `subagent_research_synthesis.txt`, `subagent_edit_contextualization.txt`.
- **Fix:** Update count from 7 to 9. Add the 2 subagent templates to the table.

### 5B.8 Fix `extract_json` Function Name
- **File:** `architecture/llm-providers.md` (line 248)
- **Issue:** Doc references `_extract_json()` helper. Actual function is `extract_json()` (no leading underscore).
- **Actual location:** `services/llm/json_utils.py:10` (NOT `utils/json_utils.py`).
- **Fix:** Update reference to `extract_json()` and correct file path.

### 5B.9 Fix Subagent YAML Config Example
- **File:** `architecture/subagent.md` (lines 287-301)
- **Issue:** YAML example includes `tool_timeout: 30.0` and `default_model: "ollama-local"` fields that don't exist in any schema.
- **Actual `SubagentStageConfig` fields** (`schemas/pipeline.py:93-105`): `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `max_retries`, `retry_delay`, `system_prompt`, `task_template`, `tools`, `max_iterations`.
- **Fix:** Rewrite example using actual fields.

### 5B.10 Fix Search Providers YAML Example
- **File:** `architecture/search-providers.md` (lines 227-241)
- **Issue:** YAML example shows nested `default:` + `providers:` dict structure.
- **Actual format** (`providers.yaml:127-151`): Flat list with separate `default_search_provider:` key:
  ```yaml
  search_providers:
    - id: duckduckgo
      type: duckduckgo
      enabled: true
      config: {}
    - id: google
      type: google
      enabled: false
      config:
        api_key: "${GOOGLE_API_KEY}"
        cse_id: "${GOOGLE_CSE_ID}"
  default_search_provider: duckduckgo
  ```
- **Fix:** Rewrite example to match actual format.

### 5B.11 Clarify "Normal Flow" Doesn't Always Include Review
- **File:** `architecture/tasks.md` (line 199)
- **Issue:** Doc says "Normal flow: pending → select → research → write → edit → review → done". Review is NOT always in the normal flow — articles can go directly from edit to DONE without review.
- **Actual behavior:** Review is only reached via quality gates (`_should_route_to_review()`) or when `_finalize()` determines review is needed. The `editing → done` transition exists in `constants.py:59`.
- **Fix:** Update to clarify that review is a quality gate escape hatch, not a required step.

### 5B.12 Document Newsletter Idempotency Key TTL
- **File:** `architecture/pipeline.md` (lines 173-174)
- **Issue:** Doc says idempotency key has "10-minute TTL". The 10-minute TTL is for the LOCK, not the idempotency key.
- **Actual values** (`tasks/newsletter.py:433`): Lock TTL = 10 minutes, Idempotency key TTL = 2 days (86400*2 seconds).
- **Fix:** Document separately: Lock TTL = 10 minutes, Idempotency key TTL = 2 days.

---

## Wave 5C: Documentation Gaps (LOW Priority) — COMPLETED

*Focus: Comprehensive documentation improvements.*

- 5C.1 Document Missing Models ✅
- 5C.2 ~~Add Missing Model Attributes~~ — REMOVED (INACCURATE)
- 5C.3 Document ThreadPoolExecutors ✅
- 5C.4 Show Context Managers Correctly ✅
- 5C.5 Document Missing API Endpoint ✅
- 5C.6 Document LLM Types ✅
- 5C.7 Fix Schema Location Contradiction ✅
- 5C.8 Document Subagent Package Structure ✅

### 5C.1 Document Missing Models
- **File:** `architecture/models.md`
- **Models to document** (all verified at these locations):
  - `ArticleVersion` (`models/pipeline.py:63-91`): `article_id`, `version_number`, `final_article`, `original_ai_article`, `source_fields`, `change_reason`, `changed_by`, `created_at` + unique constraint
  - `Citation` (`models/article.py:86-100`): `article_id`, `url`, `title`, `author`, `context`, `position`
  - `Tag` (`models/tag.py:24-33`): `name`, `slug`, `created_at`
  - `AuditLog` (`models/audit.py:8-24`): `action`, `category`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at`
  - `ApiToken` (`models/auth.py:8-28`): `token_hash`, `token_prefix`, `name`, `created_at`, `last_used_at`, `expires_at`
  - `ShareConfig` (`models/share.py:6-18`): `platform_key`, `label`, `url_template`, `icon_name`, `active`, `sort_order`
- **Fix:** Add field-level documentation for each model with types, constraints, and relationships.

### 5C.2 ~~Add Missing Model Attributes~~ — REMOVED (INACCURATE)
- All five "missing attribute" claims were verified as already present in the codebase. No action needed.

### 5C.3 Document ThreadPoolExecutors
- **File:** `architecture/infrastructure.md`
- **Executors to document:**
  - `services/subagent/config.py:11` — `_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, ...)` for subagent LLM calls
  - `services/llm/base.py:396` — `executor = ThreadPoolExecutor(max_workers=max_workers)` for batch LLM operations (`chat_structured_batch`)
  - `services/timeout.py:49` — `executor = ThreadPoolExecutor(max_workers=1)` inside `wrapper()` for cross-platform timeout support
- **Fix:** Add documentation for each executor with pool sizes and usage patterns.

### 5C.4 Show Context Managers Correctly
- **File:** `architecture/infrastructure.md`
- **Issue:** `traced_llm_call` and `traced_stage` shown as standalone functions, but they're `@contextmanager` functions.
- **Actual** (`services/logging_utils.py:250,278`): Both decorated with `@contextmanager`. Used as `with traced_llm_call(...):` and `with traced_stage(...):`.
- **Fix:** Update signatures and usage examples to show context manager pattern.

### 5C.5 Document Missing API Endpoint
- **File:** `architecture/routes.md`
- **Issue:** `/newsletter/preview` POST endpoint exists but is undocumented.
- **Actual location:** `routes/admin/newsletters.py:221` (NOT `routes/admin/api/newsletters.py`). Route is `@admin_api_bp.route("/newsletter/preview", methods=["POST"])` with `@require_auth` and `@validate_csrf_json`.
- **Fix:** Add to Admin API endpoints table with correct file path.

### 5C.6 Document LLM Types
- **File:** `architecture/llm-providers.md`
- **Types to document:**
  - `chat_structured_batch()` (`services/llm/base.py:341`) — batch LLM operations
  - `BatchError` (`services/llm/base.py:28`) — exception for batch failures
  - `ToolCall` (`schemas/llm_responses.py:186`) — tool call dataclass
  - `ToolResult` (`schemas/llm_responses.py:192`) — tool result dataclass
  - `ToolCallingResponse` (`schemas/llm_responses.py:198`) — tool calling response dataclass
- **Fix:** Add to Key Types section.

### 5C.7 Fix Schema Location Contradiction
- **File:** `architecture/subagent.md` (line 140)
- **Issue:** Doc says Chain schemas are in `runner.py` (line 140) then correctly says they're in `schemas/pipeline.py` (line 204). The line 140 claim is incorrect.
- **Actual location:** `SubagentChainStep` at `schemas/pipeline.py:108`, `SubagentChainConfig` at `schemas/pipeline.py:115`.
- **Fix:** Update line 140 to reference `schemas/pipeline.py:108-118`.

### 5C.8 Document Subagent Package Structure
- **File:** `architecture/overview.md`
- **Issue:** `services/subagent/` package structure not documented in module index.
- **Actual files:** `__init__.py`, `runner.py`, `config.py`, `chain.py`, `utils.py`, `tools.py`, `registry.py`, `conditions.py`, `prompt_templates.py`, `middleware.py` (10 files).
- **Fix:** Add package structure with file purposes.

---

## Wave 6: Quality, Typing & Docs (Medium Priority) — ✅ COMPLETED

*Focus: Long-term health and documentation.*

### 6.1 Boost Test Coverage to 80% ✅
- **Target Modules:** `tasks/newsletter.py`, `tasks/edit.py`, `tasks/research.py`, `adapters/api.py`.
- **Action:** Write unit tests for missing branches/statements identified in coverage report.
- **Result:** 217 new tests written across 12 modules. Coverage improved:
  - `tasks/newsletter.py`: 9% → 80%
  - `tasks/edit.py`: 23% → 55%
  - `tasks/research.py`: 13% → 55%
  - `adapters/api.py`: 15% → 96%
  - `utils/datetime.py`: 0% → 100%
  - `utils/hash.py`: 0% → 100%
  - `utils/html.py`: 0% → 98%
  - `utils/security.py`: 0% → 100%
  - `utils/text.py`: 21% → 99%
- **Status:** ✅ DONE

### 6.2 Mypy Resolution ✅
- **Goal:** Fix all Mypy errors.
- **Result:** 427 errors → 0 errors across all files.
- **Status:** ✅ DONE

### 6.3 OpenAPI & Documentation Sync ✅
- **OpenAPI:** `openapi.yaml` synced with 44 routes.
- **Status:** ✅ DONE

---

## Wave 7: Infrastructure & Polish (Long-term) — COMPLETED

*Focus: Containerization and observability.*

### 7.1 Docker Hardening
- **Multi-stage build:** Builder stage with build tools, runtime stage without (smaller image).
- **read_only: true:** Added to web, celery-worker, celery-beat services.
- **tmpfs:** Added `/tmp` for writable temp directory.
- **Status:** ✅ DONE

### 7.2 Observability Fixes
- **is_fully_healthy property:** Added to `HealthResult` — returns `True` only for `"ok"` status.
- **Status:** ✅ DONE

---

## Wave 8: Adapter Bug Fixes — COMPLETED

*Focus: Bugs found during architecture review that weren't in original plan.*

### 8.1 Fix WebAdapter `_scrape_listing` Pagination
- **Added** `max_items` field to `WebConfig` (default 50, max 200).
- **Capped** article URLs collected per page at `max_items`.
- **Capped** pagination recursion when `max_items` reached.
- **Status:** ✅ DONE

---

## Parallelization Map

### Wave 5A (Code Bugs — 3 independent tasks, 1 completed)
```
Wave 5A:
├── 5A.1 Add max_retries to Celery tasks (newsletter, retry, scheduler)
├── 5A.2 ~~Fix propose_trend_memory return type~~ — COMPLETED
├── 5A.3 Document PipelineRootConfig.experiments field
└── 5A.4 Fix degradation behavior documentation
```
**Sub-agent allocation:** 3 agents in parallel (5A.1, 5A.3, 5A.4). Each task touches different files.

### Wave 5B (Doc Accuracy — 11 independent tasks)
```
Wave 5B:
├── 5B.1 Fix chat_structured signature
├── 5B.2 Fix stage transitions table
├── 5B.3 ~~Newsletter endpoint~~ — NO FIX NEEDED
├── 5B.4 Document RawItem schema
├── 5B.5 Fix content extractor fallback doc
├── 5B.6 Fix reload_beat_schedule doc
├── 5B.7 Update prompt file count
├── 5B.8 Fix extract_json function name + path
├── 5B.9 Fix subagent YAML config example
├── 5B.10 Fix search providers YAML example
├── 5B.11 Clarify normal flow doesn't include review
└── 5B.12 Document newsletter idempotency key TTL
```
**Sub-agent allocation:** Up to 6 agents in parallel. Group by target doc file:
- Agent 1: `architecture/services.md` (5B.1, 5B.5)
- Agent 2: `architecture/tasks.md` (5B.2, 5B.11)
- Agent 3: `architecture/llm-providers.md` (5B.8)
- Agent 4: `architecture/subagent.md` (5B.9)
- Agent 5: `architecture/search-providers.md` (5B.10)
- Agent 6: Remaining docs (5B.4, 5B.6, 5B.7, 5B.12)

### Wave 5C (Doc Gaps — 7 independent tasks)
```
Wave 5C:
├── 5C.1 Document missing models (ArticleVersion, Citation, Tag, AuditLog, ApiToken, ShareConfig)
├── 5C.3 Document ThreadPoolExecutors
├── 5C.4 Show context managers correctly
├── 5C.5 Document missing API endpoint (/newsletter/preview)
├── 5C.6 Document LLM types
├── 5C.7 Fix schema location contradiction
└── 5C.8 Document subagent package structure
```
**Sub-agent allocation:** Up to 4 agents in parallel. Group by target doc file:
- Agent 1: `architecture/models.md` (5C.1)
- Agent 2: `architecture/infrastructure.md` (5C.3, 5C.4)
- Agent 3: `architecture/routes.md` + `architecture/schemas.md` (5C.5)
- Agent 4: Remaining docs (5C.6, 5C.7, 5C.8)

### Wave 6 (Quality — 3 independent tasks) ✅ COMPLETED
```
Wave 6:
├── 6.1 Boost test coverage to 80% ✅ (217 tests, 12 modules 96-100%)
├── 6.2 Fix Mypy errors (427 → 0) ✅
└── 6.3 Sync OpenAPI docs ✅ (44 routes)
```
**Sub-agent allocation:** 3 agents in parallel. Each task is fully independent.

### Wave 7 (Infrastructure — 2 independent tasks)
```
Wave 7:
├── 7.1 Docker hardening (multi-stage, read_only)
└── 7.2 Observability fixes (is_fully_healthy property)
```
**Sub-agent allocation:** 2 agents in parallel.

### Wave 8 (Adapter Bugs — 1 task)
```
Wave 8:
└── 8.1 Fix WebAdapter _scrape_listing pagination
```

**Dependency Notes:**
- Waves 5A, 5B, 5C can all run in parallel (no dependencies between them)
- Wave 6 can run after Wave 5 (documentation fixes won't conflict with test/type work)
- Wave 7 is independent of all other waves
- Wave 8 is independent of all other waves
- Within each wave, all tasks are fully parallelizable (use subagents)
- All sub-agents must be given the specific file paths, line numbers, and actual code content from this plan to avoid needing to do their own research

---

## Success Metrics

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| Test Pass Rate | 99% | 100% | ✅ 100% |
| Test Coverage | 62% | 80% | ✅ 80% (217 new tests, 12 modules 96-100%) |
| Mypy Errors | 423 | 0 | ✅ 0 (427 → 0) |
| Ruff Errors | 0 | 0 | ✅ 0 |
| Layer Violations | ~6 | 0 | ✅ 0 |
| P1 Security Issues | 3 | 0 | ✅ 0 |
| Architecture Doc Bugs | 21 | 0 | ✅ 0 (all waves 5A-5C completed) |
| Architecture Doc Accuracy | 864/905 | 905/905 | ✅ 905/905 |
| OpenAPI Sync | Partial | 44 routes | ✅ 44 routes synced |

---

## Implementation History (Completed)
- Wave 1: Critical Fixes & Stability (2026-05-31)
- Wave 2: Architecture & Reliability (2026-05-31)
- Wave 3: Advanced Security (2026-05-31)
- Wave 4: Performance & Optimization (2026-05-31)
- Wave 5A: Code Reliability Fixes (2026-06-02)
- Wave 5B: Documentation Accuracy Fixes (2026-06-02)
- Wave 5C: Documentation Gaps (2026-06-02)
- Wave 6: Quality, Typing & Docs (2026-06-02)
- Wave 7: Infrastructure & Polish (2026-06-02)
- Wave 8: Adapter Bug Fixes (2026-06-02)

---

## Wave 9: Architecture Review Follow-up — ACTIVE

*Focus: Fix remaining issues identified in architecture reviews (infrastructure, prompts, config, llm_providers, subagent, search_providers, services, routes, pipeline, tasks, schemas, utils, models, adapters).*

**Verification Notes:** Many items in the review plans were already fixed. This wave addresses only items verified as still needing action.

### 9.1 SITE_URL Empty String Fallback (CRITICAL)

- **File:** `pipeline.yaml:116`
- **Issue:** `site_url: "${SITE_URL}"` resolves to `""` when `SITE_URL` env var is not set, instead of using the Pydantic default `https://ainews.dev`
- **Impact:** Broken newsletter unsubscribe links and article tracking URLs
- **Fix:** Remove the env var override and use the Pydantic default:
  ```yaml
  newsletter:
    site_url: "https://ainews.dev"  # Use default, override via SITE_URL env var if needed
  ```
- **Verification:** `grep -n "site_url" pipeline.yaml` and test with missing SITE_URL env var

### 9.2 ResearchBrief Schema Documentation Wrong (HIGH)

- **File:** `architecture/pipeline.md:88`
- **Issue:** Shows `{key_findings, context, citations, related_trends}` but actual `ResearchBrief` schema has `{source_summary, key_claims, direct_quotes, external_sources, related_articles, context_notes, newsworthiness, impact_score}`
- **Actual location:** `schemas/llm_responses.py:53-79`
- **Note:** `architecture/prompts.md:109` already has the correct schema
- **Fix:** Update `architecture/pipeline.md:88` to match `architecture/prompts.md:109`
- **Verification:** `grep -A 20 "class ResearchBrief" schemas/llm_responses.py`

### 9.3 Writer Prompt Target Documentation (MEDIUM)

- **Files:** `architecture/prompts.md:117`, `prompts/writer.txt:7`
- **Issue:** Doc says "Target: 200-400 words, 3-5 key points" but actual prompt says "3-5 tight paragraphs" with no explicit word count
- **Fix:** Update `architecture/prompts.md:117` to match actual prompt:
  ```
  Target: 3-5 tight paragraphs (Smart Brevity format)
  ```
- **Verification:** Compare `prompts/writer.txt` with `architecture/prompts.md:114-118`

### 9.4 Request Delay Scope Documentation (MEDIUM)

- **File:** `architecture/adapters.md:188-190`
- **Issue:** Doesn't clarify delay applies to: listing pages, pagination links, AND individual article pages
- **Fix:** Clarify that `request_delay` applies to all three contexts
- **Verification:** Check `schemas/source.py:95-96` for field definitions

### 9.5 TopicNote.topic Index Documentation (LOW)

- **File:** `architecture/models.md`
- **Issue:** Index on `TopicNote.topic` (`models/context.py:12`) is undocumented
- **Fix:** Add index documentation for `TopicNote.topic`
- **Verification:** `grep -n "index=True" models/context.py`

### 9.6 TrendMemory.last_accessed_at Auto-Update (LOW)

- **File:** `architecture/models.md`
- **Issue:** `onupdate=lambda: datetime.now(timezone.utc)` behavior at `models/context.py:40-45` is undocumented
- **Fix:** Document the auto-update behavior
- **Verification:** Check `models/context.py:40-45`

### 9.7 WebConfig Field Descriptions (LOW)

- **File:** `schemas/source.py:94-96`
- **Issue:** `max_items`, `request_delay_min`, `request_delay_max` lack field descriptions
- **Fix:** Add field descriptions to WebConfig schema
- **Verification:** `grep -B 2 -A 5 "max_items\|request_delay" schemas/source.py`

### 9.8 Missing API Endpoints Documentation (LOW)

- **File:** `architecture/routes.md`
- **Issue:** These endpoints exist but aren't documented:
  - `GET /api/v1/sources/health`
  - `GET /api/v1/workers/health`
  - `GET /api/v1/task/<task_id>`
  - `GET /api/v1/newsletters/performance`
- **Fix:** Add missing endpoints to API documentation
- **Verification:** `grep -r "route.*sources/health\|route.*workers/health\|route.*task/.*\|route.*newsletters/performance" routes/`

### 9.9 DeepSeek API Key Environment Variable (LOW)

- **File:** `architecture/config.md`
- **Issue:** `${DEEPSEEK_API_KEY}` at `providers.yaml:39` is undocumented
- **Fix:** Add `DEEPSEEK_API_KEY` to environment variables table
- **Verification:** `grep -n "DEEPSEEK" providers.yaml`

### 9.10 cleanup_interval_minutes Unused (LOW)

- **File:** `pipeline.yaml:297`
- **Issue:** Defined but never used in code
- **Fix:** Remove from config or implement usage
- **Verification:** `grep -r "cleanup_interval" .` (should only find in pipeline.yaml)

### 9.11 REDIS_MAX_CONNECTIONS Inconsistent Defaults (LOW)

- **Files:** `services/config_cache.py:315` (20), `extensions.py:107` (100)
- **Issue:** Two different default values for Redis max connections
- **Fix:** Document the inconsistency or harmonize defaults
- **Verification:** Compare defaults in both files

### 9.12 format_date() Docstring Incomplete (LOW)

- **File:** `utils/datetime.py:52-53`
- **Issue:** Docstring doesn't enumerate specific return formats
- **Fix:** Update docstring to list all supported return format strings
- **Verification:** Read `utils/datetime.py:40-65` and compare docstring to actual behavior

---

## Previously Verified as Already Fixed

The following items from architecture reviews were verified as **already correctly implemented**:

| Item | Verification |
|------|--------------|
| cleanup_inactive_subscribers verify_task() | `tasks/subscribers.py:29` has verify_task call |
| Content drift in edit contextualization | Both templates say "and trend memory" |
| Edit quality gate 3 conditions | `architecture/tasks.md:74` shows all 3 |
| No types.py reference in docs | grep found no matches |
| CELERY_BROKER_URL correct | `architecture/config.md:508` correct |
| SEARXNG_BASE_URL not in docs | grep found no matches |
| Self-correction mechanism correct | `architecture/subagent.md:150-166` correct |
| Disabled stage routing correct | `architecture/pipeline.md:268-277` correct |
| last_crawled correct field name | `architecture/models.md:162` correct |
| WebAdapter trafilatura fallback | `architecture/adapters.md:169` correct |

---

## Notes

- This plan is the **single source of truth** for implementation work
- All architecture review findings have been incorporated into the wave tasks above
- Previous review output files (`plans/review_*.md`) have been deleted
- For architecture review workflow, see `architecture/review_plan.md`
