# Consolidated Improvement Plan

## Overview

Consolidated plan merging all prior planning documents into a single source of truth. Items are organized into **waves** — groups of work that can be executed in parallel by separate sub-agents. Each wave contains independent sub-tasks that do not depend on each other.

### Scope Summary

| Domain | Source Plan | Focus |
|--------|-------------|-------|
| Codebase Health | Plan 5 | Critical bugs, security, conventions, error handling, DRY, performance, tests |
| Pipeline | Plan 4 | Quality validation, observability, configuration, degradation |
| AI Agent Toolset | Plan 2 | Subagent observability, tool calling, configurable prompts, admin UI |
| UI/UX | Plan 3 | CSS consistency, accessibility, performance, visual polish |

---

## Completion Status

**All 65 items across 8 waves are COMPLETED.** Last updated: 2026-04-05.

| Wave | Items | Status |
|------|-------|--------|
| 1 — Critical Bugs & Security | 11 | ✅ All completed |
| 2 — Conventions & DRY | 8 | ✅ All completed |
| 3 — UI Bug Fixes | 5 | ✅ All completed |
| 4 — Subagent Observability | 7 | ✅ All completed |
| 5 — Pipeline Quality | 7 | ✅ All completed |
| 6 — New Features | 9 | ✅ All completed |
| 7 — Accessibility & Performance | 11 | ✅ All completed |
| 8 — Test Improvements | 7 | ✅ All completed |

---

## Wave 1: Critical Bugs & Security Fixes

**Priority**: Highest — fix immediately. These are runtime errors and security gaps.

**Parallelization**: All items are independent. Assign to 2-3 sub-agents.

### Agent A — Critical Bugs (Backend)

#### 1.1 Fix `current_app.config` in Celery Task
- **Problem**: `tasks/cleanup.py:51` calls `current_app.config.get("VERIFICATION_EXPIRY_SECONDS")` from a Celery task running outside Flask app context. Raises `RuntimeError`.
- **Fix**: Use `get_config_with_default()` from `services/config_utils.py`.
- **Files**: `tasks/cleanup.py`
- **Tests**: Add test verifying `cleanup_expired_verifications` runs without Flask app context.

#### 1.2 Fix Silent DB Commit Failure in `run_stage()`
- **Problem**: `tasks/pipeline.py` catches `db.session.commit()` failure, rolls back, but continues to return `result`. Caller thinks stage succeeded but DB changes were lost.
- **Fix**: Re-raise the exception after rollback. The `finally` block will still release the lock and limiter slot.
- **Files**: `tasks/pipeline.py`
- **Tests**: Add test verifying commit failure propagates as exception.

#### 1.3 Fix Unprotected Redis `get()` in Newsletter Lock Logic
- **Problem**: `tasks/newsletter.py:314` calls `redis_client.get(lock_key)` without try/except. If `get()` fails with `RedisError`, the task crashes.
- **Fix**: Wrap in `try/except redis.exceptions.RedisError`, falling through to the `acquire_lock` path.
- **Files**: `tasks/newsletter.py`
- **Tests**: Add test verifying newsletter lock logic handles RedisError on `get()`.

#### 1.4 Fix Naive/Aware Datetime Comparison in Article Filtering
- **Problem**: `routes/admin/articles.py:94,101` uses `datetime.fromisoformat()` which returns naive datetimes, compared against timezone-aware `Article.created_at`.
- **Fix**: Normalize parsed datetimes to UTC-aware: if naive, call `.replace(tzinfo=timezone.utc)`.
- **Files**: `routes/admin/articles.py`
- **Tests**: Add test with both naive and aware datetime inputs.

#### 1.5 Fix Uncaught `KeyError` in Subagent Template Formatting
- **Problem**: `services/subagent.py:89` calls `template.format(**prompt_data)` without try/except. Missing key raises uncaught `KeyError`.
- **Fix**: Wrap in try/except `KeyError`, log warning, return empty synthesis.
- **Files**: `services/subagent.py`
- **Tests**: Add test for missing template keys.

#### 1.6 Fix Unprotected Dict Key Access in Ollama Provider
- **Problem**: `services/llm/ollama.py:47` accesses `resp["message"]["content"]` without checking if `"message"` key exists.
- **Fix**: Use `.get()` with defaults or add existence checks.
- **Files**: `services/llm/ollama.py`
- **Tests**: Add test for malformed Ollama response.

#### 1.7 Fix `raise last_exc` When `last_exc` Could Be None
- **Problem**: `services/degradation.py:81` raises `last_exc`. If `functions` tuple is empty, `last_exc` is never assigned.
- **Fix**: Guard against empty input — return original value or raise descriptive error.
- **Files**: `services/degradation.py`
- **Tests**: Add test for empty functions tuple.

#### 1.8 Fix Missing Socket Exception Types in URL Validation
- **Problem**: `services/url.py:147` catches `socket.gaierror` and `TimeoutError` but `socket.getaddrinfo` can also raise `socket.herror` and `socket.timeout`.
- **Fix**: Add `socket.herror` and `socket.timeout` to the except clause.
- **Files**: `services/url.py`
- **Tests**: Add tests for DNS resolution error variants.

