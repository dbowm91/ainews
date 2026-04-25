# Consolidated Implementation Plan

**Created:** April 25, 2026
**Last Updated:** April 25, 2026
**Status:** PLANNED -- Not yet implemented

---

## Overview

This plan consolidates all pending implementation items into a single roadmap organized by execution batch. Within each batch, items can be implemented in parallel by sub-agents. Batches are ordered by dependency -- earlier batches should complete before later ones start.

**Execution Structure:**

| Batch | Contents | Sub-agents | Prerequisites |
|-------|----------|------------|---------------|
| A | Quick wins, UI/UX, small infra fixes | 8-10 | None |
| B | Testing, performance, security, architecture | 8-10 | None |
| C | Agent harness improvements | 5 | Batch A.3 (session pooling) recommended |
| D | Advanced agent features, documentation | 5-6 | Batch C recommended |

Batches A and B can run **in parallel** with each other. Batch C can start once Batch A is mostly done. Batch D follows Batch C.

---

## Batch A: Quick Wins & UI/UX

*Independent items that provide immediate value. All can be implemented in parallel by different sub-agents.*

---

### A.1 Precompile Regex in `services/llm/base.py`

**Files:** `services/llm/base.py`
**Effort:** Small (5 min)

**Current code (lines 36, 45) inside `_extract_json()`:**
```python
match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw, re.MULTILINE)
match = re.search(r'\{[\s\S]*\}', raw)
```

These patterns are recompiled on every call to `_extract_json()`, which is called from two hot-path locations (lines 199 and 239) in the same file.

**Fix:** Add module-level precompiled patterns near the top of the file:
```python
_MARKDOWN_JSON_RE = re.compile(r'```(?:json)?\s*([\s\S]+?)\s*```', re.MULTILINE)
_BRACE_JSON_RE = re.compile(r'\{[\s\S]*\}')
```

Then update `_extract_json()` to use `_MARKDOWN_JSON_RE.search(raw)` and `_BRACE_JSON_RE.search(raw)`.

**Follows convention in:** `services/validation.py`, `schemas/tasks.py`, `routes/admin/sources.py` (all use module-level precompiled regex, documented in AGENTS.md).

**Verification:** `pytest tests/test_llm_adapters/ -x -q`

---

### A.2 Add Logging to Silent Exception Handlers (4 locations)

**Files:** `services/content_extractor.py`, `services/llm/__init__.py`, `services/trend_detector.py`, `services/health.py`
**Effort:** Small (10 min)

Four locations silently swallow exceptions with no logging. Each should add `logger.debug()` or `logger.warning()` as appropriate.

| # | File | Line | Current Code | Fix |
|---|------|------|-------------|-----|
| 1 | `services/content_extractor.py` | 60 | `except Exception: return None` | `except Exception as e: logger.warning("Content fetch failed for %s: %s", url, e); return None` |
| 2 | `services/llm/__init__.py` | 127 | `except Exception: return _fetch()` | `except Exception as e: logger.debug("Cache fallback for provider info: %s", e); return _fetch()` |
| 3 | `services/trend_detector.py` | 83 | `except Exception: pass` | `except Exception as e: logger.debug("Failed to load patterns from file: %s", e)` |
| 4 | `services/trend_detector.py` | 97 | `except Exception: return _load_patterns_from_file()` | `except Exception as e: logger.debug("Config cache failed for trend patterns: %s", e); return _load_patterns_from_file()` |

**Convention:** Use %-formatting in log calls (`logger.warning("msg: %s", e)`), not f-strings. See AGENTS.md "Logging conventions" section.

**Note:** `tasks/extract.py:343` was originally listed but already has logging on the outer except block -- the inner `except Exception: pass` is for metrics fallback and is intentionally silent.

**Note:** `services/health.py:183` (reading `.git/HEAD` for commit hash) was originally listed. This is borderline -- in production containers `.git/HEAD` doesn't exist so logging would be noisy. Add `logger.debug()` only if desired.

**Verification:** `pytest tests/ -x -q`

---

### A.3 Subagent Thread Pool Configurability

**Files:** `services/subagent.py`
**Effort:** Small (5 min)

**Current code (line 28):**
```python
_subagent_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="subagent")
```

Hardcoded `max_workers=8`. `os` is not imported in this file.

**Fix:**
```python
import os

SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "8"))
_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, thread_name_prefix="subagent")
```

**Follows convention in:** `services/content_extractor.py` (lines 14-19) which uses `CONTENT_EXTRACTOR_WORKERS` env var. See AGENTS.md "Configurable thread pools".

**Verification:** `pytest tests/test_subagent.py -x -q`

---

### A.4 Add Cost Pricing for Additional Providers

**Files:** `services/cost_tracker.py`
**Effort:** Small (10 min)

**Current `_DEFAULT_RATES` (lines 17-24) only covers:** openai/gpt-4o, openai/gpt-4o-mini, openai/gpt-4-turbo, anthropic/claude-sonnet-4, anthropic/claude-haiku, anthropic/claude-opus-4.

**Missing providers** (configured in `providers.yaml` but have no pricing -- cost silently reports as $0.00):

