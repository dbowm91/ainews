# Search Providers

The `services/search/` package provides two separate search subsystems: **web search** (external sources) and **article search** (internal database-backed). Each has its own abstract base class and provider registry.

## Two Separate Class Hierarchies

```
┌─────────────────────────────────────────────────────────────┐
│  Web Search (external)                                      │
│  BaseSearchProvider (base.py)                               │
│  ├── DuckDuckGoSearchProvider (duckduckgo.py)               │
│  ├── GoogleSearchProvider (google.py)                       │
│  └── SearXNGSearchProvider (searxng.py)                     │
│  Registry: @register_search_provider                        │
│  Returns: list[SearchResult] (title, url, snippet, source)  │
│  Entry: search_web(), get_search_provider()                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Article Search (internal/database)                         │
│  SearchProvider (base.py)                                   │
│  ├── SQLiteFTSProvider (sqlite_fts.py)                      │
│  └── HybridSearchProvider (hybrid.py)                       │
│  Registry: @register_db_search_provider                     │
│  Returns: list[dict] with 'id' and 'rank' keys              │
│  Entry: get_article_search_provider(), get_db_search_provider() │
└─────────────────────────────────────────────────────────────┘
```

## Architecture

```
services/search/
├── __init__.py       # search_web(), get_search_provider(), get_article_search_provider()
├── base.py           # SearchResult dataclass, BaseSearchProvider, SearchProvider
├── duckduckgo.py     # DuckDuckGo provider (default/enabled)
├── google.py         # Google Custom Search (disabled, requires API key)
├── searxng.py        # SearxNG (disabled, self-hosted)
├── hybrid.py         # Hybrid FTS5 + vector similarity (enabled)
├── sqlite_fts.py     # SQLite FTS5 internal article search
└── session.py        # Shared crawl session (SSRFSafeRedirectHandler) for web scraping
```

## Web Search Providers

### Base Class

```python
# services/search/base.py
class BaseSearchProvider(BaseProvider, abc.ABC):
    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...
```

Registered via `@register_search_provider` into a `ProviderManager("search")` instance.

**Note:** `BaseSearchProvider` defines the abstract `search()` method. The `SearchProvider` class (for article search) is a separate abstract base class with its own `search()` signature.

### Entry Points

```python
# services/search/__init__.py
def get_search_provider(provider_id: str = None) -> BaseSearchProvider:
    """Get web search provider by ID. Falls back to default if not specified."""

def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search the web using the configured default provider."""
```

### DuckDuckGo (`duckduckgo.py`)

Default web search provider, no API key required:

```python
@register_search_provider("duckduckgo")
class DuckDuckGoSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Uses duckduckgo_search library
        # Returns: title, url, snippet for each result
        # Timeout: 20 seconds (via ThreadPoolExecutor)
```

| Property | Value |
|----------|-------|
| Status | **Enabled** (default) |
| API Key | Not required |
| Rate Limit | Built-in polite delays |
| Timeout | 20 seconds |

### Google (`google.py`)

Google Custom Search API (requires API key):

```python
@register_search_provider("google")
class GoogleSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Uses Google Custom Search JSON API
        # Requires: GOOGLE_API_KEY, GOOGLE_CSE_ID
        # Timeout: 20 seconds
```

| Property | Value |
|----------|-------|
| Status | Disabled |
| API Key | Required (`GOOGLE_API_KEY`) |
| Custom Engine | Required (`GOOGLE_CSE_ID`) |

### SearxNG (`searxng.py`)

Self-hosted metasearch engine:

```python
@register_search_provider("searxng")
class SearXNGSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Queries self-hosted SearxNG instance
        # Requires: host config in providers.yaml
        # Timeout: 20 seconds
```

| Property | Value |
|----------|-------|
| Status | Disabled |
| Self-hosted | Yes |
| Config | `host` field in `providers.yaml` |

## Article Search Providers

### Base Class