### Agent B — Security Fixes

#### 2.1 Add SSRF Validation to Webhook URLs
- **Problem**: `routes/admin/api/webhooks.py` accepts webhook URLs without SSRF validation. `test_webhook` endpoint dispatches HTTP requests to stored URL.
- **Fix**: Call `validate_url_safe()` from `services/url.py` in create, update, and test endpoints. Also validate in `services/webhooks.py` in `dispatch_webhook()` as defense-in-depth.
- **Files**: `routes/admin/api/webhooks.py`, `services/webhooks.py`
- **Tests**: Add tests for webhook URL validation: private IPs, localhost, DNS rebinding.

#### 2.2 Add SSRF Validation to Source URLs
- **Problem**: `routes/admin/sources.py:37` stores `source_url` from form input without validation.
- **Fix**: Call `validate_url_safe()` before storing.
- **Files**: `routes/admin/sources.py`
- **Tests**: Add test for source URL SSRF validation.

#### 2.3 Fix Session Clear Wiping CSRF Token
- **Problem**: `routes/admin/auth.py:52` calls `session.clear()` on successful login, wiping the CSRF token.
- **Fix**: Replace `session.clear()` with `session.pop("admin", None)`.
- **Files**: `routes/admin/auth.py`
- **Tests**: Verify CSRF token persists after login.

---

## Wave 2: Convention Enforcement & DRY Refactoring

**Priority**: High — low risk, high consistency value. Pure refactoring.

**Parallelization**: All items are independent. Assign to 2-3 sub-agents.

### Agent A — Naming & Logging Conventions

#### 3.1 Fix `self.redis` → `self._redis` in Cache Classes
- **Problem**: `services/cache.py:42` and `services/config_cache.py:79` use `self.redis` instead of `self._redis`.
- **Fix**: Rename attribute in both classes.
- **Files**: `services/cache.py`, `services/config_cache.py`
- **Tests**: Run existing suite — no behavior change.

#### 3.2 Fix f-strings in Log Calls
- **Problem**: `services/logging_utils.py:34,60,84` uses f-strings. AGENTS.md requires %-formatting.
- **Fix**: Convert to %-formatting:
  - `f"Pipeline [{stage}]: {event}"` → `"Pipeline [%s]: %s", stage, event`
  - `f"Article {article_id}: {event}"` → `"Article %s: %s", article_id, event`
  - `f"Admin [{user}] {action}"` → `"Admin [%s] %s", user, action`
- **Files**: `services/logging_utils.py`
- **Tests**: Run existing suite.

#### 3.3 Fix `float()` on Env Var Without Try/Except
- **Problem**: `services/cost_tracker.py:107-108` calls `float(os.environ.get(...))` without try/except.
- **Fix**: Use `safe_int()` / `safe_float()` pattern from `services/config_unified.py`, or wrap in try/except with fallback.
- **Files**: `services/cost_tracker.py`
- **Tests**: Add test for malformed env var.

### Agent B — Constants & Pattern Consistency

#### 3.4 Replace String Literals with `PipelineStatus` Constants
- **Problem**: Multiple files use string literals (`"done"`, `"skipped"`, `"failed"`) instead of `PipelineStatus` constants.
- **Locations**:
  - `services/related.py:19,76` — `"done"`
  - `services/dead_letter.py:105` — `"failed"`
  - `routes/public/feeds.py:147,185,228,255` — `"done"`, `"skipped"`
- **Fix**: Import `PipelineStatus` from `constants` and use constants.
- **Files**: `services/related.py`, `services/dead_letter.py`, `routes/public/feeds.py`
- **Tests**: Run existing suite.

#### 3.5 Fix Bare `Exception` Catches for Redis Operations
- **Problem**: Several locations catch bare `Exception` instead of `redis.exceptions.RedisError`:
  - `routes/admin/dashboard.py:48` — Redis ping
  - `tasks/pipeline.py:396` — lock release in `finally`
  - `tasks/scheduler.py:72` — lock release in `finally`
- **Fix**: Narrow to `redis.exceptions.RedisError`.
- **Files**: `routes/admin/dashboard.py`, `tasks/pipeline.py`, `tasks/scheduler.py`
- **Tests**: Run existing suite.

#### 3.6 Fix Bare `Exception` in `edit.py` Commit Handler
- **Problem**: `tasks/edit.py:178` catches bare `Exception` for `db.session.commit()` instead of `SQLAlchemyError`.
- **Fix**: Change to `SQLAlchemyError`.
- **Files**: `tasks/edit.py`
- **Tests**: Run existing suite.

### Agent C — DRY Consolidation

#### 3.7 Consolidate `_STAGE_STATUS_MAP`
- **Problem**: Same stage-to-status mapping in `tasks/pipeline.py:42` and `services/pipeline_degradation.py:11`.
- **Fix**: Extract to `constants.py` as `STAGE_STATUS_MAP`, import in both locations.
- **Files**: `constants.py`, `tasks/pipeline.py`, `services/pipeline_degradation.py`
- **Tests**: Run existing suite. Add test verifying shared map is importable from both locations.

