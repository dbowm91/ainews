# Utils Architecture Review

## Verified Claims

### Pure Functions with Minimal Dependencies (Most Files)

| File | Pure | Minimal Dependencies | Notes |
|------|------|---------------------|-------|
| `utils/text.py` | Yes | `re`, `html.parser` | All functions are pure |
| `utils/security.py` | Yes | `secrets`, `hmac` | Standard library only |
| `utils/hash.py` | Yes | `hashlib`, `hmac` | Standard library only |
| `utils/datetime.py` | Mostly | `datetime`, `email.utils` | Uses `datetime.now()` for `format_date` (expected) |
| `utils/html.py` | Yes | `re`, `html.parser`, (optional `trafilatura`) | Standard library + one optional package |

### File Inventory Accuracy

The architecture document accurately lists all utility files and their purposes:
- `url.py` - URL validation with SSRF protection
- `text.py` - Text processing and XML escaping  
- `datetime.py` - Date/time parsing and formatting
- `hash.py` - Hashing utilities
- `html.py` - HTML processing
- `security.py` - Security utilities

### Function Signatures

Most function signatures in the architecture document match the actual code:
- `truncate(text, length, suffix="...")` - matches
- `sanitize_html(html)` - matches
- `extract_hashtags(text)` - matches
- `esc_xml_text(text)`, `esc_xml_attr(text)` - match
- `escape_prompt_data(data)` - matches
- `parse_date(date_str)` - matches
- `format_date(dt)`, `time_ago(dt)` - match (time_ago is alias for format_date)
- `generate_token(length=32)` - matches
- `constant_time_compare(a, b)` - matches
- `generate_hash(data, algorithm="sha256")` - matches
- `strip_tags(html)`, `linkify(text)`, `extract_text(html)` - match
- `UnsafeURLError` exception class - matches

### Design Principles (Partially Verified)

- **Type hints**: Full typing present across all utility files
- **Comprehensive validation**: Input checking with clear errors present
- **Testable**: Pure functions make unit testing straightforward

---

## Discrepancies

### 1. `utils/url.py` Claims to Be Pure But Has Global Mutable State

**Architecture Document States:**
> "pure functions: No side effects, no global state"

**Actual Code (lines 126, 178-179):**
```python
_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")  # Global mutable!
_dns_cache: _TTLCache | None = None     # Global mutable!
_dns_cache_lock = threading.Lock()       # Global mutable!
```

This is explicitly noted in `AGENTS.md`:
> "utils/url.py Not Pure: Despite docstring claims, utils/url.py has global mutable state (_dns_cache, _dns_cache_lock, _dns_executor). Don't assume pure function behavior."

### 2. `clear_dns_cache()` Documented Twice in Architecture

The architecture document lists `clear_dns_cache()` twice:
- Line 122: "Clear the DNS resolution cache" in the first URL Utilities table
- Lines 122-123: Repeated in the second URL Utilities section

### 3. `normalize_url` and `normalize_title` Not in `__all__`

**Architecture Document:** Lists `normalize_url` and `normalize_title` as part of the public API (lines 113-117).

**Actual Code (`utils/url.py` lines 17-24):**
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

Wait, they ARE in `__all__`. This is actually correct. However, the architecture document does NOT list them in the initial File Inventory table (lines 7-14), only in the second detailed section. This creates confusion about what's actually public.

### 4. `extract_text` Trafilatura Fallback Not Prominently Documented

**Architecture Document (line 89):**
> "Extract readable text from HTML (uses trafilatura fallback)"

**Actual Code (`utils/html.py` lines 62-68):**
```python
try:
    import trafilatura
    downloaded = trafilatura.extract(html)
    if downloaded:
        return downloaded.strip()
except ImportError:
    pass  # Silently falls back to strip_tags
```

The trafilatura dependency is optional and silently ignored if not installed. The architecture document should clarify this is an **optional** dependency.

---

## Improvement Recommendations

### 1. Clarify `utils/url.py` is NOT Pure

The architecture document should explicitly state that `utils/url.py` contains impure functions due to DNS caching:

```markdown
## URL Utilities (`url.py`)

> **Note**: Unlike other utils modules, `url.py` contains impure functions with 
> global state for DNS caching ( `_dns_cache`, `_dns_executor`). This is intentional 
> for performance. `validate_url_safe()` performs actual DNS resolution.
```

