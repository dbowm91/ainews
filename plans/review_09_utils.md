# Architecture Review: Utils Module

**Document reviewed:** `architecture/utils.md`
**Review date:** 2026-05-08
**Status:** DISCREPANCIES FOUND

---

## Verified Items (Correct Documentation)

| File | Function | Status |
|------|----------|--------|
| `utils/text.py` | `truncate(text, length, suffix="...")` | VERIFIED - matches signature |
| `utils/text.py` | `sanitize_html(html)` | VERIFIED - matches signature |
| `utils/text.py` | `extract_hashtags(text)` | VERIFIED - matches signature |
| `utils/text.py` | `esc_xml_text(text)` | VERIFIED - matches signature |
| `utils/text.py` | `esc_xml_attr(text)` | VERIFIED - matches signature |
| `utils/text.py` | `escape_prompt_data(data)` | VERIFIED - matches signature |
| `utils/datetime.py` | `parse_date(date_str)` | VERIFIED - returns `datetime \| None` |
| `utils/datetime.py` | `time_ago(dt)` | VERIFIED - alias for `format_date` |
| `utils/hash.py` | `generate_hash(data, algorithm="sha256")` | VERIFIED - matches signature |
| `utils/hash.py` | `verify_hash(data, hash, algorithm="sha256")` | VERIFIED - matches signature |
| `utils/html.py` | `strip_tags(html)` | VERIFIED - matches signature |
| `utils/html.py` | `linkify(text)` | VERIFIED - matches signature |
| `utils/html.py` | `extract_text(html)` | VERIFIED - matches signature with trafilatura fallback |
| `utils/security.py` | `generate_token(length=32)` | VERIFIED - uses `secrets.token_urlsafe` |
| `utils/security.py` | `constant_time_compare(a, b)` | VERIFIED - uses `hmac.compare_digest` |
| `utils/url.py` | `UnsafeURLError` | VERIFIED - exists as `ValueError` subclass |
| `utils/url.py` | `validate_url_safe(url)` | VERIFIED - exists and performs SSRF checks |

---

## Discrepancies

### 1. `format_date` Signature Mismatch

**Document says:**
```python
def format_date(dt: datetime, format: str = "%Y-%m-%d") -> str:
    """Format datetime to string"""
```

**Actual implementation (`utils/datetime.py` line 52):**
```python
def format_date(dt: datetime) -> str:
    """Format datetime as human-readable relative or absolute date."""
```

**Issue:** The `format` parameter does not exist. The function returns relative time strings ("2 hours ago", "yesterday") for recent dates and "%b %d" or "%b %d, %Y" format for older dates. It is NOT a simple strftime wrapper.

---

### 2. `validate_url_safe` Return Type Mismatch

**Document says:**
```python
def validate_url_safe(url: str) -> bool:
    """Check if URL is safe for fetching (SSRF protection)"""
```

**Actual implementation (`utils/url.py` line 243):**
```python
def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP addresses..."""
    # ...raises UnsafeURLError if blocked...
    return url
```

**Issue:** Function returns `str` (the validated URL), not `bool`. It raises `UnsafeURLError` instead of returning `False`. This is a significant semantic difference.

---

### 3. Undocumented Exports in `utils/url.py`

**Documented:** `validate_url_safe`, `UnsafeURLError`

**Actual `__all__` (`utils/url.py` lines 17-28):**
```python
__all__ = [
    "normalize_url",
    "normalize_title",
    "TRACKING_PARAMS",
    "UnsafeURLError",
    "_BLOCKED_NETWORKS",
    "_is_ipv4_mapped",
    "validate_url_safe",
    "clear_dns_cache",
    "_get_dns_cache",
    "_TTLCache",
]
```

**Issue:** Multiple functions/classes are exported but not documented:
- `normalize_url(url: str) -> str` - URL normalization for deduplication
- `normalize_title(title: str) -> str` - Title normalization for fuzzy matching
- `TRACKING_PARAMS` - Set of tracking parameter names
- `clear_dns_cache()` - DNS cache clearing
- `_get_dns_cache()` - DNS cache getter (private)
- `_TTLCache` - DNS cache class (private)

