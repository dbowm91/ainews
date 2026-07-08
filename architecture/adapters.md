# Adapters Module

The `adapters/` package contains infrastructure-specific code for fetching from different source types. **Adapters must NOT contain business logic and should NOT import from services**.

## Adapter Pattern

All adapters inherit from `BaseSourceAdapter` and are registered via the `@register_adapter` decorator:

```python
@register_adapter('rss')  # Registers in SOURCE_ADAPTERS registry
class RSSAdapter(BaseSourceAdapter):
    def fetch(self) -> list[Any]: ...
    def parse_item(self, raw: Any) -> Optional[RawItem]: ...
```

## File Inventory

| File | Adapter | Purpose |
|------|---------|---------|
| `base.py` | `BaseSourceAdapter` | Abstract base with fetch/parse methods; registry decorator |
| `rss.py` | `RSSAdapter` | RSS/Atom feed parsing via feedparser + BeautifulSoup |
| `api.py` | `APIAdapter` | REST API fetching with JSONPath field extraction |
| `web.py` | `WebAdapter` | Web page scraping with CSS selectors |
| `session.py` | `SSRFSafeRedirectHandler` | SSRF protection for redirects |

## Base Source Adapter

```python
class BaseSourceAdapter(ABC):
    def __init__(self, source_config: SourceConfig):
        self.source_config = source_config
        self.source_id = source_config.id
        self.topic_config = source_config.topics
        if self.config_class and source_config.config:
            self.adapter_config = self.config_class(**source_config.config)
        else:
            self.adapter_config = None

    @abstractmethod
    def fetch(self) -> list[Any]:
        """Fetch raw data from source"""

    @abstractmethod
    def parse_item(self, raw: Any) -> Optional[RawItem]:
        """Parse raw item into RawItem"""

    def fetch_and_parse(self) -> list[RawItem]:
        """Combined fetch + parse with error handling"""

    def match_topics(self, item: RawItem) -> RawItem:
        """Match item against configured topics"""

    def _get_match_text(self, item: RawItem) -> str:
        """Build text for topic matching. Override for custom matching."""

    @staticmethod
    def _hash_ext_id(url: str = None, title: str = None) -> str:
        """Generate a stable external ID from URL or title."""

    @staticmethod
    def _truncate(text: Optional[str], limit: int = MAX_TEXT_LENGTH) -> Optional[str]:
        """Truncate text to limit, returning None for empty input."""

    def __enter__(self) -> 'BaseSourceAdapter':
        """Context manager support"""

    def __exit__(self, *exc) -> None:
        """Context manager cleanup"""
```

### Registry

```python
SOURCE_ADAPTERS: dict[str, type[BaseSourceAdapter]] = {}

def register_adapter(source_type: str):
    """Decorator to register adapter in SOURCE_ADAPTERS registry"""

def get_adapter_class(source_type: str) -> type[BaseSourceAdapter]:
    """Get adapter class by source type"""
```

### Helper Functions

```python
def _classify_topics(text: str) -> list[str]:
    """Classify article topics based on title and text content.
    Module-level function (not a class method) to avoid layering violations.
    """
```

## RSS Adapter (`rss.py`)

Fetches RSS/Atom feeds using `feedparser`:

```python
class RSSAdapter(BaseSourceAdapter):
    def fetch(self) -> list[Any]:
        # Validates feed URL via validate_url_safe()
        # Fetches feed with feedparser.parse()
        # Falls back to _scrape_feed_fallback() for malformed feeds
        cfg = self.adapter_config
        validate_url_safe(cfg.feed_url)
        # ...
        if not _validate_feed(feed):
            return _scrape_feed_fallback(cfg.feed_url, self._session, cfg.request_timeout)
        return feed.entries[: cfg.max_items]
```

Features:
- Feed validation and normalization
- Atom feed support
- Malformed feed fallback (HTTP + BeautifulSoup)
- Feed metadata extraction (title, description, language)

**Note:** `_scrape_feed_fallback()` is a standalone function that does NOT call `validate_url_safe()` — the URL is validated once in `fetch()` before any HTTP requests.

## API Adapter (`api.py`)

Fetches from REST APIs with JSONPath field extraction:

```python
class APIAdapter(BaseSourceAdapter):
    def __init__(self, source_config: SourceConfig):
        self.source_config = source_config
        self._session = get_crawl_session()

    def fetch(self) -> list[Any]:
        # Validates list URL via validate_url_safe()
        # Handles authentication (Bearer token via auth_header or Authorization fallback)
        # Rate limiting compliance
        # Pagination via next_link or query_param
        cfg = self.adapter_config
        validate_url_safe(cfg.list_url)
        # ...
```

Features:
- JSONPath field extraction via `list_items_path` (e.g., `$.items[*]`, `$.data[*].title`)
- Item URL template for individual item fetching via `item_url`
- Auth header injection (Bearer token only — API key in custom headers NOT supported)
- Field mapping via `fields` dict
- Filter operations: `equals`, `min`, `exists`, `contains`

**Note:** API adapter pagination uses `PaginationConfig` (same schema as Web adapter) with `next_link` (extract URL via JSONPath), `query_param` (increment page/offset), and `none` (disabled). Implementation differs from Web adapter: API adapter fetches all pages in `fetch()` while Web adapter uses recursive link following.

## Web Adapter (`web.py`)

