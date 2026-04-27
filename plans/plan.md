# Consolidated Implementation Plan

**Created:** April 26, 2026
**Status:** COMPLETED — All waves 1-9 implemented, all plan items verified and fixed

---

## Overview

This plan consolidates all identified issues from a comprehensive codebase review into a parallelized implementation strategy. Items are organized into waves that can be executed in parallel by sub-agents.

**Key conventions for implementing agents:**
- Run `.venv/bin/ruff check . --exclude .venv` after every file change
- Run `.venv/bin/python -m pytest tests/ -x -q` before completing a wave
- Follow AGENTS.md conventions for all changes
- Add tests for each bug fix where noted
- Use %-formatting in log calls, not f-strings
- Never add `@limiter.limit()` decorators to routes
- All `db.session.commit()` must be wrapped in try/except with rollback

---

## Deferred Items (Do Not Implement)

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
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
| Search highlighting (FTS5) | Significant architectural change |
| Keyboard navigation ARIA feed | Complex, low signal |
| Reader counts display | Simple but low signal |
| Beat task last-run display | Nice to have |
| Theme toggle keyboard shortcut | Minor convenience |
| Newsletter dry-run styling | Minor |
| Docker healthchecks | Low priority |
| ThreadPool executor lazy init + atexit | Medium effort, low production impact |
| Notification system (AdminPreference model) | Significant new feature |
| Subagent topic scope isolation | Medium effort, needs design |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage |
| Search result caching | Nice-to-have optimization |
| Search provider fallback chain | Nice-to-have optimization |
| Config version coordination | High complexity |
| Audit log decorator | Nice-to-have |

---

## WAVE 1: Independent Critical Fixes (Fully Parallel)

Each item can be implemented by a separate agent with no cross-dependencies.

---

### wave1_1: Wrong field reference in pipeline stats API

**File:** `routes/admin/api/pipeline.py:130`
**Verified:** Yes — `s.last_error` is a Text field (string), calling `.isoformat()` on it crashes with `AttributeError` when non-empty
**Status:** FIXED — `s.last_error.isoformat()` changed to `s.disabled_at.isoformat()` at line 130
**Severity:** Critical — crash bug
**Effort:** Trivial

**Current code:**
```python
"disabled_at": s.last_error.isoformat() if s.last_error else None,
```

**Fix:**
```python
"disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
```

**Test:** Add test with non-empty `last_error` on source to verify the endpoint returns successfully. Existing `test_authenticated` in `test_admin_api.py` doesn't set `last_error`.

---

### wave1_2: Invalid state transition + silent failure in extract task

**File:** `tasks/extract.py:185-191`
**Verified:** Yes — direct `pipeline_status = "failed"` at line 183 bypasses state machine
**Status:** FIXED — replaced with `db.session.rollback()` + re-raise, no direct status assignment
**Severity:** Critical — data integrity violation
**Effort:** Low

**Current code (lines 180-187):**
```python
try:
    _dispatch_next(article_id, run_id=run_id, next_status="pending")
except Exception as e:
    article.pipeline_status = "failed"
    article.last_error = "Failed to dispatch to pipeline"
    db.session.commit()
    logger.error("Failed to dispatch select_article for article %s: %s", article_id, e)
    raise
```

**Fix — remove direct status assignment and commit, use rollback:**
```python
try:
    _dispatch_next(article_id, run_id=run_id, next_status="pending")
except Exception as e:
    article.last_error = "Failed to dispatch to pipeline"
    db.session.rollback()
    logger.error("Failed to dispatch select_article for article %s: %s", article_id, e)
    raise
```

The exception is re-raised so the caller's exception handler at lines 366-383 handles it properly.

**Also fix:** The unguarded `db.session.commit()` at line 150 in `_create_article_record()` — wrap in try/except with rollback (see wave2_2).

---

### wave1_3: health_check function indentation bug

**File:** `services/search/google.py:87-110`
**Verified:** Yes — `def health_check(self)` at column 0 (module-level), not indented inside class
**Status:** FIXED — properly indented as class method (8-space method body indentation)
**Severity:** Critical — AttributeError when called as instance method
**Effort:** Trivial

**Current structure:**
```python
class GoogleSearchProvider(BaseSearchProvider):
    def search(self, ...):  # indented 4 spaces
        ...

def health_check(self) -> dict[str, Any]:  # module-level! BUG
        try:
            ...
```

**Fix:** Indent the entire `health_check` function body by 4 spaces so its `def` line aligns with `def search(...)` inside the class. The function body at lines 83-104 already has 8-space indentation (method-level), so only the `def` line at line 82 needs to be indented to 4 spaces.

**Reference:** `searxng.py:75` and `duckduckgo.py:46` correctly define `health_check` as a class method.

**Test:** Add test that calls `provider.health_check()` on a `GoogleSearchProvider` instance and verifies it returns a dict (not raises AttributeError).

---

### wave1_4: Remove ast.Call from condition evaluator (SECURITY)

