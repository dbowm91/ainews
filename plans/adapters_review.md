# Adapters Module Architecture Review

## Summary

The `architecture/adapters.md` document is largely accurate. Most claims about file structure, adapter patterns, and session ownership are verified. Several discrepancies were found, including one bug and several documentation gaps.

---

## Verified Claims

### ✓ File Inventory
| File | Purpose | Verified |
|------|---------|----------|
| `base.py` | Abstract base + registry | ✓ |
| `rss.py` | RSS/Atom via feedparser | ✓ |
| `api.py` | REST API + JSONPath | ✓ |
| `web.py` | CSS selector scraping | ✓ |
| `session.py` | SSRFSafeRedirectHandler | ✓ |

### ✓ Registry Pattern
`@register_adapter('rss')` registers in `_ADAPTER_REGISTRY`. `get_adapter_class()` retrieves adapters. Verified in `adapters/base.py:23-35`.

### ✓ BaseSourceAdapter Interface
- `fetch()` and `parse_item()` are abstract methods
- `fetch_and_parse()` combines both with error handling
- All verified in `base.py:50-69`

### ✓ RSSAdapter Session Ownership
Documented correctly: RSSAdapter creates its own `requests.Session` with its own `SSRFSafeRedirectHandler` instance (`rss.py:47-52`). APIAdapter and WebAdapter share `get_crawl_session()` (`api.py:22`, `web.py:35`).

### ✓ SSRF Protection
`SSRFSafeRedirectHandler` at `session.py:16-55` validates redirects via `validate_url_safe()`. Blocklist includes internal IPs and `javascript:`/`data:` schemes via scheme validation in `utils/url.py`.

### ✓ Config Field Naming
Documented correctly: `SourceConfig.config` (not `adapter_config`) is validated against `RSSConfig`/`APIConfig`/`WebConfig` via field_validator in `schemas/source.py:124-131`.

### ✓ Filter Operations
Documented correctly: `equals`, `min`, `exists` implemented. `contains` NOT implemented. Verified at `api.py:196-211`.

### ✓ Pagination Types
`next_link`, `query_param`, `none` all implemented. Verified at `api.py:75-90`, `schemas/source.py:59-70`.

---

## Discrepancies

### 1. APIAdapter `item_url` — BUG (HIGH)

**Documented at line 88:**
> Item URL template for individual item fetching via `item_url`

**Actual behavior at `api.py:63-71`:**
```python
if cfg.item_url and all_items:
    fetched = []
    for item in all_items[: cfg.max_items]:
        item_id = self._resolve_path(item, cfg.fields.get("external_id", "$.id"))
        if item_id:
            fetched_item = self._fetch_item(item_id)
```

The `item_url` template uses `{id}` as placeholder (`api.py:163`):
```python
url = cfg.item_url.format(id=item_id)
```

**Problem:** The external_id path is resolved from each `item` in the list page response, but the document implies direct item URL construction from list items. If the list page returns only lightweight item objects (e.g., `{id, title}`) without full URL data, the item_url template approach works. However, no validation exists to ensure `fields.external_id` is configured when `item_url` is used.

**Severity:** HIGH — silently returns empty results if `fields.external_id` is not configured.

---

### 2. WebAdapter Request Delay — DOCUMENTATION GAP (MED)

**Documented at line 139:**
> The `request_delay_min`/`request_delay_max` configuration in `WebConfig` applies **per-article**, not per-page.

**Actual behavior at `web.py:171-175`:**
```python
def _polite_get(self, url: str) -> Optional[BeautifulSoup]:
    cfg = self.adapter_config
    validate_url_safe(url)
    delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
    time.sleep(delay)
```

The delay is applied in `_polite_get`, which is called per-article URL in `fetch()` at line 64:
```python
for url in article_urls:
    soup = self._polite_get(url)
```

This is correct — delay is per-article. **The documentation is accurate**, but the concern about "more aggressive rate limiting than expected for sites with multiple pages" is valid.

---

### 3. APIAdapter Auth — DOCUMENTATION ACCURATE (LOW)

**Documented at line 89:**
> Auth header injection (Bearer token only — API key in custom headers NOT supported)

**Verified at `api.py:165-170`:**
```python
if cfg.api_key:
    if cfg.auth_header:
        headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
    else:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
```