| Key | Input ($/1M tokens) | Output ($/1M tokens) |
|-----|--------------------|--------------------|
| `"deepseek/deepseek-chat"` | 0.27 | 1.10 |
| `"minimax/MiniMax-M2.5"` | 0.20 | 1.10 |
| `"gemini/gemini-2.0-flash"` | 0.10 | 0.40 |
| `"groq/llama-3.3-70b-versatile"` | 0.59 | 0.79 |
| `"openrouter/anthropic/claude-3.5-sonnet"` | 3.00 | 15.00 |
| `"xai/grok-2-1212"` | 2.00 | 10.00 |
| `"togetherai/meta-llama/Llama-3-70b-chat-hf"` | 0.80 | 0.80 |
| `"fireworks/accounts/fireworks/models/llama-v3-70b-instruct"` | 0.80 | 0.80 |
| `"cerebras/llama-3.3-70b"` | 0.85 | 1.20 |
| `"zai/glm-4"` | 1.40 | 1.40 |

Also consider adding a `logger.debug()` when `rate = rates.get(model_key)` returns `None` so unknown providers are discoverable.

**Note:** `ollama-local` runs local models (free) -- no pricing needed. Verify `opencode` provider if it exists.

**Verification:** `pytest tests/test_cost_tracker.py -x -q` (if exists) or `pytest tests/ -x -q`

---

### A.5 Search Clear Button

**Files:** `templates/partials/feed.html`, `static/css/articles.css`, `static/js/app.js`
**Effort:** Small (15 min)

**Current state:** `templates/partials/feed.html` lines 10-25 have a `<input type="search" name="q">` with HTMX attributes but no explicit clear/reset button. Browser-native clear X is inconsistent across browsers.

**Implementation:**
1. In `feed.html` after the search input (around line 15), add:
   ```html
   <button type="button" class="search-clear" aria-label="Clear search">&times;</button>
   ```
2. In `static/css/articles.css` (alongside `.search-container` and `.search-input` per AGENTS.md "CSS module architecture"), add CSS for positioning the button inside the search container and toggling visibility based on input value.
3. In `static/js/app.js`, add JS to clear the input value and trigger HTMX refresh on click.

**Verification:** Manual browser test + `pytest tests/ -x -q`

---

### A.6 Base Font Size Increase (14px -> 15px)

**Files:** `static/css/variables.css`
**Effort:** Small (5 min)

**Current value** (`variables.css` line 65): `--text-base: 0.875rem; /* 14px */`

**Fix:** Change to `--text-base: 0.9375rem; /* 15px */`

**Caveat:** As noted in AGENTS.md, `--text-lg` (16px) is semantically "large" but renders as the default body size, while `--text-base` (14px) is smaller than browser default. Changing `--text-base` has cascading effects on all components using `var(--text-base)`. Audit consumers before changing.

**Verification:** Visual check + `pytest tests/ -x -q`

---

### A.7 Date Format Clarity

**Files:** Create `services/date_utils.py`, modify `templates/partials/article_card.html`
**Effort:** Small (20 min)

**Current state:** Dates use raw `strftime` calls directly in templates:
- `article_card.html` line 10: `{{ article.created_at.strftime('%b %d') }}` (e.g., "Jan 15")
- `article_card.html` line 49: `{{ article.created_at.strftime('%b %d, %Y') }}` (e.g., "Jan 15, 2025")

`services/date_utils.py` does NOT exist yet.

**Implementation:**

1. Create `services/date_utils.py` with a `format_date(dt)` function:
   - < 24 hours: "X hours ago" / "yesterday"
   - < 7 days: "X days ago"
   - < 1 year: "MMM d"
   - Previous year: "MMM d, YYYY"

2. Register as Jinja2 filter in `app.py` (where other template filters are registered):
   ```python
   @app.template_filter("format_date")
   def _format_date(dt):
       from services.date_utils import format_date
       return format_date(dt)
   ```

3. Update `article_card.html` to use `{{ article.created_at|format_date }}` instead of `strftime`.

**Note on naive vs aware datetimes:** AGENTS.md warns that `datetime.fromisoformat()` produces naive datetimes and that `Article.created_at` may be naive. The `format_date()` function should handle both naive and aware datetimes gracefully.

**Verification:** `pytest tests/ -x -q`

---

### A.8 Beat Schedule Reload Endpoint

**Files:** `routes/admin/api/config.py` (note: file is `routes/admin/api/config.py`, not `routes/admin/api.py` as originally stated)
**Effort:** Small (10 min)

**Current state:** `POST /admin/api/config/reload` in `routes/admin/api/config.py` (lines 10-31) clears config cache, provider cache, app cache, config singleton, task fn cache, and tag cache. It does **NOT** call `Config.reload_beat_schedule()`.

`Config.reload_beat_schedule()` exists at `config.py:155-169` and takes a `celery_app` argument to update `celery_app.conf.beat_schedule`.

**Fix:** After the existing cache clears (line 30), add:
```python
from celery import current_app as celery_current
Config.reload_beat_schedule(celery_current)
```

**Note:** `celery_current` may not be available in Flask request context. Check how other code accesses the Celery app -- likely via `celery_app.py` module import. If `reload_beat_schedule` needs a celery app instance, import it from `celery_app` module.

**Verification:** `pytest tests/test_admin_api.py -x -q`

---

### A.9 `traced_stage()` Integration

**Files:** `services/logging_utils.py`, `tasks/pipeline.py`
**Effort:** Small (15 min)