**File:** `services/subagent.py:1067-1076`
**Verified:** Yes — `ast.Call` handler allows calling any function reachable through the evaluation chain
**Status:** FIXED — `ast.Call` raises `ValueError("Function calls not allowed in conditions")`, re-raised by caller
**Note:** Other unsafe constructs (`ast.Lambda`, `ast.BinOp`, `ast.UnaryOp`, `ast.Attribute` dunder access) also raise ValueError
**Severity:** High — security
**Effort:** Trivial

**Current code (lines 1025-1029):**
```python
elif isinstance(node, ast.Call):
    func = _eval_node(node.func)
    args = [_eval_node(arg) for arg in node.args]
    kwargs = {k.arg: _eval_node(k.value) for k in node.keywords if k.arg}
    return func(*args, **kwargs)
```

**Fix:** Remove lines 1025-1029 entirely. The `else: raise ValueError(...)` block after this will catch `ast.Call` nodes and raise an explicit error. Conditions should only need comparisons and boolean operations.

**Test:** Add test that asserts function calls in conditions raise `ValueError`. Add test that dict access + boolean comparisons still work.

---

### wave1_5: Narrow safe_href exception handling

**File:** `app.py:245-252`
**Verified:** Yes — `except Exception` catches ImportError, AttributeError, etc. — too broad
**Status:** FIXED — narrowed to `(UnsafeURLError, ValueError)` with `logger.debug`
**Severity:** Medium
**Effort:** Trivial

**Current code:**
```python
try:
    from services.url import validate_url_safe
    validate_url_safe(value)
    return value
except Exception as e:
    logger.warning("safe_href validation failed for %s: %s", value, e)
    return "#"
```

**Fix:**
```python
try:
    from services.url import validate_url_safe, UnsafeURLError
    validate_url_safe(value)
    return value
except (UnsafeURLError, ValueError) as e:
    logger.warning("safe_href validation failed for %s: %s", value, e)
    return "#"
```

The `validate_url_safe` import is currently inside the try block. Move it to module level if possible, or keep inside try but narrow the except.

---

### wave1_6: Add missing entries to .dockerignore

**File:** `.dockerignore`
**Verified:** Partially — current file is functional but missing some entries
**Status:** FIXED — added `.ruff_cache/`, `tests/`, `plans/`, `dump.rdb`, `.DS_Store`, `*.log`
**Severity:** Low
**Effort:** Trivial

**Add after the `scripts/` line:**
```
.ruff_cache/
tests/
plans/
dump.rdb
.DS_Store
*.log
```

---

### wave1_7: Dead letters table missing columns

**File:** `templates/admin/dead_letters.html`
**Verified:** Yes — thead at line 59 defines 7 columns (title, source, category, status, error, updated, actions) but tbody only renders 5 `<td>` elements. Status and error columns are entirely missing.
**Status:** FIXED — status and error columns added to tbody
**Severity:** Medium — UI bug
**Effort:** Trivial

**Current thead (line 59):**
```html
<tr><th>title</th><th>source</th><th>category</th><th>status</th><th>error</th><th>updated</th><th>actions</th></tr>
```

**Current tbody (lines 63-75):** Only has title, source, category, updated, actions — missing status and error.

**Fix — insert after category `<td>` and before updated `<td>` in the tbody loop:**
```html
<td>{{ pipeline_badge(article.pipeline_status) }}</td>
<td>{{ article.last_error|e if article.last_error else '—' }}</td>
```

**Reference:** Stuck articles table (lines 104-135) correctly renders all columns including `{{ pipeline_badge(article.pipeline_status) }}` at line 111. The `pipeline_badge` macro is already imported at line 2.

---

## WAVE 2: State Machine and Validation Fixes (Parallel within wave)

These can be implemented in parallel but wave2_1 should land before wave2_3.

---

### wave2_1: Add REVIEW to PENDING valid transitions

**File:** `constants.py:41`
**Verified:** Yes — `PENDING` maps to `frozenset([PipelineStatus.RESEARCHING])` only. `tasks/select.py:89` attempts PENDING→REVIEW which raises `InvalidStateTransitionError`.
**Severity:** Critical — bug
**Effort:** Trivial

**Current:**
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING]),
```

**Fix:**
```python
PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
```

**Test:** Add test for PENDING→REVIEW transition succeeds. Add test for invalid transition raises `InvalidStateTransitionError`.

---

### wave2_2: Add rollback handling in _create_article_record

**File:** `tasks/extract.py:150`
**Verified:** Yes — bare `db.session.commit()` with no try/except
**Severity:** High — inconsistent with codebase conventions
**Effort:** Trivial

**Current code:**
```python
db.session.commit()
return article
```

**Fix:**
```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    raise
return article
```

Add `from sqlalchemy.exc import SQLAlchemyError` at module level or in the function.

---

### wave2_3: Use state machine validation in set_status action

**File:** `routes/admin/api/articles.py:243-254`
**Verified:** Yes — direct `article.pipeline_status = new_status` at line 253 bypasses `VALID_TRANSITIONS`
**Severity:** Medium — admin can create inconsistent state
**Effort:** Low
**Depends on:** wave2_1 (adds PENDING→REVIEW)

**Current code (lines 243-254):**
```python
elif action == "set_status":
    new_status = data.get("status", "")
    if new_status not in VALID_PIPELINE_STATUSES:
        return jsonify({"error": f"Invalid status: {new_status}"}), 400
    try:
        for article in articles:
            article.pipeline_status = new_status
        db.session.commit()
