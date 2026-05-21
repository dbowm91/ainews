# Adapters Module Architecture Review

**Review Date:** 2026-05-21  
**Reviewed File:** `architecture/adapters.md`  
**Code Source:** `adapters/` directory

---

## Summary

The architecture document is largely accurate and well-structured. Most claims match the actual implementation. Several discrepancies and a few bugs were identified.

---

## Verified Correct

### 1. Registry Pattern (`base.py`)

The `@register_adapter` decorator correctly registers adapters in `_ADAPTER_REGISTRY`:

```python
_ADAPTER_REGISTRY: dict[str, type[BaseSourceAdapter]] = {}

def register_adapter(source_type: str):
    def decorator(cls):
        _ADAPTER_REGISTRY[source_type] = cls
        return cls
    return decorator
```

The `SOURCE_ADAPTERS` alias points to the same registry. The `get_adapter_class()` function correctly raises `KeyError` with available adapters when not found.

### 2. RSSAdapter Implementation (`rss.py`)

- **Feed fetching**: Uses `feedparser.parse()` correctly
- **Malformed feed fallback**: `_scrape_feed_fallback()` uses BeautifulSoup to extract from HTML
- **Validation**: `_validate_feed()` checks for `entries` existence
- **Session management**: Creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`
- **User-Agent**: Correctly set to `AINwsBot/1.0` (configurable)

### 3. APIAdapter Implementation (`api.py`)

- **List method support**: Correctly handles `json_array` and `json_object_items` via `list_items_path`
- **Field extraction**: `_resolve_path()` implements JSONPath-like extraction (e.g., `$.id`, `$.title`)
- **Item URL pattern**: Supports individual item fetching via `item_url` template
- **Filters**: Implements `equals`, `min`, and `exists` filter operations
- **Authentication**: Correctly injects Bearer token via `auth_header` or `Authorization` fallback

### 4. WebAdapter Implementation (`web.py`)

- **CSS selector extraction**: Uses BeautifulSoup's `select_one()` with configured selectors
- **Pagination**: Recursive `_scrape_listing()` follows pagination links via `next_link_selector`
- **Rate limiting backoff**: Uses `2**attempt * 5 + jitter` formula (line 181)
- **User-Agent rotation**: Falls back to browser User-Agents when configured as `AINwsBot/1.0`
- **Trafilatura integration**: Extracts content via trafilatura with fallback to CSS selectors

### 5. SSRFSafeRedirectHandler (`session.py`)

- **Thread-local counter**: Uses `_thread_local` for per-request redirect counting (lines 29-35)
- **Redirect validation**: Calls `validate_url_safe()` on each redirect target
- **Max redirects**: Raises `TooManyRedirects` after 30 redirects
- **Blocklist enforcement**: Relies on `utils.url.validate_url_safe()` which blocks:
  - Private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x, etc.)
  - Reserved IPs (169.254.x, 224.x, 240.x)
  - IPv6 addresses (::1, fc00::/7, fe80::/10, ff00::/8, ::/128, ::ffff:0:0/96)

### 6. Source Configuration Schema (`schemas/source.py`)

- **Adapter config validation**: `SourceConfig.validate_adapter_config()` correctly validates against `ADAPTER_CONFIGS` based on source type
- **RSSConfig fields**: `feed_url`, `max_items`, `request_timeout`, `user_agent` all present
- **APIConfig fields**: `list_url`, `list_method`, `list_items_path`, `item_url`, `fields`, `filters` all present
- **WebConfig fields**: `listing_url`, `listing` (with `card_selector`, `link_selector`, `link_attribute`), `article` (with selectors) all present

### 7. Layering Compliance

Adapters do NOT import from `services/`:
- `base.py` imports from `schemas.item`, `schemas.source`, and `utils.url`
- `rss.py` imports from `adapters.base`, `schemas.source`, `utils.url`, and `adapters.session`
- `api.py` imports from `adapters.base`, `adapters.session`, `schemas.source`, `utils.url`
- `web.py` imports from `adapters.base`, `adapters.session`, `schemas.source`, `utils.url`
- `session.py` imports from `utils.url`

**No services imports found in adapters directory.** The comment in `base.py` line 113 explicitly acknowledges this design principle.

### 8. Error Handling Claims

- **Network errors**: Adapters return empty lists on fetch failures (verified in all three adapters)
- **Parse errors**: `fetch_and_parse()` catches `ValueError, KeyError, AttributeError` and logs warnings
- **Source health tracking**: Documented correctly - `services/crawling.py` handles `consecutive_failures/successes` updates (not adapters)
- **Rate limiting backoff**: Documented formula matches `WebAdapter._polite_get()` implementation

---

## Discrepancies Found

### 1. Documentation Mentions `item_path` but Implementation Uses `list_items_path`

**Document says (line 78):**
```python
self.item_path = config.get('item_path', '$.items[*]')
```

**Actual implementation (`schemas/source.py` line 45):**
```python
list_items_path: Optional[str] = None
```

**Actual usage in `api.py` (line 37):**
```python
elif cfg.list_method == "json_object_items" and cfg.list_items_path:
```

The documentation should be updated to reflect `list_items_path` and `list_method` instead of `item_path`.

### 2. Documentation Mentions `field_mappings` for RSS but Config is Flat

**Document says (line 147-148):**
```yaml
adapter_config:
  item_path: "entries"
  field_mappings:
    title: "title"
    url: "link"
```

**Actual `RSSConfig` (`schemas/source.py` lines 29-39):**
```python
class RSSConfig(BaseModel):
    feed_url: str
    max_items: int = 50
    request_timeout: int = 15
    user_agent: str = "AINwsBot/1.0"
    min_content_length: int = 200
