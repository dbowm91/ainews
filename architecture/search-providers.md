# Search Providers

The `services/search/` package provides web search and internal article search capabilities with multiple provider backends.

## Architecture

```
services/search/
├── __init__.py       # Provider registry, search_web(), get_search_provider()
├── base.py           # SearchResult dataclass, abstract base
├── duckduckgo.py     # DuckDuckGo provider (default/enabled)
├── google.py         # Google Custom Search (disabled, requires API key)
├── searxng.py        # SearxNG (disabled, self-hosted)
├── hybrid.py         # Hybrid FTS5 + vector similarity (enabled)
├── sqlite_fts.py     # SQLite FTS5 internal article search
└── session.py        # Search HTTP session management
```

## Provider Registry

```python
# services/search/__init__.py

def get_search_provider(provider_id: str = None) -> BaseSearchProvider:
    """Get search provider by ID. Falls back to default if not specified."""

def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search the web using the configured default provider."""

def get_article_search_provider() -> BaseSearchProvider:
    """Get provider for internal article search (Hybrid or SQLite FTS)."""
```

Providers are registered in `providers.yaml` under the `search` section.

## Provider Implementations

### DuckDuckGo (`duckduckgo.py`)

Default web search provider, no API key required:

```python
class DuckDuckGoProvider(BaseSearchProvider):
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

### Hybrid (`hybrid.py`)

Combines FTS5 full-text search with vector similarity:

```python
class HybridSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # 1. FTS5 search for keyword matches
        # 2. Vector similarity for semantic matches
        # 3. Score fusion and deduplication
        # 4. Return top results
```

| Property | Value |
|----------|-------|
| Status | **Enabled** |
| Components | SQLite FTS5 + sentence-transformers embeddings |
| Use Case | Internal article search |
| Embedding Model | `all-MiniLM-L6-v2` |

### Google (`google.py`)

Google Custom Search API (requires API key):

```python
class GoogleSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Uses Google Custom Search JSON API
        # Requires: GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_CX
        # Timeout: 20 seconds
```

| Property | Value |
|----------|-------|
| Status | Disabled |
| API Key | Required (`GOOGLE_SEARCH_API_KEY`) |
| Custom Engine | Required (`GOOGLE_SEARCH_CX`) |

### SearxNG (`searxng.py`)

Self-hosted metasearch engine:

```python
class SearxNGProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Queries self-hosted SearxNG instance
        # Requires: SEARXNG_BASE_URL
        # Timeout: 20 seconds
```

| Property | Value |
|----------|-------|
| Status | Disabled |
| Self-hosted | Yes |
| Config | `SEARXNG_BASE_URL` env var |

### SQLite FTS (`sqlite_fts.py`)

Internal full-text search over articles:

```python
class SQLiteFTSProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Uses SQLite FTS5 for full-text search
        # Searches: article titles and extracted text
        # Returns: matching articles with relevance ranking
```

| Property | Value |
|----------|-------|
| Status | Internal (for article search) |
| Engine | SQLite FTS5 |
| Scope | Article titles + content |

## SearchResult Dataclass

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""  # Provider name
    score: float = 0.0  # Relevance score
```

## Provider Selection

The default web search provider is configured in `providers.yaml`:

```yaml
search:
  default: duckduckgo
  providers:
    duckduckgo:
      enabled: true
    hybrid:
      enabled: true
    google:
      enabled: false
      api_key: "${GOOGLE_SEARCH_API_KEY}"
      cx: "${GOOGLE_SEARCH_CX}"
    searxng:
      enabled: false
      base_url: "${SEARXNG_BASE_URL}"
```

## Integration with Subagent

Search providers are exposed as subagent tools:

```python
# In services/subagent/tools.py
def _context_tool_search_web(query: str, max_results: int = 5) -> str:
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
| `services/search/__init__.py` | Provider registry, `search_web()`, `get_search_provider()` |
| `services/search/base.py` | `SearchResult` dataclass, abstract `BaseSearchProvider` |
| `services/search/duckduckgo.py` | DuckDuckGo provider (default) |
| `services/search/hybrid.py` | Hybrid FTS5 + vector search |
| `services/search/google.py` | Google Custom Search |
| `services/search/searxng.py` | SearxNG metasearch |
| `services/search/sqlite_fts.py` | SQLite FTS5 article search |
| `services/search/session.py` | HTTP session for search requests |
| `providers.yaml` | Search provider configuration |
| `services/subagent/tools.py` | Tool wrappers for search |
