# Adapters Architecture Review

## Summary

The `architecture/adapters.md` document is **highly accurate** overall. The adapter pattern, session ownership, SSRF protection, and constants are all correctly documented. One minor documentation simplification regarding WebAdapter's body fallback and a slight imprecision in the request delay description are the only notable issues.

## Verified Claims

### Adapter Pattern
- `@register_adapter` decorator registers in `_ADAPTER_REGISTRY` (`adapters/base.py:23-28`) - **VERIFIED**
- `SOURCE_ADAPTERS` is an alias for `_ADAPTER_REGISTRY` (`base.py:18-20`) - **VERIFIED**
- `BaseSourceAdapter` interface with all documented methods (`fetch`, `parse_item`, `fetch_and_parse`, `match_topics`, `_get_match_text`, `_hash_ext_id`, `_truncate`, `__enter__`, `__exit__`) - **VERIFIED**
- `_classify_topics` module-level function to avoid layering violations (`base.py:109-147`) - **VERIFIED**

### RSSAdapter
- Creates own `requests.Session` (`rss.py:47`) - **VERIFIED**
- Own `SSRFSafeRedirectHandler` instance (`rss.py:52`) - **VERIFIED**
- `validate_url_safe(cfg.feed_url)` called before fetch (`rss.py:59`) - **VERIFIED**
- Falls back to `_scrape_feed_fallback()` for malformed feeds (`rss.py:69-70`) - **VERIFIED**
- `_scrape_feed_fallback()` does NOT call `validate_url_safe()` - URL validated once in `fetch()` before any HTTP requests - **VERIFIED**
- `close()` properly closes own session (`rss.py:54-55`) - **VERIFIED**

### APIAdapter
- Uses shared global session via `get_crawl_session()` (`api.py:22`) - **VERIFIED**
- Bearer token auth via `auth_header` or `Authorization` fallback (`api.py:176-180`) - **VERIFIED**
- Pagination via `next_link` (JSONPath extraction) and `query_param` (increment) - **VERIFIED**
- JSONPath field extraction via `_resolve_path()` (`api.py:190-205`) - **VERIFIED**
- `close()` is no-op (`api.py:25-26`) - **VERIFIED**

### WebAdapter
- Uses shared global session via `get_crawl_session()` (`web.py:35`) - **VERIFIED**
- CSS selector-based extraction via `ListingConfig` and `ArticleSelectors` (`web.py:146-159`) - **VERIFIED**
- Pagination link following via `PaginationConfig` (`web.py:162-168`) - **VERIFIED**
- `base_url` used with `urljoin()` to resolve relative hrefs (`web.py:159,165`) - **VERIFIED**
- `close()` is no-op (`web.py:45-46`) - **VERIFIED**

### SSRF Protection
- `SSRFSafeRedirectHandler` validates redirect URLs - **VERIFIED** (`session.py:16-57`)
- Uses thread-local storage for redirect counting (`session.py:30-35`) - **VERIFIED**
- `__call__` signature is `(self, request, response, **kwargs)` (`session.py:37`) - **VERIFIED**
- Blocks `javascript:` and `data:` schemes via `validate_url_safe()` (`session.py:46`) - **VERIFIED**

### Constants
- `MAX_TEXT_LENGTH = 3000` in `base.py:14` - **VERIFIED**
- `MIN_CONTENT_LENGTH = 200` in `web.py:19` - **VERIFIED**
- `_max_redirects = 30` in `session.py:27` - **VERIFIED**

### Session Ownership
- RSSAdapter: Own session + own handler - **VERIFIED**
- APIAdapter: Shared global session - **VERIFIED**
- WebAdapter: Shared global session - **VERIFIED**
- Thread-local storage for redirect counting - **VERIFIED**

### Error Handling
- Fixed exponential backoff `2^attempt * 5 + jitter` (`web.py:184`) - **VERIFIED**
- Retry-After header NOT respected (`web.py:182` comment) - **VERIFIED**

## Discrepancies Found

### Minor Documentation Simplification

- **Claim**: "fallback to CSS selectors" for WebAdapter body extraction
- **Reality**: The fallback is actually **trafilatura** (full content extraction library), not CSS selectors. The code at `web.py:108-119` shows: if body is too short or missing, it tries trafilatura first, with CSS selectors being the initial attempt before trafilatura.
- **Severity**: Minor
- **Location**: `architecture/adapters.md:169`
- **Suggested fix**: Change "fallback to CSS selectors" to "fallback to trafilatura content extraction"

### Imprecise Wording in Request Delay Section

- **Claim**: "Both listing page fetches and individual article fetches go through `_polite_get()`"
- **Reality**: This is accurate. However, the document implies pagination links are followed via `_polite_get()` (which is true), but it doesn't clarify that each *article* URL (not just the listing) also goes through `_polite_get()` for body fetching.
- **Severity**: Minor
- **Location**: `architecture/adapters.md:188-190`
- **Suggested fix**: Clarify that article body fetching also uses `_polite_get()`, so the delay applies to: (1) listing pages, (2) pagination link pages, and (3) individual article pages.

## Bugs Identified

None. The adapter code is consistent with the documentation.

## Improvement Opportunities

### 1. Missing `request_delay_min`/`request_delay_max` in WebConfig Schema Documentation

The document describes `request_delay_min`/`request_delay_max` configuration but the schema (`schemas/source.py:95-96`) does not document these fields well - they have no descriptions.

**Location**: `schemas/source.py:95-96`
**Benefit**: Better developer experience when configuring web sources

### 2. `trafilatura` ImportError Handling Could Be More Visible

The `WebAdapter` silently passes on `ImportError` for trafilatura (`web.py:116-117`). If trafilatura is not installed, content extraction silently falls back to short CSS content without clear logging.

**Location**: `adapters/web.py:116-117`
**Benefit**: More visible warning when trafilatura is missing but body extraction relies on short content

### 3. `_scrape_feed_fallback` Lacks Retry Logic

The `_scrape_feed_fallback()` function (`rss.py:24-38`) makes no retry attempts and uses a simple `session.get()` without retry configuration. Meanwhile, the main RSS path uses `Retry` with `backoff_factor=1`.

**Location**: `adapters/rss.py:24-38`
**Benefit**: More robust fallback behavior for malformed feeds

## Stale Items Found

None. The document appears to have been recently updated and is in sync with the codebase.

## Recommendations

1. **Low Priority**: Update `architecture/adapters.md:169` to say "trafilatura" instead of "CSS selectors" for body fallback
2. **Low Priority**: Add field descriptions to `request_delay_min` and `request_delay_max` in `WebConfig` schema
3. **Low Priority**: Consider logging a warning when trafilatura is not installed in `WebAdapter.parse_item()`
4. **Low Priority**: Consider adding retry logic to `_scrape_feed_fallback()` for consistency

---

*Review completed on 2026-06-02*
*Code examined: `adapters/base.py`, `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py`, `schemas/source.py`*