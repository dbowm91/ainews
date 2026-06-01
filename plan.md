# Master Implementation Plan (Consolidated)

**Status:** ACTIVE  
**Last Updated:** 2026-06-01  
**Goal:** Address code quality, security gaps, performance, documentation accuracy, and technical debt.

---

## Executive Summary

This consolidated plan merges the existing wave-based implementation plan with findings from 15 deep-dive architecture reviews (863 verified claims, 41 incorrect, 22 bugs). It prioritizes **code reliability fixes** first, followed by **documentation accuracy corrections**, then **comprehensive documentation gaps**. The ultimate goals are 100% test pass rate, 80% test coverage, 0 Mypy/Ruff errors, and significant throughput improvements.

**Key Targets:**
- **Test Coverage:** 80% (Current: ~61-62%)
- **Mypy Errors:** 0 (Current: 423)
- **Ruff Errors:** 0 (Current: 0, must maintain)
- **Performance:** 2-4x throughput increase via bottleneck removal.

---

## Wave 1: Critical Fixes & Stability (Immediate) ✅ COMPLETED

*Focus: Fixing CI blockers, resource leaks, and immediate security risks.*

### 1.1 Fix share_configs Table Missing Error ✅
- **File:** `app.py`
- **Issue:** `db.create_all()` in `_setup_database()` fails because models aren't registered (imported) before call.
- **Fix:** Add `import models` inside `_setup_database()` before `db.create_all()`.
- **Verification:** `pytest tests/test_extract_task.py -v`

### 1.2 Fix Extraction Fallback Test ✅
- **File:** `tests/test_extract_task.py` or `tasks/extract.py`
- **Issue:** Mock raises generic `Exception`, but `tasks/extract.py` only catches specific errors.
- **Fix:** Either change the test mock to raise `ConnectionError` or broaden `tasks/extract.py` to catch `Exception` (with `# noqa: BLE001`).

### 1.3 Fix Failing Audit Test ✅
- **File:** `services/audit.py`
- **Issue:** `db.session` access outside app context causes `RuntimeError`.
- **Fix:** Harden `log_admin_action` to handle `RuntimeError` gracefully.

### 1.4 Fix Limiter Slot Leak ✅
- **File:** `tasks/pipeline.py`
- **Issue:** Limiter acquired but not released if `lock_acquired` is False (early return at line 417).
- **Fix:** Ensure `limiter.release()` is called before early return or restructure `try/finally`.

### 1.5 Fix Thread-Blocking Polling in Limiter ✅
- **File:** `services/limiter.py`
- **Issue:** `time.sleep()` blocks worker threads.
- **Fix:** Replace with Redis pub/sub waiting in `acquire()`. Avoid creating/destroying pubsub objects in every loop iteration.

### 1.6 Fix P1 Security: .env Permissions (Fail-Closed) ✅
- **File:** `app.py`
- **Issue:** Only warns about insecure `.env` permissions.
- **Fix:** Refuse to start in `production` if permissions are not 600 or 640.

### 1.7 Fix P1 Security: Redis CVE-2025-49844 ✅
- **File:** `pyproject.toml`
- **Fix:** Upgrade `redis>=6.4.2`.

### 1.8 Add Session Regeneration ✅
- **File:** `routes/admin/auth.py`
- **Issue:** Lack of session regeneration after login (fixation risk).
- **Fix:** Call `session.clear()` and ensure a new session ID is generated upon successful login.

---

## Wave 2: Architecture & Reliability (High Priority) ✅ COMPLETED

*Focus: Throughput, clean layering, and defense-in-depth.*

### 2.1 Resolve Layer Violations & Move URL Utils ✅
- **Task:** Create `utils/url.py` and migrate logic from `services/url.py`.
- **Import Updates:** Update ~10 files (adapters, services, routes) to import from `utils.url`.
- **Adapter Violations:**
    - `adapters/base.py`: Remove business logic import (`services.trend_detector`).
    - `services/crawling.py`: Remove adapter import (`adapters.base.RawItem`). Move `RawItem` to `schemas/`.

