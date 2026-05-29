# Review: architecture/adapters.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- `BaseSourceAdapter` ABC with `fetch()` and `parse_item()` abstract methods — `adapters/base.py:50-54`
- `@register_adapter` decorator registers in `SOURCE_ADAPTERS` registry — `adapters/base.py:23-28,18-20`
- `get_adapter_class()` exists and returns adapter by type — `adapters/base.py:31-35`
- `BaseSourceAdapter.__init__` sets `source_config`, `source_id`, `topic_config`, `adapter_config` — `adapters/base.py:41-48`
- `fetch_and_parse()` combined fetch+parse with error handling — `adapters/base.py:56-69`
- `match_topics()` matches item against configured topics — `adapters/base.py:81-88`
- `_get_match_text()` builds text for topic matching — `adapters/base.py:90-95`
- `_hash_ext_id()` static method generates stable external ID — `adapters/base.py:97-101`
- `_truncate()` static method truncates text — `adapters/base.py:103-106`
- `_classify_topics()` is a module-level function (not class method) — `adapters/base.py:109-147`
- `RSSAdapter` registered with `@register_adapter("rss")` — `adapters/rss.py:41`
- `RSSAdapter` creates own `requests.Session` with own `SSRFSafeRedirectHandler` — `adapters/rss.py:45-52`
- `RSSAdapter.close()` closes its own session — `adapters/rss.py:54-55`
- `RSSAdapter.fetch()` uses `feedparser.parse()` with BeautifulSoup fallback — `adapters/rss.py:57-71`
- `RSSAdapter` has `config_class = RSSConfig` — `adapters/rss.py:43`
- `APIAdapter` registered with `@register_adapter("api")` — `adapters/api.py:16`
- `APIAdapter` uses shared global session from `get_crawl_session()` — `adapters/api.py:22`
- `APIAdapter.close()` is a no-op (empty pass) — `adapters/api.py:25-26`
- `APIAdapter` has `config_class = APIConfig` — `adapters/api.py:18`
- `APIAdapter` supports `list_url`, `list_items_path`, `item_url`, `fields`, `filters` — `adapters/api.py:28-81` verified against `schemas/source.py:42-57`
- Filter operations `equals`, `min`, `exists`, `contains` implemented — `adapters/api.py:205-221`
- Auth header injection (Bearer token only) — `adapters/api.py:175-179`
- Pagination via `PaginationConfig` (next_link, query_param, none) — `adapters/api.py:83-61` + `schemas/source.py:59-70`
- `WebAdapter` registered with `@register_adapter("web")` — `adapters/web.py:29`
- `WebAdapter` uses shared global session — `adapters/web.py:35`
- `WebAdapter.close()` is a no-op — `adapters/web.py:48-49`
- `WebAdapter` has `config_class = WebConfig` — `adapters/web.py:31`
- WebAdapter CSS selector config via `ListingConfig` and `ArticleSelectors` — `schemas/source.py:73-86`
- `SSRFSafeRedirectHandler` in `session.py` — `adapters/session.py:16-55`
- `SSRFSafeRedirectHandler.__call__` signature `(self, request, response, **kwargs)` — `adapters/session.py:37`
- Thread-local redirect counter — `adapters/session.py:13,30-35`
- Session ownership table (RSS=own, API/Web=shared) — verified across all adapter `__init__` methods
- `get_crawl_session()` creates shared session with retry and SSRF handler — `adapters/session.py:58-77`
- Rate limiting uses fixed exponential backoff, NOT Retry-After header — `adapters/web.py:181-184`
- Source health tracking handled by `services/crawling.py`, not adapters — confirmed no health updates in adapter code
- WebAdapter pagination with `next_link_selector` — `adapters/web.py:163-167`
- Link URL resolution via `base_url` with `urljoin()` — `adapters/web.py:160,166`

## Incorrect Claims