```python
# services/search/base.py
class SearchProvider(abc.ABC):
    @abc.abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        """Search articles using full-text search.
        Returns: List of dicts with at least 'id' and 'rank' keys."""

    @abc.abstractmethod
    def index_article(self, article) -> None: ...

    @abc.abstractmethod
    def delete_article(self, article_id: int) -> None: ...

    @abc.abstractmethod
    def search_admin(self, query: str, limit: int = 1000, **kwargs) -> list[int]: ...

    def hybrid_search(self, query, limit=10, vector_weight=0.5, **kwargs) -> list[dict]:
        """Default falls back to standard search. Subclasses override for true hybrid."""
        return self.search(query, limit=limit, **kwargs)
```

Registered via `@register_db_search_provider` into a `SearchProviderManager` instance (separate from the web search `ProviderManager`).

### Entry Points

```python
# services/search/__init__.py
def get_article_search_provider() -> SearchProvider:
    """Get the configured database search provider (e.g., SQLite FTS5)."""
```

```python
# services/search/base.py
def get_db_search_provider(name: str = "sqlite_fts") -> SearchProvider:
    """Get or create the configured database search provider instance."""
```

### SQLite FTS (`sqlite_fts.py`)

Internal full-text search over articles:

```python
@register_db_search_provider("sqlite_fts")
class SQLiteFTSProvider(SearchProvider):
    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        # Uses SQLite FTS5 for full-text search
        # Searches: article titles and extracted text
        # Returns: list of dicts with 'id' and 'rank' keys
```

| Property | Value |
|----------|-------|
| Status | Internal (for article search) |
| Engine | SQLite FTS5 |
| Scope | Article titles + content |

### Hybrid (`hybrid.py`)

Combines FTS5 full-text search with vector similarity:

```python
@register_db_search_provider("hybrid")
class HybridSearchProvider(SearchProvider):
    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        # Delegates to SQLiteFTSProvider for FTS-only search

    def hybrid_search(self, query, limit=10, vector_weight=0.5, **kwargs) -> list[dict]:
        # 1. FTS5 search for keyword matches
        # 2. Vector similarity for semantic matches
        # 3. Score fusion and deduplication
        # 4. Return top results
```

| Property | Value |
|----------|-------|
| Status | **Enabled** (for article search, not web search) |
| Components | SQLite FTS5 + sentence-transformers embeddings |
| Use Case | Internal article search (hybrid similarity + FTS5) |
| Embedding Model | `all-MiniLM-L6-v2` |

## SearchResult Dataclass

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""  # Provider name
```

## Provider Selection

The default web search provider is configured in `providers.yaml`:

```yaml
search_providers:
  - id: duckduckgo
    type: duckduckgo
    enabled: true
    config: {}

  - id: google
    type: google
    enabled: false
    config:
      api_key: "${GOOGLE_API_KEY}"
      cse_id: "${GOOGLE_CSE_ID}"

  - id: searxng
    type: searxng
    enabled: false
    config:
      host: "http://localhost:8888"

  - id: hybrid
    type: hybrid
    enabled: true
    config: {}  # FTS5 + vector similarity search

default_search_provider: duckduckgo
```

## Integration with Subagent

Search providers are exposed as subagent tools:

```python
# In services/subagent/tools.py
def _search_web(query: str, max_results: int = 5) -> str:
    """Web search via configured search provider."""
    results = search_web(query, max_results)
    return format_search_results(results)
```

## Integration with Pipeline

- **Research stage**: Uses `search_web()` for web research context
- **Article search**: Uses `get_article_search_provider()` for related article lookup
- **Subagent tools**: `web_search` and `search_articles` tools use providers

## Key Files

| File | Purpose |
|------|---------|
| `services/search/__init__.py` | Entry points: `search_web()`, `get_search_provider()`, `get_article_search_provider()` |
| `services/search/base.py` | `SearchResult` dataclass, abstract `BaseSearchProvider` (web), abstract `SearchProvider` (article), both registries |
| `services/search/duckduckgo.py` | DuckDuckGo web search provider (default) |
| `services/search/google.py` | Google Custom Search web provider |
| `services/search/searxng.py` | SearxNG web metasearch provider |
| `services/search/hybrid.py` | Hybrid FTS5 + vector article search provider |
| `services/search/sqlite_fts.py` | SQLite FTS5 article search provider |
| `services/search/session.py` | HTTP session for web search requests |
| `providers.yaml` | Search provider configuration |
| `services/subagent/tools.py` | Tool wrappers for search |
