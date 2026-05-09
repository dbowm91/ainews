# Adapters Architecture Review Plan

## Verified Claims

### Base Adapter & Registry
- **TRUE**: `BaseSourceAdapter` is an abstract base class with `fetch()` and `parse_item()` abstract methods
- **TRUE**: `@register_adapter` decorator populates `_ADAPTER_REGISTRY` (exported as `SOURCE_ADAPTERS`)
- **TRUE**: `get_adapter_class()` raises `KeyError` with available adapters when source_type not found
- **TRUE**: `fetch_and_parse()` combines fetch + parse with error handling (catches ValueError, KeyError, AttributeError)
- **TRUE**: Adapters implement `match_topics()` which uses regex-based topic classification

### RSS Adapter
- **TRUE**: Uses `feedparser.parse()` for RSS/Atom feed parsing
- **TRUE**: Falls back to BeautifulSoup scraping for malformed feeds via `_scrape_feed_fallback()`
- **TRUE**: Feed validation via `_validate_feed()` checking for entries
- **TRUE**: Atom feed support via published_parsed/updated_parsed attribute handling
- **TRUE**: Config class is `RSSConfig`
- **TRUE**: Uses `SSRFSafeRedirectHandler` for redirect handling

### API Adapter
- **TRUE**: Config class is `APIConfig`
- **TRUE**: Has `_resolve_path()` for JSONPath-style field extraction
- **TRUE**: Has `_passes_filters()` for filtering items
- **TRUE**: Has `_fetch_item()` for per-item API fetching with authentication
- **TRUE**: Supports `item_url` for fetching individual items
- **TRUE**: Supports field mapping configuration
- **TRUE**: Uses `get_crawl_session()` for session management

### Web Adapter
- **TRUE**: Config class is `WebConfig`
- **TRUE**: Uses CSS selectors (`item_css`, `field_selectors`)
- **TRUE**: Has `_scrape_listing()` for pagination link following
- **TRUE**: Has `_polite_get()` with rate limiting and retry logic
- **TRUE**: Uses `trafilatura` for content extraction fallback
- **TRUE**: Uses `get_crawl_session()` for session management

### SSRF Protection
- **TRUE**: `SSRFSafeRedirectHandler` is NOT based on urllib's `HTTPRedirectHandler`
- **TRUE**: Custom `__call__` method validates redirect targets
- **TRUE**: Validates via `validate_url_safe()` for private IP checks
- **TRUE**: Blocks internal IP ranges (10.x, 172.16-31.x, 192.168.x)
- **TRUE**: Blocks `javascript:` and `data:` schemes via scheme validation in `validate_url_safe()`
- **TRUE**: Has `_max_redirects = 30` limit

### Layering (Adapters NOT Importing Services)
- **TRUE**: Adapters import from `schemas.item`, `schemas.source`, `utils.url`
- **TRUE**: Adapters do NOT import from `services` (verified with grep)
- **TRUE**: `_classify_topics()` is defined in `adapters/base.py` as a pure function to avoid layering violations

---

## Discrepancies

### Documented vs Actual Return Types
| Location | Documented | Actual |
|----------|-----------|--------|
| `BaseSourceAdapter.fetch()` returns | `list[dict]` | `list[Any]` |
| `BaseSourceAdapter.parse_item()` returns | `ArticleData` | `Optional[RawItem]` |

### API Adapter Pagination
- **DOCUMENTED**: "Pagination support (cursor, offset, page-based)"
- **ACTUAL**: The `APIConfig` schema has NO pagination fields (`cursor`, `offset`, `page` parameters). The API adapter only supports:
  - `list_method`: `json_array` or `json_object_items`
  - `list_items_path`: JSONPath to items
  - `item_url`: Per-item fetching URL
  - No cursor/offset/page-based pagination parameters exist in the config

### Error Handling - Source Health
- **DOCUMENTED**: "4. **Source health**: Update `Source.consecutive_failures/successes`"
- **ACTUAL**: Adapters do NOT update `Source.consecutive_failures` or `consecutive_successes`. This is handled by `services/crawling.py`, not the adapters. The document incorrectly attributes this to adapters.

### Error Handling - Rate Limiting
- **DOCUMENTED**: "3. **Rate limiting**: Respect `Retry-After` headers"
- **ACTUAL**: Adapters do NOT respect `Retry-After` headers. The WebAdapter has hardcoded retry logic in `_polite_get()` (exponential backoff on 429), but does not check for `Retry-After` headers. The RSSAdapter uses urllib3's `Retry` but does not handle `Retry-After` specifically. Only `services/llm/` handles `Retry-After` headers.

