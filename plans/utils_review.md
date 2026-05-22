# Utils Module Architecture Review

## Verified Claims

### File Inventory
| Documented File | Status | Notes |
|-----------------|--------|-------|
| `utils/url.py` | VERIFIED | Contains `validate_url_safe`, `UnsafeURLError`, `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, `clear_dns_cache` |
| `utils/text.py` | VERIFIED | Contains `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` |
| `utils/datetime.py` | VERIFIED | Contains `parse_date`, `format_date`, `time_ago` |
| `utils/hash.py` | VERIFIED | Contains `generate_hash`, `verify_hash` |
| `utils/html.py` | VERIFIED | Contains `strip_tags`, `linkify`, `extract_text` |
| `utils/security.py` | VERIFIED | Contains `generate_token`, `constant_time_compare` |

### Design Principles
1. **Pure functions**: Correctly documented - most functions are pure. `validate_url_safe()` and DNS functions in `url.py` are explicitly documented as having side effects due to DNS resolution with caching.
2. **Minimal dependencies**: VERIFIED - all modules use only standard library.
3. **Type hints**: VERIFIED - all functions have type annotations.
4. **URL validation layering**: VERIFIED - `utils/url.py` for adapters (clean layering), `services/url.py` for services (config-aware).

### __all__ exports in utils/url.py
VERIFIED - exports match exactly:
```python
__all__ = [
    "normalize_url",
    "normalize_title",
    "TRACKING_PARAMS",
    "UnsafeURLError",
    "validate_url_safe",
    "clear_dns_cache",
]
```

### Empty __init__.py
VERIFIED - file is 0 bytes (empty), consistent with documentation.

## Discrepancies and Issues

### CRIT-1: SVG script content executes (XSS Bypass)
**File**: `utils/text.py:83-131`
**Severity**: CRITICAL
**Bug**: When `<script>` tags are removed from SVG content, the JavaScript code inside is NOT removed.

```python
# Input:
sanitize_html('<svg><script>alert(1)</script></svg>')
# Actual output:
'<svg>alert(1)</svg>'  # XSS executes!
# Expected output:
'<svg></svg>'
```

**Root Cause**: `_TagStripper.handle_starttag()` returns early when `tag in _DANGEROUS_TAGS` (line 92-93), but `handle_data()` continues to capture content. The `handle_data` method doesn't check if we're inside a dangerous tag context.

**Fix Required**: Track dangerous tag context in `_skip_data`/`_skip_stack` pattern (similar to `utils/html.py:_HTMLTextExtractor`).

---

### MED-1: CSS `expression()` not stripped
**File**: `utils/text.py:104-106`
**Severity**: MEDIUM
**Bug**: The `expression()` CSS function is not stripped, allowing IE-compatible XSS.

```python
# Input:
sanitize_html('<div style="width:expression(alert(1))">test</div>')
# Actual output:
'<div style="width:expression(alert(1))">test</div>'
# Expected output:
'<div>test</div>'
```

**Root Cause**: `_JAVASCRIPT_PATTERNS` only contains `["javascript:", "vbscript:", "data:"]`. The pattern matching at lines 104-106 checks for these patterns in attribute VALUES, but doesn't check for `expression(` in style attributes.

**Fix Required**: Add `expression` pattern to `_JAVASCRIPT_PATTERNS` or add specific style attribute handling.

---

### MED-2: sanitize_html used in newsletter routes, not in utils/text
**File**: `routes/admin/newsletters.py:56-67`
**Severity**: MEDIUM (Architectural)
**Observation**: The codebase uses `nh3` (a proper HTML sanitizer) in `routes/admin/newsletters.py` for newsletter HTML sanitization, while `utils/text.py:sanitize_html` exists but is NOT actively imported anywhere in the codebase.

```bash
$ grep -r "sanitize_html" --include="*.py" ainews/
# Only finds: utils/text.py (definition) and test files that import it directly
# No production code actually imports sanitize_html from utils
```

The newsletter route uses `_sanitize_newsletter_html()` which wraps `nh3`. The `utils.text.sanitize_html` appears to be a legacy or unused function.

**Recommendation**: Either remove `sanitize_html` from `utils/text.py` if unused, or add test coverage and verify it's production-ready.

---

### LOW-1: normalize_url strips port from URLs with scheme-appropriate ports
**File**: `utils/url.py:74-77`
**Severity**: LOW (Design quirk)
**Observation**: The code strips port 443 for HTTPS and port 80 for HTTP, but this is inconsistent with the rest of the URL normalization (which preserves userinfo, paths, query strings). This could cause issues if a site serves both HTTP and HTTPS on different ports.

```python
if netloc.endswith(":443") and scheme == "https":
    netloc = netloc[:-4]
elif netloc.endswith(":80") and scheme == "http":
    netloc = netloc[:-3]
```

This is intentional behavior but undocumented - the architecture doc doesn't mention this stripping behavior.

---

## Layering Violations

### None Found
The documented layering is correct:
- `utils/url.py` - imported by adapters (api, session, web, rss, base)
- `services/url.py` - imported by services and routes
- `services/url.py` correctly imports from `utils/url.py` for shared constants (`TRACKING_PARAMS`, `normalize_url`, `normalize_title`)

---

## Deprecated Patterns

### Documented but Not Deprecated
- `time_ago()` is documented as an alias for `format_date()`. This is accurate and intentional.

---

## Security Concerns

| Issue | File | Line | Severity |
|-------|------|------|----------|
| SVG script content execution | `utils/text.py` | 83-131 | CRITICAL |
| CSS expression() not blocked | `utils/text.py` | 104-106 | MEDIUM |

---

## Performance Concerns

### None Found
- DNS cache uses thread-safe implementation with locks
- TTL cache properly handles concurrent access
- No obvious performance issues

---

## Recommendations Summary

| ID | Issue | Severity | Recommendation |
|----|-------|----------|----------------|
| CRIT-1 | SVG script content executes | CRITICAL | Fix `_TagStripper` to track dangerous tag context |
| MED-1 | CSS expression() not stripped | MEDIUM | Add `expression` to pattern checks |
| MED-2 | sanitize_html unused in production | MEDIUM | Add test coverage or deprecate |
| LOW-1 | Port stripping behavior undocumented | LOW | Document in arch doc or add comment |

---

## Appendix: Test Commands Used

```bash
# Verify file sizes
ls -la utils/

# Test XSS vectors
python3 -c "
from utils.text import sanitize_html
print(sanitize_html('<svg><script>alert(1)</script></svg>'))
print(sanitize_html('<div style=\"width:expression(alert(1))\">test</div>'))
"
```