1. **`_classify_topics` signature mismatch with actual call site**
   - Doc says: `_classify_topics(title: str, text: str = "")`
   - Call at `adapters/base.py:83`: `_classify_topics(text)` — passes combined title+content as first arg
   - The parameter name `title` is misleading since it receives all match text, not just the title
   - Priority: LOW (functionally correct, naming confusion)

2. **`BaseSourceAdapter.__init__` doc omits `*args, **kwargs`**
   - Doc shows explicit `__init__(self, source_config: SourceConfig)` signature
   - Actual at `adapters/base.py:41`: same explicit signature (NOT `*args, **kwargs`)
   - RSS/API/Web adapters use `*args, **kwargs` and call `super().__init__(*args, **kwargs)`
   - Priority: LOW (base class signature is accurate, subclass pattern not documented)

## Bugs Found

1. **`SSRFSafeRedirectHandler.__call__` returns original `request` object instead of redirect-modified request**
   - `adapters/session.py:54`: `return request` (not `request`)
   - For redirects, `request` is the original `PreparedRequest` with the original URL
   - Should return a new `PreparedRequest` with the redirect URL set, or `None` to skip redirect
   - In practice this may work because `requests` library handles redirect internally, but the handler returns the original request which means the redirect URL is NOT being validated by this handler's return value — it's only validated via the `validate_url_safe(location)` call
   - Priority: MEDIUM (functionally works but the return value is misleading)

2. **`_classify_topics` is recompiled on every call**
   - `adapters/base.py:141`: `compiled = {k: [re.compile(p, re.I) for p in pats] for k, pats in _PATTERNS.items()}`
   - Regex patterns are compiled inside the function body, not cached as module-level constants
   - Called once per article during `match_topics()`, so impact is minor but wasteful
   - Priority: LOW (performance, not correctness)

## Improvement Opportunities

1. **Document `WebAdapter` retry behavior more precisely**
   - Doc says "Rate limiting: Fixed exponential backoff (2^attempt * 5 + jitter)"
   - `adapters/web.py:183`: `wait = 2**attempt * 5 + random.uniform(0, 2)` — correct
   - But non-429 failures use `time.sleep(2**attempt)` (no `* 5` factor) at `adapters/web.py:192`
   - Doc should distinguish between 429 backoff and general retry backoff
   - Priority: MEDIUM

2. **Document `WebAdapter._polite_get` max_retries behavior**
   - `WebConfig.max_retries` (default 3) controls retry count for both 429 and network errors
   - Not documented in adapters.md
   - Priority: LOW

3. **Document `APIAdapter._fetch_item` sequential fetching limitation**
   - `adapters/api.py:169` has a comment noting sequential fetching could benefit from async/threaded fetching
   - Not documented as a known limitation
   - Priority: LOW

4. **Document `RSSAdapter` retry configuration**
   - `adapters/rss.py:48`: `Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])`
   - Uses urllib3 Retry adapter, different from WebAdapter's manual retry loop
   - Not documented
   - Priority: LOW

5. **Document `WebAdapter` User-Agent rotation**
   - `adapters/web.py:37-38`: Rotates through 3 User-Agent strings when default `AINwsBot/1.0` is used
   - Not documented
   - Priority: LOW

6. **Document `APIAdapter` velocity calculation**
   - `adapters/api.py:143-147`: Calculates `velocity = score / age_hours` for time-based scoring
   - Not documented
   - Priority: LOW

7. **Document `RSSConfig.min_content_length` field**
   - `schemas/source.py:34-39`: `min_content_length` field with description "If feed content is shorter than this, scrape the article page"
   - Referenced in RSSAdapter but not documented in adapters.md
   - Priority: LOW

## Stale Content

1. **Source configuration example uses `listing` key but `WebConfig` field is `listing_url`**
   - Doc YAML example at line 223 shows `listing_url: "https://example.com/articles"` — correct
   - But `listing` is shown as a nested object (correct for `ListingConfig`)
   - No stale content found in this section
   - Priority: N/A

2. **No stale file references found** — all referenced files (`base.py`, `rss.py`, `api.py`, `web.py`, `session.py`) exist and contain the documented code