**Current state:** `traced_stage()` is defined at `services/logging_utils.py:262-281` but **never called** anywhere. Meanwhile `traced_llm_call()` (line 234) IS used in `tasks/select.py:69`, `tasks/research.py:121`, `tasks/write.py:48`, and `tasks/edit.py:269`.

**Fix:** Wire `traced_stage()` into `run_stage()` at `tasks/pipeline.py:158` to wrap non-LLM work within each pipeline stage. This provides distributed tracing for the full stage execution span (not just the LLM call).

**Alternative:** If `traced_stage()` is not useful in its current form, mark it as deprecated with a docstring note.

**Verification:** `pytest tests/ -x -q`

---

### A.10 Make `TITLE_SIMILARITY_THRESHOLD` Configurable

**Files:** `services/article.py` (NOT `constants.py` as originally stated)
**Effort:** Small (10 min)

**Current state:** `TITLE_SIMILARITY_THRESHOLD = 0.5` is defined at `services/article.py:51`. Used at line 262 as default parameter: `threshold: float = TITLE_SIMILARITY_THRESHOLD`. It is **NOT** in `constants.py`.

**Fix:** Make it configurable via env var or `pipeline.yaml`:
```python
TITLE_SIMILARITY_THRESHOLD = float(os.environ.get("TITLE_SIMILARITY_THRESHOLD", "0.5"))
```

Or use the `get_config_with_default()` pattern from `services/config_utils.py` for Celery compatibility (see AGENTS.md "Celery tasks must not use `current_app.config`").

**Verification:** `pytest tests/test_article.py -x -q` (if exists) or `pytest tests/ -x -q`

---

## Batch B: Testing, Performance, Security & Architecture

*These items are independent of Batch A and can run in parallel with it. Within Batch B, items can also run in parallel.*

---

### B.1 Fix Test Mock Return Values

**Priority:** HIGH -- causes ~10-12 pre-existing test failures
**Files:** `tests/test_pipeline_e2e.py`, `tests/test_pipeline_edit.py`, `tests/test_pipeline_write.py`, `tests/test_llm_adapters/test_anthropic.py`
**Effort:** Medium (30 min)

**Problem:** Test work functions return **plain dicts** like `{"article_id": article.id, "result": article.selector_result}`, but `run_stage()` in `tasks/pipeline.py:257-259` accesses `.tokens_used` on the return:
```python
result = work_fn(article, provider, model, max_tokens)
record_provider_success(provider_id, model, tokens_used=result.tokens_used)
```

A plain dict has no `.tokens_used` attribute, causing `AttributeError`.

**Affected test files (spot-checked):**
| Test File | Issue |
|-----------|-------|
| `tests/test_pipeline_e2e.py` | Work functions (lines 96, 114, 133, 150) return dicts |
| `tests/test_pipeline_edit.py` | Multiple edit tests missing `final_article` field |
| `tests/test_pipeline_write.py` | `test_write_populates_draft` mock setup incomplete |
| `tests/test_llm_adapters/test_anthropic.py` | `test_chat_with_schema` missing `betas` kwarg |

**Fix approach:** Test work functions should return objects with a `.tokens_used` attribute. Options:
1. Return `LLMResponse` instances from `services/llm/base.py:57-61` (preferred)
2. Use `SimpleNamespace(tokens_used=100, ...)`
3. Or make `run_stage()` use `getattr(result, 'tokens_used', 0)` for robustness

**Note:** The issue is NOT in `tests/helpers/pipeline_mocks.py` (which correctly returns a 4-tuple for `get_provider_for_role`). The issue is in the individual test work functions.

**Verification:** `pytest tests/test_pipeline_e2e.py tests/test_pipeline_edit.py tests/test_pipeline_write.py tests/test_llm_adapters/test_anthropic.py -x -q`

---

### B.2 Test Helper Refactoring

**Files:** `tests/test_subagent.py`, `tests/test_pipeline_edit.py`, `tests/test_pipeline_write.py`
**Effort:** Medium (30 min)

**Items:**
1. Refactor `tests/test_pipeline_edit.py` and `tests/test_pipeline_write.py` to use `setup_pipeline_mocks` helper from `tests/helpers/pipeline_mocks.py`
2. Consider splitting `tests/test_subagent.py` (994 lines) by test class into separate files for maintainability

**Note:** Originally listed adding `LREM` and `SMEMBERS` to `tests/mock_redis.py`, but these Redis commands are not used anywhere in the codebase. Removed as unnecessary.

**Verification:** `pytest tests/ -x -q`

---

### B.3 HTTP Session Pooling for Search Providers

**Files:** Create `services/search/session.py`, modify `services/search/searxng.py`, `services/search/google.py`
**Effort:** Medium (30 min)

**Current state:** Both `searxng.py:32-36` and `google.py:29-37` use `requests.get()` directly, creating a new TCP connection per call. `duckduckgo.py` uses the `duckduckgo_search` library's context manager -- leave as-is.

**Implementation:**

