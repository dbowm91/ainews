# Utils Architecture Review

## Summary
Overall health: **Good**. Documentation is largely accurate with only minor discrepancies. The utility modules are well-structured and all documented functions exist. One minor docstring inaccuracy found.

## Verified Claims

### File Inventory
All utility files exist with correct functions:
- `utils/url.py`: `validate_url_safe`, `UnsafeURLError`, `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, `clear_dns_cache` ✅
- `utils/text.py`: `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` ✅
- `utils/datetime.py`: `parse_date`, `format_date`, `time_ago` ✅
- `utils/hash.py`: `generate_hash`, `verify_hash` ✅
- `utils/html.py`: `strip_tags`, `linkify`, `extract_text` ✅
- `utils/security.py`: `generate_token`, `constant_time_compare` ✅
- `utils/__init__.py`: Empty (0 bytes) ✅

### URL Utilities
- `validate_url_safe()`: Line 245-264, performs DNS resolution via `_resolve_and_check()` for SSRF protection ✅
- `UnsafeURLError`: Line 126-127, inherits from `ValueError` ✅
- `normalize_url()`: Line 50-87, strips tracking params and normalizes URL ✅
- `normalize_title()`: Line 90-99, normalizes title for fuzzy matching ✅
- `TRACKING_PARAMS`: Line 32-47, set of 14 tracking parameters as documented ✅
- `clear_dns_cache()`: Line 199-200, clears DNS cache ✅

### Two Truncate Functions
1. `utils/text.py:truncate()` (line 53-67): Word-boundary truncation with suffix ✅
2. `adapters/base.py:_truncate()` (line 104-106): Simple slicing `text[:limit]` for empty/non-empty handling ✅

### Text Utilities
- `truncate()`: Word-boundary breaking, finds last space before limit, appends suffix ✅
- `sanitize_html()`: Removes dangerous tags and event handler attributes ✅
- `extract_hashtags()`: Uses regex `r"#[a-zA-Z][a-zA-Z0-9_]*"` ✅
- `esc_xml_text()`: Escapes `&`, `<`, `>` ✅
- `esc_xml_attr()`: Escapes `&`, `'`, `"`, `<`, `>` ✅
- `escape_prompt_data()`: Handles strings, nested dicts, and lists recursively ✅

### DateTime Utilities
- `parse_date()`: Parses RFC 2822, ISO 8601, and other formats; naive datetimes get UTC appended (line 40) ✅
- `format_date()`: Returns 'just now', 'X minutes ago', 'X hours ago', 'yesterday', 'X days ago', '%b %d', '%b %d, %Y' ✅
- `time_ago()`: Alias for `format_date()` (line 98-99) ✅

### Security Utilities
- `generate_token()`: Uses `secrets.token_urlsafe(length)`, URL-safe base64 encoding ✅
- `constant_time_compare()`: Uses `hmac.compare_digest()` ✅

### HTML Utilities
- `strip_tags()`: Removes HTML tags using `_HTMLTextExtractor` class ✅
- `linkify()`: Converts URLs to `<a href="...">...</a>` links ✅
- `extract_text()`: Uses trafilatura with fallback to `strip_tags()` ✅

### Hash Utilities
- `generate_hash()`: Uses `hashlib.new(algorithm)` with utf-8 encoding ✅
- `verify_hash()`: Uses `hmac.compare_digest()` for constant-time comparison ✅

### Global State (utils/url.py)
- `_dns_cache`: Global `_TTLCache` singleton (line 184) ✅
- `_dns_cache_lock`: `threading.Lock` for double-checked locking (line 185) ✅
- `_TTLCache`: Uses `threading.Lock` at line 143 to protect `get`/`set`/`clear` operations ✅
- `_dns_executor`: `ThreadPoolExecutor(max_workers=4)` at line 132 ✅
- Hardcoded constants: `_DNS_CACHE_TTL = 5`, `_DNS_CACHE_MAX = 1024` (line 134-135) ✅

### Layering (services/url.py)
- `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py` unchanged (line 15) ✅
- `services/url.py:_get_dns_cache_config()` reads `DNS_CACHE_TTL` and `DNS_CACHE_MAX` via `get_config_with_default()` (line 60-63) ✅

### Empty `__init__.py`
- `utils/__init__.py` is empty (0 bytes) as documented ✅

## Discrepancies Found

### Minor Inaccuracy
- **Claim**: "Returns 'just now', 'X minutes ago', 'X hours ago', 'yesterday', 'X days ago', '%b %d' (same year), or '%b %d, %Y' (different year)."
- **Reality**: The docstring for `time_ago()` says "Return human-readable time difference" but implementation is simply `return format_date(dt)` which is correct. However, `format_date()` docstring at line 52-53 only says "Format datetime as human-readable relative or absolute date" without listing specific formats.
- **Severity**: Minor
- **Location**: `utils/datetime.py:52-53` (docstring), `utils/datetime.py:98-99` (time_ago)
- **Suggested fix**: Consider updating `format_date()` docstring to list the specific format strings returned, matching the architecture doc.

## Bugs Identified
None.

## Stale Items Found
None.

## Recommendations

1. **Low Priority - Docstring Enhancement**: Update `format_date()` docstring to enumerate the specific return formats (`'just now'`, `'X minutes ago'`, etc.) for consistency with architecture documentation. This would eliminate the minor discrepancy between the architecture doc and implementation docstring.