```

**Fix — add transition validation before assignment:**
```python
elif action == "set_status":
    new_status = data.get("status", "")
    if new_status not in VALID_PIPELINE_STATUSES:
        return jsonify({"error": f"Invalid status: {new_status}"}), 400
    from constants import PipelineStatus as PS, VALID_TRANSITIONS
    new_status_obj = PS(new_status)
    for article in articles:
        valid_next = VALID_TRANSITIONS.get(article.pipeline_status, frozenset())
        if new_status_obj not in valid_next:
            return jsonify(
                {"error": f"Invalid transition from '{article.pipeline_status}' to '{new_status}'"}
            ), 400
    try:
        for article in articles:
            article.pipeline_status = new_status
        db.session.commit()
```

**Test:** Add test that PENDING→DONE returns 400. Add test that PENDING→RESEARCHING returns 200.

---

### wave2_4: Add rollback to SoftTimeLimitExceeded blocks in cleanup tasks

**File:** `tasks/cleanup.py`
**Verified:** Yes — both `consolidate_trend_memory` (lines 137-142) and `purge_trend_memory` (lines 213-218) lack `db.session.rollback()` in their SoftTimeLimitExceeded handlers.
**Severity:** High — data integrity
**Effort:** Trivial

**Fix for `consolidate_trend_memory` (lines 137-142):**
```python
except SoftTimeLimitExceeded:
    logger.error("consolidate_trend_memory exceeded soft time limit")
    db.session.rollback()
    raise
```

**Fix for `purge_trend_memory` (lines 213-218):**
```python
except SoftTimeLimitExceeded:
    logger.error("purge_trend_memory exceeded soft time limit")
    db.session.rollback()
    raise
```

**Reference:** `cleanup_old_pipeline_logs` (lines 47-50) correctly calls `db.session.rollback()` before re-raising.

---

### wave2_5: Return False on SQLAlchemyError in trigger_webhook

**File:** `services/webhooks.py:274-284`
**Verified:** Yes — after rollback at line 277, falls through to return `(success, error)` at line 284, which reports HTTP delivery success even though DB write failed.
**Severity:** High — incorrect behavior
**Effort:** Trivial

**Current code:**
```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()

if success:
    logger.info(...)
else:
    logger.error(...)

return success, error
```

**Fix:**
```python
try:
    db.session.commit()
except SQLAlchemyError as e:
    db.session.rollback()
    return False, f"Database error: {e}"

if success:
    logger.info("Webhook '%s' delivered successfully to %s", name, url)
else:
    logger.error("Webhook '%s' failed to deliver to %s: %s", name, url, error)

return success, error
```

**Test:** Add test that mocks `db.session.commit()` to raise `SQLAlchemyError` and verifies return is `(False, "Database error: ...")`.

---

### wave2_6: Use yield_per(500) for subscriber queries

**File:** `tasks/newsletter.py:507` and `tasks/newsletter.py:513-520`
**Verified:** Yes — `.all()` loads all subscribers into memory (OOM risk at scale)
**Severity:** High — OOM risk
**Effort:** Trivial

**Fix at line 507:**
```python
# Before:
subscribers = Subscriber.query.filter(*base_filters).all()
# After:
subscribers = Subscriber.query.filter(*base_filters).yield_per(500)
```

**Also fix retry_failed_newsletter_deliveries (lines 513-520):**
Change the subscriber query there to also use `yield_per(500)`.

**Reference:** `routes/admin/subscribers.py` already uses `yield_per(500)` for CSV export.

---

## WAVE 3: Subagent and LLM Provider Fixes (Parallel within wave)

---

### wave3_1: Fix initialize_tool_registry() signature mismatch

**File:** `services/subagent.py:328-333`, callers at `tasks/research.py:106` and `tasks/edit.py:108`
**Verified:** Yes — function takes 0 args, returns None. Callers pass `stage_config.tools` and capture return value as `list[ToolDefinition]`. Would crash with `TypeError` at runtime.
**Severity:** Critical — runtime crash on tool-calling path
**Effort:** Medium

**Current code:**
```python
def initialize_tool_registry() -> None:
    """Initialize the tool registry with built-in tools."""
    for tool in _build_context_tools():
        register_tool(tool)
    for tool in _build_search_tools():
        register_tool(tool)
```

**Fix:**
```python
def initialize_tool_registry(tool_names: list[str] | None = None) -> list[ToolDefinition]:
    """Initialize the tool registry with built-in tools, optionally filtered."""
    all_tools = []
    for tool in _build_context_tools():
        register_tool(tool)
        all_tools.append(tool)
    for tool in _build_search_tools():
        register_tool(tool)
        all_tools.append(tool)
    if tool_names is not None:
        return [t for t in all_tools if t.name in tool_names]
    return all_tools
