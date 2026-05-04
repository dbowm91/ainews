# AINews Implementation Plan

**Status:** ACTIVE
**Last Updated:** 2026-05-04 (Test fixes added after BLE001 narrowing)
**Goal:** Track deferred items only. All plan items have been verified complete.

---

## Deferred Items

The following items were intentionally deferred during plan implementation and remain outstanding:

### Deferred: Cache Warming
- **Status:** Not implemented (deferred)
- **Rationale:** Not on critical path; ResponseCache already handles cold cache efficiently
- **Consider:** Implement if latency on cache miss becomes a problem

### Deferred: Mypy Adoption
- **Status:** Not implemented (deferred)
- **Rationale:** Requires significant refactoring for type annotations across codebase
- **Consider:** Implement in a dedicated refactoring effort with thorough testing

### Deferred: Test Coverage Gaps
- **Status:** Not implemented (deferred)
- **Rationale:** Requires additional test writing effort for untested modules
- **Consider:** Implement incrementally as part of normal development

---

## Verification Notes

All completed items were verified to be correctly implemented as of 2026-05-04.
Additional fixes applied 2026-05-04 for BLE001 exception handling issues.

### BLE001 Exception Handling Fixes (2026-05-04)

After Wave 3 BLE001 narrowing, some tests failed because the narrowed exception
lists didn't cover all exceptions that could be raised in practice:

**Fixed locations:**
1. `services/circuit_breaker.py` - Added `RuntimeError` to 4 exception handlers:
   - `_on_state_change`: `metrics.counter_inc` can raise RuntimeError when metrics fail
   - `_get_redis`: Redis connection can raise RuntimeError in various scenarios
   - `_emit_metric`: metrics can raise RuntimeError
   - `circuit_protected`: fallback function can raise RuntimeError

2. `services/email.py` - Added `RuntimeError` to 2 exception handlers:
   - `_get_smtp_pool`: catches RuntimeError when Flask app context unavailable
   - `get_smtp_config`: catches RuntimeError when accessing `current_app`

3. `services/content_extractor.py` - Kept broad `Exception` catch with noqa:
   - `_fetch_with_timeout`: trafilatura raises diverse exceptions beyond HTTPError/ValueError
   - Test `test_extract_article_fetch_error` uses plain `Exception("Network error")`

### Test Status

**Passing tests after fixes:**
- `test_circuit_breaker.py`: All 34 tests pass
- `test_content_extractor.py`: All 11 tests pass
- `test_email.py`: Most tests pass (1 pre-existing fixture error unrelated to changes)

**Pre-existing test issues (not caused by BLE001 fixes):**
- `test_extract_task.py::TestProcessItem::test_extraction_failure_uses_fallback` - fixture setup error
- `test_extract_task.py::TestProcessItem::test_happy_path` - same fixture issue
- `test_email.py::TestGetSMTPConfig::test_get_smtp_config_from_app` - fixture setup error

### Ruff Lint Status (2026-05-04)
- BLE001: 1 intentional remaining (`services/content_extractor.py:62` with noqa)
- E402: 3 remaining (justified for circular import avoidance in `routes/admin/__init__.py`, `routes/public/__init__.py`)
- F401: 0 remaining (all fixed with explicit re-exports)
- S311: 0 remaining (all justified for jitter in retry/delays)
- C901: 1 remaining (`services/subagent/runner.py:run_subagent` with noqa)

---

(End of file - minimal plan - deferred items only)