### 2.2 Increase Pipeline Throughput ✅
- **pipeline.yaml:** Increase `writer` stage concurrency from 1 to 2.
- **docker-compose.yml:** Support `CELERY_CONCURRENCY` env var (default 4).
- **Subagent:** Increase `SUBAGENT_WORKERS` to 16.

### 2.3 SSRF Hardening (IP Normalization) ✅
- **File:** `utils/url.py` (after move)
- **Fix:** Add decimal/hex IP normalization to `validate_url_safe`.

### 2.4 MultiFernet Webhooks ✅
- **File:** `services/webhooks.py`
- **Fix:** Use `cryptography.fernet.MultiFernet` for easier key rotation.

### 2.5 Semantic Search OOM Protection ✅
- **File:** `services/trend_memory.py`
- **Fix:** Add limits/pre-filtering to `semantic_search_trends`.

### 2.6 Asset Bundling (CSS/JS) ✅
- **CSS:** Eliminate `@import` waterfall in `style.css` by bundling into `style.bundled.css`.
- **JS:** Minify and bundle JS files (app, theme, toast, admin) into `bundle.min.js`.

---

## Wave 3: Advanced Security (High Priority) ✅ COMPLETED

*Focus: 2FA enhancements and secure storage.*

### 3.1 2FA Backup Codes ✅
- **Model:** Add `backup_codes` (JSON) to `AdminUser`.
- **Service:** Implement generation (plaintext/hashed) and verification in `services/totp.py`.
- **UI:** Update setup flow to show codes once; update login to accept backup codes.

### 3.2 2FA Rate Limiting ✅
- **Auth:** Track failed 2FA attempts. Lock 2FA for 15 mins after 5 failures.

### 3.3 Encrypt TOTP Secrets ✅
- **Storage:** Encrypt `AdminUser.totp_secret` at rest using Fernet.

### 3.4 Fix CSP unsafe-inline ✅
- **Policy:** Remove `'unsafe-inline'` from `style-src`.
- **Refactor:** Move all inline styles to external CSS files.

---

## Wave 4: Performance & Optimization (Medium Priority) ✅ COMPLETED

*Focus: Efficiency and maintainability.*

### 4.1 Token Budgeting & LLM Caching ✅
- **Subagent:** Add `_budget_tokens` check before sending prompts to avoid context overflow.
- **Truncation:** Cache `summarize_context` results to avoid redundant 2-10s LLM calls.

### 4.2 DB & Query Optimization ✅
- **Indexes:** Add index to `PipelineRun.status`.
- **Queries:** Optimize COUNT queries in dashboard; use `lazy="selectin"` for Article metrics.
- **Caching:** Implement proactive cache warming for critical paths (Homepage, RSS).

### 4.3 Refactor Large Files ✅
- **test_subagent.py:** Split 1964-line file into modular components (models, templates, runner, tools, middleware).
- **models.py:** Convert into a `models/` package with domain-grouped files.
- **runner.py / llm/base.py:** Extract helper logic and types into separate modules.

---

## Wave 5A: Code Reliability Fixes (HIGH Priority) ⏳

*Focus: Fix code bugs that could cause runtime failures. These are independent and can be parallelized.*

