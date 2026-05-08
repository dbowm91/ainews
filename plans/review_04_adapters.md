# Review 04: Adapters Module Architecture Compliance

**Date:** 2026-05-08  
**Reviewer:** Architecture Review  
**Files Reviewed:** `adapters/base.py`, `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py`, `adapters/__init__.py`, `utils/url.py`

---

## Status Summary

| Category | Items | Notes |
|----------|-------|-------|
| Verified | 14 | Features correctly implemented |
| Discrepancies | 3 | Documentation vs implementation differences |
| Bugs | 2 | Critical runtime issues |
| Documentation Issues | 2 | Outdated items in review_plan.md |

---

## Verified Items (Correct Implementations)

### V-1: Base Adapter Pattern ✅
- `BaseSourceAdapter` with abstract `fetch()` and `parse_item()` methods
- `@register_adapter` decorator correctly populates `_ADAPTER_REGISTRY`
- `SOURCE_ADAPTERS = _ADAPTER_REGISTRY` alias present (H-1 fix)
- `get_adapter_class()` function works correctly

### V-2: RSS Adapter - Malformed Feed Fallback ✅
Lines 69-70 in `rss.py`:
```python
if not _validate_feed(feed):
    return _scrape_feed_fallback(cfg.feed_url, self._session, cfg.request_timeout)
```
BeautifulSoup fallback IS implemented in `_scrape_feed_fallback()` function (lines 24-38).

### V-3: API Adapter - Auth Header Injection ✅
Lines 129-134 in `api.py`:
```python
headers = {}
if cfg.api_key:
    if cfg.auth_header:
        headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
    else:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
```
Auth header injection IS implemented. Bearer token and custom auth_header both supported.

### V-4: Web Adapter - Multiple Start URLs ✅
The adapter correctly handles multiple URLs via `_scrape_listing()` which iterates through listing pages.

### V-5: Web Adapter - CSS Selector Extraction ✅
Line 147: `card_sel = cfg.listing.card_selector` and line 155: `href = link_el.get(link_attr)` - CSS-based extraction correctly implemented.

### V-6: Web Adapter - Pagination ✅
Lines 160-164: Pagination logic with `next_link_selector` and `max_pages` correctly implemented.

### V-7: Web Adapter - Trafilatura Fallback ✅
Lines 111-119: Content extraction with trafilatura fallback when body < MIN_CONTENT_LENGTH works correctly.

### V-8: SSRF Protection - IP Range Blocking ✅
`utils/url.py` lines 100-114: `_BLOCKED_NETWORKS` correctly blocks:
- 10.x.x.x (10.0.0.0/8)
- 172.16-31.x.x (172.16.0.0/12)  
- 192.168.x.x (192.168.0.0/16)
- Plus many other private/reserved ranges

### V-9: SSRF Protection - DNS Rebinding Prevention ✅
`_resolve_and_check()` in `utils/url.py` performs DNS resolution and validates IPs against blocked networks.

### V-10: Session Management - Retry Logic ✅
Both `rss.py` (lines 48-51) and `session.py` (lines 52-56) correctly configure retry with backoff for 5xx errors.

### V-11: Error Handling - Network Errors ✅
All adapters log and return empty list on network errors.

### V-12: Error Handling - Parse Errors ✅
`fetch_and_parse()` in base.py (lines 56-69) catches `ValueError, KeyError, AttributeError` and logs warnings.

### V-13: File Structure Matches Documentation ✅
All documented files exist: `base.py`, `rss.py`, `api.py`, `web.py`, `session.py`.

### V-14: __init__.py Exports ✅
`__all__ = ["APIAdapter", "RSSAdapter", "WebAdapter", "get_adapter_class", "SOURCE_ADAPTERS"]` correctly exports all public adapters.

---

## Discrepancies

### D-1: SSRFSafeRedirectHandler - Not urllib.request.HTTPRedirectHandler

**Document says:** `class SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler)`

**Actual code:** `class SSRFSafeRedirectHandler:` - does NOT inherit from HTTPRedirectHandler

**Impact:** Low - The class works correctly as a callable redirect handler for requests library, but documentation is inaccurate.

**Code location:** `adapters/session.py` line 14

---

### D-2: javascript:/data: URL Blocking Not in Redirect Handler

**Document says:** "Blocked patterns: javascript:, data: URLs"

**Actual code:** The `SSRFSafeRedirectHandler` only validates via `validate_url_safe()` which checks IP ranges. It does NOT explicitly block `javascript:` or `data:` schemes.

**Impact:** Medium - If a redirect Location header contains `javascript:alert('xss')`, the current code would pass it to `validate_url_safe()` which only checks URL scheme against http/https (line 253 of utils/url.py). This could be a security gap.

