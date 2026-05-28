# Architecture Review: adapters.md and utils.md

Review of `architecture/adapters.md` and `architecture/utils.md` against actual codebase.

## Verified Claims

### adapters.md

1. **File inventory (5 files)**: All 5 files exist — `base.py`, `rss.py`, `api.py`, `web.py`, `session.py`. (CORRECT)
2. **`@register_adapter` decorator exists**: Defined at `adapters/base.py:23-28`, works via `_ADAPTER_REGISTRY` dict. (CORRECT)
3. **`SOURCE_ADAPTERS` registry exists**: `adapters/base.py:20` — `SOURCE_ADAPTERS = _ADAPTER_REGISTRY`. (CORRECT)
4. **`RSSAdapter` registered as `'rss'`**: `adapters/rss.py:41`. (CORRECT)
5. **`APIAdapter` registered as `'api'`**: `adapters/api.py:16`. (CORRECT)
6. **`WebAdapter` registered as `'web'`**: `adapters/web.py:29`. (CORRECT)
7. **`RSSAdapter` creates own session**: `adapters/rss.py:47` — `self._session = requests.Session()`. (CORRECT)
8. **`RSSAdapter.close()` closes its session**: `adapters/rss.py:54-55`. (CORRECT)
9. **`APIAdapter` uses shared global session**: `adapters/api.py:22` — `self._session = get_crawl_session()`. (CORRECT)
10. **`APIAdapter.close()` is no-op**: `adapters/api.py:25-26`. (CORRECT)
11. **`WebAdapter` uses shared global session**: `adapters/web.py:35` — `self._session = get_crawl_session()`. (CORRECT)
12. **`WebAdapter.close()` is no-op**: `adapters/web.py:48-49`. (CORRECT)
13. **Session ownership table**: RSS=own, API/Web=shared — verified in code. (CORRECT)
14. **Filter operations (equals, min, exists, contains)**: All 4 implemented in `adapters/api.py:205-221`. (CORRECT)
15. **`APIAdapter` config fields (`list_url`, `list_items_path`, `fields`, `filters`, `metadata`)**: All match `schemas/source.py:APIConfig`. (CORRECT)
16. **`WebAdapter` CSS selector config via `ListingConfig` and `ArticleSelectors`**: Both exist in `schemas/source.py:73-85`. (CORRECT)
17. **`WebAdapter` pagination**: Implemented via `PaginationConfig` in `schemas/source.py:59-70` and used in `adapters/web.py:138-168`. (CORRECT)
18. **`WebAdapter` trafilatura fallback**: `adapters/web.py:112-122`. (CORRECT)
19. **Error handling: network errors → log + return empty**: Verified across all adapters. (CORRECT)
20. **Rate limiting: fixed exponential backoff, NOT Retry-After**: `adapters/web.py:181-183` — `wait = 2**attempt * 5 + random.uniform(0, 2)`. Comment at line 181 confirms "Retry-After header is not currently respected". (CORRECT)
21. **Adapters do NOT update Source health**: Verified — no `consecutive_failures` manipulation in any adapter. (CORRECT)
22. **`SSRFSafeRedirectHandler.__call__` signature**: `adapters/session.py:37` — `(self, request, response, **kwargs)`. (CORRECT)
23. **`SSRFSafeRedirectHandler` uses thread-local redirect counter**: `adapters/session.py:30-35`. (CORRECT)
24. **`SSRFSafeRedirectHandler` blocks javascript:/data: schemes**: Via `validate_url_safe()` call at line 46 which checks scheme. (CORRECT)
25. **Interface verification note about `**kwargs`**: Matches actual signature. (CORRECT)
26. **`request_delay_min`/`request_delay_max` per-article**: `adapters/web.py:174` — delay is in `_polite_get()` called per article URL. (CORRECT)

### utils.md

