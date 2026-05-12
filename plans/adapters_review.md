# Adapters Architecture Review

## Verified Claims

### 1. Adapter Pattern with `@register_adapter` Decorator
**Status: VERIFIED**

- `base.py` defines `_ADAPTER_REGISTRY` dict (line 18) and `register_adapter(source_type)` function (lines 23-28)
- `SOURCE_ADAPTERS` exports the registry (line 20)
- All three adapters correctly use the decorator:
  - `rss.py` line 41: `@register_adapter("rss")`
  - `api.py` line 16: `@register_adapter("api")`
  - `web.py` line 29: `@register_adapter("web")`
- `get_adapter_class()` correctly retrieves adapters from registry (lines 31-35)

### 2. SSRF Protection via `validate_url_safe`
**Status: VERIFIED**

- `utils/url.py` implements comprehensive SSRF protection with `_BLOCKED_NETWORKS` list (lines 96-111)
- Blocked networks include: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 0.0.0.0/8, 169.254.0.0/16, 224.0.0.0/4, 240.0.0.0/4, and IPv6 equivalents
- `validate_url_safe()` only allows http/https schemes (line 249)
- DNS resolution with cache to detect DNS rebinding attacks (lines 197-236)
- `SSRFSafeRedirectHandler` in `session.py` calls `validate_url_safe(location)` on redirects (line 34)

### 3. Clean Layering (No Services Imports)
**Status: VERIFIED**

- Adapters do NOT import from `services/` module
- `base.py` comment at line 113 explicitly notes: "to avoid layering violations (adapters should not import from services)"
- All adapters import from `utils/` for URL validation, which is correct

### 4. Source Health Tracking Fields Exist
**Status: VERIFIED**

- `models/source.py` has `consecutive_failures` (line 19) and `consecutive_successes` (line 20) fields

### 5. Error Handling Structure
**Status: PARTIALLY VERIFIED**

- Parse errors in `fetch_and_parse()` catch `ValueError, KeyError, AttributeError` and log warning (base.py lines 64-65)
- Network errors in `fetch()` methods use `raise_for_status()` which raises on HTTP errors
- WebAdapter has retry logic with exponential backoff for 429 responses (web.py lines 180-182)

---

## Discrepancies

### 1. Source Health Tracking NOT Done by Adapters
**Architecture Doc Claims:** "Source health: Update `Source.consecutive_failures/successes`"

**Reality:** Adapters do NOT update `consecutive_failures` or `consecutive_successes`. This is handled by `services/crawling.py` via `record_crawl_failure()` and `record_crawl_success()` functions (lines 222-265). Adapters have no knowledge of these updates.

### 2. "Retry-After Headers" NOT Respected
**Architecture Doc Claims:** "Rate limiting: Respect `Retry-After` headers"

**Reality:** The adapters do NOT read or respect the `Retry-After` header. `WebAdapter._polite_get()` implements basic exponential backoff on 429 (lines 180-182), but uses fixed wait times (`2**attempt * 5 + random.uniform(0, 2)`) rather than parsing the `Retry-After` header.

### 3. APIAdapter Pagination Implementation Differs from Docs
**Architecture Doc Claims:** "Pagination support (cursor, offset, page-based)"

**Reality:** The `APIAdapter` has no `cursor`, `offset`, or `page` pagination parameters. It implements:
- `item_url`: For fetching individual items by ID (api.py lines 45-51, 124-140)
- `list_items_path`: JSONPath for extracting items from response (line 38)
- `list_method`: Either `json_array` or `json_object_items` (lines 35-40)

### 4. WebAdapter Has Additional trafilatura Extraction
**Architecture Doc Does Not Mention:** The WebAdapter includes trafilatura-based content extraction as a fallback when CSS selector body text is insufficient (web.py lines 112-122)

---

## Bugs Found

### Bug 1: SSRFSafeRedirectHandler Redirect Counter Accumulates Across Requests