1. Create `services/search/session.py`:
   ```python
   import os
   import requests
   from requests.adapters import HTTPAdapter
   from urllib3.util.retry import Retry

   _SEARCH_POOL_MAXSIZE = int(os.environ.get("SEARCH_POOL_MAXSIZE", "10"))
   _SEARCH_POOL_CONNECTIONS = int(os.environ.get("SEARCH_POOL_CONNECTIONS", "5"))

   _search_session = None

   def get_session() -> requests.Session:
       global _search_session
       if _search_session is None:
           session = requests.Session()
           retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
           adapter = HTTPAdapter(pool_connections=_SEARCH_POOL_CONNECTIONS, pool_maxsize=_SEARCH_POOL_MAXSIZE, max_retries=retry)
           session.mount("http://", adapter)
           session.mount("https://", adapter)
           _search_session = session
       return _search_session
   ```

2. Update `searxng.py`: Replace `requests.get(...)` with `get_session().get(...)` at lines 32 and 83.
3. Update `google.py`: Replace `requests.get(...)` with `get_session().get(...)` at lines 29 and 90.

**Note:** DuckDuckGo uses context manager from `duckduckgo_search` library -- leave unchanged.

**Verification:** `pytest tests/ -x -q`

---

### B.4 Duplicate Detection Memory Optimization

**Files:** `services/article.py`
**Effort:** Small (10 min)

**Current code (`services/article.py:307`):**
```python
.limit(1000)
```

Hardcoded in `find_duplicate_titles()`. The function already breaks on first match (line 314), so the full 1000 rarely loads.

**Fix:**
```python
DUPLICATE_DETECTION_LIMIT = int(os.environ.get("DUPLICATE_DETECTION_LIMIT", "200"))
# ...
.limit(DUPLICATE_DETECTION_LIMIT)
```

Use 200 as default (reduced from 1000) since the function breaks on first match anyway.

**Verification:** `pytest tests/ -x -q`

---

### B.5 Add `index=True` to `Article.updated_at` in Model

**Files:** `models.py`
**Effort:** Small (5 min)

**Current state:** `models.py:128-131` has `updated_at` without `index=True`:
```python
updated_at = db.Column(
    db.DateTime,
    default=lambda: datetime.now(timezone.utc),
)
```

**Note:** The index already exists at the database level via migration `026_article_updated_at_index.py`. The fix is to add `index=True` to the model definition for consistency (so `db.create_all()` in tests also creates it).

**Fix:** Add `index=True`:
```python
updated_at = db.Column(
    db.DateTime,
    default=lambda: datetime.now(timezone.utc),
    index=True,
)
```

No new migration needed -- the index already exists in production.

**Verification:** `pytest tests/ -x -q`

---

### B.6 Newsletter Dead Letter Retry Task

**Files:** `tasks/newsletter.py`, `config.py`
**Effort:** Medium (30 min)

**Current gap:** Permanently failed newsletter emails (SMTP 5xx) are returned as error dicts from `send_single_email` but never aggregated or retried. `_send_emails_parallel` fires emails via Celery groups (fire-and-forget).

**Newsletter model fields** (`models.py:185-186`): `delivered_count` (Integer, default=0), `error_message` (Text, nullable).

**Implementation:**
1. Create `retry_failed_newsletter_deliveries` Celery task in `tasks/newsletter.py`
2. Query `Newsletter` where `error_message IS NOT NULL`
3. Re-attempt delivery using same `autoretry_for`/`dont_autoretry_for` pattern as `send_single_email` (see AGENTS.md "autoretry_for over manual self.retry()" convention)
4. Add to Celery beat schedule in `config.py` `get_beat_schedule()` -- every 2 hours

**Pattern to follow:** `send_single_email` task in `tasks/newsletter.py`

**Verification:** `pytest tests/test_newsletter.py -x -q`

---

### B.7 Split Trend Memory Consolidation into Two Tasks

**Files:** `tasks/cleanup.py`, `config.py`
**Effort:** Small (15 min)

**Current state:** The Celery task `consolidate_trend_memory` in `tasks/cleanup.py:119-144` calls two independent functions sequentially:
- `consolidate_all_topics()` -- promotes LOW to MEDIUM importance
- `purge_expired()` -- deletes expired memory entries

These are **already separate functions** in `services/trend_memory.py` (lines 336-347 and 350-362). The task just calls both.

**Fix:**
1. Split into two Celery tasks in `tasks/cleanup.py`:
   - `consolidate_trend_memory` -- calls `consolidate_all_topics()` only
   - `purge_trend_memory` -- calls `purge_expired()` only
2. Stagger in beat schedule: consolidation at 3:30 AM, purge at 3:45 AM
3. Update `config.py` `get_beat_schedule()` with both entries

**Verification:** `pytest tests/test_trend_memory.py -x -q` (if exists) or `pytest tests/ -x -q`

---

### B.8 Secret Rotation Support

**Files:** `config.py`, `services/task_security.py`, `services/webhooks.py`
**Effort:** Medium (45 min)

**Components:**

1. **Flask `SECRET_KEY_FALLBACKS`** -- In `config.py`, add:
   ```python
   SECRET_KEY_FALLBACKS = [
       v for v in [
           os.environ.get("SECRET_KEY_PREVIOUS_1", ""),
           os.environ.get("SECRET_KEY_PREVIOUS_2", ""),
       ] if v
   ]
   ```
   Flask 2.3+ natively supports `SECRET_KEY_FALLBACKS` for session cookie rotation.