### 2. Fix Duplicate `clear_dns_cache()` in Documentation

Remove the duplicate entry and consolidate into a single, accurate description.

### 3. Add `normalize_url` and `normalize_title` to File Inventory Table

The initial file inventory table should include all public functions, not just a subset.

### 4. Document `extract_text` Dependency More Clearly

Add a note that `trafilatura` is an optional dependency:
```markdown
def extract_text(html: str) -> str:
    """Extract readable text from HTML (uses trafilatura fallback if available)."""
```

### 5. Consider Separating Pure and Impure URL Functions

For cleaner architecture, consider:
- Keep `validate_url_safe()` in `utils/url.py` (with documented impurity)
- Move pure URL normalization (`normalize_url`, `normalize_title`) to a separate module or keep in `utils/url.py` but document clearly

### 6. Add Type Safety for `sanitize_html` Return Type

Currently returns `str` but `strip_tags` regex fallback could theoretically return `None`. Add explicit `-> str`.

---

## Bugs Found

### 1. `sanitize_html` Uses Bare `except Exception`

**File:** `utils/text.py` line 102
```python
except Exception:  # noqa: BLE001 - return original on any parse error
    return html
```

This catches ALL exceptions including `KeyboardInterrupt`, `SystemExit`, etc. Should be more specific:
```python
except (Exception, ValueError):  # Or specifically HTMLParseError if on older Python
```

### 2. `strip_tags` Fallback Uses Bare Exception

**File:** `utils/html.py` line 41
```python
except Exception:  # noqa: BLE001 - fallback to regex strip on parse error
    return re.sub(r"<[^>]+>", "", html)
```

Same issue - catches too board exceptions.

### 3. `extract_text` Silently Swallows trafilatura ImportError

**File:** `utils/html.py` lines 62-68

When `trafilatura` is not installed, the `ImportError` is silently caught and the function continues with the basic `strip_tags` result. This is likely intentional for graceful degradation, but could mask installation issues if trafilatura is expected but fails to import for other reasons.

### 4. No Input Validation for Negative Length in `truncate`

**File:** `utils/text.py` line 53
```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
```

If `length` is negative, the function produces unexpected results:
- `truncate("hello", -5)` returns `"..."` (5 characters of suffix)

Should add validation:
```python
if length < 0:
    raise ValueError("length must be non-negative")
```

### 5. `parse_date` Returns `None` for Invalid Input Silently

**File:** `utils/datetime.py` lines 45-49
```python
try:
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(date_str)
except (ValueError, TypeError):
    return None
```

The architecture document says "Returns datetime | None" which is accurate, but there's no way for the caller to distinguish between "malformed date" and "valid date that was actually parsed". This may be intentional but worth noting.

---

## Layer Violations

### 1. URL Validation Duplication Across Layers

The AGENTS.md notes this explicitly:
> "URL Validation Duplication: utils/url.py and services/url.py have duplicate SSRF protection implementations. services/url.py does NOT re-export from utils/url.py - it redefines everything locally with its own config support. Use utils/url.py for adapters (clean layering), services/url.py for services (has config support)."

This is a known architectural issue but documented. The `services/url.py` module exists and duplicates the SSRF protection for configuration support.

### 2. No Layer Violations Detected in Utils

The utils modules themselves do NOT import from `services` or `adapters`, which is correct:
- `utils/url.py` imports only stdlib (`ipaddress`, `socket`, `threading`, etc.)
- `utils/text.py` imports only stdlib
- `utils/datetime.py` imports only stdlib (`datetime`, `email.utils`)
- `utils/security.py` imports only stdlib
- `utils/hash.py` imports only stdlib
- `utils/html.py` imports stdlib + optional `trafilatura`

This maintains clean layering as specified in the architecture.

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 8 |
| Discrepancies | 4 |
| Improvement Recommendations | 6 |
| Bugs Found | 5 |
| Layer Violations | 0 (in utils modules themselves) |

**Overall Assessment**: The utils modules generally follow the architecture document, with the main discrepancy being the impure nature of `utils/url.py` which claims to be pure. The architecture document should be updated to reflect this reality and provide guidance on when to use `utils/url.py` vs `services/url.py`.
