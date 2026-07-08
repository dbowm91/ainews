---
name: adapter_system
description: "Adapter system for source content extraction — covering RSSAdapter, APIAdapter, WebAdapter, session management, config validation, and SSRFSafeRedirectHandler. Triggers: adapter, rss, api, web, crawl, session, ssrf."
---

## Adapter Types

### RSSAdapter

**Location:** `adapters/rss.py`
- Creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`
- Independent session management (does NOT share global session)
- Properly closes its session in `close()` method

### APIAdapter

**Location:** `adapters/api.py`
- Uses shared global session from `get_crawl_session()`
- Has pagination support via `PaginationConfig`
- Implements `close()` as no-op (does NOT close shared session)

### WebAdapter

**Location:** `adapters/web.py`
- Uses shared global session from `get_crawl_session()`
- Implements `close()` as no-op (does NOT close shared session)
- Content extraction: CSS selectors first, then trafilatura if body is too short/missing

## Session Management

### Shared Session Pattern

`APIAdapter` and `WebAdapter` share the global session from `get_crawl_session()`. This is BY DESIGN — different adapter types have different session management requirements.

**Critical:** APIAdapter and WebAdapter implement `close()` as empty pass. They do NOT close the shared global session because doing so would break other adapters using the same session.

### SSRFSafeRedirectHandler

**Location:** `adapters/session.py`

Validates redirect URLs via `validate_url_safe()` before allowing redirect:
- Blocks internal IPs (10.x, 172.16-31.x, 192.168.x)
- Blocks private hostnames
- Blocks scheme-relative URLs (`//evil.com`)
- Uses thread-local storage for `_redirect_count` to prevent cross-request accumulation

**Redirect handler tests**: `tests/test_services_search_session.py` covers redirect counting, thread-local storage, UnsafeURLError propagation, and max-redirect enforcement.

## Adapter Configuration

### SourceConfig Validation

`SourceConfig.config` in `schemas/source.py` has a `field_validator` that validates config against the appropriate adapter schema:
- RSSConfig for RSS sources
- APIConfig for API sources
- WebConfig for Web sources

The `ADAPTER_CONFIGS` dict maps source type to config class.

### Config Fields by Type

**RSSConfig:** `max_items`, `request_delay_min`, `request_delay_max`

**APIConfig:**
- `list_url`: URL to fetch items from
- `list_method`: `"json_array"` or `"json_object_items"`
- `list_items_path`: JSONPath to items array (optional)
- `next_link`: Pagination type - extracts next URL from JSON response via JSONPath selector
- `query_param`: Pagination type - increments page/offset query parameter
- `none`: Disables pagination
- `max_pages`: Default 3
- `max_items`: Default 50
- Filter operations: `equals`, `min`, `exists`, `contains`
- Only supports Bearer token authentication

**WebConfig:**
- `max_items`: Default 50, max 200
- `request_delay_min`: Minimum delay between HTTP requests in seconds
- `request_delay_max`: Maximum delay between HTTP requests in seconds

## Pagination

### APIAdapter Pagination Types

1. **`next_link`**: Extracts next URL from JSON response via JSONPath
   ```yaml
   pagination:
     type: next_link
     path: "$.next_page_url"
   ```

2. **`query_param`**: Increments page/offset query parameter
   ```yaml
   pagination:
     type: query_param
     param: page
     start: 1
   ```

3. **`none`**: Disables pagination

### WebAdapter Pagination

WebAdapter has `max_items` cap on article collection per page:
- Default: 50 items
- Maximum: 200 items
- Cap enforced at `adapters/web.py:152-153`

## Content Extraction

### WebAdapter Extraction Order

1. Try CSS selectors first (via `parse_article_body()`)
2. If body is too short/missing, try trafilatura
3. If trafilatura fails, return EMPTY status (no raw HTML fallback)

### Trafilatura Fallback

`adapters/web.py:108-119` shows the fallback order:
- trafilatura is tried as second extraction method
- If trafilatura fails, returns `ExtractionResult` with `ExtractionStatus.EMPTY`

## URL Validation Layering

Adapters import from `utils/url.py` for SSRF protection (clean layering):
```python
from utils.url import validate_url_safe, UnsafeURLError
```

`services/url.py` has duplicate SSRF implementation with config support, but adapters should NOT import from `services/url.py`.

## RawItem Schema

All adapters produce a `RawItem` (from `schemas/item.py`):

```python
class RawItem(BaseModel):
    source_id: str
    external_id: str
    title: str
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    text_content: str | None = None
    raw_score: float = 0.0
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
```

## Key Files

| File | Purpose |
|------|---------|
| `adapters/base.py` | `BaseSourceAdapter`, `RawItem` schema |
| `adapters/rss.py` | RSSAdapter with own session |
| `adapters/api.py` | APIAdapter with pagination, filters, Bearer auth |
| `adapters/web.py` | WebAdapter with CSS/trafilatura extraction |
| `adapters/session.py` | `get_crawl_session()`, `SSRFSafeRedirectHandler` |
| `schemas/source.py` | `SourceConfig`, `RSSConfig`, `APIConfig`, `WebConfig` |
| `schemas/item.py` | `RawItem` schema |
| `utils/url.py` | SSRF protection for adapters |
| `services/safe_fetch.py` | Safe HTTP fetch client (SSRF, redirects, byte limits, content-type) |