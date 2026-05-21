# Utils Module Architecture Review

## Summary

This review verifies the claims in `architecture/utils.md` against the actual codebase. The utils module is well-structured with minimal dependencies and proper layering. However, several discrepancies and issues were found.

## Verified Claims

| Claim | Status | Notes |
|-------|--------|-------|
| File inventory complete | ✅ VERIFIED | All 7 files exist: `url.py`, `text.py`, `datetime.py`, `hash.py`, `html.py`, `security.py`, `__init__.py` |
| Pure functions with minimal deps | ✅ VERIFIED | Only standard library imports |
| Type hints present | ✅ VERIFIED | Full typing on all functions |
| URL validation with SSRF protection | ✅ VERIFIED | `validate_url_safe()` with DNS resolution and private IP blocking |
| Text utilities (truncate, sanitize_html, extract_hashtags, esc_xml_text, esc_xml_attr, escape_prompt_data) | ✅ VERIFIED | All functions present |
| DateTime utilities (parse_date, format_date, time_ago) | ✅ VERIFIED | All functions present |
| Security utilities (generate_token, constant_time_compare) | ✅ VERIFIED | Both functions present using `secrets` and `hmac` |
| HTML utilities (strip_tags, linkify, extract_text) | ✅ VERIFIED | All functions present |
| Hash utilities (generate_hash, verify_hash) | ✅ VERIFIED | Both functions present with hmac.compare_digest |
| No layering violations | ✅ VERIFIED | No imports from `services` or `adapters` in utils modules |
| TRACKING_PARAMS documented | ✅ VERIFIED | Set of 12 tracking parameters |
| clear_dns_cache documented | ✅ VERIFIED | Function present |
| UnsafeURLError documented | ✅ VERIFIED | Exception class present |

## Discrepancies and Issues

### 1. `sanitize_html()` Does Not Remove Dangerous Attributes (MED)

**Location:** `utils/text.py:96-108`

**Issue:** The document claims `sanitize_html()` "Remove dangerous HTML tags and attributes" but the implementation only removes tags via `_TagStripper`. The `_DANGEROUS_ATTRS` set (line 74-78) is defined but **never used** in the function.

```python
_DANGEROUS_TAGS = {...}  # Used by _TagStripper
_DANGEROUS_ATTRS = {...}  # DEFINED BUT NEVER USED
```

**Impact:** XSS vectors like `<img src=x onerror=alert(1)>` pass through unchanged since only the `<img>` tag might be stripped but the `onerror` attribute is not filtered.

**Recommendation:** Implement attribute stripping in `sanitize_html()` or remove `_DANGEROUS_ATTRS` if intentionally not used.

---

### 2. `sanitize_html()` Has No Unit Tests (MED)

**Status:** No tests found for any `utils/text.py` functions.

**Recommendation:** Add unit tests for `sanitize_html()`, `truncate()`, `extract_hashtags()`, and the XML escaping functions.

---

### 3. URL Validation Duplication Between `utils/url.py` and `services/url.py` (LOW - Architecture)

**Issue:** The AGENTS.md documents this as a known duplication:
> "URL Validation Duplication: `utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` does NOT re-export from `utils/url.py` - it redefines everything locally with its own config support."

The duplication is **intentional** per architecture decision because `services/url.py` needs config support (`get_config_with_default`) while `utils/url.py` must remain pure. However, the duplication is not clearly documented in `architecture/utils.md`.

**Recommendation:** Add a note in `architecture/utils.md` explaining that `services/url.py` contains a config-aware version of URL validation, and adapters should import from `utils/url.py` per clean layering.

---

### 4. `linkify()` Missing from Documented Functions (LOW)

**Location:** `utils/html.py:52-60`

**Issue:** The File Inventory table in `architecture/utils.md` lists functions for `html.py` but shows only `strip_tags`, `linkify`, `extract_text`. However, the text utilities section only shows `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` - it doesn't list `linkify` separately. This is actually **correct** since `linkify` is in `html.py` not `text.py`.

**Actually Verified:** The document is correct. `linkify` is in `html.py`.

---

### 5. No Tests for `utils/hash.py` (LOW)

**Status:** No unit tests found for `generate_hash` or `verify_hash`.

**Recommendation:** Add unit tests to verify hash generation and verification work correctly.

---

### 6. No Tests for `utils/security.py` (LOW)

**Status:** No unit tests found for `generate_token` or `constant_time_compare`.

**Recommendation:** Add unit tests.

---

## Specific Bugs

### BUG-1: `sanitize_html()` Never Uses `_DANGEROUS_ATTRS` (MED)

```python
# utils/text.py:74-78 - Defined but never used
_DANGEROUS_ATTRS = {
    "onerror", "onload", "onclick", "onmouseover", "onfocus", "onblur",
    "onchange", "onsubmit", "onkeydown", "onkeyup", "onkeypress",
    "javascript:", "vbscript:", "data:", "href", "src",
}
```

The `sanitize_html()` function only strips dangerous tags via `_TagStripper`, but never processes attributes. The `_DANGEROUS_ATTRS` set is dead code.

**Fix options:**
1. Implement proper attribute sanitization using the `_DANGEROUS_ATTRS` set
2. Remove `_DANGEROUS_ATTRS` if not part of the design
3. Document that attribute filtering is out of scope

---

## Improvement Recommendations

| Priority | Issue | Recommendation |
|----------|-------|----------------|
| MED | `sanitize_html()` doesn't filter dangerous attributes | Either implement attribute filtering using `_DANGEROUS_ATTRS` or remove the unused set |
| MED | No unit tests for `utils/text.py` functions | Add tests for all text utilities |
| LOW | URL validation duplication not documented | Add note in architecture docs explaining `services/url.py` vs `utils/url.py` |
| LOW | No tests for `utils/hash.py` | Add unit tests |
| LOW | No tests for `utils/security.py` | Add unit tests |

## Conclusion

The utils module is well-implemented with proper layering and minimal dependencies. The main issue is `sanitize_html()` claiming to remove dangerous attributes when it only removes tags. The `_DANGEROUS_ATTRS` set is dead code that should either be implemented or removed. All other issues are test coverage gaps and documentation improvements.