#### 3.8 Consolidate `_get_max_stage_retries()` and `_get_max_total_retries()`
- **Problem**: Duplicate implementations in `tasks/pipeline.py:22-39` and `services/pipeline_failure.py:10-17`.
- **Fix**: Keep single implementation in `services/pipeline_failure.py`, import in `tasks/pipeline.py`.
- **Files**: `services/pipeline_failure.py`, `tasks/pipeline.py`
- **Tests**: Run existing suite.

---

## Wave 3: UI Bug Fixes & Consistency

**Priority**: High — user-facing fixes. Independent of backend changes.

**Parallelization**: CSS, JS, and template items are independent. Assign to 2 sub-agents.

### Agent A — CSS Fixes

#### 4.1 Sync `critical.css` with `variables.css`
- **Problem**: `critical.css` defines `--text-dim: #9ea7b0` while `variables.css` defines `--text-dim: #adbac7`. Light mode also differs.
- **Fix**: Update `critical.css` to match `variables.css` exactly for all shared tokens. Regenerate inlined partials.
- **Files**: `static/css/critical.css`, `templates/partials/critical_css.html`, `templates/partials/critical_css_admin.html`

#### 4.2 Move `.search-kbd` CSS to Correct Module
- **Problem**: `.search-kbd` is in `pages.css` (admin) but used in `feed.html` (public). Belongs in `articles.css`.
- **Fix**: Move `.search-kbd` and related `.search-container .search-input` padding rule from `pages.css` to `articles.css`.
- **Files**: `static/css/pages.css`, `static/css/articles.css`

#### 4.3 Fix Admin Nav Scroll Fade Background Dependency
- **Problem**: `pages.css:445-454` uses `var(--bg-secondary)` for gradient fade. Brittle if header background changes.
- **Fix**: Use `inherit` or `currentColor` with alpha, or `mask-image` gradient approach. ✅ COMPLETED — Uses mask-image gradient with --bg-secondary background.
- **Files**: `static/css/pages.css`

#### 4.4 Standardize Button Border-Radius
- **Problem**: Button variants use inconsistent border-radius: `.btn` = `5px`, `.subscribe-btn` = `4px`, `--radius-md` = `4px`, `--radius-lg` = `6px`.
- **Fix**: Use `var(--radius-md)` or `var(--radius-lg)` consistently. ✅ COMPLETED — All 14 hardcoded border-radius values replaced with var(--radius-*) variables.
- **Files**: `static/css/components.css`

### Agent B — JS & Template Fixes

#### 4.5 Remove Inline `onfocusout` from Share Macro
- **Problem**: `templates/partials/share_macro.html:2` uses `onfocusout="this.open=false"` — inline handler violating CSP pattern. `app.js` already has a `focusout` handler.
- **Fix**: Remove the `onfocusout` attribute.
- **Files**: `templates/partials/share_macro.html`

---

## Wave 4: Subagent Observability & Core Improvements

**Priority**: High — subagent system is used in production but lacks visibility.

**Parallelization**: Items are mostly independent. Assign to 2 sub-agents.

### Agent A — Observability & Reliability

#### 5.1 Subagent Observability & Metrics
- **Problem**: Subagent failures are logged as warnings only. No metrics, dead-letter tracking, or alerting.
- **Fix**:
  - Wrap `run_subagent()` body with `time_histogram("subagent.duration_seconds", labels={"stage": stage, "task_type": task_type})`
  - Emit `subagent.calls` counter with success/failure labels
  - On success: `get_metrics().counter_inc("subagent.success", labels={"stage": stage, "task_type": task_type})`
  - On failure: `get_metrics().counter_inc("subagent.failure", labels={"stage": stage, "task_type": task_type})`
- **Files**: `services/subagent.py`, `tests/test_subagent.py`

#### 5.2 Structured Logging for Subagent Calls
- **Problem**: Subagent calls use basic `logger.warning()` on failure. No structured logging with article_id, stage, duration, or model info.
- **Fix**:
  - Add optional `article_id` parameter to `run_subagent()`
  - Use `log_pipeline_event(stage="subagent", ...)` from `services/logging_utils`
  - Log `subagent.start`, `subagent.complete`, `subagent.failure` events
  - Pass `article_id=article.id` from `tasks/research.py` and `tasks/edit.py`
- **Files**: `services/subagent.py`, `tasks/research.py`, `tasks/edit.py`, `tests/test_subagent.py`

#### 5.3 Subagent Retry Mechanism
- **Problem**: Subagent calls have no retry logic. Transient network errors cause immediate fallback to empty synthesis.
- **Fix**:
  - Add `max_retries` (default 1) and `retry_delay` (default 5s) to `SubagentStageConfig`
  - Wrap `provider.chat_structured()` in retry loop for transient errors (`ProviderTimeoutError`, `ConnectionError`, `TimeoutError`)
  - Do NOT retry on `AuthError` or `ProviderServerError`
- **Files**: `schemas/pipeline.py`, `services/subagent.py`, `pipeline.yaml`, `tests/test_subagent.py`

#### 5.4 Subagent Timeout Enforcement
- **Problem**: `timeout_seconds` is defined in `SubagentStageConfig` but never enforced in `run_subagent()`.
- **Fix**:
  - Wrap `provider.chat_structured()` in `ThreadPoolExecutor` with `timeout=stage_config.timeout_seconds`
  - Use `cancel_futures=True` on shutdown
  - On timeout, return fallback response and log warning
