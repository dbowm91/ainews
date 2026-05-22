# Adapters Module

The `adapters/` package contains infrastructure-specific code for fetching from different source types. **Adapters must NOT contain business logic and should NOT import from services**.

## Adapter Pattern

All adapters inherit from `BaseSourceAdapter` and are registered via the `@register_adapter` decorator:

```python
@register_adapter('rss')  # Registers in SOURCE_ADAPTERS registry
class RSSAdapter(BaseSourceAdapter):
    def fetch(self) -> list[dict]: ...
    def parse_item(self, item: dict) -> ArticleData: ...
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
    @abstractmethod
    def fetch(self) -> list[dict]:
        """Fetch raw data from source"""

    @abstractmethod
    def parse_item(self, item: dict) -> ArticleData:
        """Parse raw item into ArticleData"""

    def fetch_and_parse(self) -> list[ArticleData]:
        """Combined fetch + parse with error handling"""
```

### Registry

```python
SOURCE_ADAPTERS: dict[str, type[BaseSourceAdapter]] = {}

def register_adapter(source_type: str):
    """Decorator to register adapter in SOURCE_ADAPTERS registry"""
```

## RSS Adapter (`rss.py`)

Fetches RSS/Atom feeds using `feedparser`:

```python
class RSSAdapter(BaseSourceAdapter):
    def fetch(self) -> list[dict]:
        # Uses feedparser.parse()
        # Falls back to requests + BeautifulSoup for malformed feeds
        return self._fetch_feed(url) or self._scrape_feed(url)
```

Features:
- Feed validation and normalization
- Atom feed support
- Malformed feed fallback (HTTP + BeautifulSoup)
- Feed metadata extraction (title, description, language)

## API Adapter (`api.py`)

Fetches from REST APIs with JSONPath field extraction:

```python
class APIAdapter(BaseSourceAdapter):
    def __init__(self, config: dict):
        self.list_url = config['list_url']
        self.list_items_path = config.get('list_items_path')
        self.fields = config.get('fields', {})

    def fetch(self) -> list[dict]:
        # Handles authentication (Bearer token via auth_header or Authorization fallback)
        # Rate limiting compliance
        return self._fetch_page() or []
```

Features:
- JSONPath field extraction via `list_items_path` (e.g., `$.items[*]`, `$.data[*].title`)
- Item URL template for individual item fetching via `item_url`
- Auth header injection (Bearer token only — API key in custom headers NOT supported)
- Field mapping via `fields` dict
- Filter operations: `equals`, `min`, `exists` (no `contains`)

**Note:** API adapter pagination is implemented via `PaginationConfig` (same as Web adapter). Supports `next_link` (extract URL via JSONPath), `query_param` (increment page/offset), and `none` (disabled).

## Web Adapter (`web.py`)

Scrapes listing pages with CSS selectors:

```python
class WebAdapter(BaseSourceAdapter):
    def __init__(self, config: dict):
        self.listing_url = config['listing_url']
        self.listing = ListingConfig(**config['listing'])
        self.article = ArticleSelectors(**config['article'])

    def fetch(self) -> list[dict]:
        # Fetches listing URL
        # Optionally follows pagination links via next_link_selector
        # Extracts items via CSS selectors
        return self._scrape_listing(url)
```

Features:
- Single listing URL (not multiple start_urls)
- CSS selector-based extraction via `ListingConfig` and `ArticleSelectors`
- Pagination link following via `PaginationConfig`
- Link URL discovery
- Trafilatura content extraction with fallback to CSS selectors

## SSRF Protection

`session.py` provides safe redirect handling:

```python
class SSRFSafeRedirectHandler:
    """Custom redirect handler (not based on urllib HTTPRedirectHandler)"""
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        # Validates newurl against allowlist
        # Blocks javascript:, data:, and internal IP ranges
        # Logs blocked redirects
```

Blocklist patterns include internal IP ranges and the `javascript:` and `data:` URL schemes are blocked via scheme validation.

Blocked patterns:
- Internal IP ranges (10.x, 172.16-31.x, 192.168.x)
- Private hostnames and DNS rebinding attacks
- Non-http/https schemes (javascript:, data:, etc.) via scheme validation

## Session Ownership

Each adapter type manages HTTP sessions differently based on its requirements:

| Adapter | Session Type | Redirect Handler |
|---------|-------------|------------------|
| `RSSAdapter` | Own `requests.Session` | Own `SSRFSafeRedirectHandler` instance |
| `APIAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` |
| `WebAdapter` | Shared global session | Shared global `SSRFSafeRedirectHandler` |

**RSSAdapter** creates its own `requests.Session` with its own `SSRFSafeRedirectHandler` instance. This is intentional — RSS feeds have different session requirements (longer-lived connections, specific user agents) from API/Web adapters.

**APIAdapter** and **WebAdapter** share the global session from `get_crawl_session()` in `adapters/session.py`. They use the same `SSRFSafeRedirectHandler` instance for redirect counting across all requests.

The global session handler shares state per-request (via thread-local storage for redirect counting). This means redirect counting is reset per-request but the handler instance is shared across all adapter types.

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