Scrapes listing pages with CSS selectors:

```python
class WebAdapter(BaseSourceAdapter):
    def __init__(self, source_config: SourceConfig):
        self.source_config = source_config
        self._session = get_crawl_session()

    def fetch(self) -> list[Any]:
        # Fetches listing URL
        # Optionally follows pagination links via next_link_selector
        # Extracts items via CSS selectors
        return self._scrape_listing(url)
```

Features:
- Single listing URL (not multiple start_urls)
- CSS selector-based extraction via `ListingConfig` and `ArticleSelectors`
- Pagination link following via `PaginationConfig`
- Link URL resolution via `base_url` (used with `urljoin()` at `adapters/web.py:160,166` to resolve relative hrefs)
- Content extraction: CSS selectors first, then trafilatura if body is too short or missing

## SSRF Protection

`session.py` provides safe redirect handling:

```python
class SSRFSafeRedirectHandler:
    """Custom redirect handler (not based on urllib HTTPRedirectHandler)"""
    def __call__(self, request, response, **kwargs):
        # Validates newurl against allowlist
        # Blocks javascript:, data:, and internal IP ranges
        # Logs blocked redirects
```

Blocklist patterns include internal IP ranges and the `javascript:` and `data:` URL schemes are blocked via scheme validation.

**Interface Verification:** The `SSRFSafeRedirectHandler.__call__` signature is `(self, request, response, **kwargs)`. While this differs from the `requests.Session.redirect_handler` expected interface of `(self, request, response)`, it has been verified to work correctly in practice with the `requests` library (tested 2026-05-22). The `**kwargs` parameter absorbs any additional arguments passed by newer requests versions.

## WebAdapter Request Delay

The `request_delay_min`/`request_delay_max` configuration in `WebConfig` applies **per HTTP request**. Both listing page fetches and individual article fetches go through `_polite_get()`, so the delay is applied to each request. This means paginated sources accumulate delays across both page loads and article fetches.

## Session Ownership

Each adapter type manages HTTP sessions differently based on its requirements:

| Adapter | Session Type | Redirect Handler |
|---------|-------------|------------------|
| `RSSAdapter` | Own `requests.Session` | Own `SSRFSafeRedirectHandler` instance |
| `APIAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` |
| `WebAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` |

**RSSAdapter** creates its own `requests.Session` with its own `SSRFSafeRedirectHandler` instance. This is intentional — RSS feeds have different session requirements (longer-lived connections, specific user agents) from API/Web adapters.

**APIAdapter** and **WebAdapter** share the global session from `get_crawl_session()` in `adapters/session.py`. They use the same `SSRFSafeRedirectHandler` instance for redirect counting across all requests.

**Important:** `APIAdapter` and `WebAdapter` do NOT close the shared session in their `close()` methods — they implement `close()` as no-ops. This prevents closing the global shared session which would break other adapters. `RSSAdapter` creates its own session and therefore its `close()` method correctly closes its own session.

The global session handler shares state per-request (via thread-local storage for redirect counting). This means redirect counting is reset per-request but the handler instance is shared across all adapter types.

The `SSRFSafeRedirectHandler` redirect validation is tested in `tests/test_services_search_session.py` (20+ tests covering count tracking, thread-local storage, UnsafeURLError propagation, and edge cases).

## Adapter Constants vs Service Configuration

Adapters use **hardcoded constants** (e.g., `MAX_TEXT_LENGTH = 3000` in `base.py`, `MIN_CONTENT_LENGTH = 200` in `web.py`, `_max_redirects = 30` in `session.py`), while services use **configurable values** from Flask config or environment variables. This is intentional:

- **Adapters** are pure infrastructure code that must not depend on Flask app context or complex configuration loading. Hardcoded constants ensure adapters remain simple, testable, and decoupled from the application layer.
- **Services** have access to Flask config, environment variables, and `get_config_with_default()` for Celery-safe access. They can afford configuration complexity because they operate within the application context.

## Source Configuration

Sources are defined in `sources.yaml`:

```yaml
sources:
  - name: "Hacker News"
    type: "rss"
    url: "https://hnrss.org/frontpage"
    config:
      feed_url: "https://hnrss.org/frontpage"
      max_items: 50

  - name: "TechCrunch"
    type: "api"
    config:
      list_url: "https://api.techcrunch.com/v1/articles"
      list_items_path: "$.articles[*]"
      api_key: "${TC_API_KEY}"
      auth_header: "Authorization"

  - name: "Example Blog"
    type: "web"
    config:
      base_url: "https://example.com"
      listing_url: "https://example.com/articles"
      listing:
        card_selector: "article.post"
        link_selector: "a::attr(href)"
      article:
        title_selector: "h2.title"
        body_selector: "div.content"
```

**Note:** The `config` field name is used in `SourceConfig`, not `adapter_config`. The config is validated against `RSSConfig`, `APIConfig`, or `WebConfig` based on source type.

## Error Handling

All adapters implement consistent error handling:

1. **Network errors**: Log and return empty list
2. **Parse errors**: Log and skip invalid items
3. **Rate limiting**: Fixed exponential backoff (2^attempt * 5 + jitter), NOT reading Retry-After header
4. **Source health**: Adapters do NOT update `Source.consecutive_failures/successes` — this is handled by `services/crawling.py` after adapter returns