```

**Additional issue — tool name mismatch in pipeline.yaml:** The `tools:` list in pipeline.yaml may use names like `web_search` while actual tool names are `search_web`. This should be investigated and either pipeline.yaml updated or an aliasing layer added. For now, the function fix above matches by actual function name.

**Callers already assign the return value to `tools`, so they work as-is once the function returns the filtered list.**

**Tests needed:**
- `test_initialize_tool_registry_returns_all_tools`
- `test_initialize_tool_registry_filters_by_name`
- `test_initialize_tool_registry_empty_list_returns_empty`

---

### wave3_2: Add error handling to tool functions

**File:** `services/subagent.py:43-177`
**Verified:** Yes — all 7 tool functions have no error handling for DB/Redis failures
**Severity:** High — degradation
**Effort:** Medium

**Affected functions:** `_get_topic_note`, `_get_topic_notes_for_topics`, `_get_related_articles`, `_get_trend_memory`, `_get_article_by_id`, `_search_articles`, `_get_source_health`

**Pattern to apply to each:**
```python
def _get_topic_note(topic: str, source: str | None = None) -> str:
    from services.context_service import get_topic_note
    try:
        note = get_topic_note(topic, source)
        return note.note if note else "No note found for this topic."
    except Exception as e:
        logger.warning("Tool get_topic_note failed for topic=%s: %s", topic, e)
        return f"Error retrieving topic note: {type(e).__name__}"
```

**Key principles:**
- Catch `SQLAlchemyError` and `redis.exceptions.RedisError` specifically where possible
- Return human-readable error strings (not raw exception messages)
- Log at warning level (not error — these are expected degradation scenarios)

---

### wave3_3: Add AuthError to provider fallback tuple

**File:** `tasks/pipeline.py:188`
**Verified:** Claim not directly verified but consistent with codebase patterns
**Severity:** High — reliability
**Effort:** Trivial

**Fix:**
```python
# Before:
except (RateLimitError, ProviderServerError, ProviderTimeoutError) as transient_err:
# After:
except (RateLimitError, ProviderServerError, ProviderTimeoutError, AuthError) as transient_err:
```

Note: Import `AuthError` from the appropriate module if not already imported.

---

### wave3_4: Retry loop in run_subagent_chain iterates providers

**File:** `services/subagent.py:868-878` (context: lines 867-933)
**Severity:** High — reliability
**Effort:** Medium

**Issue:** Retry loop retries same provider, doesn't try fallback providers.

**Fix:** Move `_get_subagent_provider_and_config()` inside the attempt loop so each retry picks a fresh provider:

```python
for attempt in range(stage_config.max_retries + 1):
    try:
        provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
            stage_config, default_role="editor"
        )
        def _chain_call():
            return provider.chat(...)
        future = _subagent_executor.submit(_chain_call)
        resp = future.result(timeout=stage_config.timeout_seconds)
        step_succeeded = True
        break
    except (ProviderTimeoutError, TimeoutError) as e:
        if attempt < stage_config.max_retries:
            import random
            delay = min(1.0 * (2 ** attempt) + random.uniform(0, 0.5), stage_config.retry_delay)
            time.sleep(delay)
            continue
        results[step_name] = {"synthesis": f"[Fallback: {e}]", "used_fallback": True}
        break
    except Exception as e:
        results[step_name] = {"synthesis": f"[Fallback: {e}]", "used_fallback": True}
        break
```

---

### wave3_5: Fix retry backoff formula

**File:** `services/subagent.py:512`
**Verified:** Yes — uses `2 ** (attempt - 1)`, should be `2 ** attempt`
**Severity:** Low — inconsistency
**Effort:** Trivial

**Fix:**
```python
# Before:
delay = min(1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5), stage_config.retry_delay)
# After:
delay = min(1.0 * (2 ** attempt) + random.uniform(0, 0.5), stage_config.retry_delay)
```

---

### wave3_6: Add `previous` to `_ALLOWED_NAMES`

**File:** `services/subagent.py:966`
**Verified:** Yes — only `{"True", "False", "None", "results"}`, no `previous`
**Severity:** Medium — chain conditions broken
**Effort:** Trivial

**Fix:**
```python
_ALLOWED_NAMES = {"True", "False", "None", "results", "previous"}
```

---

### wave3_7: Fix single-brace template variable detection

**File:** `services/subagent.py:1050`
**Verified:** Yes — checks `"{{" in value` but `.format()` uses single braces `{}`
**Severity:** Medium — chain template resolution broken
**Effort:** Trivial

**Fix:**
```python
# Before:
if isinstance(value, str) and "{{" in value:
# After:
if isinstance(value, str) and "{" in value:
```

**Important:** After this fix, verify that chain step templates with single braces still work correctly and that the subsequent `template.format()` call doesn't double-substitute.

---

## WAVE 4: Search, Circuit Breaker, and Adapter Fixes (Parallel within wave)

---

### wave4_1: DuckDuckGo SSRF validation on result URLs

**File:** `services/search/duckduckgo.py:16-29`
**Verified:** Yes — no call to `validate_url_safe()` anywhere. `searxng.py` and `google.py` both validate.
**Severity:** High — security
**Effort:** Low

**Fix:** Validate each result URL with `validate_url_safe()` before returning:
```python
def _search_impl(provider, query, max_results):
    from duckduckgo_search import DDGS
    from services.url import validate_url_safe, UnsafeURLError

    validated_results = []
    with DDGS(timeout=15) as ddgs:
        results = ddgs.text(query, max_results=max_results)
        for r in results:
            url = r.get("href", "")
            try:
                validate_url_safe(url)
                validated_results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=url,
                        snippet=r.get("body", ""),
                        source=provider.provider_id,
                    )
                )
            except UnsafeURLError:
                logger.warning("DuckDuckGo returned blocked URL: %s", url)
                continue
        return validated_results