2. **Celery task secret rotation** -- In `services/task_security.py`, update `_get_task_secret()` to support multiple secrets:
   ```python
   def _get_task_secrets() -> list[str]:
       primary = os.environ.get("CELERY_TASK_SECRET", "")
       fallback = os.environ.get("CELERY_TASK_SECRET_PREVIOUS", "")
       return [s for s in [primary, fallback] if s]
   ```
   Update `verify_task()` to try each secret in order (primary first, fallbacks after).

3. **Webhook key versioning** -- In `services/webhooks.py`, embed key version in encrypted ciphertext (prefix like `v1:enc:...` or `v2:enc:...`). `_decrypt_secret()` checks version and uses the corresponding key. Store `WEBHOOK_SECRET_KEY_PREVIOUS` for old-key decryption.

**Verification:** `pytest tests/test_task_security.py tests/test_webhooks.py -x -q`

---

### B.9 Audit Logging Expansion

**Files:** `models.py`, new migration, `routes/admin/subscribers.py`, `routes/admin/api/articles.py`
**Effort:** Medium (30 min)

**Current `AuditLog` model** (`models.py:448-463`): Has `action`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at`. No `category` column.

**Implementation:**
1. Add `category` column (String(32), indexed, nullable=True) to `AuditLog` model
2. Create migration for the new column
3. Add audit calls for:
   - Subscriber CSV export (in `routes/admin/subscribers.py`)
   - Bulk article operations (in `routes/admin/api/articles.py`)
4. Use categories: "auth", "article", "pipeline", "webhook", "config", "subscriber"
5. Log IDs not emails per GDPR considerations

**Verification:** `pytest tests/test_admin_api.py -x -q`

---

### B.10 Request Size Limits Enhancement

**Files:** `routes/admin/api/articles.py`
**Effort:** Small (5 min)

**Current state:** `bulk_article_operations()` at line 184 has `@require_auth` and `@validate_csrf_json` but no `@limit_content_length()`. Global fallback is `MAX_CONTENT_LENGTH = 64KB` in `config.py:35`.

**Fix:** Add explicit per-route limit. Since the bulk endpoint accepts max 500 article IDs (~10 digits each) + action + tags, expected payload is well under 10KB:
```python
from routes.public import limit_content_length

