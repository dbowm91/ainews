# Adapters Architecture Review - Detailed Improvement Plan

**Date:** 2026-05-07
**Type:** Architecture Review (Review Agent)
**Status:** Draft
**Reviewed Files:** architecture/adapters.md, adapters/*.py, services/url.py, schemas/source.py

---

## Executive Summary

Reviewed `architecture/adapters.md` against actual implementation. Found **8 verified claims**, **5 discrepancies**, and **5 bugs** including a critical missing import that would cause runtime failure.

**Critical Finding:** All adapters violate the architecture constraint against importing from `services/` by importing `validate_url_safe` from `services.url`. This was supposed to be resolved in Wave 2 but persists.

---

## Verification Matrix

### File Inventory
| File | Claimed | Actual | Status |
|------|---------|--------|--------|
| `base.py` | BaseSourceAdapter + registry | Present | VERIFIED |
| `rss.py` | RSSAdapter | Present | VERIFIED |
| `api.py` | APIAdapter | Present | VERIFIED |
| `web.py` | WebAdapter | Present | VERIFIED |
| `session.py` | SSRFSafeRedirectHandler | Present | VERIFIED |

### Core Claims from architecture/adapters.md

| Claim | Status | Evidence |
|-------|--------|----------|
| Adapters must NOT import from services | **VIOLATED** | All 4 adapters import `validate_url_safe` from `services.url` |
| `fetch()` abstract method | VERIFIED | base.py:50-51 |
| `parse_item()` abstract method | VERIFIED | base.py:53-54 |
| `fetch_and_parse()` combined method | VERIFIED | base.py:56-69 |
| `SOURCE_ADAPTERS` registry | PARTIAL | base.py exports `_ADAPTER_REGISTRY`; `SOURCE_ADAPTERS = _ADAPTER_REGISTRY` at line 20 |
| `@register_adapter` decorator | VERIFIED | base.py:23-28 |
| RSS: Uses feedparser | VERIFIED | rss.py:44 |
| RSS: BeautifulSoup fallback | DISCREPANCY | BS used for text extraction, NOT malformed feed fallback |
| RSS: Feed validation | DISCREPANCY | No validation code found |
| API: JSONPath field extraction | VERIFIED | api.py:136-152 `_resolve_path()` |
| API: Pagination support | VERIFIED | api.py:44-54 `item_url` pattern |
| API: Auth header injection | DISCREPANCY | Not explicitly implemented |
| Web: CSS selector extraction | VERIFIED | web.py uses BeautifulSoup |
| Web: Pagination following | VERIFIED | web.py:160-166 |
| SSRF: Blocks javascript:/data: | VERIFIED | services/url.py:183 only allows http/https |
| SSRF: Blocks internal IPs | VERIFIED | services/url.py:32-47 `_BLOCKED_NETWORKS` |

---

## Critical Bugs

### CR-1: Missing `random` Import in web.py (RUNTIME FAILURE)
**File:** `adapters/web.py:171, 178`
**Evidence:**
```python
# Line 171:
delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
# Line 178:
wait = 2**attempt * 5 + random.uniform(0, 2)
```
**Problem:** `random` is never imported but is used in two places.
**Impact:** Runtime `NameError: name 'random' is not defined` when `_polite_get()` is called.
**Fix:** Add `import random` at top of file (line 3 after `import secrets`).

### CR-2: Layering Violation - Adapters Import from Services
**Files:**
- `adapters/rss.py:12` - `from services.url import validate_url_safe`
- `adapters/api.py:11` - `from services.url import validate_url_safe`
- `adapters/web.py:14` - `from services.url import UnsafeURLError, validate_url_safe`
- `adapters/session.py:8` - `from services.url import UnsafeURLError, validate_url_safe`

**Architecture Claim:** "Adapters must NOT contain business logic and should NOT import from services."

**Problem:** Per plan.md Wave 2.1: "Create `utils/url.py` and move URL-related logic from `services/url.py`" and "Update all imports to ensure `adapters` do not import from `services`". This was marked complete but the violation persists.

**Evidence that utils/url.py exists but doesn't provide validation:**
```python
# utils/url.py:80-92
def is_valid_url(url: str) -> bool:
    """Check if URL is valid and uses http/https scheme.
    
    This is a pure wrapper that delegates to services.url.validate_url_safe
    for SSRF protection. Adapters should use this function for URL validation.
    """
    from services.url import validate_url_safe  # <-- Still imports from services!
```

**Fix Options:**
1. Move `validate_url_safe()` core logic to `utils/url.py` (keeping DNS resolution in services)
2. Have adapters import from `utils/url.py` using `is_valid_url()` wrapper
3. Accept that URL validation is infrastructure (SSRF protection) and document the exception

---

## High-Priority Issues

### H-1: Registry Name Export (Minor)
**File:** `adapters/base.py:18,20`
```python
_ADAPTER_REGISTRY: dict[str, type[BaseSourceAdapter]] = {}
SOURCE_ADAPTERS = _ADAPTER_REGISTRY  # This IS exported
```
**Status:** Actually this IS correct - `SOURCE_ADAPTERS` is exported at line 20. Previous review was in error.

### H-2: RSSAdapter Missing Malformed Feed Fallback
**File:** `adapters/rss.py`
**Documentation Claims:** "Falls back to requests + BeautifulSoup for malformed feeds"
**Actual:** No such fallback exists in `fetch()` method.
```python
# rss.py:33-45
def fetch(self) -> list[Any]:
    cfg = self.adapter_config
    validate_url_safe(cfg.feed_url)
    headers = {...}
    resp = self._session.get(cfg.feed_url, headers=headers, timeout=cfg.request_timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    return feed.entries[: cfg.max_items]
```
**Fix:** Either implement `_scrape_feed()` fallback or update documentation.

### H-3: RSSAdapter Missing Feed Validation
**Documentation Claims:** "Feed validation and normalization"
**Actual:** No validation code found.
**Fix:** Add validation or update documentation.

### H-4: APIAdapter Missing Explicit Auth Headers
**Documentation Claims:** "Auth header injection (Bearer token, API key)"
**Actual:** No auth header injection in `fetch()` method.
```python
# api.py:28-33
def fetch(self) -> list[Any]:
    cfg = self.adapter_config
    validate_url_safe(cfg.list_url)
    resp = self._session.get(cfg.list_url, timeout=cfg.request_timeout)
    # No auth headers set
```
**Fix:** Implement auth header support or update documentation.

---

## Medium-Priority Issues

### M-1: base.py `_classify_topics` Duplicates Purpose
**File:** `adapters/base.py:109-147`
**Issue:** The `_classify_topics()` function uses regex patterns for topic classification. This duplicates functionality that likely exists in `services/trend_detector.py`. Comment at line 112-113 states this was intentionally placed here to avoid layering violations.
```python
"""Classify topics from title/text using regex patterns.

This is a pure function with no external dependencies, defined here
to avoid layering violations (adapters should not import from services).
"""
```
**Analysis:** This is actually correct architecture - a pure function with no deps appropriately lives in the adapters layer. The comment explains the reasoning.

### M-2: Error Handling Inconsistency
**Documentation Claims:** "All adapters implement consistent error handling"
**Actual:**
- `rss.py`: Uses `raise_for_status()` - exceptions propagate
- `api.py`: Catches `RequestException` only in `_fetch_item()`
- `web.py`: Returns empty list on failure, catches multiple exception types

**Recommendation:** Standardize error handling patterns.

### M-3: Trafilatura Import in WebAdapter
**File:** `adapters/web.py:112`
```python
import trafilatura  # Inside function, not at module level
```
**Issue:** Local import is acceptable for optional dependencies, but inconsistent with other imports at module level.

---

## Bugs Found

| ID | Severity | File | Issue |
|----|----------|------|-------|
| CR-1 | CRITICAL | web.py:171,178 | `random.uniform` used without import |
| CR-2 | CRITICAL | All adapters | Import from `services.url` violates architecture |
| H-2 | HIGH | rss.py | No malformed feed fallback |
| H-3 | HIGH | rss.py | No feed validation |
| H-4 | HIGH | api.py | No auth header injection |
| M-2 | MEDIUM | All adapters | Inconsistent error handling |

---

## Specific Improvement Recommendations

### 1. Fix CR-1: Add `import random` to web.py
```python
# adapters/web.py line 2-3
import logging
import random  # ADD THIS
import secrets
import time
```

### 2. Fix CR-2: Resolve services import in adapters
**Option A (Recommended):** Move `validate_url_safe()` to `utils/url.py` keeping only the pure URL parsing/scheme check, and keep DNS resolution in `services/url.py`. Adapters would import from `utils/url.py`.

**Option B:** Document that SSRF protection is infrastructure concern and explicit exception to the layering rule.

### 3. Fix H-2: Implement RSS malformed feed fallback
Add to `adapters/rss.py`:
```python
def _scrape_feed(self, url: str) -> list[dict]:
    """Fallback for malformed feeds using requests + BeautifulSoup."""
    # Implementation
```

### 4. Fix H-4: Add auth header support to APIAdapter
```python
# In fetch(), before resp = self._session.get(...)
if cfg.auth_header:
    self._session.headers["Authorization"] = cfg.auth_header
```

---

## Action Items

| Priority | Item | Files Affected | Effort |
|----------|------|---------------|--------|
| P0 | Fix missing `import random` | adapters/web.py | 2 min |
| P0 | Resolve services import violation | adapters/*.py, utils/url.py | 45 min |
| P1 | Implement RSS malformed feed fallback | adapters/rss.py | 30 min |
| P1 | Add auth header support to APIAdapter | adapters/api.py | 20 min |
| P2 | Document/fix feed validation | adapters/rss.py | 15 min |
| P2 | Standardize error handling | adapters/*.py | 1 hour |
| P3 | Add type annotations where missing | adapters/*.py | 30 min |

---

## Files Reviewed

- `/home/sugarwookie/projects/ainews/architecture/adapters.md`
- `/home/sugarwookie/projects/ainews/adapters/base.py`
- `/home/sugarwookie/projects/ainews/adapters/rss.py`
- `/home/sugarwookie/projects/ainews/adapters/api.py`
- `/home/sugarwookie/projects/ainews/adapters/web.py`
- `/home/sugarwookie/projects/ainews/adapters/session.py`
- `/home/sugarwookie/projects/ainews/adapters/__init__.py`
- `/home/sugarwookie/projects/ainews/services/url.py`
- `/home/sugarwookie/projects/ainews/utils/url.py`
- `/home/sugarwookie/projects/ainews/schemas/source.py`
- `/home/sugarwookie/projects/ainews/schemas/item.py`
- `/home/sugarwookie/projects/ainews/plans/04_adapters.md` (previous review)

---

## Conclusion

The adapters layer has one critical runtime bug (missing `random` import) and one persistent architecture violation (importing from services). The previous review from 2026-05-06 identified many issues but they remain unfixed. The most impactful fix is adding `import random` to web.py, followed by resolving the services import issue.