1. **File inventory (6 files)**: All 6 files exist — `url.py`, `text.py`, `datetime.py`, `hash.py`, `html.py`, `security.py`. (CORRECT)
2. **`utils/__init__.py` is empty (0 bytes)**: Confirmed — file is empty. (CORRECT)
3. **`truncate()` signature**: `utils/text.py:53` — `def truncate(text: str, length: int, suffix: str = "...") -> str`. (CORRECT)
4. **`sanitize_html()` exists**: `utils/text.py:146`. (CORRECT)
5. **`extract_hashtags()` exists**: `utils/text.py:169`. (CORRECT)
6. **`esc_xml_text()` exists**: `utils/text.py:19`. (CORRECT)
7. **`esc_xml_attr()` exists**: `utils/text.py:24`. (CORRECT)
8. **`escape_prompt_data()` exists**: `utils/text.py:36` — `def escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]`. (CORRECT)
9. **`parse_date()` signature**: `utils/datetime.py:10` — `def parse_date(date_str: str) -> datetime | None`. (CORRECT)
10. **`format_date()` behavior**: Returns 'just now', 'X minutes ago', 'X hours ago', 'yesterday', 'X days ago', '%b %d', '%b %d, %Y'. Verified at `utils/datetime.py:52-95`. (CORRECT)
11. **`time_ago()` is alias for `format_date()`**: `utils/datetime.py:98-100`. (CORRECT)
12. **`generate_token()` signature**: `utils/security.py:10` — `def generate_token(length: int = 32) -> str`. (CORRECT)
13. **`constant_time_compare()` exists**: `utils/security.py:15`. (CORRECT)
14. **`strip_tags()` exists**: `utils/html.py:37`. (CORRECT)
15. **`linkify()` exists**: `utils/html.py:52`. (CORRECT)
16. **`extract_text()` with trafilatura fallback**: `utils/html.py:63-75`. (CORRECT)
17. **`generate_hash()` signature**: `utils/hash.py:10` — `def generate_hash(data: str, algorithm: str = "sha256") -> str`. (CORRECT)
18. **`verify_hash()` signature**: `utils/hash.py:17` — `def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool`. (CORRECT)
19. **`normalize_url()` exists**: `utils/url.py:50`. (CORRECT)
20. **`normalize_title()` exists**: `utils/url.py:90`. (CORRECT)
21. **`clear_dns_cache()` exists**: `utils/url.py:199`. (CORRECT)
22. **`UnsafeURLError` inherits from `ValueError`**: `utils/url.py:126`. (CORRECT)
23. **`TRACKING_PARAMS` has 14 entries**: Counted from `utils/url.py:32-47` — exactly 14. (CORRECT)
24. **`TRACKING_PARAMS` contents match docs**: All 14 params listed in docs match code. (CORRECT)
25. **`__all__` exports in `utils/url.py`**: Matches docs — `["normalize_url", "normalize_title", "TRACKING_PARAMS", "UnsafeURLError", "validate_url_safe", "clear_dns_cache"]`. (CORRECT)
26. **`__all__` exports in `utils/text.py`**: `["esc_xml_text", "esc_xml_attr", "escape_prompt_data", "truncate", "sanitize_html", "extract_hashtags"]`. (CORRECT)
27. **`__all__` exports in `utils/datetime.py`**: `["parse_date", "format_date", "time_ago"]`. (CORRECT)
28. **`__all__` exports in `utils/hash.py`**: `["generate_hash", "verify_hash"]`. (CORRECT)
29. **`__all__` exports in `utils/html.py`**: `["strip_tags", "linkify", "extract_text"]`. (CORRECT)
30. **`__all__` exports in `utils/security.py`**: `["generate_token", "constant_time_compare"]`. (CORRECT)
31. **URL validation layering note**: `services/url.py` imports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py` — verified at `services/url.py:15`. (CORRECT)
32. **DNS cache uses global state**: `_dns_cache`, `_dns_executor`, `_TTLCache` all exist in `utils/url.py`. (CORRECT)
33. **Design principles #1**: `validate_url_safe()` performs DNS resolution with caching — confirmed. (CORRECT)

## Incorrect Claims

### adapters.md

1. **`RawItem` import location**: The docs state `RawItem` is imported from `adapters.base`:
   ```python
   from schemas.item import RawItem
   ```
   But `adapters/base.py:8` imports it from `schemas/item.py`, not from `adapters/base.py`. The other adapters (`rss.py`, `api.py`, `web.py`) import `RawItem` from `adapters.base` as a re-export. The docs don't clarify this chain. **(LOW — misleading but functional)**

2. **`BaseSourceAdapter.__init__` signature**: The docs show:
   ```python
   class BaseSourceAdapter(ABC):
       @abstractmethod
       def fetch(self) -> list[dict]: ...
   ```
   The actual `__init__` signature is `def __init__(self, source_config: SourceConfig)` at `adapters/base.py:41-48`, not `config: dict`. The docs omit the constructor entirely. **(MEDIUM — wrong signature would confuse new developers)**

3. **`fetch()` return type**: The docs claim `def fetch(self) -> list[dict]`, but the actual signature at `adapters/base.py:51` is `def fetch(self) -> list[Any]`. The return type is `list[Any]`, not `list[dict]`. **(LOW — technically inaccurate)**

4. **`parse_item()` parameter name**: The docs show `def parse_item(self, item: dict) -> RawItem`, but the actual signature at `adapters/base.py:54` is `def parse_item(self, raw: Any) -> Optional[RawItem]`. Both the parameter name and return type differ. **(LOW — technically inaccurate)**

5. **`SSRFSafeRedirectHandler.redirect_request` method**: The docs show:
   ```python
   class SSRFSafeRedirectHandler:
       def redirect_request(self, req, fp, code, msg, hdrs, newurl):
   ```
   This method does NOT exist in the actual code. The class uses `__call__` at `adapters/session.py:37`. The `redirect_request` method from `urllib` is not implemented. **(MEDIUM — docs show non-existent method)**

6. **`validate_url_safe()` raises `UnsafeURLError` for invalid URLs**: The docstring in `utils/url.py:92-97` says:
   ```
   Raises UnsafeURLError if URL is invalid or unsafe.
   ```
   But the actual code raises `ValueError` for empty URLs (line 252), unsupported schemes (line 256), and missing hostnames (line 260). Only DNS resolution failures and blocked IPs raise `UnsafeURLError`. **(HIGH — wrong exception type documented; callers catching `UnsafeURLError` will miss `ValueError`)**

7. **`services/url.py` duplication description**: The docs claim "it has duplicate implementations and should not be imported by adapters." In reality, `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py` (line 15). Only `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` are truly duplicated with config support. **(MEDIUM — oversimplified description)**

### utils.md

8. **`validate_url_safe()` return type for invalid URLs**: The docs say "Returns the validated URL string. Raises UnsafeURLError if URL is invalid or unsafe." As noted above, `ValueError` is raised for most invalid cases, not `UnsafeURLError`. **(HIGH — same issue as #6)**

## Bugs Found

### 1. `validate_url_safe()` exception type mismatch (HIGH)

**File:** `utils/url.py:245-264`

The function raises `ValueError` for most invalid inputs but the docstring claims `UnsafeURLError`. Callers in `adapters/web.py:55` catch `UnsafeURLError`:
```python
except UnsafeURLError as e:
    logger.error("[%s] Unsafe listing URL: %s", self.source_id, e)
