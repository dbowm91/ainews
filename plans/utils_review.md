# Utils Module Architecture Review

## Summary

This review verifies the claims in `architecture/utils.md` against the actual codebase in `utils/`. The document accurately describes the file inventory and function signatures for most files, but contains significant discrepancies and design principle violations in `url.py`.

---

## Verified Claims

### text.py ✅
All 6 functions documented and match exactly:
- `truncate(text: str, length: int, suffix: str = "...") -> str` ✅
- `sanitize_html(html: str) -> str` ✅
- `extract_hashtags(text: str) -> list[str]` ✅
- `esc_xml_text(text: str) -> str` ✅
- `esc_xml_attr(text: str) -> str` ✅
- `escape_prompt_data(data: dict) -> dict` ✅ (uses `dict[str, Any]`)

### datetime.py ✅
All 3 functions documented and match:
- `parse_date(date_str: str) -> datetime | None` ✅
- `format_date(dt: datetime) -> str` ✅
- `time_ago(dt: datetime) -> str` ✅ (alias for format_date)

### hash.py ✅
All 2 functions documented and match:
- `generate_hash(data: str, algorithm: str = "sha256") -> str` ✅
- `verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool` ✅

### html.py ✅
All 3 functions documented and match:
- `strip_tags(html: str) -> str` ✅
- `linkify(text: str) -> str` ✅
- `extract_text(html: str) -> str` ✅ (uses trafilatura fallback)

### security.py ✅
All 2 functions documented and match:
- `generate_token(length: int = 32) -> str` ✅
- `constant_time_compare(a: str, b: str) -> bool` ✅

---

## Discrepancies and Issues Found

### CRITICAL: url.py Global Mutable State (Design Principle Violation)

**Location:** `utils/url.py:130-194`

The document claims all utils are "pure functions with no side effects and no global state" (line 131), but `url.py` has extensive global mutable state:

1. **`_dns_executor` (line 130):** Global `ThreadPoolExecutor` with 4 workers
2. **`_dns_cache` (line 182):** Module-level cache variable
3. **`_dns_cache_lock` (line 183):** Module-level lock
4. **`_TTLCache` class (lines 136-179):** Mutable cache with internal state (`_hits`, `_misses`)

**Issue:** `validate_url_safe()` is documented as a pure function but performs DNS resolution with caching - a side effect with global state.

**Note:** The file itself acknowledges this in its docstring (lines 3-5):
> "Most functions are pure, but validate_url_safe() and related DNS functions have side effects - they perform DNS resolution with caching using global state"

However, the architecture document does NOT reflect this deviation from the pure function principle.

### Issue 2: Document Duplication in url.py Section (lines 102-127)

The document has two "URL Utilities (`url.py`)" sections:
- Lines 16-28: Basic signature documentation
- Lines 102-127: Extended documentation with additional functions

The second section (102-127) documents `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, and `clear_dns_cache()` which are correct and present, but the document structure is confusing with the duplicate sections.

---

## Specific Bugs

### Bug 1: url.py Returns Unnormalized URL

**Location:** `utils/url.py:243-262`

```python
def validate_url_safe(url: str) -> str:
    # ... validation logic ...
    return url  # line 262 - returns original URL, not normalized
```

The function validates the URL but returns the original input, not a normalized version. The document says "Returns the validated URL string" which is ambiguous - it could mean the validated original or the normalized form.

**Recommendation:** Either:
1. Return `url` (current behavior - returns original, just validated)
2. Return `normalize_url(url)` if normalization is expected

Currently it returns the original, so there's no bug, but the behavior could be clarified.

### Bug 2: time_ago() Captures Global State

**Location:** `utils/datetime.py:52-95`

```python
def format_date(dt: datetime) -> str:
    now = datetime.now(timezone.utc)  # line 57 - captures current time
```

This function relies on `datetime.now()` which is technically non-deterministic (depends on when it's called). This is generally acceptable for utility functions but violates the "pure function" principle if "pure" is interpreted strictly (same input → same output, no external state).

However, this is a common pattern for date formatting and likely acceptable.

---

## Improvement Recommendations

### 1. Update architecture/utils.md

The document should clearly note that `validate_url_safe()` in `url.py` is NOT a pure function due to DNS resolution side effects. The "Design Principles" section (line 129-135) should be updated to reflect this exception.

**Proposed addition:**
> Note: `validate_url_safe()` in `url.py` performs DNS resolution with caching and is therefore not a pure function. It modifies global state (`_dns_cache`) as a side effect.

### 2. Consider Extracting DNS Resolution to Services Layer

Currently `utils/url.py` has significant infrastructure code (ThreadPoolExecutor, TTLCache) that arguably belongs in the services layer. Consider:
- Moving DNS resolution to `services/url.py` (which already has SSRF implementation per AGENTS.md)
- Keeping only pure URL normalization in `utils/url.py`

### 3. Clarify validate_url_safe Return Value

The function returns the original URL after validation. Document this behavior clearly:
> Returns the original URL string if valid (does not return normalized URL)

### 4. Remove Duplicate url.py Section

Lines 102-127 duplicate the url.py section. Remove the first section (lines 16-28) or restructure to avoid confusion.

---

## Files Reviewed

| File | Status | Issues |
|------|--------|--------|
| `utils/url.py` | ⚠️ Partially Accurate | Global mutable state, document duplication |
| `utils/text.py` | ✅ Accurate | None |
| `utils/datetime.py` | ✅ Accurate | time_ago captures current time (acceptable) |
| `utils/hash.py` | ✅ Accurate | None |
| `utils/html.py` | ✅ Accurate | None |
| `utils/security.py` | ✅ Accurate | None |

---

## Conclusion

The architecture document is mostly accurate for the pure utility modules (text, hash, html, security, datetime). However, `url.py` has a significant design principle violation: it contains global mutable state (DNS cache, ThreadPoolExecutor) despite the document claiming all utils are pure functions. This should be documented explicitly.