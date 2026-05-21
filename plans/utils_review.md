# Utils Module Architecture Review

This document reviews the claims in `architecture/utils.md` against the actual implementation in `utils/` and `services/url.py`.

---

## 1. Verified Correct

### Text Utilities (`utils/text.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `esc_xml_text` | Verified | Correctly escapes &, <, > |
| `esc_xml_attr` | Verified | Correctly escapes &, ', ", <, > |
| `escape_prompt_data` | Verified | Recursively escapes dict/list/string values |
| `truncate` | Verified | Word-boundary breaking, handles edge cases |
| `sanitize_html` | Verified | Uses HTMLParser to strip dangerous tags/attrs |
| `extract_hashtags` | Verified | Regex pattern #[a-zA-Z][a-zA-Z0-9_]* works correctly |

### Security Utilities (`utils/security.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `generate_token` | Verified | Uses secrets.token_urlsafe() for cryptographic security |
| `constant_time_compare` | Verified | Uses hmac.compare_digest() for timing-attack prevention |

### Hash Utilities (`utils/hash.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `generate_hash` | Verified | Correctly uses hashlib with utf-8 encoding |
| `verify_hash` | Verified | Uses hmac.compare_digest() for safe comparison |

### DateTime Utilities (`utils/datetime.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `parse_date` | Verified | Supports RFC 2822, ISO 8601, and 12 common formats via email.utils fallback |
| `format_date` | Verified | Returns correct relative/absolute strings ("just now", "X minutes ago", etc.) |
| `time_ago` | Verified | Correctly aliases format_date() |

### HTML Utilities (`utils/html.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `strip_tags` | Verified | Uses HTMLParser with fallback to regex |
| `linkify` | Verified | Regex-based URL to anchor conversion |
| `extract_text` | Verified | Has trafilatura import with logger warning fallback |

### URL Utilities (`utils/url.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `normalize_url` | Verified | Correctly strips tracking params, lowercases, removes www |
| `normalize_title` | Verified | Correctly normalizes for fuzzy matching |
| `TRACKING_PARAMS` | Verified | 14 tracking params defined (utm_*, fbclid, gclid, etc.) |

---

## 2. Discrepancies Found

### CRITICAL: validate_url_safe is NOT in utils/url.py

**Documentation claims:**
> url.py: validate_url_safe, UnsafeURLError - URL validation with SSRF protection

**Actual implementation:**
- utils/url.py only contains normalize_url, normalize_title, TRACKING_PARAMS, and the UnsafeURLError **exception class only** (lines 124-125)
- The **actual SSRF validation with DNS resolution** is in services/url.py (lines 178-192)
- services/url.py imports and re-exports from utils/url.py (line 15)

**Implication:** The architecture docs imply adapters can import SSRF validation from utils/url.py, but:
- adapters/session.py, adapters/web.py correctly import from utils/url.py only UnsafeURLError and do NOT use validate_url_safe
- adapters/api.py, adapters/rss.py import validate_url_safe from utils/url.py but utils/url.py does NOT export it!
- All actual usage of validate_url_safe comes from services.url

**This is a BUG:** adapters/api.py and adapters/rss.py import validate_url_safe from utils.url, but utils.url does not export this function. This would cause ImportError at runtime.

### Documentation vs Code: Pure Functions Claim

**Documentation claims (line 131):**
> Pure functions: No side effects, no global state

**Actual utils/url.py has global mutable state:**
- Line 130: _dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")
- Lines 182-183: _dns_cache: _TTLCache | None = None and _dns_cache_lock = threading.Lock()
- Lines 186-194: _get_dns_cache() lazily initializes global cache
- Line 197-198: clear_dns_cache() calls _get_dns_cache().clear()

**The module docstring acknowledges this (lines 3-5):**
> Note: Most functions are pure, but validate_url_safe() and related DNS functions have side effects - they perform DNS resolution with caching using global state (_dns_cache, _dns_executor).

However, validate_url_safe is NOT even in utils/url.py - it is in services/url.py. The global state in utils/url.py is only for the clear_dns_cache() function.

### Documentation vs Code: URL Validation Layering

**Documentation states (lines 102-127):**
```python
def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP addresses.
    Performs DNS resolution to check for SSRF attempts via DNS rebinding.
    ...
```

**Actual:** This exact function with DNS resolution logic is in services/url.py, NOT utils/url.py. The utils/url.py has:
- UnsafeURLError exception class only
- normalize_url, normalize_title, TRACKING_PARAMS
- clear_dns_cache() (which delegates to services via _get_dns_cache())

---

## 3. Bugs Identified

### BUG-1: Import Error in Adapters

**Files affected:** adapters/api.py, adapters/rss.py

