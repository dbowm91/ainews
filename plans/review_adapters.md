# Review: architecture/adapters.md

**Review Date:** 2026-05-29
**Reviewer:** Architecture Review
**Document Status:** Mostly Accurate

---

## Verified Claims

### Base Adapter (`adapters/base.py`)
- [x] `BaseSourceAdapter` abstract methods (`fetch`, `parse_item`) at lines 50-54
- [x] `@register_adapter` decorator at lines 23-28
- [x] `SOURCE_ADAPTERS` registry at lines 18-20
- [x] `get_adapter_class()` at lines 31-35
- [x] `_classify_topics()` helper at lines 109-147
- [x] Context manager support (`__enter__`, `__exit__`) at lines 71-75
- [x] `close()` as no-op base implementation at line 77-79

### RSS Adapter (`adapters/rss.py`)
- [x] `@register_adapter('rss')` decorator at line 41
- [x] Creates own `requests.Session` at line 47
- [x] Own `SSRFSafeRedirectHandler` instance at line 52
- [x] `fetch()` uses `feedparser.parse()` with BeautifulSoup fallback at lines 57-71
- [x] `parse_item()` implementation at lines 73-118
- [x] `close()` properly closes own session at lines 54-55

### API Adapter (`adapters/api.py`)
- [x] Creates session via `get_crawl_session()` at line 22
- [x] `close()` is no-op (empty `pass`) at lines 25-26
- [x] Bearer token auth at lines 175-179
- [x] Filter operations: `equals`, `min`, `exists`, `contains` at lines 205-221
- [x] `PaginationConfig` with `next_link`, `query_param`, `none` types at schemas/source.py:59-70

### Web Adapter (`adapters/web.py`)
- [x] Creates session via `get_crawl_session()` at line 35
- [x] `close()` is no-op (empty `pass`) at lines 48-49
- [x] CSS selector extraction via `ListingConfig` and `ArticleSelectors`
- [x] `urljoin()` used at line 160 (card links) and line 166 (pagination)
- [x] `request_delay_min`/`request_delay_max` applied per-article at line 174

### SSRF Protection (`adapters/session.py`)
- [x] `SSRFSafeRedirectHandler.__call__` signature: `(self, request, response, **kwargs)` at line 37
- [x] Thread-local redirect counting at lines 29-35
- [x] Returns `PreparedRequest` with updated URL at lines 54-56

### Session Ownership
- [x] RSSAdapter: own session + own handler (lines rss.py:47, 52)
- [x] APIAdapter/WebAdapter: shared global session (lines api.py:22, web.py:35)
- [x] API/Web `close()` as no-ops prevent closing global session

### Error Handling
- [x] Fixed exponential backoff (not Retry-After) at web.py:183 - "Note: Retry-After header is not currently respected"
- [x] Network errors return empty list
- [x] Parse errors logged and skipped

---

## Incorrect Claims

### 1. Pagination Config Shared Between API and Web (MEDIUM)
**Location:** architecture/adapters.md:133

**Claim:**
> API adapter pagination is implemented via `PaginationConfig` (same as Web adapter)

**Issue:** The documentation implies the pagination implementation is "the same as Web adapter" which could be misinterpreted as identical implementation. While both use `PaginationConfig` schema, the actual pagination logic differs:
- `APIAdapter`: Lines 36-61 (fetches all pages in `fetch()`)
- `WebAdapter`: Lines 162-167 (recursive `next_link_selector` following in `_scrape_listing`)

**Priority:** MEDIUM - Could mislead developers about behavior differences

---

## Bugs Found

### 1. Filter "contains" Operation with None Values (LOW)
**Location:** `adapters/api.py:220`

```python
if "contains" in f and f["contains"] not in str(current):
    return False
```

**Issue:** When `current` is `None`, `str(None)` returns `"None"`, which could cause unexpected matches if someone filters for the string "None".

**Severity:** LOW - Unlikely to cause issues in practice; requires explicit filter for string "None"

**Priority:** LOW

---

## Improvement Opportunities

### 1. Documentation: query_param Pagination Independence (LOW)
**Location:** architecture/adapters.md:133

**Note:** The documentation does NOT claim query_param requires next_link_selector, but the implementation at `api.py:60-61` could be clarified. The `_get_next_url()` method at line 83-86 only returns a URL for `next_link` type, not `query_param`. This is correct behavior but could confuse readers.

**Priority:** LOW - Not incorrect, could add clarity

### 2. Document Per-Article Delay Behavior (INFO)
**Location:** architecture/adapters.md:176-178

The documentation accurately notes that delays apply per-article, not per-page. This is correct behavior but worth highlighting for operators.

**Priority:** INFO

---

## Stale Content

### None Identified

All file paths, line numbers, class names, function names, and enum values verified against actual codebase.

---

## Summary

The `adapters.md` document is **highly accurate** with minor opportunities for clarification:
- 1 medium clarification opportunity about pagination implementation differences
- 1 low-severity potential bug in filter handling (unlikely to cause issues)
- No incorrect claims about actual implementation
- All line references and code examples verified
