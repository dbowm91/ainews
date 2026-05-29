# Review: architecture/utils.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- `utils/__init__.py` is empty (0 bytes) — `utils/__init__.py:0`
- `__all__` exports in `url.py` match documented list — `utils/url.py:21-28`
- `normalize_url()` strips tracking params, lowercases, normalizes — `utils/url.py:50-87`
- `normalize_title()` lowercases, collapses whitespace — `utils/url.py:90-99`
- `TRACKING_PARAMS` is a set — `utils/url.py:32-47`
- `UnsafeURLError` inherits from `ValueError` — `utils/url.py:126-127`
- `validate_url_safe()` raises `UnsafeURLError` for empty URL, unsupported scheme, missing hostname, DNS failure, blocked IP — `utils/url.py:245-264`
- `clear_dns_cache()` exists — `utils/url.py:199-200`
- `esc_xml_text()` escapes `&`, `<`, `>` — `utils/text.py:19-21`
- `esc_xml_attr()` escapes `&`, `'`, `"`, `<`, `>` — `utils/text.py:24-33`
- `escape_prompt_data()` recursively escapes dict string values — `utils/text.py:36-50`
- `truncate()` breaks on word boundaries — `utils/text.py:53-67`
- `sanitize_html()` removes dangerous tags and event handlers — `utils/text.py:146-166`
- `extract_hashtags()` extracts `#hashtags` — `utils/text.py:169-174`
- `parse_date()` supports multiple formats including RFC 2822 — `utils/datetime.py:10-49`
- `format_date()` returns relative or absolute date strings — `utils/datetime.py:52-95`
- `time_ago()` is an alias for `format_date()` — `utils/datetime.py:98-100`
- `generate_token()` uses `secrets.token_urlsafe()` — `utils/security.py:10-12`
- `constant_time_compare()` uses `hmac.compare_digest()` — `utils/security.py:15-18`
- `strip_tags()` removes HTML tags — `utils/html.py:37-49`
- `linkify()` converts URLs to clickable links — `utils/html.py:52-60`
- `extract_text()` uses trafilatura with fallback — `utils/html.py:63-75`
- `generate_hash()` and `verify_hash()` exist — `utils/hash.py:10-21`
- `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py` — `services/url.py:15`
- `services/url.py` duplicates `UnsafeURLError`, `_resolve_and_check`, `validate_url_safe` with config support — `services/url.py:60-63,132-192`
- DNS cache uses global mutable state (`_dns_cache`, `_dns_executor`, `_TTLCache`) — `utils/url.py:132-196`
- All utils files exist in `utils/` directory — verified via glob

## Incorrect Claims