- **Files**: `services/subagent.py`, `tests/test_subagent.py`

### Agent B — Configuration & Provider Resolution

#### 5.5 Move Subagent Templates to Configurable Prompts
- **Problem**: Subagent task templates are hardcoded in `services/subagent.py` as `_SUBAGENT_TASK_TEMPLATES`. Not configurable via YAML or `prompts/` directory.
- **Fix**:
  - Add `task_template` field under each subagent stage config in `pipeline.yaml`
  - Add `task_template: Optional[str]` to `SubagentStageConfig` in `schemas/pipeline.py`
  - Default templates move to `prompts/subagent_research_synthesis.txt` and `prompts/subagent_edit_contextualization.txt`
  - `run_subagent()` loads template from: stage config → prompt file → hardcoded fallback
- **Files**: `pipeline.yaml`, `schemas/pipeline.py`, `services/subagent.py`, `prompts/subagent_research_synthesis.txt` (new), `prompts/subagent_edit_contextualization.txt` (new), `tests/test_subagent.py`

#### 5.6 Subagent Provider Fallback Should Not Be Editor-Biased
- **Problem**: When subagent doesn't specify its own provider/model, it falls back to the `editor` role. Research synthesis might benefit from the `researcher` role's model.
- **Fix**:
  - `resolve_subagent_config()`: Accept optional `default_role` parameter
  - If `provider`/`model` are null, fall back to stage-matching role (research → researcher, edit → editor)
  - Pass appropriate role name based on `task_type` when resolving config
- **Files**: `schemas/pipeline.py`, `services/subagent.py`, `tests/test_subagent.py`

#### 5.7 Enable Subagents with Sensible Defaults
- **Problem**: Both `research` and `edit` subagents are `enabled: false` in `pipeline.yaml`.
- **Fix**: Set `research.enabled: true`, `edit.enabled: true` in `pipeline.yaml`. Both already fail gracefully.
- **Files**: `pipeline.yaml`

---

## Wave 5: Pipeline Quality & Reliability

**Priority**: Medium — additive improvements to pipeline behavior.

**Parallelization**: Items are mostly independent. Assign to 2 sub-agents.

### Agent A — Pipeline Quality

#### 6.1 Add Post-Edit Content Quality Validation
- **Problem**: After edit stage produces `final_article`, there's no validation that output is non-empty, structurally valid, or contains required fields.
- **Fix**: Add `validate_final_article()` function that checks:
  - `final_article` is valid JSON
  - Required fields present: `headline`, `tldr`, `body`
  - `body` is non-empty and contains at least one paragraph
  - `headline` is non-empty and under 120 characters
  - Called in `tasks/edit.py` after successful edit, before transitioning to `DONE` or `REVIEW`
- **Files**: `services/article_validation.py` (new), `tasks/edit.py`, `tests/test_article_validation.py` (new)

#### 6.2 Decouple Extract → Select Dispatch
- **Problem**: `tasks/extract.py:process_item` directly calls `select_article.delay()` instead of using `_dispatch_next()`. Creates invisible coupling.
- **Fix**: After creating article with `pipeline_status="pending"`, use `_dispatch_next(article.id, run_id=run_id, next_status="pending")` instead of direct `select_article.delay()`. Preserve existing try/except error handling.
- **Files**: `tasks/extract.py`
- **Tests**: Update `tests/test_extract.py` to verify dispatch goes through standard mechanism.

#### 6.3 Add Pipeline-Level Timeout Tracking
- **Problem**: Individual stages have `soft_time_limit=300s`, but an article can cycle through retries and autoretries for 30+ minutes.
- **Fix**: Track article pipeline start time and add hard timeout check in `run_stage()`. If `now - start_time > PIPELINE_TIMEOUT_SECONDS` (default 3600s), mark as `FAILED` and dead-letter. ✅ COMPLETED — Added pipeline_started_at column (migration 015), timeout check in run_stage(), timestamp set in extract.py and reprocess routes.
- **Files**: `config.py`, `tasks/pipeline.py`, `constants.py`, `models.py` (add `pipeline_started_at` column or reuse `created_at`), `tests/test_pipeline/`

#### 6.4 Improve Degradation Quality for Multi-Stage Failures
- **Problem**: When multiple stages degrade in sequence, article quality compounds poorly.
- **Fix**:
  - Add `degradation_count` column to Article model (Integer, default 0, server_default="0", nullable=False)
  - Increment `degradation_count` in `_apply_degrade_config()` and `_degrade_edit_stage()`
  - When `degradation_count >= 2`, route directly to `REVIEW` status
  - Increment in `tasks/retry.py` when `_degrade_and_advance()` is called
- **Files**: `models.py`, `migrations/`, `services/pipeline_degradation.py`, `tasks/retry.py`, `tests/`

### Agent B — Pipeline Observability & Hardening

