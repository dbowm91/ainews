# Review: architecture/utils.md

**Review Date:** 2026-05-29
**Reviewer:** Architecture Review
**Document Status:** Accurate with Minor Discrepancies

---

## Verified Claims

### File Inventory
- [x] `url.py` - validate_url_safe, UnsafeURLError, normalize_url, normalize_title, TRACKING_PARAMS, clear_dns_cache
- [x] `text.py` - truncate, sanitize_html, extract_hashtags, esc_xml_text, esc_xml_attr, escape_prompt_data
- [x] `datetime.py` - parse_date, format_date, time_ago
- [x] `hash.py` - generate_hash, verify_hash
- [x] `html.py` - strip_tags, linkify, extract_text
- [x] `security.py` - generate_token, constant_time_compare
- [x] `utils/__init__.py` is empty (0 bytes)

### Function Signatures
- [x] `truncate(text: str, length: int, suffix: str = "...") -> str` at utils/text.py:53
- [x] `sanitize_html(html: str) -> str` at utils/text.py:146
- [x] `extract_hashtags(text: str) -> list[str]` at utils/text.py:169
- [x] `esc_xml_text(text: str) -> str` at utils/text.py:19
- [x] `esc_xml_attr(text: str) -> str` at utils/text.py:24
- [x] `escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]` at utils/text.py:36
- [x] `parse_date(date_str: str) -> datetime | None` at utils/datetime.py:10
- [x] `format_date(dt: datetime) -> str` at utils/datetime.py:52
- [x] `time_ago(dt: datetime) -> str` at utils/datetime.py:98 (alias for format_date)
- [x] `generate_token(length: int = 32) -> str` at utils/security.py:10
- [x] `constant_time_compare(a: str, b: str) -> bool` at utils/security.py:15
- [x] `strip_tags(html: str) -> str` at utils/html.py:37
- [x] `linkify(text: str) -> str` at utils/html.py:52
- [x] `extract_text(html: str) -> str` at utils/html.py:63
- [x] `generate_hash(data: str, algorithm: str = "sha256") -> str` at utils/hash.py:10
- [x] `verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool` at utils/hash.py:17

### TRACKING_PARAMS
- [x] Contains exactly 14 entries at utils/url.py:32-47:
  - utm_source, utm_medium, utm_campaign, utm_term, utm_content, utm_id, fbclid, gclid, ref, source, mc_cid, mc_eid, twclid, yclid

### UnsafeURLError
- [x] Inherits from `ValueError` at utils/url.py:126-127

### validate_url_safe() Behavior
- [x] Raises UnsafeURLError for empty URL at line 252
- [x] Raises UnsafeURLError for unsupported scheme at line 256
- [x] Raises UnsafeURLError for missing hostname at line 260
- [x] Raises UnsafeURLError for DNS failure at line 212
- [x] Raises UnsafeURLError for blocked IP at lines 230-238
- [x] Returns validated URL string at line 264

### Global Mutable State
- [x] `_dns_cache` global at line 184
- [x] `_dns_cache_lock` global at line 185
- [x] `_dns_executor` ThreadPoolExecutor at line 132
- [x] Module docstring explicitly notes non-pure behavior at lines 3-5

### __all__ exports
- [x] `__all__` at utils/url.py:21-28 correctly exports all functions

### services/url.py Duplication (Intentional)
- [x] Re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` unchanged from utils/url.py (line 15)
- [x] Duplicates `UnsafeURLError`, `_resolve_and_check`, `validate_url_safe`
- [x] Has `_get_dns_cache_config()` function at lines 60-63 for config support

### Empty __init__.py
- [x] `utils/__init__.py` is empty (0 bytes)

---

## Incorrect Claims

### 1. Config Support in services/url.py Not Actually Used (MEDIUM)
**Location:** architecture/utils.md:132

**Claim:**
> Only `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` are duplicated in `services/url.py` — these copies add config support by reading `DNS_CACHE_TTL` and `DNS_CACHE_MAX` via `get_config_with_default()`

**Issue:** The `_get_dns_cache_config()` function exists at services/url.py:60-63 but is **never called**. Both `utils/url.py` and `services/url.py` initialize `_TTLCache` with hardcoded values:
- `utils/url.py:195`: `_dns_cache = _TTLCache(maxsize=_DNS_CACHE_MAX, ttl=_DNS_CACHE_TTL)`
- `services/url.py:124`: `_dns_cache = _TTLCache(maxsize=maxsize, ttl=ttl)` where ttl/maxsize come from **hardcoded** `_DNS_CACHE_TTL`/`_DNS_CACHE_MAX` (lines 56-57), NOT from config

**Impact:** The duplication claim implies config support exists, but the config infrastructure is dead code. Either:
1. The config support was intended but never completed
2. The documentation is premature in noting this as a feature

**Priority:** MEDIUM - Documentation overstates the actual implementation

---

## Minor Discrepancies

### 1. truncate() Docstring Mismatch (INFO)
**Location:** architecture/utils.md:20-21

**Documentation Claim:**
> Truncate text to length, breaking on words

**Actual Implementation** (utils/text.py:53-67):
```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on word boundaries."""
    if length < 0:
        raise ValueError("length must be non-negative")
    if not text:
        return ""
    if len(text) <= length:
        return text
    if length <= len(suffix):
        return suffix[:length]
    truncated = text[: length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + suffix
```

**Analysis:** The implementation DOES break on word boundaries (lines 64-66). However, this is `utils/text.py:truncate()`, not `BaseSourceAdapter._truncate()` (adapters/base.py:104) which is:
```python
@staticmethod
def _truncate(text: Optional[str], limit: int = MAX_TEXT_LENGTH) -> Optional[str]:
    """Truncate text to limit, returning None for empty input."""
    return text[:limit] if text else None
```

**Note:** The architecture document correctly documents `utils/text.py:truncate()`, but doesn't mention `BaseSourceAdapter._truncate()` which has different behavior (no word-boundary breaking, different empty handling).

**Priority:** INFO - Not incorrect, but could cause confusion about which truncate is used where

---

## Improvement Opportunities

### 1. Clarify "utils/url.py Not Pure" Section (LOW)
**Location:** architecture/utils.md:127

The documentation correctly notes that `validate_url_safe()` has global mutable state, but could be clearer that this applies to the entire DNS resolution infrastructure, not just `validate_url_safe()`.

**Priority:** LOW

### 2. Note Two Different truncate Functions (LOW)
The architecture document correctly describes `utils/text.py:truncate()`, but developers working with adapters may encounter `BaseSourceAdapter._truncate()` which behaves differently.

**Priority:** LOW

---

## Stale Content

### None Identified

All file paths, function names, parameter counts, and return types verified against actual codebase. The TRACKING_PARAMS count (14) and list match exactly.

---

## Summary

The `utils.md` document is **largely accurate** with one notable discrepancy:
- 1 medium issue where documentation claims config support in `services/url.py` that is not actually implemented
- 1 minor info-level discrepancy about which truncate function has word-boundary breaking
- All core function signatures, file paths, and constants verified correct
- TRACKING_PARAMS count (14) and contents verified
- Global mutable state correctly documented
- Empty `__init__.py` confirmed