### 5A.1 Add `max_retries` to Celery Tasks
- **File:** `tasks/newsletter.py:476-487`
- **Issue:** `generate_daily_newsletters` has `autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError)` but no `max_retries`. Could retry indefinitely on transient errors.
- **Fix:** Add `max_retries=CELERY_TASK_MAX_RETRIES` to the `@shared_task` decorator, consistent with pipeline tasks (select, research, write, edit).
- **File:** `tasks/retry.py:67-77`
- **Issue:** `retry_stuck` has `autoretry_for=(ConnectionError, TimeoutError)` but no `max_retries`.
- **Fix:** Add `max_retries=CELERY_TASK_MAX_RETRIES`.
- **File:** `tasks/scheduler.py:10`
- **Issue:** `publish_scheduled_articles` has NO `autoretry_for` and NO `max_retries`. The task uses Redis locks and SQLAlchemy error handling internally. Adding `max_retries` is still recommended for consistency and safety.
- **Fix:** Add `max_retries=CELERY_TASK_MAX_RETRIES` to the `@shared_task` decorator.
- **Verification:** Run `celery -A celery_app inspect active` to verify task registration.

### 5A.2 Fix `propose_trend_memory` Return Type Documentation
- **File:** `services/trend_memory.py:217`
- **Issue:** Documentation says it returns `list[TrendMemory]`, but it actually returns `SubagentResponse(synthesis=..., used_fallback=..., fallback_stages=[])`. Callers expecting a list will fail at runtime.
- **Fix:** Update all documentation references to show `SubagentResponse` return type. The `synthesis` field contains the proposed trend memory entries as text.
- **Verification:** `grep -r "propose_trend_memory" --include="*.py"` to find all callers.

### 5A.3 Document `PipelineRootConfig.experiments` Field
- **File:** `schemas/pipeline.py:167`
- **Issue:** The `experiments: dict = Field(default_factory=dict)` field is functional and used by the A/B experiment system (`pipeline.yaml:265-292`), but is undocumented.
- **Fix:** Add field to `PipelineRootConfig` documentation with note about A/B experiment configuration. Structure: `experiments.prompt_variants` maps stage names to variant dicts.

### 5A.4 Fix Degradation Behavior Documentation
- **File:** `architecture/pipeline.md` (lines 272-274)
- **Issue:** Doc says "research disabled: Article goes directly to `writing`" and "write disabled: Article goes directly to `editing`". Actual code in `tasks/pipeline.py:260-267` routes through `_finalize()` which goes to REVIEW or DONE.
- **Fix:** Rewrite degradation behavior table. When a stage is disabled with `skip_next="finalize"`, the article routes through `_finalize()` which:
  - Routes to `review` if quality gates trigger or auto-publish threshold not met
  - Routes to `done` if auto-publish threshold met
  - Does NOT go directly to the next stage
- **Verification:** `grep -A 20 "skip_next" tasks/pipeline.py` to trace the actual code path.

---

## Wave 5B: Documentation Accuracy Fixes (MEDIUM Priority) ⏳

*Focus: Correct inaccurate documentation that could mislead future agents. These are independent and can be parallelized.*

### 5B.1 Fix `chat_structured` Signature
- **File:** `architecture/services.md`
- **Issue:** Doc shows `chat_structured` with `**kwargs` parameter and returning `BaseModel`. Actual signature at `services/llm/base.py:217-227` has `max_validation_retries: int = 2, stage: str = ""` params (no `**kwargs`), returns `T` (TypeVar bound to BaseModel).
- **Fix:** Update documentation to show correct signature and return type.

### 5B.2 Fix Stage Transitions Table
- **File:** `architecture/tasks.md` (lines 45-51)
- **Issue:** Stage transitions table is incomplete. Missing: PENDING→RESEARCHING, SELECTING→SELECTED (transient), WRITTEN→EDITING (transient).
- **Fix:** Rewrite table with all transitions from `constants.py:52-64`:
  - `pending` → `selecting`, `review`, `researching`
  - `selecting` → `selected`, `failed`
  - `selected` → `researching`, `failed`
  - `researching` → `writing`, `failed`
  - `writing` → `editing`, `failed`
  - `written` → `editing`, `failed`
  - `editing` → `review`, `done`, `failed`
  - `review` → `done`, `failed`
  - `done` → (terminal)
  - `skipped` → (terminal)
  - `failed` → `pending`

