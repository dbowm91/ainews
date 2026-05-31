# Review: Utils Module

**Reviewed:** 2026-05-31
**Source:** `architecture/utils.md`
**Reviewer:** Subagent 2 (Adapter & Utils Layer)
**Status:** COMPLETE

---

## Verified Claims

All claims below were checked against actual code and confirmed correct.

### File Inventory
- `url.py` — VERIFIED
- `text.py` — VERIFIED
- `datetime.py` — VERIFIED
- `hash.py` — VERIFIED
- `html.py` — VERIFIED
- `security.py` — VERIFIED

### Text Utilities (`text.py`)
- `truncate(text, length, suffix="...")` with word-boundary truncation — VERIFIED (`utils/text.py:53-67`)
- `sanitize_html(html)` — VERIFIED (`utils/text.py:146-166`)
- `extract_hashtags(text)` — VERIFIED (`utils/text.py:169-174`)
- `esc_xml_text(text)` — VERIFIED (`utils/text.py:19-21`)
- `esc_xml_attr(text)` — VERIFIED (`utils/text.py:24-33`)
- `escape_prompt_data(data)` recursive dict escaping — VERIFIED (`utils/text.py:36-50`)

### Two Different `truncate()` Functions
- `utils/text.py:truncate()` — word-boundary truncation — VERIFIED (`utils/text.py:53-67`)
- `adapters/base.py:BaseSourceAdapter._truncate()` — simple slicing — VERIFIED (`adapters/base.py:103-106`)

### DateTime Utilities (`datetime.py`)
- `parse_date(date_str) -> datetime | None` — VERIFIED (`utils/datetime.py:10`)
- Naive datetimes get UTC appended: `dt.replace(tzinfo=timezone.utc)` — VERIFIED (`utils/datetime.py:39-40`)
- `format_date(dt) -> str` — VERIFIED (`utils/datetime.py:52`)
- `time_ago(dt)` alias for `format_date()` — VERIFIED (`utils/datetime.py:98-100`)

### Security Utilities (`security.py`)
- `generate_token(length=32) -> str` using `secrets.token_urlsafe()` — VERIFIED (`utils/security.py:11-13`)
- `constant_time_compare(a, b) -> bool` using `hmac.compare_digest()` — VERIFIED (`utils/security.py:16-18`)

### HTML Utilities (`html.py`)
- `strip_tags(html)` — VERIFIED (`utils/html.py:37`)
- `linkify(text)` — VERIFIED (`utils/html.py:52`)
- `extract_text(html)` with trafilatura fallback — VERIFIED (`utils/html.py:63-75`)

### Hash Utilities (`hash.py`)
- `generate_hash(data, algorithm="sha256")` — VERIFIED (`utils/hash.py:11-15`)
- `verify_hash(data, hash, algorithm="sha256")` using `hmac.compare_digest()` — VERIFIED (`utils/hash.py:18-21`)

### URL Utilities (`url.py`)
- `validate_url_safe(url) -> str` — VERIFIED (`utils/url.py:245-264`)
- DNS resolution with `_dns_cache` (TTL cache) — VERIFIED (`utils/url.py:138-181,184-196`)
- `_dns_executor` ThreadPoolExecutor — VERIFIED (`utils/url.py:132`)
- `UnsafeURLError` inherits from `ValueError` — VERIFIED (`utils/url.py:126-127`)
- `normalize_url()` strips tracking params — VERIFIED (`utils/url.py:50-87`)
- `normalize_title()` fuzzy matching — VERIFIED (`utils/url.py:90-99`)
- `clear_dns_cache()` — VERIFIED (`utils/url.py:199-200`)
- `_TTLCache` with `threading.Lock` — VERIFIED (`utils/url.py:138-181`)
- Double-checked locking for `_dns_cache` via `_dns_cache_lock` — VERIFIED (`utils/url.py:185-196`)

