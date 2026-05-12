# Adapters Review Plan

Review the `adapters/` package and [adapters.md](../architecture/adapters.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual adapter implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Layer Violations**: Adapters must NOT import from services

## Key Files

- `adapters/base.py` - BaseSourceAdapter, @register_adapter decorator, SOURCE_ADAPTERS registry
- `adapters/rss.py` - RSSAdapter with feedparser
- `adapters/api.py` - APIAdapter with JSONPath field extraction
- `adapters/web.py` - WebAdapter with CSS selectors
- `adapters/session.py` - SSRFSafeRedirectHandler

## Known Issues to Verify

- SSRFSafeRedirectHandler bug (fixed) - redirect counter not reset after successful validation
- trafilatura ImportError handling split between ImportError and ValueError/AttributeError
- URL validation duplication between utils/url.py and services/url.py

## Review Checklist

- [ ] Verify adapter pattern: BaseSourceAdapter with fetch() and parse_item() abstract methods
- [ ] Verify @register_adapter decorator adds to SOURCE_ADAPTERS registry
- [ ] Verify RSSAdapter: feedparser + BeautifulSoup fallback, feed validation
- [ ] Verify APIAdapter: JSONPath extraction, pagination (cursor/offset/page), auth headers
- [ ] Verify WebAdapter: CSS selectors, pagination link following
- [ ] Verify SSRFSafeRedirectHandler: blocks internal IPs, javascript:, data: schemes
- [ ] Verify error handling: network errors return empty list, parse errors skipped
- [ ] Verify source health tracking: consecutive_failures/successes updated

## Output

Save findings to `plans/adapters_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found