```python
# adapters/api.py line 11:
from utils.url import validate_url_safe

# adapters/rss.py line 12:
from utils.url import validate_url_safe
```

But utils/url.py __all__ (lines 21-28) is:
```python
__all__ = [
    "normalize_url",
    "normalize_title",
    "TRACKING_PARAMS",
    "UnsafeURLError",
    "validate_url_safe",  # <-- exported but not defined!
    "clear_dns_cache",
]
```

The function validate_url_safe is listed in __all__ but NOT defined in utils/url.py. It exists only in services/url.py. This would cause:
```
ImportError: cannot import name 'validate_url_safe' from 'utils.url'
```

**Note:** adapters/web.py and adapters/session.py correctly only import UnsafeURLError and validate_url_safe is not used in these adapters.

### BUG-2: utils/url.py exports validate_url_safe but does not define it

The __all__ in utils/url.py lists validate_url_safe but it is never defined in that file. This is misleading and would cause import errors if anyone actually tried to use the documented API.

### BUG-3: clear_dns_cache in utils/url.py is misleading

utils/url.py exports clear_dns_cache() (line 27) which calls _get_dns_cache().clear(). But _get_dns_cache() in utils/url.py (lines 186-194) creates a local _TTLCache with hardcoded values (TTL=5, MAX=1024), NOT the configured values from services/url.py.

When called:
1. utils.url.clear_dns_cache() calls _utils.url._get_dns_cache()
2. This creates a NEW cache in utils/url.py module scope
3. The actual DNS cache used by services/url.py is separate

This means utils.url.clear_dns_cache() clears a different cache than the one actually used for SSRF validation.

---

## 4. Improvement Suggestions

### IMP-1: Remove false exports from utils/url.py

utils/url.py should not advertise validate_url_safe in __all__ since it does not define it. Either:
- Remove it from __all__, OR
- Actually define it in utils/url.py (which would require moving the SSRF logic)

### IMP-2: Add tests for utility functions

Missing test coverage for:
- utils/text.py: truncate, sanitize_html, extract_hashtags
- utils/datetime.py: parse_date, format_date, time_ago
- utils/html.py: strip_tags, linkify, extract_text
- utils/hash.py: generate_hash, verify_hash
- utils/security.py: generate_token, constant_time_compare

### IMP-3: Document global state accurately

If utils/url.py is documented as having "pure functions", the global state for DNS caching should either:
- Be removed (have services/url.py handle all caching)
- Or documentation should be updated to acknowledge the caching layer

### IMP-4: Consider consolidating URL utilities

There are two URL utility modules:
- utils/url.py - normalization only
- services/url.py - validation with SSRF protection

The relationship is unclear. Consider:
- Moving normalization to services/url.py and removing utils/url.py
- Or having services/url.py only add the SSRF validation layer on top of utils/url.py

---

## 5. Questions for Architecture

### Q-1: Why is validate_url_safe in services/url.py not utils/url.py?

The architecture doc describes utils/url.py as having SSRF protection functions, but the actual implementation is in services/url.py. This creates confusion about:
- Which module adapters should import from
- Why utils/url.py exports validate_url_safe in __all__ but does not define it

### Q-2: What is the intended relationship between utils/url.py and services/url.py?

Currently:
- services/url.py imports from utils/url.py: TRACKING_PARAMS, normalize_title, normalize_url
- utils/url.py appears to export but not define validate_url_safe
- Both have their own _TTLCache implementation
- Both have their own _dns_executor

This duplication suggests unclear layering or copy-paste residue.

### Q-3: Are the undocumented functions (truncate, sanitize_html, etc.) intentionally unused?

Several functions are documented but never imported anywhere:
- truncate, sanitize_html, extract_hashtags in utils/text.py
- strip_tags, linkify, extract_text in utils/html.py
- generate_hash, verify_hash in utils/hash.py
- generate_token, constant_time_compare in utils/security.py
- parse_date, format_date, time_ago in utils/datetime.py

Are these:
1. Reserved for future use?
2. Legacy functions no longer used?
3. Intended for external consumption only?

### Q-4: Should utils/url.clear_dns_cache() synchronize with services/url.clear_dns_cache()?

Currently they clear different cache instances. If clear_dns_cache() is meant to be a admin/debugging function, it should probably clear all caches.

---

## Summary

| Category | Count |
|----------|-------|
| Verified correct implementations | 15 |
| Discrepancies (docs vs code) | 3 |
| Bugs identified | 3 |
| Improvement suggestions | 4 |
| Questions for architecture | 4 |

**Most Critical Issue:** The documentation implies utils/url.py contains validate_url_safe for SSRF protection, but the actual implementation is in services/url.py. Meanwhile, adapters/api.py and adapters/rss.py incorrectly try to import validate_url_safe from utils/url.py where it does not exist. This is a latent import error.
