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
        self.url_template = config['url']
        self.item_path = config.get('item_path', '$.items[*]')
        self.field_mappings = config.get('field_mappings', {})

    def fetch(self) -> list[dict]:
        # Supports pagination (cursor, offset, page)
        # Handles authentication (Bearer, API key headers)
        # Rate limiting compliance
        return self._fetch_page() or []
```

Features:
- JSONPath field extraction (`$.items[*]`, `$.data[*].title`)
- Pagination support (cursor, offset, page-based)
- Auth header injection (Bearer token, API key)
- Field mapping configuration

## Web Adapter (`web.py`)

Scrapes listing pages with CSS selectors:

```python
class WebAdapter(BaseSourceAdapter):
    def __init__(self, config: dict):
        self.listing_url = config['listing_url']
        self.item_css = config['item_css']
        self.field_selectors = config['field_selectors']

    def fetch(self) -> list[dict]:
        # Fetches listing URL
        # Optionally follows pagination links
        # Extracts items via CSS selectors
        return self._scrape_page(url)
```

Features:
- Listing URL scraping
- CSS selector-based extraction
- Pagination link following
- Link URL discovery

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

## Source Configuration

Sources are defined in `sources.yaml`:

```yaml
sources:
  - name: "Hacker News"
    type: "rss"
    url: "https://hnrss.org/frontpage"
    adapter_config:
      item_path: "entries"
      field_mappings:
        title: "title"
        url: "link"
        published: "published"

  - name: "TechCrunch"
    type: "api"
    url: "https://api.techcrunch.com/v1/articles"
    adapter_config:
      item_path: "$.articles[*]"
      auth_header: "Bearer token"

  - name: "Example Blog"
    type: "web"
    url: "https://example.com/articles"
    adapter_config:
      item_css: "article.post"
      field_selectors:
        title: "h2.title"
        url: "a::attr(href)"
```

## Error Handling

All adapters implement consistent error handling:

1. **Network errors**: Log and return empty list
2. **Parse errors**: Log and skip invalid items
3. **Rate limiting**: Respect `Retry-After` headers
4. **Source health**: Update `Source.consecutive_failures/successes`
