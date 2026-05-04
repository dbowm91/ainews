# BLE001 Exception Handling Guide

> **Status:** Active skill - documents lessons learned from BLE001 narrowing in Wave 3.

## The Problem

When BLE001 (blind exception catch) was narrowed to specific exception types, some tests failed
because the narrowed lists didn't cover all exceptions that could be raised in practice.

## Key Lessons Learned

### 1. trafilatura Can Raise Generic Exceptions

```python
# services/content_extractor.py - trafilatura.fetch_url raises diverse exceptions
def _fetch_with_timeout(url: str, timeout: int = 30) -> str | None:
    try:
        return trafilatura.fetch_url(url, config=cfg)
    except (urllib3.exceptions.HTTPError, ValueError, Exception):  # noqa: BLE001
        # trafilatura raises many exception types beyond HTTPError
        return None
```

**Lesson:** External libraries like trafilatura can raise generic `Exception` from their
network operations. Tests using plain `Exception("message")` will fail if you narrow too much.

### 2. Flask current_app Raises RuntimeError Outside Context

```python
# services/email.py - Flask context not available in all scenarios
try:
    pool_size = current_app.config.get("SMTP_POOL_SIZE", 5)
except (smtplib.SMTPException, RuntimeError):  # noqa: BLE001
    # RuntimeError raised when current_app accessed outside request context
    pool_size = int(os.environ.get("SMTP_POOL_SIZE", "5"))
```

**Lesson:** `current_app` raises `RuntimeError: Working outside of application context` when
accessed outside a request. Always include `RuntimeError` when catching Flask config access.

### 3. Metrics Subsystem Can Raise RuntimeError

```python
# services/circuit_breaker.py - metrics can fail in various ways
try:
    metrics.counter_inc("circuit_breaker.state_change", labels={...})
except (RedisError, ImportError, AttributeError, ValueError, RuntimeError):
    logger.debug("Failed to emit metric")
```

**Lesson:** The metrics subsystem (`services/metrics.py`) can raise `RuntimeError` when its
internal state is invalid or when Redis operations fail in unexpected ways.

### 4. Always Add noqa Comments for Intentional Broad Catches

```python
except Exception:  # noqa: BLE001 - trafilatura raises diverse network exceptions
except Exception:  # noqa: BLE001 - Flask current_app raises RuntimeError outside context
```

**Lesson:** When keeping a broad `Exception` catch, always document WHY it's intentional
with a noqa comment. This prevents Ruff from flagging it and documents the rationale.

## When to Narrow vs. Keep Broad

| Scenario | Approach |
|----------|----------|
| External library with diverse exceptions | Keep broad with noqa |
| Flask current_app access | Add RuntimeError to specific list |
| Metrics/Redis operations | Add RuntimeError to specific list |
| Internal code with predictable errors | Narrow to specific types |
| Non-critical fallback operations | Keep broad with noqa |

## Testing Considerations

When writing tests that mock external libraries:
- Mock the actual exception type the library raises
- Don't rely on plain `Exception` unless that's what you're testing
- If testing broad catch behavior, use `Exception` explicitly in the mock

## Pre-Commit Verification

```bash
# Always run before committing
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/test_circuit_breaker.py tests/test_content_extractor.py tests/test_email.py -v
```

---

*This skill was created after fixing BLE001 narrowing issues in 2026-05-04.*