### 5B.3 ~~Fix Newsletter Endpoint Name~~ — NO FIX NEEDED
- **File:** `architecture/routes.md` (lines 148, 252)
- **Issue:** Review claimed `/newsletters/performance` should be `/newsletters/stats`. Investigation shows BOTH endpoints exist:
  - `/api/v1/newsletters/performance` at `routes/admin/api/newsletter.py:175` (performance metrics)
  - `/api/v1/newsletters/stats` at `routes/admin/newsletters.py:177` (stats)
- **Status:** Architecture doc is correct. No fix needed.

### 5B.4 Document `RawItem` Schema
- **File:** `schemas/item.py:9-19`
- **Issue:** `RawItem` schema is used by all adapters to return crawled items but is undocumented.
- **Fix:** Add `RawItem` schema documentation with fields: `source_id`, `external_id`, `title`, `url`, `author`, `published_at`, `text_content`, `raw_score`, `raw_metadata`, `topics`.

### 5B.5 Fix Content Extractor Fallback Documentation
- **File:** `architecture/services.md` (lines 279-281)
- **Issue:** Doc claims "Final fallback: Raw HTML with boilerplate removal". Actual code at `services/content_extractor.py:123` returns `ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)` — no raw HTML extraction.
- **Fix:** Remove false claim. Document actual behavior: trafilatura → readability → EMPTY status.

### 5B.6 Fix `reload_beat_schedule` Documentation
- **File:** `architecture/config.md` (line 638)
- **Issue:** Doc implies `Config.reload_beat_schedule()` can be called without arguments. Actual signature at `config.py:206` requires `celery_app` parameter.
- **Fix:** Update documentation to mention `celery_app` parameter: `Config.reload_beat_schedule(celery_app)`.

### 5B.7 Update Prompt File Count
- **File:** `architecture/prompts.md` (lines 7-18)
- **Issue:** Doc says "7 prompt template files" but 9 exist in `prompts/`: selector.txt, researcher.txt, writer.txt, editor.txt, newsletter_reader.txt, newsletter_writer.txt, newsletter_editor.txt, subagent_research_synthesis.txt, subagent_edit_contextualization.txt.
- **Fix:** Update count from 7 to 9. Add the 2 subagent templates to the table.

### 5B.8 Fix `extract_json` Function Name
- **File:** `architecture/llm-providers.md` (line 248)
- **Issue:** Doc references `_extract_json()` helper. Actual function is `extract_json()` (no leading underscore) in `json_utils.py:10`.
- **Fix:** Update reference to `extract_json()`.

### 5B.9 Fix Subagent YAML Config Example
- **File:** `architecture/subagent.md` (lines 287-301)
- **Issue:** YAML example includes `tool_timeout: 30.0` and `default_model: "ollama-local"` fields that don't exist in `SubagentStageConfig` or `SubagentConfig` schemas.
- **Fix:** Rewrite example using actual fields from `SubagentStageConfig` (`schemas/pipeline.py:93-105`): `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`.

### 5B.10 Fix Search Providers YAML Example
- **File:** `architecture/search-providers.md` (lines 227-241)
- **Issue:** YAML example shows nested `default:` + `providers:` dict structure, but actual format in `providers.yaml:127-150` uses flat list with separate `default_search_provider:` key at top level.
- **Fix:** Rewrite example to match actual format:
  ```yaml
  search_providers:
    - id: duckduckgo
      enabled: true
      ...
    - id: google
      enabled: false
      ...
  default_search_provider: duckduckgo
  ```

### 5B.11 Clarify "Normal Flow" Doesn't Always Include Review
- **File:** `architecture/tasks.md` (line 199)
- **Issue:** Doc says "Normal flow: pending → select → research → write → edit → review → done". Review is NOT always in the normal flow — articles can go directly from edit to DONE without review. Review is only reached via quality gates or `_should_route_to_review()`.
- **Fix:** Update to clarify that review is a quality gate escape hatch, not a required step.