Confirmed: Only Bearer token auth is supported. No API key header support (e.g., `X-Api-Key`).

---

### 4. Rate Limiting Backoff — NOT READING RETRY-AFTER (MED)

**Documented at line 198:**
> Rate limiting: Fixed exponential backoff (2^attempt * 5 + jitter), NOT reading Retry-After header

**Actual behavior at `web.py:180-182`:**
```python
if resp.status_code == 429:
    wait = 2**attempt * 5 + random.uniform(0, 2)
    time.sleep(wait)
```

Confirmed: Does NOT read `Retry-After` header. Documented correctly.

**Note:** This is a known limitation. The document should note this applies specifically to `WebAdapter` since `RSSAdapter` uses urllib3's `Retry` which also doesn't respect `Retry-After`.

---

### 5. RSSAdapter `user_agent` Default (LOW)

The document at line 33 shows:
```python
user_agent: str = "AINwsBot/1.0"
```

But `schemas/source.py:33` shows:
```python
user_agent: str = "AINwsBot/1.0"
```

The document has a typo ("AINwsBot" vs "AINewsBot"), but the default matches. Minor documentation issue.

---

### 6. `list_method` values in APIConfig — NOT DOCUMENTED (MED)

**Documented at line 73:**
```python
list_url: config['list_url']
list_items_path: config.get('list_items_path')
```

**Documented at line 87:**
> JSONPath field extraction via `list_items_path`

**Actual at `api.py:41-46`:**
```python
if cfg.list_method == "json_array":
    items = data if isinstance(data, list) else []
elif cfg.list_method == "json_object_items" and cfg.list_items_path:
    items = self._resolve_path(data, cfg.list_items_path) or []
```

The `list_method` values (`json_array`, `json_object_items`) are NOT documented in `adapters.md`. The document only shows pseudo-code with `list_items_path` but doesn't document the `list_method` field or its valid values.

---

### 7. WebAdapter `base_url` Requirement — NOT DOCUMENTED (MED)

The document shows:
```yaml
listing_url: "https://example.com/articles"
```

But `WebConfig` requires `base_url` (`schemas/source.py:89`). The document doesn't mention this required field. The `base_url` is used for resolving relative links in `_scrape_listing` (`web.py:160`).

---

## Layering Violations

### NONE — Clean Layering Verified

Adapters do NOT import from `services/`:
- `rss.py` imports only from `adapters.base`, `schemas.source`, `utils.url`, and `adapters.session`
- `api.py` imports only from `adapters.base`, `adapters.session`, `schemas.source`, `utils.url`
- `web.py` imports only from `adapters.base`, `adapters.session`, `schemas.source`, `utils.url`

The `_classify_topics()` function in `base.py` is a pure function with no external dependencies (just `re` module), avoiding a services import.

---

## Performance Concerns

### APIAdapter `_fetch_item` sequential fetching (MED)

`api.py:63-71` fetches individual items sequentially:
```python
for item in all_items[: cfg.max_items]:
    item_id = self._resolve_path(item, cfg.fields.get("external_id", "$.id"))
    if item_id:
        fetched_item = self._fetch_item(item_id)
```

No parallelization or batching. Could be improved with `asyncio` or thread pool.

---

## Recommendations

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|-----------------|
| HIGH | `item_url` external_id validation | `adapters/api.py:63-71` | Add validation that `fields.external_id` is configured when `item_url` is set; return clear error or log warning |
| MED | `list_method` values not documented | `adapters/api.py:41-46` | Document valid values (`json_array`, `json_object_items`) in `adapters.md` |
| MED | `base_url` requirement not documented | `schemas/source.py:89` | Document `base_url` field requirement in `adapters.md` |
| MED | `Retry-After` header not respected | `web.py:180-182` | Consider reading `Retry-After` header when present; document limitation |
| LOW | Typo "AINwsBot" | `schemas/source.py:33` | Fix typo to "AINewsBot" |
| LOW | Sequential item fetching | `adapters/api.py:63-71` | Consider async/threaded fetching for `item_url` when many items |

---

## Conclusion

The architecture document is mostly accurate. The main concerns are:
1. Missing documentation for `list_method` values and `base_url` requirement
2. Bug risk in `item_url` handling when `fields.external_id` is not configured
3. Known limitations around `Retry-After` header handling

No layering violations or security issues found. SSRF protection is correctly implemented.