**Code location:** `adapters/session.py` lines 26-42

---

### D-3: API Adapter - Document Claims JSONPath but Implementation is Simplified

**Document says:** Uses `JSONPath field extraction ($.items[*], $.data[*].title)`

**Actual code:** `_resolve_path()` in `api.py` (lines 143-158) implements a simple dot-notation resolver, NOT full JSONPath. It only supports:
- Simple property access: `$.title`
- Array index access: `$.items[0]`

It does NOT support JSONPath features like:
- Recursive descent: `$.items[*]`
- Array slicing
- Filters: `$.items[?@.price > 100]`

**Impact:** Low - The current implementation works for simple cases but documentation overstates capabilities.

**Code location:** `adapters/api.py` lines 143-158

---

## Bugs Found

### B-1: CRITICAL - `random` Module Used Without Import in web.py

**Location:** `adapters/web.py` lines 171 and 178

```python
delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)  # Line 171
wait = 2**attempt * 5 + random.uniform(0, 2)  # Line 178
```

**Problem:** `random` is imported via `secrets` at line 2, but `secrets` does NOT expose `random.uniform()`. The correct import would be `import random` or `from random import uniform`.

**Evidence:** Only imports at top of file:
```python
import logging
import secrets
import time
```

No `import random` statement exists.

**Impact:** Runtime `NameError` when `_polite_get()` is called - `name 'random' is not defined`

---

### B-2: HIGH - RSS Adapter May Use Wrong Config Attribute

**Location:** `adapters/rss.py` lines 57-71

```python
def fetch(self) -> list[Any]:
    cfg = self.adapter_config
    validate_url_safe(cfg.feed_url)  # Line 59
    headers = {
        "User-Agent": cfg.user_agent,  # Line 61
        "Accept": "application/rss+xml, ...",
    }
    resp = self._session.get(
        cfg.feed_url, headers=headers, timeout=cfg.request_timeout  # Line 66
    )
```

**Problem:** `RSSAdapter.config_class = RSSConfig` (line 43), but need to verify `RSSConfig` has `feed_url`, `user_agent`, and `request_timeout` attributes.

**Recommendation:** Check `schemas/source.py` to confirm RSSConfig has these fields. If missing, this is a config mismatch bug.

---

## Documentation Issues

### DOC-1: review_plan.md Items Are Outdated

**Context:** Items M-2, M-3, M-4 in review_plan.md (lines 99-109) state:

> **M-2: APIAdapter Explicit Auth Headers** - Action: Deferred  
> **M-3: Add Feed Validation in RSSAdapter** - Action: Deferred  
> **M-4: Implement RSS Malformed Feed Fallback** - Action: Deferred  

**Finding:** All three features are actually implemented:
- M-2: Auth headers implemented (verified in V-3 above)
- M-3: `_validate_feed()` exists at lines 17-21 of rss.py
- M-4: `_scrape_feed_fallback()` exists at lines 24-38 of rss.py

**Action needed:** Update review_plan.md to mark M-2, M-3, M-4 as completed, not deferred.

---

## Recommendations

### R-1: Fix B-1 Immediately - Add `import random`

In `adapters/web.py`, add after line 1:
```python
import random
```

### R-2: Fix D-2 - Add javascript:/data: scheme blocking

In `adapters/session.py`, add explicit scheme check in `redirect_request`:
```python
# After line 28, after getting location
parsed_redirect = urlparse(location)
if parsed_redirect.scheme.lower() in ('javascript', 'data', 'vbscript'):
    raise requests.exceptions.InvalidURL(f"Blocked dangerous redirect scheme: {parsed_redirect.scheme}")
```

### R-3: Fix D-1 - Update documentation

Update `architecture/adapters.md` line 122:
```diff
- class SSRFSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
+ class SSRFSafeRedirectHandler:
```

Or document that it's a custom implementation not tied to urllib's class hierarchy.

### R-4: Verify RSSConfig attributes

Verify `schemas/source.py` has `feed_url`, `user_agent`, and `request_timeout` in RSSConfig. If not, this is a blocking bug.

### R-5: Update review_plan.md

Mark M-2, M-3, M-4 as completed.

---

## Summary

| Severity | Count | Items |
|----------|-------|-------|
| Critical | 1 | B-1 (random module not imported) |
| High | 1 | B-2 (RSSConfig attribute verification needed) |
| Medium | 1 | D-2 (javascript:/data: not blocked in redirects) |
| Low | 2 | D-1, D-3 (documentation accuracy) |
| Documentation | 1 | review_plan.md outdated |

**Priority:** Fix B-1 immediately as it causes runtime failure. Verify RSSConfig (B-2) before next deploy. Address D-2 for security hardening.