### 5B.12 Document Newsletter Idempotency Key TTL
- **File:** `architecture/pipeline.md` (lines 173-174)
- **Issue:** Doc says idempotency key has "10-minute TTL". Actual TTL is 2 days (86400*2) at `tasks/newsletter.py:433`. The 10-minute TTL is for the lock, not the idempotency key.
- **Fix:** Document separately: Lock TTL = 10 minutes, Idempotency key TTL = 2 days.

---

## Wave 5C: Documentation Gaps (LOW Priority) ⏳

*Focus: Comprehensive documentation improvements. Can be parallelized.*

### 5C.1 Document Missing Models
- **File:** `architecture/models.md`
- **Issue:** 6 models listed in inventory but lack detailed field documentation:
  - `ArticleVersion` (`models/pipeline.py:63-91`): `article_id`, `version_number`, `final_article`, `original_ai_article`, `source_fields`, `change_reason`, `changed_by`, `created_at` + unique constraint
  - `Citation` (`models/article.py:86-100`): `article_id`, `url`, `title`, `author`, `context`, `position`
  - `Tag` (`models/tag.py:24-33`): `name`, `slug`, `created_at`
  - `AuditLog` (`models/audit.py:8-24`): `action`, `category`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at`
  - `ApiToken` (`models/auth.py:8-28`): `token_hash`, `token_prefix`, `name`, `created_at`, `last_used_at`, `expires_at`
  - `ShareConfig` (`models/share.py:6-18`): `platform_key`, `label`, `url_template`, `icon_name`, `active`, `sort_order`
- **Fix:** Add field-level documentation for each model with types, constraints, and relationships.

### 5C.2 Add Missing Model Attributes
- **File:** `architecture/models.md`
- **Issue:** Several field definitions missing `index=True` or `nullable=` attributes:
  - `TopicNote.topic` missing `index=True` (`models/context.py:12`)
  - `TrendMemory.topic` missing `nullable=False, index=True` (`models/context.py:31`)
  - `AdminUser.password_hash` missing `nullable=False` (`models/auth.py:36`)
  - `AdminUser.backup_codes` missing `nullable=True` (`models/auth.py:39`)
  - `TrendMemory.last_accessed_at` missing `nullable=True, index=True, onupdate=` (`models/context.py:40-44`)
- **Fix:** Update field definitions to include all actual attributes.

### 5C.3 Document ThreadPoolExecutors
- **File:** `architecture/infrastructure.md`
- **Issue:** 3 ThreadPoolExecutors not documented:
  - `services/subagent/config.py:11` — subagent LLM calls (configurable `SUBAGENT_WORKERS`)
  - `services/llm/base.py:396` — batch LLM operations (`chat_structured_batch`)
  - `services/timeout.py:29-49` — cross-platform timeout support
- **Fix:** Add documentation for each executor with pool sizes and usage patterns.

### 5C.4 Show Context Managers Correctly
- **File:** `architecture/infrastructure.md`
- **Issue:** `traced_llm_call` and `traced_stage` shown as standalone functions, but they're `@contextmanager` functions (`services/logging_utils.py:251,278`). Used as `with traced_llm_call(...):`.
- **Fix:** Update signatures and usage examples to show context manager pattern.

### 5C.5 Document Missing API Endpoint
- **File:** `architecture/routes.md`
- **Issue:** `/newsletter/preview` POST endpoint exists at `routes/admin/api/newsletters.py:221` with `@require_auth` and `@validate_csrf_json` but is not documented.
- **Fix:** Add to Admin API endpoints table.

### 5C.6 Document LLM Types
- **File:** `architecture/llm-providers.md`
- **Issue:** Several types not documented:
  - `chat_structured_batch()` and `BatchError` (`services/llm/base.py`)
  - `ToolCall`, `ToolResult`, `ToolCallingResponse` dataclasses (`schemas/llm_responses.py:186-202`)
- **Fix:** Add to Key Types section.

### 5C.7 Fix Schema Location Contradiction
- **File:** `architecture/subagent.md` (line 140)
- **Issue:** Doc says Chain schemas are in `runner.py` (line 140) then correctly says they're in `schemas/pipeline.py` (line 204). The line 140 claim is incorrect.
- **Fix:** Update line 140 to reference `schemas/pipeline.py:108-118`.

### 5C.8 Document Subagent Package Structure
- **File:** `architecture/overview.md`
- **Issue:** `services/subagent/` package structure not documented in module index.
- **Fix:** Add package structure: `runner.py`, `chain.py`, `tools.py`, `registry.py`, `middleware.py`, `conditions.py`, `prompt_templates.py`, `config.py`, `utils.py`.

### 5C.9 Document `WebhookCreate` and `WebhookResponse` Schemas
- **File:** `architecture/schemas.md`
- **Issue:** `schemas/webhook.py` defines these schemas used by webhook API routes but they're undocumented.
- **Fix:** Add schema documentation.

---

## Wave 6: Quality, Typing & Docs (Medium Priority) ⏳ REMAINING

*Focus: Long-term health and documentation.*

### 6.1 Boost Test Coverage to 80%
- **Target Modules:** `tasks/newsletter.py`, `tasks/edit.py`, `tasks/research.py`, `adapters/api.py`.
- **Action:** Write unit tests for missing branches/statements identified in `coverage_report.md`.
- **Status:** NOT DONE - Still at 62% coverage

### 6.2 Mypy Resolution
- **Goal:** Fix all 423 Mypy errors.
- **Strategy:** Use `isinstance()` for AST narrowing in `conditions.py`; add `cast()` for `Any` returns; fix implicit `Optional` in `logging_utils.py`.
- **Status:** NOT DONE - Errors increased from 22+ to 423

### 6.3 OpenAPI & Documentation Sync
- **OpenAPI:** Sync `openapi.yaml` with actual routes (fix `/api/v1/` prefixes).
- **Docs:** Update `trend-memory.md` (topic column size), `security.md` (scrypt), and create `key_rotation.md`.
- **Status:** PARTIALLY DONE - Files exist, sync status unknown

---

## Wave 7: Infrastructure & Polish (Long-term) ⏳ REMAINING

*Focus: Containerization and observability.*

### 7.1 Docker Hardening
- Implement multi-stage builds, non-root users, and `read_only` filesystem in `docker-compose.yml`.
- **Status:** PARTIALLY DONE - Non-root user only, missing read_only and multi-stage builds

### 7.2 Observability Fixes
- Fix OTel defaults and add `is_fully_healthy` semantics to health checks.
- **Status:** PARTIALLY DONE - OTel defaults done, missing is_fully_healthy property

---

## Parallelization Map

The following waves can be executed **in parallel** within each wave (independent tasks):

```
Wave 5A (Code Bugs - 4 independent tasks):
├── 5A.1 Add max_retries to Celery tasks
├── 5A.2 Fix propose_trend_memory return type doc
├── 5A.3 Document PipelineRootConfig.experiments
└── 5A.4 Fix degradation behavior documentation