```

---

### wave4_2: Make `_LLM_FAILURE_THRESHOLD` configurable

**File:** `services/llm/__init__.py:18`
**Verified:** Yes — hardcoded `_LLM_FAILURE_THRESHOLD = 5`
**Severity:** Low — operational
**Effort:** Trivial

**Fix:**
```python
import os
_LLM_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
```

---

### wave4_3: Add `_record_success`/`_record_failure` to BaseLLMProvider

**File:** `services/llm/base.py`
**Severity:** Medium — circuit breaker tracking gaps
**Effort:** Medium

**Issue:** `_retry_with_backoff()` doesn't record intermediate failures. `chat_with_tools()` never records success/failure. Subagent calls bypass `run_stage` which is where recording currently happens.

**Fix:**

1. Add methods to `BaseLLMProvider`:
```python
def _record_success(self, model: str) -> None:
    from services.llm import record_provider_success
    record_provider_success(self.provider_id, model)

def _record_failure(self, model: str) -> None:
    from services.llm import record_provider_failure
    record_provider_failure(self.provider_id, model)
```

2. Call `_record_success()` at end of successful `chat()`, `chat_structured()`, `chat_with_tools()`.
3. Call `_record_failure()` in `_retry_with_backoff` except blocks.
4. Remove success recording from `run_stage` line 301 to avoid double-counting. Keep failure recording in `run_stage` for the generic exception path.

---

### wave4_4: Add search circuit breaker helpers

**File:** `services/search/__init__.py`
**Severity:** Medium — cascading failure risk
**Effort:** Medium
**Depends on:** wave1_3 (Google health_check fix)

**Fix:**

1. Add helper functions to `services/search/__init__.py`:
```python
from services.circuit_breaker import get_breaker

def record_search_success(provider_id: str):
    get_breaker(f"search:{provider_id}").record_success()

def record_search_failure(provider_id: str):
    get_breaker(f"search:{provider_id}").record_failure()
```

2. Update each search provider's `search()` method to call `record_search_success()` on success and `record_search_failure()` on failure (timeout, exception).

---

### wave4_5: Change retry_backoff=30 to retry_backoff=True

**Files:** `tasks/select.py:24`, `tasks/write.py:41`, `tasks/research.py:54`, `tasks/edit.py:354`
**Verified:** Yes — all four use `retry_backoff=30`
**Severity:** Low — incorrect retry behavior (fixed 30s delay instead of exponential)
**Effort:** Trivial

**Fix (all four):** Change `retry_backoff=30` to `retry_backoff=True`

---

### wave4_6: Add retry logic to API and Web adapters

**Files:** `adapters/api.py:21`, `adapters/web.py:31`
**Verified:** Yes — both create `requests.Session()` without `HTTPAdapter` with retry logic
**Severity:** Medium — no retry on transient failures
**Effort:** Medium

**Note:** `requests.Session()` already has default connection pooling via urllib3. The gap is **retry logic on transient HTTP failures**, not connection pooling.

**Fix:** Create `adapters/session.py` with shared session factory:
```python
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_CRAWL_SESSION = None
_CRAWL_SESSION_LOCK = threading.Lock()

def get_crawl_session() -> requests.Session:
    global _CRAWL_SESSION
    if _CRAWL_SESSION is None:
        with _CRAWL_SESSION_LOCK:
            if _CRAWL_SESSION is None:
                _CRAWL_SESSION = requests.Session()
                retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
                adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry)
                _CRAWL_SESSION.mount("http://", adapter)
                _CRAWL_SESSION.mount("https://", adapter)
    return _CRAWL_SESSION