```
This means a URL with an unsupported scheme (e.g., `ftp://`) would raise `ValueError` (not caught by the `UnsafeURLError` handler), causing an unhandled exception instead of the intended error log.

**Impact:** Adapter error handling silently misses non-DNS URL validation failures.

### 2. `_scrape_feed_fallback` uses hardcoded timeout (LOW)

**File:** `adapters/rss.py:24`

```python
def _scrape_feed_fallback(url: str, session: requests.Session, timeout: int = 15) -> list[dict[str, Any]]:
```

Called at line 70 with `cfg.request_timeout`, which is correct. However, the function signature has a default of `15` which could mask configuration issues if the default is used accidentally. **(LOW — not currently a bug, but fragile)**

## Improvement Opportunities

### 1. Document missing adapter methods (MEDIUM)

The following methods exist in `BaseSourceAdapter` but are not documented in `architecture/adapters.md`:
- `match_topics(item: RawItem) -> RawItem` — `adapters/base.py:81-88`
- `_get_match_text(item: RawItem) -> str` — `adapters/base.py:90-95`
- `_hash_ext_id(url, title) -> str` — `adapters/base.py:97-101`
- `_truncate(text, limit) -> Optional[str]` — `adapters/base.py:103-106`
- `__enter__` / `__exit__` context manager — `adapters/base.py:71-75`