**Location:** `adapters/session.py` lines 21-23, 30-32

**Issue:** The `_redirect_count` instance variable on `SSRFSafeRedirectHandler` persists across ALL requests when using the shared `get_crawl_session()` singleton.

**Code:**
```python
class SSRFSafeRedirectHandler:
    def __init__(self) -> None:
        self._max_redirects = 30
        self._redirect_count = 0  # Persists across requests!
```

**Problem:** 
- `get_crawl_session()` returns a global singleton session (lines 45-63)
- This singleton session has ONE `SSRFSafeRedirectHandler` instance
- The `_redirect_count` accumulates across different redirect chains from different requests
- After 30 successful redirects across ANY requests, subsequent redirects will fail with `TooManyRedirects`

**Impact:** After enough successful crawl operations, adapters may get false `TooManyRedirects` errors.

**Fix:** The counter should be reset when a new request starts, or the handler should be request-scoped rather than session-scoped.

### Bug 2: get_crawl_session() Creates Session Without SSRF Handler

**Location:** `adapters/session.py` lines 45-63

**Issue:** When `get_crawl_session()` creates the singleton session, it correctly sets `redirect_handler` (line 63). However, `RSSAdapter` creates its own session (rss.py line 47) and sets its own `SSRFSafeRedirectHandler` (line 52). The APIAdapter and WebAdapter share the global session with the handler.

**Code:**
```python
# session.py line 63
_CRAWL_SESSION.redirect_handler = SSRFSafeRedirectHandler()

# rss.py lines 47-52
self._session = requests.Session()
# ... retry setup ...
self._session.redirect_handler = SSRFSafeRedirectHandler()  # Own handler
```

**Problem:**
- RSSAdapter has its own session and handler (counter resets per RSSAdapter instance)
- APIAdapter and WebAdapter share the global session and handler (counter accumulates)
- Inconsistent behavior between adapter types

---

## Improvement Recommendations

### 1. Add Retry-After Header Support to WebAdapter
Currently uses fixed exponential backoff. Should parse `Retry-After` header:

```python
# In _polite_get():
if resp.status_code == 429:
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            wait = int(retry_after)
        except ValueError:
            # HTTP date format - would need parsing
            pass
    else:
        wait = 2**attempt * 5 + random.uniform(0, 2)
    time.sleep(wait)
```

### 2. Document Source Health Tracking is Services Responsibility
The architecture doc should clarify that adapters only fetch/parse and report errors, while `services/crawling.py` handles source health tracking.

### 3. Remove Pagination Documentation Error
The architecture doc should accurately reflect APIAdapter's `item_url` pattern rather than claiming cursor/offset/page pagination.

### 4. Consider Request-Scoped Redirect Handler
The `SSRFSafeRedirectHandler` should be reset per-request rather than accumulating. Consider:
- Using a thread-local counter
- Creating a new handler per request
- Using the requests library's built-in redirect handling with custom redirect logic

### 5. Add Error Propagation to fetch_and_parse
Currently `fetch_and_parse()` catches exceptions and returns empty list on parse errors. Consider:
- Adding a metric/counter for parse failures
- Making fetch errors more distinguishable from parse errors

---

## Layer Violations

### None Found

The adapters correctly follow the architecture:
- No adapter imports from `services/`
- All URL validation uses `utils/url.py` (not `services/url.py`)
- Business logic like `_classify_topics()` is defined within `adapters/base.py` to avoid layering violations

---

## Summary

| Claim | Status |
|-------|--------|
| @register_adapter decorator | VERIFIED |
| SSRF protection (internal IPs, javascript:, data:) | VERIFIED |
| Source health tracking in adapters | **FALSE** - done in services/crawling.py |
| Retry-After header handling | **FALSE** - not implemented |
| Clean layering (no services imports) | VERIFIED |
| Pagination (cursor/offset/page) | **FALSE** - different implementation |