```

Replace `self._session = requests.Session()` in both adapters with `self._session = get_crawl_session()`. Pass per-request headers for User-Agent since the shared session can't have per-source headers.

---

## WAVE 5: Performance and Cache Fixes (Parallel within wave)

---

### wave5_1: Replace blpop polling with direct cache key check

**File:** `services/cache.py:141-158`
**Verified:** Yes — blpop on string lock key causes WRONGTYPE error, falls through to unprotected load
**Severity:** Medium — stampede protection broken
**Effort:** Low

**Fix — replace blpop approach with bounded polling:**
```python
# Replace lines 141-158:
else:
    for _ in range(10):  # 10 × 50ms = 500ms max wait
        cached = self.get(key)
        if cached is not None:
            return cached
        if not self._redis.exists(lock_key):
            break
        time.sleep(0.05)

    cached = self.get(key)
    if cached is not None:
        return cached

    if self._redis.set(lock_key, "1", nx=True, ex=10):
        # ... load as normal
```

---

### wave5_2: Add joinedload for source in metrics queries

**File:** `routes/admin/metrics.py:33-68`
**Verified:** Yes — no `joinedload(Article.source)` on any of the three queries. Currently not an N+1 because template doesn't access `.source`, but this is a latent risk.
**Severity:** Low — preventive
**Effort:** Trivial

**Fix:** Add `.options(joinedload(Article.source))` to `top_by_views`, `top_by_shares`, and `top_by_link_views` queries. Add `from sqlalchemy.orm import joinedload` import.

---

### wave5_3: Clear stage failure Redis keys on reprocess

**Files:** `routes/admin/api/articles.py` (_bulk_reprocess), `routes/admin/articles.py` (reprocess_article)
**Verified:** Yes — both paths reset DB counters but leave Redis `ainews:article:stage_failures:{article_id}:{stage}` keys intact. Reprocessed articles can hit immediate 3-failure early termination.
**Severity:** Critical — reprocessed articles can fail immediately
**Effort:** Low

**Fix in `_bulk_reprocess` (after db.session.commit(), before dispatching):**
```python
try:
    from extensions import get_redis
    redis_client = get_redis()
    for article in articles:
        pattern = f"ainews:article:stage_failures:{article.id}:*"
        for key in redis_client.scan_iter(match=pattern):
            redis_client.delete(key)
except redis.exceptions.RedisError:
    logger.warning("Failed to clear stage failure keys during reprocess")
```

**Same pattern in `reprocess_article`:**
```python
try:
    from extensions import get_redis
    redis_client = get_redis()
    pattern = f"ainews:article:stage_failures:{article.id}:*"
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)
except redis.exceptions.RedisError:
    logger.warning("Failed to clear stage failure keys for article %s", article_id)
