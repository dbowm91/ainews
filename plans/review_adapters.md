# Review: Adapters Module

**Reviewed:** 2026-05-31
**Source:** `architecture/adapters.md`
**Reviewer:** Subagent 2 (Adapter & Utils Layer)
**Status:** COMPLETE

---

## Verified Claims

All claims below were checked against actual code and confirmed correct.

### Base Source Adapter (`base.py`)
- `BaseSourceAdapter` abstract class with `__init__(self, source_config: SourceConfig)` — VERIFIED (`adapters/base.py:41`)
- Abstract method `fetch(self) -> list[Any]` — VERIFIED (`adapters/base.py:50-51`)
- Abstract method `parse_item(self, raw: Any) -> Optional[RawItem]` — VERIFIED (`adapters/base.py:53-54`)
- `fetch_and_parse(self) -> list[RawItem]` concrete method — VERIFIED (`adapters/base.py:56`)
- `match_topics(self, item: RawItem) -> RawItem` concrete method — VERIFIED (`adapters/base.py:81`)
- `_get_match_text(self, item: RawItem) -> str` override hook — VERIFIED (`adapters/base.py:90`)
- `_hash_ext_id(url, title)` static method — VERIFIED (`adapters/base.py:97-98`)
- `_truncate(text, limit)` static method with `MAX_TEXT_LENGTH` default — VERIFIED (`adapters/base.py:103-104`)
- `config_class: ClassVar = None` pattern — VERIFIED (`adapters/base.py:39`)
- `adapter_config` set from `config_class(**source_config.config)` — VERIFIED (`adapters/base.py:45-46`)
- Context manager `__enter__`/`__exit__` with `close()` — VERIFIED (`adapters/base.py:71-79`)

### Registry (`base.py`)
- `SOURCE_ADAPTERS: dict[str, type[BaseSourceAdapter]] = {}` — VERIFIED (`adapters/base.py:18-20`)
- `@register_adapter(source_type)` decorator — VERIFIED (`adapters/base.py:23-28`)
- `get_adapter_class(source_type)` with `KeyError` for unknown types — VERIFIED (`adapters/base.py:31-35`)

### Helper Functions (`base.py`)
- `_classify_topics(text)` exists as module-level function — VERIFIED (`adapters/base.py:109`)

### RSS Adapter (`rss.py`)
- Uses `feedparser.parse()` for feed parsing — VERIFIED (`adapters/rss.py:68`)
- `_validate_feed()` checks for entries — VERIFIED (`adapters/rss.py:17-21`)
- `_scrape_feed_fallback()` for malformed feeds (HTTP + BeautifulSoup) — VERIFIED (`adapters/rss.py:24-38`)
- `_scrape_feed_fallback()` does NOT call `validate_url_safe()` — VERIFIED (URL validated once in `fetch()` at line 59)
- Feed metadata extraction (title, description, language) — VERIFIED via feed.entries (`adapters/rss.py:71`)
- Creates own `requests.Session` with own `SSRFSafeRedirectHandler` — VERIFIED (`adapters/rss.py:47-52`)
- `close()` closes own session — VERIFIED (`adapters/rss.py:54-55`)
- `config_class = RSSConfig` — VERIFIED (`adapters/rss.py:43`)

### API Adapter (`api.py`)
- `list_url` in `APIConfig` schema — VERIFIED (`schemas/source.py:58`)
- `list_items_path` JSONPath extraction — VERIFIED (`schemas/source.py:60`, `adapters/api.py:43-44`)
- `fields` dict for field mapping — VERIFIED (`schemas/source.py:64`)
- `pagination` via `PaginationConfig` — VERIFIED (`schemas/source.py:67`)
- `filters` list with `equals`, `min`, `exists`, `contains` operations — VERIFIED (`adapters/api.py:205-221`)
- Auth header injection (Bearer token only) — VERIFIED (`adapters/api.py:175-179`)
- `PaginationConfig` types: `next_link`, `query_param`, `none` — VERIFIED (`schemas/source.py:52`)
- Shares global session from `get_crawl_session()` — VERIFIED (`adapters/api.py:22`)
- `close()` is no-op — VERIFIED (`adapters/api.py:25-26`)
- `config_class = APIConfig` — VERIFIED (`adapters/api.py:18`)

### Web Adapter (`web.py`)
- CSS selector-based extraction via `ListingConfig` and `ArticleSelectors` — VERIFIED (`schemas/source.py:74-86`)
- Link URL resolution via `base_url` with `urljoin()` — VERIFIED (`adapters/web.py:157,163`)
- Trafilatura content extraction with fallback — VERIFIED (`adapters/web.py:109-119`)
- Shares global session from `get_crawl_session()` — VERIFIED (`adapters/web.py:35`)
- `close()` is no-op — VERIFIED (`adapters/web.py:45-46`)
- `config_class = WebConfig` — VERIFIED (`adapters/web.py:31`)

### SSRF Protection (`session.py`)
- `SSRFSafeRedirectHandler.__call__(self, request, response, **kwargs)` signature — VERIFIED (`adapters/session.py:37`)
- Thread-local redirect counter via `_thread_local` — VERIFIED (`adapters/session.py:13,30-35`)
- `_max_redirects = 30` — VERIFIED (`adapters/session.py:27`)
- Blocks `javascript:` and `data:` schemes via `validate_url_safe()` — VERIFIED (delegated to `utils/url.py:validate_url_safe()`)
- `get_crawl_session()` with double-checked locking — VERIFIED (`adapters/session.py:60-78`)