#### 6.5 Add Degradation Metrics and Alerting
- **Problem**: No visibility into how often articles degrade or which stages fail most frequently.
- **Fix**:
  - Emit `pipeline.degradation` counter with labels `{stage, reason}`
  - Emit `pipeline.multi_stage_degradation` counter when `degradation_count >= 2`
  - Add degradation rate to admin pipeline stats endpoint
  - Add Prometheus alert rule for degradation rate > 5% over 15 minutes ✅ COMPLETED — Degradation rate added to pipeline_stats endpoint, Prometheus alert rules documented in monitoring.md.
- **Files**: `services/pipeline_degradation.py`, `services/metrics.py`, `routes/admin/api.py` (or relevant pipeline stats module), `docs/monitoring.md`

#### 6.6 Harden Limiter Slot Release
- **Problem**: If both release attempts fail in `ModelLimiter.release()`, the slot leaks until TTL expires.
- **Fix**: Add periodic cleanup task (Celery Beat, every 5 minutes) that scans for stale limiter keys and releases them if holder task is no longer active.
- **Files**: `tasks/cleanup.py` (or `tasks/retry.py`), `config.py` (Celery Beat schedule), `services/limiter.py` (add `cleanup_stale_slots()` method), `tests/`

#### 6.7 Document Fallback LLM Provider Configuration
- **Problem**: All stages use `ollama-local` with `qwen3:8b`. 13 alternative providers defined in `providers.yaml` but all `enabled: false`.
- **Fix**: Documentation only — document how to enable fallback providers, configure fallback chains per stage, and test circuit breaker failover.
- **Files**: `docs/fallback-providers.md` (new)

---

## Wave 6: New Features — Tool Calling & Admin UI

**Priority**: Medium — new capabilities. Depends on Wave 4 for subagent improvements.

**Parallelization**: Tool calling (backend) and Admin UI (frontend) are independent. Assign to 2 sub-agents.

### Agent A — LLM Tool/Function Calling

#### 7.1 Add Tool/Function Calling Support to LLM Providers
- **Problem**: System exclusively uses structured JSON output. Agents cannot call external functions or tools during generation.
- **Fix**:
  - `services/llm/base.py`: Add `chat_with_tools(messages, tools, tool_choice, model, system, temperature, max_tokens)` abstract method. Define `ToolDefinition` dataclass/Pydantic model.
  - `services/llm/openai.py`: Implement using `tools` parameter and `tool_choice` on `chat.completions.create()`. Handle `tool_calls` in response, execute tool function, continue conversation loop.
  - `services/llm/anthropic.py`: Implement using `tools` parameter on `messages.create()`. Handle `tool_use` content blocks.
  - `services/llm/ollama.py`: Implement using Ollama's tool calling support.
  - `services/llm/gemini.py`: Implement using Gemini's function calling API.
  - `schemas/llm_responses.py`: Add `ToolCall`, `ToolResult`, `ToolCallingResponse` models.
- **Design decisions**:
  - Tool execution happens synchronously within the calling task
  - Tool definitions passed as list of `ToolDefinition` objects
  - Provider handles conversation loop (tool call → execute → continue) up to configurable max iterations
  - Start with OpenAI and Anthropic (best tool calling support), then Ollama and Gemini
- **Files**: `services/llm/base.py`, `services/llm/openai.py`, `services/llm/anthropic.py`, `services/llm/ollama.py`, `services/llm/gemini.py`, `schemas/llm_responses.py`, `tests/test_llm_adapters/`

#### 7.2 Expand Subagent System to Support Custom Tools
- **Problem**: Subagents are single-shot structured output calls. Cannot use tools to fetch additional information.
- **Fix**:
  - Add `run_subagent_with_tools(task_type, stage, prompt_data, tools, response_model)` variant in `services/subagent.py`
  - Uses the new `chat_with_tools` from providers
  - Supports built-in tool registry (web search, DB lookup, topic notes)
  - Expose `context_service.py` functions as callable tools
  - Wrap `services/search/__init__.py` `search_web` and `get_search_provider` as tool definitions
  - Add `tools` list under subagent stage configs in `pipeline.yaml` ✅ COMPLETED — tools lists added to research and edit subagent stages in pipeline.yaml.
- **Files**: `services/subagent.py`, `services/context_service.py`, `services/search/`, `pipeline.yaml`, `schemas/pipeline.py`, `tests/test_subagent.py`

#### 7.3 Subagent Chaining & Multi-Step Orchestration
- **Problem**: Subagents are single-shot calls. No multi-step agent reasoning or iterative refinement.
- **Fix**:
  - Add `run_subagent_chain(steps)` function in `services/subagent.py`
  - Each step: `{task_type, prompt_data_template, response_model, condition}`
  - Steps can reference outputs of previous steps via template variables
  - Max chain length enforced (default 5)
  - Each step independently respects enabled/disabled config
  - Add `SubagentChainStep` and `SubagentChainConfig` models to `schemas/pipeline.py`
  - Add `chains` section under `subagent` in `pipeline.yaml` ✅ COMPLETED — chains section added with research_deep and edit_review configs in pipeline.yaml.
- **Design decisions**:
  - Chains are synchronous (each step waits for previous)
  - If any step fails, chain returns partial results with fallback markers
  - Chain steps can have `condition` expressions
- **Files**: `services/subagent.py`, `schemas/pipeline.py`, `pipeline.yaml`, `tests/test_subagent.py`