```

---

### wave5_4: Invalidate pub:related:* cache in bulk operations

**File:** `routes/admin/api/articles.py`
**Severity:** Low — stale cache (600s TTL provides eventual consistency)
**Effort:** Trivial

**Fix:** Add `cache.invalidate_prefix("pub:related")` to all bulk operation cache invalidation blocks (delete, set_status, reprocess, set_category, add_tags).

---

### wave5_5: Call _evict_stale() in get() miss path

**File:** `services/cache.py:52-58`
**Verified:** Yes — `_evict_stale()` only called in `set()`, not in `get()`. Stale entries accumulate under read-heavy workloads.
**Severity:** Low
**Effort:** Trivial

**Fix:** Call `self._evict_stale()` at the start of the `get()` method.

---

### wave5_7: Add autoretry to retry_stuck task

**File:** `tasks/retry.py:20`
**Verified:** Yes — decorator is `@shared_task(bind=True, soft_time_limit=300, time_limit=360)` with no autoretry
**Severity:** Medium
**Effort:** Trivial

**Fix:**
```python
@shared_task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def retry_stuck(self):
```

---

## WAVE 6: UI/UX Improvements (Parallel within wave)

---

### wave6_1: Add sort parameter to get_articles_paginated()

**Files:** `services/article.py`, `routes/public/feeds.py`, `templates/partials/feed.html`, `static/css/articles.css`
**Severity:** Medium — missing feature
**Effort:** Low

**Changes:**

1. **`services/article.py`:** Add `_get_sort_order(sort: str)` helper and `sort` parameter to `get_articles_paginated()`. Replace hardcoded `.order_by(Article.created_at.desc())` with `_get_sort_order(sort)`.

2. **`routes/public/feeds.py`:** Add `sort` query param to `index()`, `topic_feed()`, `tag_feed()`. Update cache keys to include sort. Pass `sort` to template context.

3. **`templates/partials/feed.html`:** Add sort dropdown with HTMX after the search form. Options: "most recent", "highest impact", "published date".

4. **`static/css/articles.css`:** Add `.sort-dropdown` and `.sort-select` styles.

---

### wave6_2: Add date_from and date_to inputs to admin articles page

**Files:** `templates/admin/articles.html`, `templates/admin/partials/articles_table.html`
**Severity:** Low — UI gap
**Effort:** Low

**Changes:**

1. Add date range `<input type="date">` elements to the filter bar in `articles.html`.
2. Update all `hx-include` attributes to include `[name='date_from'],[name='date_to']`.
3. Fix `articles_table.html:70` pagination to pass all filter parameters including `date_from`, `date_to`, `impact_min`, `impact_max`, `tag_slug`.

---

### wave6_3: Fix pagination to pass all filter params

**File:** `templates/admin/partials/articles_table.html:70`
**Severity:** Low — pagination loses filters
**Effort:** Trivial

**Fix:** Update `pagination_nav` call to include all filter parameters:
```html
{{ pagination_nav(page, has_next, next_page, total_count, 20, "/admin/articles", {"q": query, "status": status, "category": category, "date_from": date_from, "date_to": date_to, "impact_min": impact_min, "impact_max": impact_max, "tag_slug": tag_slug}) }}
```

---

### wave6_4: Add sort dropdown to public feed

**File:** `templates/partials/feed.html`, `static/css/articles.css`
**Severity:** Low — UX improvement
**Effort:** Low
**Depends on:** wave6_1

Add `<select>` with HTMX attributes for sort, styled with `.sort-select` CSS class.

---

### wave6_5: Add "Select all matching" checkbox and endpoint

**Files:** `templates/admin/partials/articles_table.html`, `routes/admin/api/articles.py`
**Severity:** Low — UX improvement
**Effort:** Medium

Add a new endpoint `GET /admin/api/articles/ids` that returns matching article IDs given filter params. Add "select all matching" checkbox UI that fetches all IDs via this API.

---

### wave6_6: Add hx-push-url to search and fix impact filter triggers

**File:** `templates/admin/articles.html`
**Severity:** Low — UX improvement
**Effort:** Trivial

1. Add `hx-push-url="true"` to the search input.
2. Change impact filter triggers from `hx-trigger="change"` to `hx-trigger="input changed delay:500ms, change"`.

---

### wave6_7: Make "What To Watch" collapsible

**Files:** `templates/partials/condensed_article.html`, `static/css/articles.css`
**Severity:** Low — UX improvement
**Effort:** Low

Wrap what-to-watch section in `<details>/<summary>` pattern. Add CSS for the disclosure widget with rotation arrow.

---

### wave6_8: Improve "View Original" link and limit tags to 3

**Files:** `templates/partials/article_card.html`, `static/css/articles.css`
**Severity:** Low — UX improvement
**Effort:** Low

1. Limit tags to 3 with `article.tags[:3]` and "+N more" pattern.
2. Make View Original link more prominent with SVG icon + inline-flex styling.

---

### wave6_9: Remove aria-haspopup from share button summary

**File:** `templates/partials/share_macro.html`
**Severity:** Low — accessibility
**Effort:** Trivial

Remove `aria-haspopup="true"` from the `<summary>` element. Keep `aria-expanded="false"`.

---

## WAVE 7: Documentation Files (Fully Parallel)

Each doc can be created by a separate agent. Use the doc structure template from AGENTS.md.

---

### wave7_1: Create docs/subagent.md

Document the subagent system: tool registry (9 tools), chain execution, configuration, failure scenarios, known bugs (`initialize_tool_registry` signature mismatch, `max_iterations=5` hardcoded).

**Note:** Write after wave3_1 fix is applied, or document both current behavior and fix.

---

### wave7_2: Create docs/trend-memory.md

Document trend memory: importance tiers (LOW 7d / MEDIUM 30d / HIGH no expiry), consolidation algorithm, admin endpoints, Celery schedule, known bugs (`_find_overlapping_low_entries` dead code, admin UI time inconsistency).

---

### wave7_3: Create docs/search-providers.md

Document search providers: BaseSearchProvider interface, provider comparison, SSRF validation, known bugs (Google health_check outside class, DuckDuckGo no SSRF validation).

**Note:** Write after wave4_1 fix is applied, or document both current and fixed behavior.

---

### wave7_4: Create docs/context-service.md

Document context service: TopicNote CRUD, related articles algorithm, caching, admin endpoints, known bugs (related articles cache never invalidated, `update_topic_note` only updates note field).

---

### wave7_5: Create docs/pipeline-failure-tracking.md

Document pipeline failure tracking: Redis key structure, decision tree, stage degradation map, reprocessing behavior (DB reset but Redis keys persist), known bugs.

---

### wave7_6: Create docs/newsletter-pipeline.md

Document newsletter generation: orchestrator flow, 3-stage pipeline, fallback cascade, delivery tracking, known bugs (`newsletter_id` always NULL in webhook events).

---

### wave7_7: Create docs/cost-tracking.md

Document LLM cost tracking: token counting flow, blended rate formula, default rates table, shortcomings (no input/output token distinction).

---

## WAVE 8: Deployment Script Improvements (Parallel within wave)

---

### wave8_1: scripts/install.sh improvements

**File:** `scripts/install.sh`
**Effort:** Low

1. Replace hardcoded `REPO_URL` with `${REPO_URL:-}`
2. Add `-d|--dir` argument for `APP_DIR` override
3. Add `--pull-ollama-model` flag
4. Improve end-of-run messaging

---

### wave8_2: scripts/deploy.sh improvements

**File:** `scripts/deploy.sh`
**Effort:** Low

1. Add `unset GIT_DIR GIT_WORK_TREE GIT_QUARANTINE_PATH GIT_ASKPASS GIT_NOTES_REF`
2. Add detached HEAD check
3. Improve `.git` directory validation

---

### wave8_3: Fix docs/deployment.md Docker Nginx example

**File:** `docs/deployment.md`
**Effort:** Trivial

Fix path routing bug: `location /static/` should use `alias /opt/ainews/static/;` not `proxy_pass`.

---

### wave8_4: docker-compose.yml healthchecks

**File:** `docker-compose.yml`
**Effort:** Low

Add Redis-ping healthchecks for `celery-worker` and `celery-beat` services.

---

### wave8_5: .env.example ADMIN_PASSWORD instruction

**File:** `.env.example`
**Effort:** Trivial

Add inline instruction for generating hashed password with `python scripts/hash_password.py`.

---

## WAVE 9: PWA and Additional UI (Parallel within wave)

---

### wave9_1: Create static/manifest.json

PWA manifest with name, icons, theme colors. Use existing `static/svg/ai.svg` for icons.

---

### wave9_2: Create static/js/service-worker.js

Service worker with cache-first strategy and offline fallback.

---

### wave9_3: Add manifest link and service worker registration

Update `templates/base.html` and `static/js/app.js` to register the service worker.

---

### wave9_4: Add reading_time calculation to article_detail

**File:** `routes/public/links.py`
**Effort:** Trivial

Calculate `word_count // 200` and pass `reading_time` to template.