### Session Ownership
- RSS: own session, own `SSRFSafeRedirectHandler` — VERIFIED (`adapters/rss.py:47-52`)
- API/Web: shared global session, shared `SSRFSafeRedirectHandler` — VERIFIED (`adapters/session.py:78`)
- API/Web `close()` are no-ops — VERIFIED (`adapters/api.py:25-26`, `adapters/web.py:45-46`)
- RSS `close()` closes own session — VERIFIED (`adapters/rss.py:54-55`)

### Adapter Constants vs Service Configuration
- `MAX_TEXT_LENGTH = 3000` in `base.py` — VERIFIED (`adapters/base.py:14`)
- `MIN_CONTENT_LENGTH = 200` in `web.py` — VERIFIED (`adapters/web.py:19`)
- `_max_redirects = 30` in `session.py` — VERIFIED (`adapters/session.py:27`)

### Source Configuration
- Sources defined in `sources.yaml` with `config` field (not `adapter_config`) — VERIFIED (`schemas/source.py:113`)
- Config validated against `RSSConfig`, `APIConfig`, or `WebConfig` via `ADAPTER_CONFIGS` — VERIFIED (`schemas/source.py:100-104,125-132`)

### Error Handling
- Adapters do NOT update `Source.consecutive_failures/successes` — VERIFIED (grep found zero matches in `adapters/`)
- Fixed exponential backoff for rate limiting: `2^attempt * 5 + jitter` — VERIFIED (`adapters/web.py:180`)

### Imports / Layering
- All adapter imports from `utils.url` (not `services.url`) — VERIFIED for `base.py`, `rss.py`, `api.py`, `web.py`, `session.py`
- No adapter imports from `services` — VERIFIED via grep

### File Inventory
- `base.py` — VERIFIED
- `rss.py` — VERIFIED
- `api.py` — VERIFIED
- `web.py` — VERIFIED
- `session.py` — VERIFIED
- `__init__.py` exports `APIAdapter`, `RSSAdapter`, `WebAdapter`, `get_adapter_class`, `SOURCE_ADAPTERS` — VERIFIED

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 86 | `_classify_topics(title: str, text: str = "") -> list[str]` | `adapters/base.py:109` — `def _classify_topics(text: str) -> list[str]:` (single parameter) | MEDIUM |
| 67 | `__exit__(self, *args) -> None:` | `adapters/base.py:74` — `def __exit__(self, *exc):` | LOW |
| 190 | `request_delay` applies **per-article**, not per-page | `adapters/web.py:171-172` — delay is in `_polite_get()` which is called for BOTH listing pages (line 142) and individual articles (line 61); delay applies per-HTTP-request | MEDIUM |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | WebAdapter `_scrape_listing` returns ALL article URLs across all pages with no limit. Combined with `fetch()` iterating all returned URLs, a paginated source with many pages could fetch an unbounded number of articles (limited only by `max_retries` failures). No `max_items` cap is applied during listing scrape. | `adapters/web.py:135-166` | MEDIUM | `_scrape_listing` accumulates all URLs from all pages, then `fetch()` (line 59) iterates all of them. Only `_polite_get` failures limit the count. No equivalent of APIAdapter's `cfg.max_items` check during listing. |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | WebAdapter `_scrape_listing` should apply `max_items` cap during link collection to prevent unbounded fetches on paginated sources. | reliability | P2 |
| 2 | WebAdapter `_polite_get` applies delay before every HTTP request including listing pages. Consider separating page-fetch delay from article-fetch delay for better rate limiting control. | performance | P3 |
| 3 | `APIAdapter._fetch_item()` fetches items sequentially (noted in code comment at line 169). Could benefit from ThreadPoolExecutor for large item counts. | performance | P3 |
| 4 | `_scrape_feed_fallback` in RSSAdapter doesn't validate individual item URLs — it trusts the feed content. Consider adding `validate_url_safe()` for extracted URLs. | security | P3 |
| 5 | RSSAdapter creates its own session per instance. If many RSS sources are crawled concurrently, this creates many connection pools. Consider sharing a session pool across RSSAdapter instances. | performance | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 86 | `_classify_topics(title: str, text: str = "")` signature | Function signature changed — now takes single `text` parameter | Update signature to `def _classify_topics(text: str) -> list[str]:` |
| 67 | `__exit__(self, *args) -> None:` | Code uses `*exc` not `*args` | Update to `__exit__(self, *exc) -> None:` |
| 190 | "applies **per-article**, not per-page" | Delay applies per-HTTP-request (both pages and articles) via `_polite_get()` | Rewrite to clarify: "The `request_delay_min`/`request_delay_max` configuration applies per HTTP request. Both listing page fetches and individual article fetches go through `_polite_get()`, so the delay is applied to each request." |

---

## Summary

- Verified: 48 claims
- Incorrect: 3 claims
- Bugs: 1 (MEDIUM: 1)
- Improvements: 5
- Stale items: 3

The adapters.md document is largely accurate. The three incorrect claims are all documentation errors (wrong function signature, wrong delay behavior description) rather than architectural misrepresentations. The most significant finding is the WebAdapter delay behavior description being misleading about per-article vs per-request scoping.