@limit_content_length(32768)  # 32KB -- generous upper bound for bulk ops
```

**Verification:** `pytest tests/test_admin_api.py -x -q`

---

### B.11 Enforce Pipeline State Machine Validation

**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `services/pipeline_failure.py`, `services/pipeline_degradation.py`
**Effort:** Medium (30 min)

**Problem:** All pipeline task files use direct `article.pipeline_status = PipelineStatus.X` assignment, bypassing `_transition_article_status()` which validates transitions against `VALID_TRANSITIONS` in `constants.py:40-49`.

**`_transition_article_status()` is defined at** `tasks/pipeline.py:127-145` but only called once (line 241, in the timeout dead-letter handler).

**Direct assignments to replace (verified locations):**
| File | Line | Current | Target Status |
|------|------|---------|--------------|
| `tasks/select.py` | 85 | `= PipelineStatus.RESEARCHING` | RESEARCHING |
| `tasks/select.py` | 110 | `= PipelineStatus.SKIPPED` | SKIPPED |
| `tasks/research.py` | 53 | `= PipelineStatus.RESEARCHING` | RESEARCHING |
| `tasks/research.py` | 136 | `= PipelineStatus.WRITING` | WRITING |
| `tasks/write.py` | 63 | `= PipelineStatus.EDITING` | EDITING |
| `tasks/edit.py` | 142 | `= PipelineStatus.REVIEW` | REVIEW |
| `tasks/edit.py` | 163 | `= PipelineStatus.REVIEW` | REVIEW |
| `tasks/edit.py` | 190 | `= PipelineStatus.DONE` | DONE |
| `services/pipeline_failure.py` | 78 | `= PipelineStatus.FAILED` | FAILED |
| `services/pipeline_failure.py` | 101 | `= PipelineStatus.FAILED` | FAILED |
| `services/pipeline_failure.py` | 134 | `= PipelineStatus.FAILED` | FAILED |

Also check `services/pipeline_degradation.py` for additional direct assignments.

**Caveats:**
- `PipelineStatus.SELECTING` exists in the enum but is NOT in `VALID_TRANSITIONS`. Check if it should be added.
- The FAILED -> PENDING reprocess path (in admin bulk reprocess) may need `VALID_TRANSITIONS` updates.
- Test files are intentionally excluded (they mock state).

**Verification:** `pytest tests/ -x -q`

---

### B.12 Docker Compose for Development

**Files:** `docker-compose.yml`, `.env.docker` (template)
**Effort:** Medium (30 min)

**Services:** redis, web, worker, beat, (optional) flower
**Key configs:**
- Health checks for all services
- `worker_prefetch_multiplier=1` for Celery worker
- Persistent volumes for Redis data
- `.env.docker` template with all required env vars documented

**Verification:** `docker compose config` (validate file)

---

### B.13 CI/CD Pipeline Setup

**Files:** `.github/workflows/ci.yml`, `.github/workflows/cd.yml`
**Effort:** Medium (45 min)

**ci.yml:** Ruff lint, pytest, type check on PR
**cd.yml:** Build Docker, push to registry, deploy on push to main

**Verification:** Push to a PR branch and verify CI runs.

---

## Batch C: Agent Harness Improvements

*Recommended to start after Batch A completes. Items within this batch have some dependencies.*

---

### C.1 Enable Tool-Calling in Research/Edit Stages

**Files:** `services/subagent.py`, `schemas/pipeline.py`, `tasks/research.py`, `tasks/edit.py`
**Effort:** Large (60 min)

**Current state (verified):**
- `resolve_subagent_config()` in `schemas/pipeline.py:175-204` builds kwargs and passes through: `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`. It does **NOT** pass `tools` (defined at line 101: `tools: list[str] = Field(default_factory=list)`). The field is silently dropped.
- `run_subagent_with_tools()` exists at `services/subagent.py:608-787` and is fully implemented with retry/fallback logic. But it is **never called** from any pipeline task.
- Tool definitions exist: `_build_context_tools()` (lines 41-266) defines `get_topic_note`, `get_topic_notes_for_topics`, `get_related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`. `_build_search_tools()` (lines 269-323) defines `search_web`, `get_search_provider`.
- Pipeline tasks call `run_subagent()` (which uses `chat_structured`) instead of `run_subagent_with_tools()`.

**Implementation:**
1. In `schemas/pipeline.py:resolve_subagent_config()`, add `tools` field to kwargs dict (~line 202):
   ```python
   if stage_config.tools:
       kwargs["tools"] = stage_config.tools
   ```
2. In `tasks/research.py` and `tasks/edit.py`, check if config has `tools` and call `run_subagent_with_tools()` instead of `run_subagent()` when present.
3. Ensure graceful fallback when provider doesn't support tools (`run_subagent_with_tools()` should detect and fall back to `run_subagent()`).

**Verification:** `pytest tests/test_subagent.py -x -q`

---

### C.2 Multi-Provider Fallback Chain

**Files:** `services/llm/__init__.py`
**Effort:** Large (60 min)

**Current behavior (verified):** `get_provider_for_role()` only tries a fallback provider when the primary's circuit breaker is OPEN (after 5 failures in 120s window). There is **no per-request error-to-fallback** wiring.

**Errors that should trigger immediate fallback (but don't):**
| Error | Rationale |
|-------|----------|
| `RateLimitError` | Another provider may have capacity |
| `ProviderTimeoutError` | Transient, try another provider |
| `ProviderServerError` | 5xx from one provider, another may work |
| `ConnectionError` | Network issue to one endpoint |

**Fatal errors (don't catch/fallback):**
| Error | Rationale |
|-------|----------|
| `AuthError` | Invalid API key -- all providers would fail |
| `CircuitOpenError` | All circuits open -- wait for recovery |

**Implementation:** Add `get_provider_chain()` function in `services/llm/__init__.py` that returns an ordered list of `(provider, model, max_tokens, provider_id)`, filtering out open circuits. Pipeline stages iterate through the chain on recoverable errors.

**Verification:** `pytest tests/test_llm_fallback.py -x -q` (may need new test file)

---

### C.3 Context Injection in Research/Write Stages

**Files:** `services/researcher.py`, `services/writer.py`, `tasks/research.py`, `tasks/write.py`
**Effort:** Medium (45 min)

**Current state (verified):**
- **Research** (`tasks/research.py`): HAS related articles (via `find_related_articles_dicts()` at lines 100-103, passed to `build_research_prompt()`). Does NOT have topic notes or trend memory.
- **Write** (`tasks/write.py`): NO additional context beyond `title`, `topics`, `research_brief`, `max_key_points` (see `services/writer.py:23-43`).
- **Edit** (`tasks/edit.py`): HAS topic notes, related articles, AND trend memory (via `_gather_editor_context()` at lines 69-119).

**What's needed:**
1. **Research stage** -- Add topic notes via `get_topic_notes_for_topics()` from `services/context_service.py`. Pass to `build_research_prompt()` as new parameter.
2. **Write stage** -- Add trend memory via `get_memory_for_topics()` from `services/trend_memory.py`. Pass to `build_writer_prompt()` as new parameter.
3. **Writer** -- Add `trend_memory` parameter to `build_writer_prompt()` in `services/writer.py`.

**Caveat:** Adding too much context risks token bloat. Research already has related articles. Be selective about what additional context truly improves output.

**Verification:** `pytest tests/test_pipeline_research.py tests/test_pipeline_write.py -x -q`

---

### C.4 Quality Gates Per Stage

**Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`
**Effort:** Medium (30 min)

**Current state (verified):**
- **Select stage** ALREADY has a quality gate: `if result.selected and result.score >= (rc.min_score or 6)` at line 84. Articles below threshold are set to `PipelineStatus.SKIPPED`. Threshold is configurable via `RoleConfig.min_score` in `schemas/pipeline.py:23`.
- **Research stage** has NO validation of `ResearchBrief` output. Brief is produced and immediately advances to WRITING.
- **Write stage** has NO validation of `CondensedArticle` output. Draft is saved and immediately advances to EDITING.

**What's needed:**
1. **Research stage:** Validate that brief has non-empty key claims and a reasonable impact score. Route degenerate outputs to REVIEW instead of auto-advancing.
2. **Write stage:** Validate minimum article length, presence of key points, and citation count. Route degenerate outputs to REVIEW.

**Note:** Select stage is already done -- no changes needed there.

**Verification:** `pytest tests/ -x -q`

---

### C.5 Add Type Hints to Admin Routes

