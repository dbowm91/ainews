# Adapters Module Architecture Review

## Summary

The `adapters/` module implements the infrastructure layer for fetching content from different source types. The architecture document at `architecture/adapters.md` is mostly accurate, with all major claims verified. However, several discrepancies and issues were identified.

## Verified Claims

### ✅ File Inventory (lines 18-25)
All files exist as documented:
- `adapters/base.py` - BaseSourceAdapter with registry decorator
- `adapters/rss.py` - RSSAdapter using feedparser + BeautifulSoup
- `adapters/api.py` - APIAdapter with JSONPath extraction
- `adapters/web.py` - WebAdapter with CSS selectors
- `adapters/session.py` - SSRFSafeRedirectHandler

### ✅ Layering Rules (line 3)
> "Adapters must NOT contain business logic and should NOT import from services"

**Verified**: No adapters import from `services/` at runtime. The `TYPE_CHECKING` block in `services/crawling.py` is intentional and documented with a comment explaining the layer violation.

### ✅ Registry Pattern (lines 42-49)
`register_adapter` decorator correctly populates `_ADAPTER_REGISTRY`. The `SOURCE_ADAPTERS` alias is properly exported.

### ✅ BaseSourceAdapter Interface (lines 29-40)
`fetch()` and `parse_item()` are abstract methods. `fetch_and_parse()` combines them with error handling (catches `ValueError`, `KeyError`, `AttributeError`).

### ✅ Session Ownership (lines 140-154)
- **RSSAdapter**: Creates its own `requests.Session` with own `SSRFSafeRedirectHandler` (line 52: `self._session.redirect_handler = SSRFSafeRedirectHandler()`)
- **APIAdapter/WebAdapter**: Share global session from `get_crawl_session()` (confirmed in code)

### ✅ SSRF Protection (lines 120-133)
`SSRFSafeRedirectHandler` correctly:
- Uses thread-local storage for redirect counter (`_thread_local`)
- Blocks unsafe redirects with `validate_url_safe()`
- Decrements counter on `UnsafeURLError` to prevent counter exhaustion attacks
- Has `javascript:` and `data:` schemes blocked via `validate_url_safe()`

### ✅ WebAdapter Trafilatura Fallback (line 118)
Documented correctly. trafilatura is used when CSS selector body extraction yields < 200 chars.

---

## Discrepancies and Issues

### 1. SSRF Handler Not Based on urllib HTTPRedirectHandler (HIGH)

**Document says** (line 126):
> "Custom redirect handler (not based on urllib HTTPRedirectHandler)"

**Actual code** (`adapters/session.py:16-55`):
```python
class SSRFSafeRedirectHandler:
    def __init__(self) -> None:
        self._max_redirects = 30

    @property
    def _redirect_count(self) -> int:
        return getattr(_thread_local, 'redirect_count', 0)

    @_redirect_count.setter
    def _redirect_count(self, value: int) -> None:
        _thread_local.redirect_count = value

    def __call__(self, request: requests.Response, response: requests.Response, **kwargs) -> requests.PreparedRequest | None:
```

**Issue**: This is not a standard urllib handler interface. It's a callable that acts as a redirect handler for `requests.Session`, but the signature `__call__(self, request, response, **kwargs)` doesn't match what `requests` expects for a redirect handler. The `requests.Session` uses `redirect_handler` attribute differently than assumed.

**Bug location**: `adapters/session.py:37` - `__call__` signature is wrong. For `requests.Session`, the redirect handler should be a callable that accepts `(request, response, context)` but the actual behavior depends on how `requests` internally calls it.

**Verification needed**: This handler may not actually receive all redirects due to the non-standard signature.

### 2. Rate Limiting Does Not Read Retry-After Header (MED)

**Document says** (line 196):
> "Rate limiting: Fixed exponential backoff (2^attempt * 5 + jitter), NOT reading Retry-After header"

**Actual code**:
- `adapters/web.py:181`: `wait = 2**attempt * 5 + random.uniform(0, 2)` - **Confirmed**: No Retry-After header handling
- `adapters/api.py`: No Retry-After handling - **Confirmed**

**Issue**: This is correct as documented. However, the document states this as a fact but it should be noted as intentional design choice. The `services/llm/errors.py` has `RetryAfterError` class that can parse Retry-After headers, but this is not used by adapters.

### 3. APIAdapter _passes_filters Missing "contains" Operation (MED)

**Document says** (line 91):
> "Filter operations: `equals`, `min`, `exists` (no `contains`)"

**Actual code** (`adapters/api.py:194-209`):
```python
def _passes_filters(self, data: Any, filters: list[dict]) -> bool:
    if not filters:
        return True
    for f in filters:
        current = self._resolve_path(data, f.get("field", ""))
        if "equals" in f and current != f["equals"]:
            return False
        if "min" in f:
            try:
                if float(current) < f["min"]:
                    return False
            except (ValueError, TypeError):
                return False
        if "exists" in f and f["exists"] and current is None:
            return False
    return True
```

**Verified**: Only `equals`, `min`, and `exists` are implemented. `contains` is not implemented, matching the documentation.

### 4. Source Health Tracking Correctly Delegated (MED)

**Document says** (line 197):
> "Source health: Adapters do NOT update `Source.consecutive_failures/successes` — this is handled by `services/crawling.py` after adapter returns"

**Verified**: `services/crawling.py:216-267` has `record_crawl_success()` and `record_crawl_failure()` that update `consecutive_failures` and `consecutive_successes`. Adapters do not touch these fields.

### 5. WebAdapter Request Delay Per-Article (MED)