---

### wave9_5: Display reading_time in condensed_article template

**File:** `templates/partials/condensed_article.html`
**Effort:** Trivial

Add reading time display with meta separator.

---

### wave9_6: Add WebhookEvent payload column and resend endpoint

**Files:** New migration, `models.py`, `services/webhooks.py`, `routes/admin/api/webhooks.py`
**Effort:** Medium

1. Add migration for `payload` column on `webhook_events`.
2. Update `dispatch_webhook()` to store `event_data` as `payload`.
3. Add `POST /admin/api/webhooks/events/<id>/resend` endpoint.
4. Update template to show resend button for failed events.

---

### wave9_7: Add pagination to dead letters queries

**File:** `routes/admin/dashboard.py`
**Effort:** Low

Add `failed_page` and `stuck_page` params. Query with offset/limit. Pass pagination data to template.

---

## Implementation Order and Dependencies

```
WAVE 1 (7 items) ───── Fully parallel, no dependencies
  │
WAVE 2 (6 items) ───── Parallel, but wave2_3 depends on wave2_1
  │
WAVE 3 (7 items) ───── Parallel, no cross-deps within wave
  │
WAVE 4 (6 items) ───── Parallel, wave4_4 depends on wave1_3
  │
WAVE 5 (6 items) ───── Parallel, no cross-deps within wave
  │                    NOTE: wave5_6 REMOVED (bug already fixed)
  │
WAVE 6 (9 items) ───── Parallel, wave6_4 depends on wave6_1
  │
WAVE 7 (7 items) ───── Fully parallel
  │                    wave7_1 best after wave3_1 fix
  │                    wave7_3 best after wave4_1 fix
  │
WAVE 8 (5 items) ───── Fully parallel
  │
WAVE 9 (7 items) ───── Fully parallel
```

**Total actionable items: 60**
**Estimated waves: 9**
**Minimum sequential phases: 9** (waves can overlap where dependencies allow)

---

## Test Coverage Gaps to Address

| Issue | Missing Test |
|-------|--------------|
| pipeline.py:130 wrong field | Test with non-empty `last_error` on source |
| webhooks.py:274 rollback | Test DB commit failure propagation |
| newsletter.py:507 yield_per | Test with large subscriber count (mock) |
| google.py health_check | Test method call on provider instance |
| subagent.py ast.Call removal | Test function calls in conditions raise ValueError |
| cleanup.py rollback | Test rollback called on SoftTimeLimitExceeded |
| state machine validation | Test InvalidStateTransitionError for invalid transitions |
| set_status bypass | Test PENDING→DONE returns 400 |
| initialize_tool_registry | Test filtered return, empty list, name matching |
| retry_stuck autoretry | Test transient errors trigger retry |

---

## Items Removed During Verification

| Item | Reason |
|------|--------|
| wave5_6: Add autoretry to aggregate_crawl_results | **Already has `autoretry_for=(ConnectionError, TimeoutError)` at line 198** — claim was false |
| wave4_6: RSS adapter socket timeout (connect/read params on Retry) | Per-request `timeout=cfg.request_timeout` at line 38 provides the actual timeout; `connect`/`read` params on `Retry` object only control retry-on-socket-error, not timeout itself. Low value. |
| Subagent chain template resolution "result unused" | Verified in AGENTS.md: result IS used via `prompt_data_escaped` in `.format()` call |
| `_find_overlapping_low_entries` dead code removal | Low priority, just dead code, no functional impact |

---

*Consolidated and verified April 26, 2026*