**Files:** `routes/admin/auth.py`, `routes/admin/dashboard.py`, `routes/admin/sources.py`, `routes/admin/webhooks.py`, `routes/admin/subscribers.py`, `routes/admin/shares.py` and any others
**Effort:** Small (20 min)

**Current state (verified):** API routes in `routes/admin/api/articles.py` have some type hints. Page-rendering routes (`auth.py`, `dashboard.py`, `sources.py`, `webhooks.py`) uniformly lack return type annotations.

**Fix:** Add `-> str | Response` (for page-rendering routes) or `-> tuple[Response, int] | Response` (for API routes) return type annotations to all admin route handlers.

**Note:** This is a code quality improvement, not a bug fix. Low priority.

**Verification:** `ruff check . --exclude .venv` + `pytest tests/ -x -q`

---

## Batch D: Advanced Agent Features & Documentation

*Batch D depends on Batch C completing. Items within Batch D can run in parallel.*

---

### D.1 Feedback Loop from Published Articles

**Files:** `models.py`, `services/newsletter.py`, `routes/public/links.py`, `services/trend_memory.py`
**Effort:** Large (60 min)

**Phase 1 -- Tracking:**
1. Add `newsletter_clicks` column to `ArticleMetric` model
2. Create tracking endpoint `/track/newsletter-click/<int:article_id>` (add to public routes)
3. Use trackable URLs in newsletter templates

**Phase 2 -- Feedback Integration:**
1. Enhance `propose_trend_memory()` to include engagement data
2. Create `recalculate_impact_scores` nightly Celery task

**Verification:** `pytest tests/ -x -q`

---

### D.2 Confidence Scoring in Responses

**Files:** `schemas/llm_responses.py`, `tasks/select.py`, `tasks/research.py`
**Effort:** Medium (30 min)

**Implementation:**
1. Add `confidence: str = Field(default="medium", pattern="^(low|medium|high)$")` to `SelectionResult` in `schemas/llm_responses.py`
2. Update selection prompt (in `pipeline.yaml`) to request confidence field
3. Route low-confidence selections to REVIEW instead of automatically advancing

**Verification:** `pytest tests/test_select.py -x -q`

---

### D.3 Trend Memory SQL Consolidation

**Files:** `services/trend_memory.py`
**Effort:** Small (15 min)

**Current:** `consolidate_topic()` iterates in Python to promote LOW to MEDIUM importance.

**Fix:** Replace Python loop with a single SQL UPDATE statement:
```python
db.session.execute(
    update(TrendMemory)
    .where(
        TrendMemory.topic == topic,
        TrendMemory.importance == MemoryImportance.LOW.value,
        TrendMemory.id.in_(
            select(TrendMemory.id).where(
                TrendMemory.topic == topic,
                TrendMemory.importance == MemoryImportance.HIGH.value
            )
        )
    )
    .values(importance=MemoryImportance.MEDIUM.value)
)
```

**Verification:** `pytest tests/ -x -q`

---

### D.4 A/B Testing for Prompts

**Files:** `pipeline.yaml`, `models.py`, `tasks/select.py`, `routes/admin/api.py`
**Effort:** Large (60 min)

**Implementation:**
1. Add `experiments` config section in `pipeline.yaml`
2. Add `experiment_group` column to `Article` model + migration
3. Assign variant in select stage
4. Track results for comparison

**Verification:** `pytest tests/ -x -q`

---

### D.5 Context Window Optimization

**Files:** `services/prompts.py`, `services/writer.py`, `services/editor.py`
**Effort:** Small (15 min)

**Implementation:** Add sliding window truncate helper to `services/prompts.py`:
```python
def sliding_window_truncate(text: str, max_chars: int = 8000, ellipsis: str = "\n\n[... truncated ...]\n\n") -> str:
    if not text or len(text) <= max_chars:
        return text
    half = (max_chars - len(ellipsis)) // 2
    return text[:half] + ellipsis + text[-half:]
```

Apply to `research_brief` in write stage and draft in edit stage to prevent token overflow.

**Verification:** `pytest tests/ -x -q`

---

### D.6 Critical Metric Naming Fixes in Documentation

**Files:** `docs/monitoring.md`
**Effort:** Small (10 min)

**Docs show vs. code emits (verified):**
| Docs Show | Code Emits | Code Location |
|----------|------------|---------------|
| `circuit_breaker_state_change` | `circuit_breaker.state_change` | `services/circuit_breaker.py:80` |
| `pipeline_stage_duration_seconds` | `pipeline.stage_duration_seconds` | pipeline tasks |

`MetricsCollector._make_key()` at `services/metrics.py:60-65` preserves the name as-is (with dots). Tests also use dot notation.

**Fix:** Update `docs/monitoring.md` to use the actual dot-separated metric names. Also add documentation for `pipeline_sla_seconds` histogram.

**Verification:** Manual review of docs.

---

### D.7 New Documentation Files

**Files:** `docs/pipeline.md`, `docs/operations.md`, `docs/webhooks.md`, `docs/analytics.md`
**Effort:** Large (60 min)

| File | Contents |
|------|----------|
| `docs/pipeline.md` | State machine diagram, degradation system, retry budget, per-stage failure tracking, duplicate detection |
| `docs/operations.md` | All 9 Celery Beat tasks, dead letter queue, config cache reload, task HMAC signing, distributed lock pattern |
| `docs/webhooks.md` | All 7 API endpoints, event types, encryption at rest, trigger integration, idempotency |
| `docs/analytics.md` | Search analytics endpoint, topic notes CRUD, subscriber export, pipeline SLA endpoint |