1. **TRACKING_PARAMS count claimed as 14 but has only 14 entries — CORRECT**
   - Doc says "14 params" — actual set has exactly 14 entries: `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `fbclid`, `gclid`, `ref`, `source`, `mc_cid`, `mc_eid`, `utm_id`, `twclid`, `yclid`
   - `utils/url.py:32-47`
   - Priority: N/A (verified correct)

2. **`format_date()` return values documented incorrectly**
   - Doc says returns "just now", "X minutes ago", "X hours ago", "yesterday", "X days ago", "%b %d", "%b %d, %Y"
   - Actual at `utils/datetime.py:70-95`: Returns "just now" for ≤1 min, "{minutes} minutes ago" for <60min, "1 hour ago" or "{hours} hours ago" for <24h, "yesterday" for <48h, "{days} days ago" for <7d, "%b %d" same year, "%b %d, %Y" different year
   - Doc omits "1 hour ago" (singular) vs "{hours} hours ago" (plural) distinction
   - Priority: LOW (minor inaccuracy in documentation)

3. **`escape_prompt_data()` documented as `dict` return but actually returns `dict[str, Any]`**
   - Doc: `def escape_prompt_data(data: dict) -> dict:`
   - Actual at `utils/text.py:36`: `def escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]:`
   - Priority: LOW (type hint precision)

4. **`constant_time_compare()` documented as returning `bool` but takes `str` params**
   - Doc: `def constant_time_compare(a: str, b: str) -> bool:`
   - Actual at `utils/security.py:15`: `def constant_time_compare(a: str, b: str) -> bool:`
   - Signature matches — no issue
   - Priority: N/A (verified correct)

## Bugs Found

1. **`utils/text.py` `sanitize_html()` regex replacement produces invalid HTML**
   - `utils/text.py:165`: `result = re.sub(rf'href\s*=\s*["\']?{re.escape(pat)}[^"\']*["\']?', f'href="#"', result, flags=re.IGNORECASE)`
   - The replacement `href="#"` replaces the entire matched attribute but uses a bare `href="#"` without quotes around the value
   - Should be `href="#"` (already has quotes) — actually this is fine, it produces `href="#"`
   - Wait, re-reading: the replacement string is `f'href="#"'` which produces the literal string `href="#"` — this is correct HTML
   - Priority: N/A (false alarm)

2. **`utils/url.py` DNS cache TTL not configurable in utils version**
   - `utils/url.py:134-135`: `_DNS_CACHE_TTL = 5` and `_DNS_CACHE_MAX = 1024` are hardcoded
   - `services/url.py:60-63`: reads from config via `get_config_with_default()`
   - Doc at line 126 documents this difference correctly
   - Not a bug, but worth noting that `utils/url.py` ignores config while `services/url.py` respects it
   - Priority: LOW (documented intentional difference)

3. **`utils/text.py` `_TagStripper` may produce malformed output for nested dangerous tags**
   - `utils/text.py:130-136`: `handle_endtag` pops from `_skip_stack` but only decrements `_skip_data` when stack is empty
   - If dangerous tags are nested (e.g., `<script><script>...</script></script>`), the first `</script>` pops the stack but `_skip_data` remains True until the second `</script>`
   - This is actually correct behavior — nested dangerous tags should all be stripped
   - Priority: N/A (correct behavior)

## Improvement Opportunities

1. **`utils/url.py` should document the `_BLOCKED_NETWORKS` list completeness**
   - 14 networks covering IPv4 private ranges, loopback, link-local, multicast, broadcast, and IPv6 equivalents
   - Not documented in utils.md
   - Priority: LOW

2. **`utils/text.py` should document `_DANGEROUS_TAGS` and `_EVENT_HANDLER_ATTRS`**
   - The `sanitize_html()` function's behavior depends on these constants
   - Not documented in utils.md
   - Priority: LOW

3. **`utils/datetime.py` `parse_date()` should document timezone handling**
   - Naive datetimes get `timezone.utc` appended (`utils/datetime.py:39-40`)
   - This is a significant behavior not mentioned in the doc
   - Priority: MEDIUM

4. **`utils/hash.py` `verify_hash()` should document constant-time comparison**
   - Uses `hmac.compare_digest()` for timing-attack resistance
   - Not mentioned in utils.md
   - Priority: LOW

5. **`utils/html.py` `extract_text()` ImportError warning**
   - `utils/html.py:73`: Logs warning when trafilatura not available
   - Per AGENTS.md: "The `extract_text()` function in `utils/html.py` logs a warning when trafilatura is not available, rather than silently passing on the ImportError"
   - This behavior is not documented in utils.md
   - Priority: LOW

6. **`utils/security.py` `constant_time_compare()` imports hmac inside function body**
   - `utils/security.py:17`: `import hmac` is inside the function, not at module level
   - Minor: could be a module-level import for consistency
   - Priority: LOW

## Stale Content

1. **No stale file references found** — all referenced files (`url.py`, `text.py`, `datetime.py`, `security.py`, `html.py`, `hash.py`) exist and contain the documented functions

2. **`services/url.py` duplication is correctly documented**
   - Doc at line 126 accurately describes the duplication pattern and the config support difference
   - No stale content here

3. **`utils/__init__.py` empty file explanation is accurate**
   - Doc at lines 147-152 correctly explains why it's empty
   - Verified: file is 0 bytes