#### 7.4 Response Model Validation Error Reporting
- **Problem**: When `chat_structured()` fails Pydantic validation, raw exception is raised. No structured error reporting or retry with validation feedback.
- **Fix**:
  - Catch `ValidationError` in `chat_structured()` in `services/llm/base.py`
  - If validation fails, retry once with validation error appended to prompt as feedback
  - Log validation failures with raw response for debugging
  - Add `max_validation_retries` parameter (default 1)
- **Files**: `services/llm/base.py`, `tests/test_llm_adapters/test_shared.py`

### Agent B — Admin UI & UX Features

#### 7.5 Admin UI for Topic Notes
- **Problem**: `TopicNote` has full CRUD in `context_service.py` but no admin web interface.
- **Fix**:
  - `routes/admin/topic_notes.py` (new): CRUD routes for topic notes
  - `templates/admin/topic_notes.html` (new): List view with search/filter, create/edit form
  - `templates/admin/partials/topic_note_row.html` (new): HTMX swap target
  - Register blueprint in `routes/admin/__init__.py`
- **Files**: `routes/admin/topic_notes.py` (new), `templates/admin/topic_notes.html` (new), `templates/admin/partials/topic_note_row.html` (new), `routes/admin/__init__.py`, `tests/test_admin_topic_notes.py` (new)

#### 7.6 Add Theme Transition
- **Problem**: Theme toggle is instant with no transition. Switching feels jarring.
- **Fix**: Add `transition` on `background-color` and `color` to `body` and key surfaces. In `theme.js`, add `.theme-transitioning` class before toggling, remove after `requestAnimationFrame` to avoid transition on initial page load.
- **Files**: `static/css/base.css` or `variables.css`, `static/js/theme.js`

#### 7.7 Add Skeleton Loading States for Article Detail Page
- **Problem**: Article cards have skeleton loading states, but article detail page (`article.html`) does not. HTMX boost navigation shows blank flash.
- **Fix**: Create `skeleton_article_detail.html` partial with placeholder shapes for title, meta, TL;DR, key points, and body. Trigger via HTMX indicators.
- **Files**: `templates/partials/skeleton_article_detail.html` (new), `templates/article.html`, `static/css/articles.css`

#### 7.8 Add HTMX Error Toast with Retry Capability
- **Problem**: `app.js:101-111` shows generic "Request failed" toast. Doesn't show actual error, status code, or offer retry.
- **Fix**: Parse error response to show status code and message. Add "Retry" button that re-triggers failed request. Auto-dismiss after 8s for error toasts.
- **Files**: `static/js/app.js`, `static/css/components.css`

#### 7.9 Add Loading States to Admin Bulk Operations
- **Problem**: Bulk article operations have no visual feedback. Button doesn't show spinner or disabled state.
- **Fix**: Add `hx-indicator` and `hx-disabled-elt` attributes to bulk action buttons. Style disabled state with spinner. ✅ COMPLETED — hx-disabled-elt="this" added to all three bulk action buttons.
- **Files**: `templates/admin/articles.html`, `static/css/components.css`

---

## Wave 7: Accessibility & Performance

**Priority**: Medium — user-facing polish and performance improvements.

**Parallelization**: Accessibility and performance items are independent. Assign to 2 sub-agents.

### Agent A — Accessibility

#### 8.1 Add `aria-label` to Article Card Links
- **Problem**: Article card titles are `<a>` tags inside `.card-title`. Screen readers announce title text but not context.
- **Fix**: Add `aria-label="Read article: {{ article.title }}"` to card title links.
- **Files**: `templates/partials/article_card.html`

#### 8.2 Add Focus Trap to Share Dropdown
- **Problem**: Share dropdown closes on `focusout` but doesn't trap focus. Tab key can escape while open.
- **Fix**: Implement focus trap that cycles focus within dropdown when open. Return focus to trigger button when closed.
- **Files**: `static/js/app.js`, `static/js/share-a11y.js`

#### 8.3 Add `aria-live` Region for Admin Search Result Count
- **Problem**: Admin search updates article results via HTMX but has no `aria-live` region announcing result count changes.
- **Fix**: Wrap result count / table area in `aria-live="polite"` region.
- **Files**: `templates/partials/search.html`, `templates/admin/articles.html`

### Agent B — Performance

#### 8.4 Add `content-visibility: auto` to Article Cards
- **Problem**: Long article feeds render all cards at once. `content-visibility: auto` defers off-screen card rendering.
- **Fix**: Add `content-visibility: auto; contain-intrinsic-size: 0 200px;` to `.article-card`. Test with skeleton cards to ensure HTMX swaps work.
- **Files**: `static/css/articles.css`

#### 8.5 Add Limit to URL Deduplication Query
- **Problem**: `tasks/extract.py:34` calls `.all()` on URL deduplication query without `.limit()`.
- **Fix**: Add `.limit(20)` to match title dedup pattern at line 54.
- **Files**: `tasks/extract.py`
- **Tests**: Add test verifying URL dedup respects limit.