---

### 4. `services/url.py` Duplicates `utils/url.py`

Per AGENTS.md: "services/url.py is now a thin wrapper that re-exports from utils/url.py"

**Actual situation:**
- `services/url.py` does NOT simply re-export from `utils/url.py`
- It has DUPLICATED implementations of `_TTLCache`, `_BLOCKED_NETWORKS`, `_is_ipv4_mapped`, `_resolve_and_check`, `validate_url_safe`
- It adds `get_config_with_default` integration for cache TTL/size
- It redefines `UnsafeURLError` class

**Issue:** Not a thin re-export wrapper as documented. Code duplication exists between `utils/url.py` and `services/url.py`.

---

### 5. `utils/__init__.py` is Empty

**Issue:** The `utils/__init__.py` file is empty (0 lines). While not necessarily a bug, this means `from utils import *` will not import any utilities. Each module must be imported individually.

---

## Issues Found

### Bug: No Major Bugs Identified

The implementations are functional and well-structured. No critical bugs found.

### Design Concern: Duplicate Code

`services/url.py` duplicates significant code from `utils/url.py` instead of importing and extending. This violates DRY and could lead to divergence over time.

### Type Safety: Missing TYPE_CHECKING Pattern

Some modules could benefit from the `TYPE_CHECKING` pattern for type hints without runtime imports, but this is not critical for utils modules.

---

## Recommendations

### 1. Fix `format_date` Documentation

Update the architecture document to reflect the actual behavior:

```markdown
def format_date(dt: datetime) -> str:
    """Format datetime as human-readable relative or absolute date.
    
    Returns "just now", "X minutes ago", "X hours ago", "yesterday", 
    "X days ago", "%b %d" (same year), or "%b %d, %Y" (different year).
    """
```

### 2. Fix `validate_url_safe` Documentation

Update to reflect actual return type:

```markdown
def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP addresses.
    
    Performs DNS resolution to check for SSRF attempts via DNS rebinding.
    Returns the validated URL string.
    Raises UnsafeURLError if URL is invalid or unsafe.
    """
```

### 3. Document All Public APIs

Either update `architecture/utils.md` to include all public exports, OR restrict `utils/url.py.__all__` to only documented items. Recommend documenting the full API.

Add to `architecture/utils.md`:

```markdown
### Additional URL Utilities

| Function | Purpose |
|----------|---------|
| `normalize_url(url)` | Normalize URL for deduplication |
| `normalize_title(title)` | Normalize title for fuzzy matching |
| `TRACKING_PARAMS` | Set of tracking parameter names to strip |
| `clear_dns_cache()` | Clear the DNS resolution cache |
```

### 4. Consolidate URL Validation

Consider having `services/url.py` truly re-export from `utils/url.py` instead of duplicating code:

```python
# services/url.py should be:
from utils.url import (
    UnsafeURLError,
    clear_dns_cache,
    normalize_title,
    normalize_url,
    TRACKING_PARAMS,
    validate_url_safe,
)
# Add config-based cache initialization if truly needed
```

### 5. Consider Adding `utils/__init__.py` Exports

If consistent package-level imports are desired:
```python
from utils.text import esc_xml_text, truncate, sanitize_html, extract_hashtags
# etc.
```

---

## Summary

| Category | Count |
|----------|-------|
| Verified correct | 16 |
| Discrepancies | 5 |
| Bugs | 0 |
| Recommendations | 4 |

**Overall Assessment:** The utils module implementations are solid and functional. Most discrepancies are documentation issues rather than code bugs. The main concerns are: (1) `format_date` documentation is misleading about its behavior, (2) `validate_url_safe` return type mismatch, (3) undocumented exports in `utils/url.py`, and (4) code duplication between `utils/url.py` and `services/url.py`.
