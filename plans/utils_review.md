# Utils Architecture Review Plan

## Verified Claims
- `url.py` exports: `validate_url_safe`, `UnsafeURLError`, `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, `clear_dns_cache` - ALL confirmed
- `text.py` exports: `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` - ALL confirmed
- `datetime.py` exports: `parse_date`, `format_date`, `time_ago` - ALL confirmed
- `hash.py` exports: `generate_hash`, `verify_hash` - ALL confirmed
- `html.py` exports: `strip_tags`, `linkify`, `extract_text` - ALL confirmed
- `security.py` exports: `generate_token`, `constant_time_compare` - ALL confirmed
- `validate_url_safe` blocks private/reserved IPs via `_BLOCKED_NETWORKS` with SSRF protection - CONFIRMED
- `UnsafeURLError` is raised for SSRF violations - CONFIRMED
- XML escaping functions (`esc_xml_text`, `esc_xml_attr`) exist for LLM prompt safety - CONFIRMED
- `extract_text` uses trafilatura with fallback to strip_tags - CONFIRMED
- All functions use type hints - CONFIRMED
- All utility files have minimal dependencies (mostly stdlib) - CONFIRMED

## Discrepancies
1. **Architecture doc is incomplete**: `url.py` has `normalize_url`, `normalize_title`, `clear_dns_cache`, `TRACKING_PARAMS` documented in one place (lines 113-127) but NOT in the initial File Inventory table (lines 6-14). The File Inventory only lists `validate_url_safe` and `UnsafeURLError` for url.py but the detailed section shows many more functions.
2. **Design Principles claim "no global state"**: `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`) with a singleton pattern (lines 182-194). This is global state with side effects.
3. **`normalize_url` not documented in url.py section**: Only appears in the second URL Utilities section (lines 102-127) but not in the initial table or first url.py section.
4. **`normalize_title` not documented in url.py section**: Same issue - appears later but not in main documentation.

## Improvement Recommendations
1. [HIGH] **Consolidate URL validation**: `services/url.py` and `utils/url.py` have nearly identical implementations of `UnsafeURLError`, `_TTLCache`, `_BLOCKED_NETWORKS`, `_resolve_and_check`, `validate_url_safe`. The services version has config support for TTL/maxsize but both exist. Consolidate into one location (likely `utils/url.py`) with config support and have `services/url.py` re-export from there.
2. [HIGH] **Fix "pure functions" claim**: The architecture doc claims utils should have "no side effects, no global state" but `utils/url.py` has global mutable DNS cache state. Either update the claim or refactor the DNS cache to be passed in (or use a thread-local pattern).
3. [MEDIUM] **Fix documentation inconsistencies**: The architecture doc has URL utilities appearing twice (lines 16-28 and lines 102-127). The File Inventory table is incomplete. Update to match actual exports.
4. [MEDIUM] **Add missing functions to exports**: `utils/url.py` exports many internal items (`_BLOCKED_NETWORKS`, `_is_ipv4_mapped`, `_get_dns_cache`, `_TTLCache`) that shouldn't be part of the public API. Clean up `__all__` to only export intended public functions.
5. [LOW] **Test coverage for utils**: No test files directly import from `utils/` - tests go through `services/url.py` instead. Add dedicated unit tests for `utils/` module functions to ensure they work correctly in isolation.

## Bugs Found
1. **No bugs found**: The implementations are functionally correct based on code review.

## Layer Violations
1. **CRITICAL LAYER VIOLATION - Circular dependency**: 
   - `services/url.py` imports from `utils/url.py` (line 15): `from utils.url import TRACKING_PARAMS, normalize_title, normalize_url`
   - But `utils/url.py` is supposed to be a minimal utils module with no service dependencies
   - However, `services/url.py` has its own duplicate implementation of everything including `_BLOCKED_NETWORKS`, `_TTLCache`, `UnsafeURLError`
   - The import from `utils.url` only brings in: `TRACKING_PARAMS`, `normalize_title`, `normalize_url`
   - This means `services/url.py` doesn't actually depend on `utils/url.py`'s SSRF validation functions - it has its own
   - This is confusing but not a runtime bug since `services/url.py` re-exports from itself

2. **Layer confusion - SSRF protection location**: 
   - `utils/url.py` has full SSRF protection (`validate_url_safe`, `_resolve_and_check`, `_BLOCKED_NETWORKS`)
   - `services/url.py` has duplicate full SSRF protection
   - Adapters import from `utils/url.py` for SSRF (e.g., `adapters/session.py`, `adapters/web.py`, `adapters/rss.py`, `adapters/api.py`)
   - But many other places import from `services/url.py` (e.g., `services/search/*.py`, `services/llm/*.py`)
   - This creates inconsistency in which DNS cache is used

3. **The `_dns_executor` ThreadPoolExecutor in `utils/url.py` is a global side effect**:
   - Line 130: `_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")`
   - This is module-level global state that performs I/O
   - Contradicts "pure functions" design principle
   - Also creates resource leaks if the module is loaded multiple times (though in practice it won't be)

## Summary
The utils module implementations are functionally correct and well-tested (via `services/url` wrapper). However, there are significant documentation inconsistencies and architectural issues:

1. Duplicate URL validation implementations in `utils/url.py` and `services/url.py`
2. Global mutable state in a module claiming to have "pure functions"
3. Inconsistent imports across the codebase (some use `utils.url`, others use `services.url`)
4. Documentation doesn't match actual exports (incomplete File Inventory table)

The architecture claim that "adapters should import from utils/url.py for clean layering" is being violated because `services/url.py` exists as a duplicate with the same functionality. The architecture doc doesn't mention `services/url.py` at all.