#### 8.6 Add Batching to Stuck Article Retry
- **Problem**: `tasks/retry.py:63` calls `.all()` on stuck articles query. Memory-intensive for large counts.
- **Fix**: Use `yield_per(100)` with iterative processing, or add configurable batch size.
- **Files**: `tasks/retry.py`
- **Tests**: Add test for large stuck article counts.

#### 8.7 Add Batching to Scheduled Article Publishing
- **Problem**: `tasks/scheduler.py:45` calls `.all()` on due articles.
- **Fix**: Use `yield_per(100)` or add configurable batch size.
- **Files**: `tasks/scheduler.py`
- **Tests**: Add test for large scheduled article counts.

#### 8.8 Add Smooth Scroll Behavior
- **Problem**: No `scroll-behavior: smooth` on `html`. Anchor links jump abruptly.
- **Fix**: Add `scroll-behavior: smooth` to `html` rule. Wrap in `@media (prefers-reduced-motion: no-preference)`.
- **Files**: `static/css/base.css`

#### 8.9 Add Hover Micro-Interaction to Article Cards
- **Problem**: Cards have `translateY(-2px)` on hover but shadow change is subtle.
- **Fix**: Increase shadow spread on hover from `0 4px 12px` to `0 8px 24px`. Add subtle border color brightening.
- **Files**: `static/css/articles.css`

#### 8.10 Add `:has()` Selector for Card Hover Improvements
- **Problem**: When hovering a link inside an article card, the entire card doesn't respond.
- **Fix**: Add `.article-card:has(a:hover)` rule. Use `@supports` guard for browsers without `:has()` support.
- **Files**: `static/css/articles.css`

#### 8.11 Reduce Critical CSS Duplication
- **Problem**: `critical.css` (409 lines) duplicates large portions of `variables.css`, `base.css`, and `layout.css`. Maintenance burden.
- **Fix**: Create a build step (Python script) that generates `critical_css.html` from `critical.css` automatically. Add CI check that verifies `critical.css` tokens match `variables.css`.
- **Files**: `static/css/critical.css`, `templates/partials/critical_css.html`, `templates/partials/critical_css_admin.html`, `templates/base.html`

---

## Wave 8: Test Improvements

**Priority**: Medium — can run in parallel with any other wave.

**Parallelization**: All items are independent. Assign to 2-3 sub-agents.

### Agent A — Provider & Pipeline Tests

#### 9.1 Add Functional Tests for OpenAI and Anthropic Providers
- **Problem**: `test_openai.py` (28 lines) and `test_anthropic.py` (25 lines) only test config validation and registry lookup. Missing: `chat()`, `chat_structured()`, error handling, health checks, lazy client initialization.
- **Fix**: Add comprehensive tests matching coverage of `test_ollama.py` (231 lines) and `test_google.py` (162 lines).
- **Files**: `tests/test_llm_adapters/test_openai.py`, `tests/test_llm_adapters/test_anthropic.py`

#### 9.2 Fix Mocked API in Pipeline Stage Tests
- **Problem**: `tests/test_pipeline/test_stages.py:157,169` mocks `MockArticle.query.get` (legacy Query API) but production code uses `db.session.get(Article, id)`.
- **Fix**: Update mocks to use `db.session.get` pattern.
- **Files**: `tests/test_pipeline/test_stages.py`

#### 9.3 Fix `_call_crawl` Helper Missing `PipelineRun`
- **Problem**: `tests/test_crawl_task.py:28,46` calls `_call_crawl(cfg)` which defaults to `run_id=1` but doesn't create a `PipelineRun`.
- **Fix**: Create a `PipelineRun` with id=1 in the helper or in each test.
- **Files**: `tests/test_crawl_task.py`

#### 9.4 Convert Manual Patch Cleanup to Context Managers
- **Problem**: `tests/test_pipeline_e2e.py:57-275` uses `try/finally` with `p.stop()` instead of `with patch(...)` context managers.
- **Fix**: Refactor to use `with patch(...)` context managers or pytest `@patch` decorators.
- **Files**: `tests/test_pipeline_e2e.py`

### Agent B — New Test Files

#### 9.5 Add SSRF Validation Tests
- **Problem**: No tests for `validate_url_safe()` SSRF prevention.
- **Fix**: Create `tests/test_url_ssrf.py` with tests for private IP ranges, localhost, DNS rebinding, valid public URLs.
- **Files**: `tests/test_url_ssrf.py` (new)

#### 9.6 Add Tests for `tasks/scheduler.py`
- **Problem**: No test file covers the scheduled publishing task.
- **Fix**: Create `tests/test_scheduler.py` with tests for publishing at scheduled time, skipping not-yet-due articles, handling failures, lock acquisition/release.
- **Files**: `tests/test_scheduler.py` (new)

#### 9.7 Remove Duplicate Test Class
- **Problem**: `tests/test_llm_adapters/test_shared.py:138-145` defines `TestProviderRegistryFull` which is a duplicate of `TestProviderRegistry`.
- **Fix**: Remove the duplicate class.
- **Files**: `tests/test_llm_adapters/test_shared.py`

---

## Wave Dependency Graph