**Verification:** Manual review for accuracy.

---

### D.8 Documentation Fixes

**Files:** `docs/api.md`, `docs/fallback-providers.md`, `docs/development.md`, `docs/runbook.md`, `docs/configuration.md`, `docs/components/badge.md`
**Effort:** Medium (30 min)

| File | Fix |
|------|-----|
| `docs/api.md` | Add missing endpoints, workflow context, error examples |
| `docs/fallback-providers.md` | Fix outdated API format, document all providers |
| `docs/development.md` | Correct pipeline flow, add env vars reference, add LLM provider docs |
| `docs/runbook.md` | Add missing admin endpoints |
| `docs/configuration.md` | Add Celery Beat schedule section |
| `docs/components/badge.md` | Remove `.confidence-label` (not in CSS) |

**Verification:** Manual review.

---

## Items Verified as Already Done (No Action Needed)

| Item | Finding |
|------|---------|
| `tasks/edit.py:300` commit | Already has try/except with rollback |
| `services/subagent.py:1029` silent except | Intentional -- returns False appropriately |
| `retry_stuck` / `publish_scheduled` autoretry | Fail-closed is correct design |
| Lock release pattern | Uses atomic `release_lock` from redis_utils |
| `services/trend_memory.py` unbounded loading | Self-bounded by TTLs |
| ResponseCache L1/L2 | 2-tier caching with stampede protection |
| Eager loading | Consistent joinedload usage |
| ThreadPoolExecutor usage | Proper non-blocking I/O |
| Streaming CSV export | Uses `yield_per(500)` |
| Database indexes | All critical indexes in place (including `updated_at` via migration 026) |
| ARIA attributes on filter tabs | Already present in `templates/partials/feed.html` |
| Shares toggle logic | Properly implemented in `routes/admin/shares.py:15-28` |
| AGENTS.md task count | Already correctly says "Nine" and lists all 9 tasks |
| `tasks/extract.py:343` bare except | Outer except already has logging; inner metrics catch is intentionally silent |

---

## Deferred Items (Do Not Implement Without Explicit Direction)

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
| Trend memory admin UI | Nice-to-have |
| Public API rate limiting | AGENTS.md says don't add `@limiter.limit()` |
| Pagination cursor-based | Works for current scale |
| Global LLM circuit breaker | Per-provider sufficient |
| Batch duplicate detection | Current approach sufficient |
| Redis pool segregation | Hasn't hit limits |
| CSS minification | CDN handles gzip |
| Announcement banner | Only if needed |
| Tool expansion/validation | Low ROI |
| Admin route fragmentation | Current split acceptable |
| Tool registry auto-init | Optional |
| Input/output token separation | Requires provider changes |
| Provider logprobs confidence | Complex, not universal |
| Ollama tool-calling | Not all models support |
| Full editor with tools | Higher effort |
| Persistent DuckDuckGo instance | Rate limits make pooling less impactful |

---

## Testing Requirements

### Before any changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each batch:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Some LLM adapter tests may have pre-existing failures unrelated to code changes (per AGENTS.md).

---

## Rollback Methods

| Change | Rollback Method |
|--------|----------------|
| Precompiled regex | Remove constants, revert to inline `re.search()` |
| Type hints | Remove `-> Response` annotations |
| Database index (model only) | Remove `index=True` from model |
| Logging additions | Revert logger calls |
| Session pooling | Remove session import, revert to `requests.get()` |
| Duplicate limit | Revert to hardcoded `limit(1000)` |
| Subagent workers | Remove env var, revert to `max_workers=8` |
| Cost pricing | Remove pricing entries |
| State machine | Revert to direct assignment |
| Docker Compose | Remove `docker-compose.yml` |
| CI/CD pipeline | Remove `.github/workflows/` |
| Secret rotation | Remove fallback env vars |
| Audit category | Drop column via migration |

---

## Sub-agent Assignment Recommendations

| Sub-agent | Items | Estimated Time |
|-----------|-------|---------------|
| **Performance** | A.1 (regex), A.2 (logging), A.3 (thread pool), A.4 (cost pricing) | 30 min |
| **UX** | A.5 (search clear), A.6 (font size), A.7 (date format) | 40 min |
| **Infra-small** | A.8 (beat reload), A.9 (traced_stage), A.10 (threshold config) | 35 min |
| **Testing** | B.1 (mock fixes), B.2 (test helpers) | 60 min |
| **Performance-2** | B.3 (session pooling), B.4 (dup limit), B.5 (index) | 45 min |
| **Newsletter** | B.6 (dead letter retry), B.7 (trend memory split) | 45 min |
| **Security** | B.8 (secret rotation), B.9 (audit logging), B.10 (size limits) | 80 min |
| **Architecture** | B.11 (state machine), B.12 (docker), B.13 (CI/CD) | 105 min |
| **Agent-harness** | C.1 (tools), C.2 (fallback), C.3 (context), C.4 (quality gates), C.5 (type hints) | 195 min |
| **Advanced** | D.1-D.5 (advanced features) | 180 min |
| **Docs** | D.6-D.8 (documentation) | 100 min |

---

*Consolidated April 25, 2026*