**Document says** (lines 135-138):
> "The `request_delay_min`/`request_delay_max` configuration in `WebConfig` applies **per-article**, not per-page."

**Actual code** (`adapters/web.py:171-175`):
```python
def _polite_get(self, url: str) -> Optional[BeautifulSoup]:
    cfg = self.adapter_config
    validate_url_safe(url)
    delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
    time.sleep(delay)
```

**Verified**: Delay is applied in `_polite_get()` which is called per article URL in `fetch()` loop (line 64). This is correct per-document.

### 6. APIAdapter item_url Fetches By ID Template (HIGH - Potential Bug)

**Document says** (lines 88-89):
> "Item URL template for individual item fetching via `item_url`"

**Actual code** (`adapters/api.py:63-71`):
```python
if cfg.item_url and all_items:
    fetched = []
    for item_id in all_items[: cfg.max_items]:
        item = self._fetch_item(item_id)
        if item:
            fetched.append(item)
    return fetched
```

**Issue**: The `all_items` list contains the **full item objects** from the list endpoint, not just IDs. The code passes these to `_fetch_item(item_id)` which then calls `cfg.item_url.format(id=item_id)`. 

If `list_method` is `json_array`, `all_items` contains full objects, not IDs. The `_fetch_item` method then does:
```python
def _fetch_item(self, item_id) -> Optional[dict]:
    try:
        url = cfg.item_url.format(id=item_id)  # item_id is actually a dict!
```

This will fail because `item_id` is a dict, not a string, and `cfg.item_url.format()` will raise a `KeyError` or produce garbage URLs.

**Bug location**: `adapters/api.py:63-71` and `adapters/api.py:158-174`

### 7. APIAdapter Pagination Query Param Handling (MED - Bug)

**Document doesn't mention**: The `_increment_query_param` method in APIAdapter has a bug at line 85:
```python
qs[page_param] = [str(page + 1)]
```

When `page_param` doesn't exist in `qs` (neither "page" nor "offset" are present), this creates a new parameter. But if neither is found, the code defaults to "page" which may not be the actual pagination parameter used by the API.

Additionally, for page 1, it sets `qs[page_param] = ["2"]`, which means the first fetch with `next_url = cfg.list_url` will have `page=2` applied **before** the first page is fetched if pagination is triggered.

**Bug location**: `adapters/api.py:78-88`

---

## Recommendations

### CRIT

1. **APIAdapter item_url bug** (`adapters/api.py:63-71`)
   - When `list_method` is `json_array`, `all_items` contains full objects but code treats them as IDs
   - `_fetch_item()` receives dict instead of string ID
   - Fix: Use `cfg.fields.get("external_id")` or similar to extract ID from item objects before calling `_fetch_item`

### HIGH

2. **SSRFSafeRedirectHandler interface mismatch** (`adapters/session.py:37`)
   - Handler signature doesn't match what `requests.Session` expects for redirect handlers
   - Verify that redirects are actually being intercepted and validated
   - The `__call__` method signature `(self, request: requests.Request, response: requests.Response, **kwargs)` is non-standard

3. **APIAdapter pagination off-by-one** (`adapters/api.py:85`)
   - When using `query_param` pagination, first page load already uses `page=2`
   - Should start with `page=1` (original URL) then increment to `page=2` for next

### MED

4. **WebAdapter redirect handler not configured**
   - `WebAdapter` uses `get_crawl_session()` which has the global `SSRFSafeRedirectHandler`
   - But `WebAdapter` doesn't explicitly set `redirect_handler` attribute
   - The global session's handler is shared, which is correct per architecture, but should be documented

5. **Missing `contains` filter** (`adapters/api.py:194-209`)
   - Document states `contains` is not implemented - this is accurate
   - Consider adding if API sources require it

6. **RSSAdapter retry configuration** (`adapters/rss.py:48`)
   - Uses `backoff_factor=1` which gives retries at 1s, 2s, 4s intervals
   - `WebAdapter` uses implicit retry via session adapter with same `backoff_factor=1`
   - `APIAdapter` uses same pattern - consistent but not documented

### LOW

7. **Documentation missing pagination behavior for query_param type**
   - The document mentions pagination but doesn't explain that `query_param` type requires the pagination parameter to already exist in `list_url`

8. **trafilatura fallback warning** (`adapters/web.py:120`)
   - When trafilatura is not installed, a warning is logged but no fallback is provided
   - This is correct behavior but could be more user-friendly

---

## Verified Claims Summary

| Claim | Status |
|-------|--------|
| File inventory complete | ✅ |
| Registry pattern works | ✅ |
| Layering rules respected | ✅ |
| RSSAdapter own session | ✅ |
| API/WebAdapter shared session | ✅ |
| SSRF protection implemented | ✅ (with concerns) |
| Rate limiting exponential backoff | ✅ |
| Retry-After NOT used | ✅ |
| Source health delegated to services | ✅ |
| Request delay per-article | ✅ |
| Filter operations: equals, min, exists only | ✅ |
| WebAdapter trafilatura fallback | ✅ |

---

## Files Reviewed

- `adapters/base.py` - lines 1-147
- `adapters/rss.py` - lines 1-118
- `adapters/api.py` - lines 1-209
- `adapters/web.py` - lines 1-224
- `adapters/session.py` - lines 1-77
- `adapters/__init__.py` - lines 1-5
- `schemas/source.py` - lines 1-150
- `schemas/item.py` - lines 1-19
- `utils/url.py` - lines 1-262
- `services/crawling.py` - lines 1-267