```
Wave 1 (Critical Bugs & Security) ──────────────────────────────────────┐
Wave 2 (Conventions & DRY) ─────────────────────────────────────────────┤  Can start immediately
Wave 3 (UI Bug Fixes) ──────────────────────────────────────────────────┤  (all independent)
Wave 4 (Subagent Observability) ────────────────────────────────────────┤
Wave 5 (Pipeline Quality) ──────────────────────────────────────────────┘

Wave 6 (New Features: Tool Calling & Admin UI) ────────────────────────┐
  └── Depends on Wave 4 (subagent improvements must be in place first) │
                                                                        │
Wave 7 (Accessibility & Performance) ──────────────────────────────────┤  Can start after Waves 1-5
  └── CSS items depend on Wave 3 (UI fixes must be merged first)       │
                                                                        │
Wave 8 (Test Improvements) ────────────────────────────────────────────┘  Can run in parallel with any wave
```

## Execution Strategy

1. **Waves 1-5**: Can all start in parallel. No cross-wave dependencies.
2. **Wave 6**: Must wait for Wave 4 to complete (tool calling builds on subagent system).
3. **Wave 7**: CSS items must wait for Wave 3. Accessibility and performance items are otherwise independent.
4. **Wave 8**: Can run in parallel with any wave. Test improvements are additive and don't block other work.

## Testing Strategy

- **Waves 1-2**: Each fix includes a targeted test. Run full suite after each wave.
- **Wave 3**: Visual changes — verify in browser. Run existing suite.
- **Wave 4**: New unit tests for each new function/method. Run full suite.
- **Wave 5**: New unit tests for validation. Integration tests for timeout behavior. Migration tests for new columns.
- **Wave 6**: Tool calling tested with mock providers (not real APIs). Admin UI tested with standard patterns.
- **Wave 7**: Accessibility tested with screen reader tools. Performance tested with Lighthouse.
- **Wave 8**: Test additions only — no production code changes.

## Rollback Plan

- **Waves 1-2**: Revert commits — no data changes.
- **Wave 3**: Revert commits — visual changes only.
- **Wave 4**: Revert commits — additive changes, no breaking API changes.
- **Wave 5**: Requires migration rollback for new columns. Timeout can be disabled by setting `PIPELINE_TIMEOUT_SECONDS` very high.
- **Wave 6**: Revert commits — new features, existing functionality unchanged.
- **Wave 7**: Revert commits — additive changes only.
- **Wave 8**: Revert commits — test changes only.

## Files Summary

### New Files
- `prompts/subagent_research_synthesis.txt`
- `prompts/subagent_edit_contextualization.txt`
- `services/article_validation.py`
- `routes/admin/topic_notes.py`
- `templates/admin/topic_notes.html`
- `templates/admin/partials/topic_note_row.html`
- `templates/partials/skeleton_article_detail.html`
- `tests/test_article_validation.py`
- `tests/test_admin_topic_notes.py`
- `tests/test_url_ssrf.py`
- `tests/test_scheduler.py`
- `docs/fallback-providers.md`
- `docs/monitoring.md` (updated)

### Modified Files
- `services/subagent.py`
- `services/llm/base.py`
- `services/llm/openai.py`
- `services/llm/anthropic.py`
- `services/llm/ollama.py`
- `services/llm/gemini.py`
- `services/context_service.py`
- `services/cache.py`
- `services/config_cache.py`
- `services/logging_utils.py`
- `services/cost_tracker.py`
- `services/url.py`
- `services/degradation.py`
- `services/related.py`
- `services/dead_letter.py`
- `services/pipeline_degradation.py`
- `services/metrics.py`
- `services/pipeline_failure.py`
- `services/limiter.py`
- `schemas/pipeline.py`
- `schemas/llm_responses.py`
- `constants.py`
- `pipeline.yaml`
- `config.py`
- `models.py`
- `tasks/pipeline.py`
- `tasks/extract.py`
- `tasks/cleanup.py`
- `tasks/newsletter.py`
- `tasks/edit.py`
- `tasks/retry.py`
- `tasks/scheduler.py`
- `routes/admin/articles.py`
- `routes/admin/auth.py`
- `routes/admin/sources.py`
- `routes/admin/dashboard.py`
- `routes/admin/api/webhooks.py`
- `routes/admin/__init__.py`
- `routes/admin/api.py` (or relevant pipeline stats module)
- `routes/public/feeds.py`
- `static/css/critical.css`
- `static/css/variables.css`
- `static/css/base.css`
- `static/css/components.css`
- `static/css/articles.css`
- `static/css/pages.css`
- `static/js/app.js`
- `static/js/theme.js`
- `static/js/share-a11y.js`
- `templates/partials/share_macro.html`
- `templates/partials/critical_css.html`
- `templates/partials/critical_css_admin.html`
- `templates/partials/article_card.html`
- `templates/partials/search.html`
- `templates/article.html`
- `templates/admin/articles.html`
- `templates/base.html`
- `tests/test_subagent.py`
- `tests/test_llm_adapters/test_openai.py`
- `tests/test_llm_adapters/test_anthropic.py`
- `tests/test_llm_adapters/test_shared.py`
- `tests/test_pipeline/test_stages.py`
- `tests/test_pipeline_e2e.py`
- `tests/test_crawl_task.py`
- `tests/test_extract.py`