### 2. Document `_classify_topics` function (MEDIUM)

`_classify_topics(title: str, text: str = "") -> list[str]` at `adapters/base.py:109-147` is a module-level function for topic classification. It's undocumented but important for understanding adapter behavior.

### 3. Document `get_adapter_class` function (MEDIUM)

`get_adapter_class(source_type: str) -> type[BaseSourceAdapter]` at `adapters/base.py:31-35` is exported via `adapters/__init__.py` but not documented in the architecture docs.

### 4. Document `WebConfig.base_url` field (LOW)

The `WebConfig` schema requires `base_url` (line 89 of `schemas/source.py`) which is used in `adapters/web.py:160,166` for URL resolution. The adapter config example in `architecture/adapters.md` omits this field.

### 5. Fix `validate_url_safe` docstring (HIGH)

Update `utils/url.py:92-97` to accurately describe exception behavior:
- `ValueError` for empty URL, unsupported scheme, no hostname
- `UnsafeURLError` for DNS resolution failure, blocked IP

### 6. Clarify `services/url.py` relationship (MEDIUM)

Update `architecture/utils.md:124` to note that `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py`, and only duplicates `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` with config support.

## Stale Content

### 1. `SSRFSafeRedirectHandler.redirect_request` method (MEDIUM)

`architecture/adapters.md:127` shows a `redirect_request` method that doesn't exist in the codebase. The actual implementation uses `__call__`. This appears to be stale content from before the handler was reimplemented as a callable.

### 2. `fetch()` return type annotation (LOW)

`architecture/adapters.md:31` shows `def fetch(self) -> list[dict]` but the actual return type is `list[Any]`. The `[dict]` type hint may be stale from when feeds returned dict-like feedparser entries.

## Priority Summary

| Priority | Finding | File |
|----------|---------|------|
| HIGH | `validate_url_safe()` raises `ValueError` not `UnsafeURLError` for most invalid inputs | `utils/url.py:245-264` |
| HIGH | `validate_url_safe()` docstring claims wrong exception type | `utils/url.py:92-97` |
| MEDIUM | `BaseSourceAdapter.__init__` signature wrong in docs | `architecture/adapters.md` |
| MEDIUM | `SSRFSafeRedirectHandler.redirect_request` doesn't exist | `architecture/adapters.md:127` |
| MEDIUM | `services/url.py` duplication description oversimplified | `architecture/utils.md:124` |
| MEDIUM | Missing adapter methods not documented | `architecture/adapters.md` |
| MEDIUM | `_classify_topics` undocumented | `architecture/adapters.md` |
| MEDIUM | `get_adapter_class` undocumented | `architecture/adapters.md` |
| LOW | `fetch()` return type is `list[Any]` not `list[dict]` | `architecture/adapters.md:31` |
| LOW | `parse_item()` param name is `raw` not `item`, return is `Optional[RawItem]` | `architecture/adapters.md:35` |
| LOW | `WebConfig.base_url` field not documented | `architecture/adapters.md` |
| LOW | `_scrape_feed_fallback` has hardcoded default timeout | `adapters/rss.py:24` |