```

RSSAdapter maps fields internally (e.g., `raw.get("title")`, `raw.get("link")`) rather than via configurable `field_mappings`. The documentation is inaccurate for RSS adapter config.

### 3. WebAdapter Uses `listing_url` not `listing_url` in Config

**Document shows (line 163):**
```python
self.listing_url = config['listing_url']
```

This matches actual implementation (`WebConfig` has `listing_url`). The document is correct.

### 4. Documentation Claims Authentication Supports "Bearer, API key headers" but Implementation Only Supports Bearer

**Document says (line 83):**
```python
# Handles authentication (Bearer, API key headers)
```

**Actual `APIAdapter._fetch_item()` (lines 130-134):**
```python
if cfg.api_key:
    if cfg.auth_header:
        headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
    else:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
```

The implementation only supports Bearer token authentication. There is no support for API key headers like `X-Api-Key`.

---

## Bugs Identified

### BUG-1: APIAdapter Missing Pagination Support

**Severity:** Medium  
**Location:** `adapters/api.py`

The document claims (line 81):
```python
# Supports pagination (cursor, offset, page)
```

The actual `APIAdapter` implementation has NO pagination support. The `fetch()` method only makes a single request to `list_url`. There is no mechanism for cursor-based, offset-based, or page-based pagination in the API adapter.

**Note:** `WebAdapter` does have pagination support via `ListingConfig.pagination`.

### BUG-2: SSRFSafeRedirectHandler Allows Relative Redirects

**Severity:** Medium  
**Location:** `adapters/session.py` lines 50-52

```python
except ValueError as e:
    parsed = urlparse(location)
    if not parsed.scheme or not parsed.netloc:
        raise requests.exceptions.InvalidURL(f"Invalid redirect location: {location}") from e
```

The handler catches `ValueError` from `validate_url_safe()` (which happens when scheme is missing) and only raises `InvalidURL` if scheme OR netloc is missing. A relative URL like `/evil/redirect` has no scheme AND no netloc, but the code raises `InvalidURL`.

However, a redirect to `//evil.com` (netloc-only URL interpreted as scheme-relative) would pass because it has no scheme but does have a netloc. This could be an SSRF vector.

**Actual behavior:** The `validate_url_safe()` on line 46 would be called with `//evil.com`, which would parse as scheme-relative. The URL would pass since the scheme check in `validate_url_safe()` only catches schemes not in `http/https`, and `//` is not a scheme.

### BUG-3: WebAdapter Body Selector Inefficiency

**Severity:** Low  
**Location:** `adapters/web.py` lines 107-122

When `body_selector` is configured and body text is found via that selector, the code still attempts trafilatura extraction if the body is shorter than `MIN_CONTENT_LENGTH`. This is correct behavior.

However, the `min_content_length` config in `WebConfig` is used to decide whether to try trafilatura, but the config doesn't have this field - it only exists in `RSSConfig`.

**Actually verified:** `WebConfig` does NOT have `min_content_length` field, but the code at line 111 compares `len(body) < MIN_CONTENT_LENGTH` where `MIN_CONTENT_LENGTH = 200` (hardcoded).

This is not a bug - it's a design choice to use a constant. But the documentation doesn't mention this.

---

## Improvement Suggestions

### IMP-1: Add Pagination Support to APIAdapter

The API adapter should support pagination similar to the Web adapter. The implementation could use:
- Cursor-based: track `next_cursor` field
- Offset-based: increment offset parameter
- Page-based: increment page parameter

### IMP-2: Update Documentation for `list_items_path` and `list_method`

The documentation should reflect the actual `list_items_path` and `list_method` configuration instead of the non-existent `item_path`.

### IMP-3: Add Support for API Key Header Authentication

Currently only Bearer token authentication is supported. Many APIs use custom headers like `X-Api-Key`. The `APIConfig` should add an `api_key_header` field.

### IMP-4: Improve SSRFSafeRedirectHandler for Scheme-Relative URLs

Consider blocking scheme-relative URLs (those starting with `//`) at the redirect handler level, as they can be used for cross-domain redirects.

### IMP-5: Document Hard-Coded Constants

The `MIN_CONTENT_LENGTH = 200` in `WebAdapter` and other constants should be documented or made configurable.

---

## Questions for Architecture

### Q-1: Should APIAdapter Support Pagination?

The architecture document explicitly mentions "pagination (cursor, offset, page)" for the API adapter, but the implementation has no pagination support. Was pagination planned but never implemented? Should it be added?

### Q-2: What Authentication Methods Should Be Supported?

The current implementation only supports Bearer token authentication. Should we add support for:
- API key in header (`X-Api-Key`, etc.)
- Basic auth
- OAuth

### Q-3: Should RSS `field_mappings` Be Configurable?

The RSS adapter currently hard-codes field mapping (title, link, author, published, content). Should this be made configurable via `field_mappings` as documented?

### Q-4: Scheme-Relative URL Handling

The SSRFSafeRedirectHandler allows scheme-relative URLs (`//evil.com`). Should these be blocked at the redirect handler level, or is relying on the subsequent `validate_url_safe()` call sufficient?

---

## Conclusion

The architecture document is generally accurate and well-organized. The main discrepancies are:
1. API adapter pagination not implemented (but documented)
2. `list_items_path` vs `item_path` naming mismatch
3. Authentication limited to Bearer tokens (but document suggests broader support)

The implementation is solid with proper layering, SSRF protection, and error handling. The identified bugs and suggestions are minor and don't indicate fundamental architectural issues.