Wave 5B (Doc Accuracy - 12 independent tasks):
├── 5B.1 Fix chat_structured signature
├── 5B.2 Fix stage transitions table
├── 5B.3 Fix newsletter endpoint name
├── 5B.4 Document RawItem schema
├── 5B.5 Fix content extractor fallback doc
├── 5B.6 Fix reload_beat_schedule doc
├── 5B.7 Update prompt file count
├── 5B.8 Fix extract_json function name
├── 5B.9 Fix subagent YAML config example
├── 5B.10 Fix search providers YAML example
├── 5B.11 Clarify normal flow doesn't include review
└── 5B.12 Document newsletter idempotency key TTL

Wave 5C (Doc Gaps - 9 independent tasks):
├── 5C.1 Document missing models
├── 5C.2 Add missing model attributes
├── 5C.3 Document ThreadPoolExecutors
├── 5C.4 Show context managers correctly
├── 5C.5 Document missing API endpoint
├── 5C.6 Document LLM types
├── 5C.7 Fix schema location contradiction
├── 5C.8 Document subagent package structure
└── 5C.9 Document WebhookCreate/WebhookResponse schemas

Wave 6 (Quality - 3 independent tasks):
├── 6.1 Boost test coverage to 80%
├── 6.2 Fix Mypy errors
└── 6.3 Sync OpenAPI docs

