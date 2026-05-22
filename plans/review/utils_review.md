# Utils Module Review

Review of `architecture/utils.md` against actual implementation in `utils/`.

## Verified Claims

### File Inventory
All documented files exist and match implementation:
- `utils/url.py` - URL validation with SSRF protection (264 lines)
- `utils/text.py` - Text processing with 6 functions (174 lines)
- `utils/datetime.py` - DateTime parsing with 3 functions (100 lines)
- `utils/hash.py` - Hashing utilities with 2 functions (21 lines)
- `utils/html.py` - HTML processing with 3 functions (75 lines)
- `utils/security.py` - Security utilities with 2 functions (18 lines)

### Function Signatures
All documented function signatures match implementation:
- `text.py`: `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`
- `datetime.py`: `parse_date`, `format_date`, `time_ago`
- `security.py`: `generate_token`, `constant_time_compare`
- `html.py`: `strip_tags`, `linkify`, `extract_text`
- `hash.py`: `generate_hash`, `verify_hash`
- `url.py`: `validate_url_safe`, `normalize_url`, `normalize_title`, `clear_dns_cache`, `UnsafeURLError`

### Design Principles
1. **Pure functions claim**: Correct - most functions are pure; `validate_url_safe()` uses global mutable state (`_dns_cache`, `_dns_executor`, `_TTLCache`) as documented.
2. **Minimal dependencies**: Verified - only standard library imports.
3. **Type hints**: Verified - full typing present in all modules.
4. **URL validation layering**: Verified - `services/url.py` contains config-aware version using `get_config_with_default`; `utils/url.py` is the simple version. Duplication is intentional.

### `__all__` exports
`utils/url.py` exports match documentation exactly:
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

### Empty `__init__.py`
Verified - `utils/__init__.py` is 0 bytes as documented, confirming it's intentionally empty.

## Discrepancies

None identified. All documented claims match implementation.

## Bugs

No bugs identified. Implementation appears correct and complete.

## Improvements

### 1. Documentation accuracy for `format_date()` return values
The documentation states `format_date()` returns specific strings like `'just now'`, `'X minutes ago'`, etc. The actual implementation matches this, but the documentation does not mention the singular forms:
- `"1 hour ago"` (not "1 hours ago")
- `"yesterday"` is correctly documented

This is minor but could be clarified.

### 2. Missing documentation for `parse_date()` fallback behavior
The `parse_date()` function falls back to `email.utils.parsedate_to_datetime()` when standard formats fail. This is an implementation detail not mentioned in the documentation, but the documented "Supports RFC 2822, ISO 8601, and common date formats" is accurate enough.

### 3. Consider documenting `TRACKING_PARAMS` set size
The `TRACKING_PARAMS` constant contains 14 tracking parameters (utm_source, utm_medium, utm_campaign, utm_term, utm_content, fbclid, gclid, ref, source, mc_cid, mc_eid, utm_id, twclid, yclid). The documentation lists it as a set but doesn't specify contents. This is fine for documentation meant as an API reference.

### 4. `services/url.py` duplicates `_BLOCKED_NETWORKS` constant
While the documentation correctly identifies this as intentional duplication for config-awareness, both `utils/url.py` and `services/url.py` have identical `_BLOCKED_NETWORKS` lists. This is 13 lines of duplication, but changing it would require refactoring shared constants between layers, which may break the intentional layering pattern.

## Summary

The `architecture/utils.md` documentation is **highly accurate** and matches the implementation completely. No discrepancies that would confuse a developer reading the documentation and implementing against it.