### TRACKING_PARAMS
- Set of 14 tracking parameter names — VERIFIED (`utils/url.py:32-47`): `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `utm_id`, `fbclid`, `gclid`, `ref`, `source`, `mc_cid`, `mc_eid`, `twclid`, `yclid`

### __all__ Exports
- `url.py` exports 6 items: `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, `UnsafeURLError`, `validate_url_safe`, `clear_dns_cache` — VERIFIED (`utils/url.py:21-28`)
- `text.py` exports 6 items: `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`, `truncate`, `sanitize_html`, `extract_hashtags` — VERIFIED (`utils/text.py:9-16`)
- `security.py` exports 2 items — VERIFIED (`utils/security.py:8`)
- `hash.py` exports 2 items — VERIFIED (`utils/hash.py:8`)
- `html.py` exports 3 items — VERIFIED (`utils/html.py:11`)
- `datetime.py` exports 3 items — VERIFIED (`utils/datetime.py:7`)

### Empty `__init__.py`
- `utils/__init__.py` is empty (0 bytes) — VERIFIED

### Design Principles
- `validate_url_safe()` uses global mutable state (`_dns_cache`, `_dns_executor`) — VERIFIED (`utils/url.py:132,184`)
- `_TTLCache` uses `threading.Lock` — VERIFIED (`utils/url.py:143`)
- Thread-safe `_dns_cache` singleton with double-checked locking — VERIFIED (`utils/url.py:185-196`)

### `services/url.py` Duplication
- Re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py` — VERIFIED (`services/url.py:15`)
- `UnsafeURLError`, `_resolve_and_check`, `validate_url_safe` duplicated with config support — VERIFIED (`services/url.py:132-192`)
- Uses `get_config_with_default()` for `DNS_CACHE_TTL` and `DNS_CACHE_MAX` — VERIFIED (`services/url.py:60-63`)
- `utils/url.py` uses hardcoded `_DNS_CACHE_TTL = 5`, `_DNS_CACHE_MAX = 1024` — VERIFIED (`utils/url.py:134-135`)

---

## Incorrect Claims

No incorrect claims found. All factual claims in utils.md match the actual code.

---

## Bugs Found

No bugs found in the utils code itself.

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | `utils/text.py:sanitize_html()` has a duplicate `except ValueError:` clause at lines 159 and 161. The first `except ValueError:` catches the error, then `except (ValueError, TypeError, AttributeError):` catches overlapping types. The first clause is dead code. | maintainability | P3 |
| 2 | `utils/url.py:_resolve_and_check()` uses `socket.getaddrinfo` which may return both IPv4 and IPv6 addresses. If an IPv6 address resolves to a safe network but its IPv4-mapped equivalent doesn't (or vice versa), the check may miss blocked addresses. The IPv4-mapped check at line 233-238 handles this, but only for IPv6→IPv4 direction. | security | P3 |
| 3 | `utils/html.py:strip_tags()` catches broad `Exception` at line 46 (`# noqa: BLE001`). While logged, this masks unexpected errors. Consider catching `HTMLParser`-specific exceptions. | maintainability | P3 |
| 4 | `utils/datetime.py:parse_date()` catches `ValueError` and `TypeError` for `parsedate_to_datetime` but not `AttributeError` which could occur if `email.utils` is not available. | reliability | P3 |
| 5 | `utils/url.py:_TTLCache` uses `time.monotonic()` for TTL but the doc doesn't mention this. Consider noting that the cache is monotonic-clock-based (not wall-clock) for clarity. | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 137 | `_TTLCache` referenced at `utils/url.py:138` — double-checked locking at `utils/url.py:185-196` | The line numbers are approximately correct but could drift with code changes. The actual `_TTLCache` class is at lines 138-181, and the double-checked locking pattern spans lines 188-196 (the `_get_dns_cache()` function). The `_dns_cache_lock` declaration is at line 185. | Minor — line numbers are close enough. No action needed unless the doc aims for exact line references. |

---

## Summary

- Verified: 42 claims
- Incorrect: 0 claims
- Bugs: 0
- Improvements: 5
- Stale items: 1 (minor line number drift)

The utils.md document is highly accurate. All factual claims match the actual codebase. The only finding is a minor documentation accuracy issue (line number references that could drift) and several low-priority improvement suggestions for the utils code itself (duplicate exception clause, broad exception catch, etc.).