Wave 7 (Infrastructure - 2 independent tasks):
├── 7.1 Docker hardening
└── 7.2 Observability fixes
```

**Dependency Notes:**
- Waves 5A, 5B, 5C can all run in parallel (no dependencies between them)
- Wave 6 can run after Wave 5 (documentation fixes won't conflict with test/type work)
- Wave 7 is independent of all other waves
- Within each wave, all tasks are fully parallelizable (use subagents)

---

## Success Metrics

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| Test Pass Rate | 99% | 100% | ✅ 100% |
| Test Coverage | 62% | 80% | ⏳ 62% |
| Mypy Errors | 22+ | 0 | ❌ 423 |
| Ruff Errors | 0 | 0 | ✅ 0 |
| Layer Violations | ~6 | 0 | ✅ 0 |
| P1 Security Issues | 3 | 0 | ✅ 0 |
| Architecture Doc Bugs | 21 | 0 | ⏳ 21 (2H, 7M, 12L) |
| Architecture Doc Accuracy | 864/905 | 905/905 | ⏳ 864 verified |

---

## Implementation History (Completed)
- Wave 1: Critical Fixes & Stability (2026-05-31)
- Wave 2: Architecture & Reliability (2026-05-31)
- Wave 3: Advanced Security (2026-05-31)
- Wave 4: Performance & Optimization (2026-05-31)

---

## Architecture Review Summary

From 15 architecture document reviews (863 verified claims):

| Document | Verified | Incorrect | Bugs | Priority |
|----------|----------|-----------|------|----------|
| overview.md | 138 | 0 | 1 (LOW) | ✅ Accurate |
| config.md | 92 | 0 | 1 (MED) | ⏳ Minor fix |
| infrastructure.md | 68 | 2 | 3 (LOW) | ⏳ Minor fixes |
| schemas.md | 58 | 6 | 3 (1H, 1M, 1L) | ❌ Needs work |
| adapters.md | 48 | 3 | 1 (MED) | ⏳ Minor fix |
| routes.md | 47 | 1 | 1 (LOW) | ⏳ Minor fix |
| models.md | 42 | 6 | 6 (1M, 5L) | ⏳ Missing docs |
| utils.md | 42 | 0 | 0 | ✅ Accurate |
| services.md | 38 | 3 | 1 (HIGH) | ❌ Wrong return type |
| pipeline.md | 38 | 6 | 1 (MED) | ❌ Wrong degradation |
| tasks.md | 35 | 5 | 3 (2M, 1L) | ❌ Incomplete |
| subagent.md | 35 | 4 | 2 (HIGH) | ❌ Wrong YAML example |
| llm_providers.md | 32 | 6 | 0 | ⏳ Minor fixes |
| search_providers.md | 28 | 3 | 1 (HIGH) | ❌ Wrong YAML example |
| prompts.md | 22 | 3 | 1 (LOW) | ⏳ Minor fix |

**Top 3 Critical Documentation Issues:**
1. `propose_trend_memory` returns `SubagentResponse`, not `list[TrendMemory]` — will break callers
2. Degradation behavior table wrong — disabled stages route through `_finalize()`, not directly to next stage
3. Subagent YAML config example has non-existent fields (`tool_timeout`, `default_model`)
