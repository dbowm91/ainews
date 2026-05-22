# Adapters Module Review

## Verified Claims

### File Inventory
| File | Adapter | Purpose | Status |
|------|---------|---------|--------|
| `base.py` | `BaseSourceAdapter` | Abstract base with fetch/parse methods; registry decorator | **Correct** |
| `rss.py` | `RSSAdapter` | RSS/Atom feed parsing via feedparser + BeautifulSoup | **Correct** |
| `api.py` | `APIAdapter` | REST API fetching with JSONPath field extraction | **Correct** |
| `web.py` | `WebAdapter` | Web page scraping with CSS selectors | **Correct** |
| `session.py` | `SSRFSafeRedirectHandler` | SSRF protection for redirects | **Correct** |

### Adapter Pattern and Registry
- `@register_adapter` decorator correctly registers adapters in `_ADAPTER_REGISTRY` (aliased as `SOURCE_ADAPTERS`)
- All adapters inherit from `BaseSourceAdapter`
- Registry lookup via `get_adapter_class()` works correctly

### BaseSourceAdapter Interface
- `fetch()` and `parse_item()` are abstract methods
- `fetch_and_parse()` combines fetch + parse with error handling (catches `ValueError`, `KeyError`, `AttributeError`)
- Returns `list[RawItem]` (not `ArticleData` - see Discrepancies)

### Session Ownership
| Adapter | Session Type | Redirect Handler | Status |
|---------|-------------|------------------|--------|
| `RSSAdapter` | Own `requests.Session` | Own `SSRFSafeRedirectHandler` instance | **Correct** |
| `APIAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` | **Correct** |
| `WebAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` | **Correct** |

### SSRF Protection
- `SSRFSafeRedirectHandler` uses thread-local storage for redirect counting
- Blocks unsafe URLs via `validate_url_safe()`
- Handles `javascript:` and `data:` schemes via URL validation
- The `__call__` signature `(self, request, response, **kwargs)` is implemented

### Error Handling
- Network errors: Log and return empty list - **Correct**
- Parse errors: Log and skip invalid items - **Correct**
- Rate limiting: Fixed exponential backoff (`2**attempt * 5 + jitter`) - **Correct**
- Source health: Adapters do NOT update `Source.consecutive_failures/successes` - **Correct**

### Source Configuration
- Config field name is `config` in `SourceConfig` - **Correct**
- Config validated against `RSSConfig`, `APIConfig`, `WebConfig` - **Correct**

### Layering
- Adapters do NOT import from `services` - **Verified** (checked with grep)

---

## Discrepancies

### 1. `ArticleData` vs `RawItem` (Documentation Error)
**Documentation says:**
```python
def parse_item(self, item: dict) -> ArticleData: ...
```

**Actual implementation:**
```python
def parse_item(self, raw: Any) -> Optional[RawItem]: ...
```

The return type is `RawItem` (from `schemas/item.py`), not `ArticleData`. The documentation should be updated to use `RawItem`.

### 2. Filter Operations - `contains` IS Implemented
**Documentation says:**
> Filter operations: `equals`, `min`, `exists` (no `contains`)

**Actual implementation in `api.py:205-221`:**
```python
def _passes_filters(self, data: Any, filters: list[dict]) -> bool:
    ...
    if "contains" in f and f["contains"] not in str(current):
        return False
    return True
```

The `contains` filter operation IS implemented. The documentation is out of date.

### 3. WebAdapter `request_delay` Behavior (Documentation Incomplete)
**Documentation states:**
> The `request_delay_min`/`request_delay_max` configuration in `WebConfig` applies **per-article**, not per-page.

**Actual implementation in `web.py:171-175`:**
```python
def _polite_get(self, url: str) -> Optional[BeautifulSoup]:
    ...
    delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
    time.sleep(delay)
```

The delay is applied in `_polite_get()` which is called **per article URL** during the fetch loop in `fetch()`. The documentation accurately describes the behavior, though it could be more explicit that this applies when iterating over article URLs.

---

## Bugs

### 1. APIAdapter Closes Shared Global Session (Critical)
**Location:** `adapters/api.py:25-26`
```python
def close(self):
    self._session.close()
```

**Issue:** `APIAdapter` gets the global shared session via `get_crawl_session()` (line 22):
```python
self._session = get_crawl_session()
```

When `APIAdapter.close()` is called, it closes the **global shared session**. This affects all other adapters (including `WebAdapter`) that are using the same global session.

**Impact:** After an `APIAdapter` instance closes, any subsequent requests by `WebAdapter` or other `APIAdapter` instances using the global session will fail because the underlying connection pool is closed.

**Same issue exists in `WebAdapter`** at `web.py:48-49`.

### 2. RSSAdapter Redirect Handler Assignment Method
**Location:** `adapters/rss.py:52`
```python
self._session.redirect_handler = SSRFSafeRedirectHandler()
```

**Issue:** The `requests.Session.redirect_handler` is normally a class attribute that gets passed to `PreparedRequest` objects during redirect handling. Setting it as an instance attribute like this is non-standard and relies on implementation details of the `requests` library.

The documentation acknowledges this quirk (line 135):
> **Interface Verification:** The `SSRFSafeRedirectHandler.__call__` signature is `(self, request, response, **kwargs)`. While this differs from the `requests.Session.redirect_handler` expected interface...

However, the documentation does not mention that setting `session.redirect_handler` directly as an instance attribute (rather than subclassing or using a proper redirect handler mechanism) is also non-standard.

---

## Security Concerns

### 1. Shared Session Closure (From Bug #1)
The fact that `close()` on `APIAdapter` or `WebAdapter` closes the global shared session is a security/reliability concern:
- Race condition: If multiple adapters are used concurrently and one closes, others fail
- Resource leak: Closing the session doesn't reset `_CRAWL_SESSION` to `None`, so `get_crawl_session()` continues returning the closed session

### 2. Global Session Reuse After Close
**Location:** `adapters/session.py:58-76`
```python
def get_crawl_session() -> requests.Session:
    global _CRAWL_SESSION
    if _CRAWL_SESSION is None:
        ...
```

After `close()` is called on the global session, `_CRAWL_SESSION` still holds the reference to the closed session. The singleton check `if _CRAWL_SESSION is None` will be `False`, so the closed session will continue to be returned.

---

## Improvements

### 1. Update Documentation for `RawItem` Terminology
Replace all occurrences of `ArticleData` with `RawItem` in the documentation to match actual implementation.

### 2. Update Filter Operations Documentation
Remove "(no `contains`)" from the filter operations description since `contains` is implemented.

### 3. Consider Not Closing Shared Session
`APIAdapter.close()` and `WebAdapter.close()` should NOT close the global shared session. They should either:
- Not implement `close()`, relying on the global session lifecycle
- Or only close their session if it's NOT the global shared session

### 4. Add Thread-Safety Warning for Global Session
The global session is not thread-safe for adapter instances that share it. If multiple adapters run concurrently and one closes the session, others will be affected. Consider documenting this limitation.

### 5. Standardize Redirect Handler Assignment
Instead of directly assigning `self._session.redirect_handler`, consider using a custom `requests.Session` subclass or a middleware approach for more predictable behavior.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 9 |
| Discrepancies | 3 |
| Bugs | 2 |
| Security Concerns | 2 |
| Improvements | 5 |

**Priority Issues:**
1. **Critical Bug:** `APIAdapter` and `WebAdapter` close the shared global session, potentially breaking other adapters
2. **Documentation Error:** Use `RawItem` instead of `ArticleData`
3. **Documentation Error:** `contains` filter is implemented (contrary to docs)