### Web Adapter Multiple Start URLs
- **DOCUMENTED**: "Multiple start URLs" as a feature
- **ACTUAL**: `WebConfig` only has `listing_url` (single URL), not multiple start URLs. The `start_urls` config field mentioned in the doc does not exist in `WebConfig`.

### Web Adapter - URL Discovery
- **DOCUMENTED**: "Link URL discovery" as a feature
- **ACTUAL**: `WebAdapter` does extract article URLs from listing pages, but the config shows `listing_url` (singular), not `start_urls` (plural). The documentation is misleading.

### RSS Adapter Config Field Name
- **DOCUMENTED**: Uses `url` parameter example in sources.yaml config
- **ACTUAL**: `RSSConfig` uses `feed_url` not `url`

### API Adapter Config Field Name
- **DOCUMENTED**: Uses `url` in sources.yaml example
- **ACTUAL**: `APIConfig` uses `list_url` not `url`

### Web Adapter Config Field Name
- **DOCUMENTED**: Uses `url` in sources.yaml example
- **ACTUAL**: `WebConfig` uses `listing_url` and `base_url`, not `url`

---

## Improvement Recommendations

1. **[MEDIUM]** **Update architecture doc to accurately reflect API pagination**: The API adapter does not support cursor/offset/page pagination. Either implement it or remove from documentation.

2. **[MEDIUM]** **Add pagination support to API adapter**: If cursor/offset/page pagination is needed, implement `pagination` config with type enum and parameters.

3. **[MEDIUM]** **Fix WebAdapter documentation**: `WebConfig` uses `listing_url` (singular), not `start_urls`. Update documentation or implement multiple start URLs if actually needed.

4. **[LOW]** **Document return type mismatch**: `BaseSourceAdapter.fetch()` returns `list[Any]` not `list[dict]` as documented. Update docstring and architecture doc.

5. **[LOW]** **Document actual config field names**: Update architecture doc's YAML examples to use actual field names (`feed_url` not `url`, `list_url` not `url`, `listing_url` not `url`).

6. **[LOW]** **Clarify source health tracking**: Architecture doc says adapters update source health, but this is done by `services/crawling.py`. Update doc to clarify this is handled by the crawling service, not adapters directly.

7. **[LOW]** **Clarify rate limiting responsibility**: Remove "Respect Retry-After headers" from adapter error handling list since adapters don't do this. Document that LLM services handle this.

---

## Bugs Found

1. **[LOW] SSRFSafeRedirectHandler reset bug**: In `session.py:41`, `_redirect_count` is reset to 0 after a successful redirect check, but the next redirect would start counting from 0 again. If there are many redirects within a single redirect chain, this could be bypassed. The counter should probably not be reset, or the logic should track per-host redirects.

2. **[LOW] WebAdapter date parsing silently returns None**: In `web.py:206-221`, `_parse_date()` silently returns `None` for unparseable dates. This is not a bug per se, but there's no logging when date parsing fails, making debugging difficult.

3. **[LOW] WebAdapter trafilatura ImportError suppressed broadly**: In `web.py:119`, the ImportError is caught with a general `except` that also catches ValueError and AttributeError. This could mask real issues. Should be more specific: `except ImportError`.

---

## Layer Violations

**NONE FOUND**: Verified that adapters do not import from `services/`. All imports are from:
- `schemas/` (item.py, source.py)
- `utils/` (url.py)
- Standard library (abc, hashlib, logging, requests, feedparser, BeautifulSoup, etc.)
- Third-party libraries (requests, feedparser, bs4, urllib3)

The architecture correctly documents that adapters should NOT import from services, and the code complies with this requirement.

---

## Summary

The adapters module is well-architected with proper layering (adapters do NOT import from services). The architecture document is mostly accurate but has several discrepancies:

1. **Pagination**: API adapter doesn't support cursor/offset/page pagination as documented
2. **Web start URLs**: Only single `listing_url`, not multiple `start_urls`
3. **Error handling**: Source health and Retry-After handling attributed to adapters but actually handled by services
4. **Config field names**: Document shows `url` but actual fields are `feed_url`, `list_url`, `listing_url`
5. **Return types**: Document shows `list[dict]` and `ArticleData` but actual types are `list[Any]` and `Optional[RawItem]`

The most impactful recommendation is to either implement the missing pagination features or update the documentation to match reality.
