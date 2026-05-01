# Search Providers

This document covers the search provider infrastructure in the AI news pipeline.

## Overview

Search providers enable web search functionality for the pipeline (primarily for research stages). They follow a common interface and support fallback chains, circuit breaking, and SSRF protection.

## Base Class

`BaseSearchProvider` in `services/search/base.py` defines the interface that all search providers must implement:

```python
class BaseSearchProvider(BaseProvider, abc.ABC):
    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...

    def health_check(self) -> dict[str, Any]: ...
```

### SearchResult Namedtuple

All providers return a list of `SearchResult` namedtuples:

```python
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""
```

### Health Check

The `health_check()` method returns a dict with:
- `provider`: The provider ID
- `status`: Status string ("ok", error message, or HTTP status)
- `latency_ms`: (optional) response latency
- `host`: (optional) for self-hosted providers like SearXNG

## Available Providers

### SearXNG (`services/search/searxng.py`)

Self-hosted meta-search engine that aggregates results from multiple search backends.

**Configuration** (`providers.yaml`):
```yaml
search:
  searxng:
    enabled: true
    host: "http://localhost:8888"
    categories: "general"
    engines: ""  # optional, comma-separated
    request_timeout: 15
    max_results: 10
```

**Features**:
- Most privacy-friendly option (self-hosted)
- Uses `/healthz` endpoint for health checks
- Validates search URL before calling

### Google (`services/search/google.py`)

Uses Google Custom Search API.

**Configuration** (`providers.yaml`):
```yaml
search:
  google:
    enabled: true
    api_key: "${GOOGLE_API_KEY}"
    cse_id: "${GOOGLE_SEARCH_ENGINE_ID}"
    base_url: "https://www.googleapis.com/customsearch/v1"
    request_timeout: 15
    max_results: 10
```

**Environment Variables**:
- `GOOGLE_API_KEY`: Google API key with Custom Search API enabled
- `GOOGLE_SEARCH_ENGINE_ID`: Google Search Engine ID (CSE)

### DuckDuckGo (`services/search/duckduckgo.py`)

Uses the `duckduckgo_search` library. No API key required.

**Configuration** (`providers.yaml`):
```yaml
search:
  duckduckgo:
    enabled: true
    request_timeout: 15
    max_results: 10
```

**Features**:
- No API key needed
- Uses `DDGS().text()` for text search with 15s timeout

## SSRF Validation

All search providers validate result URLs against private IP ranges using `validate_url_safe()` from `services/url.py` before returning results. This prevents SSRF attacks through search results.

Implementation locations:
- **SearXNG**: Validates `search_url` at `services/search/searxng.py:21`
- **Google**: Validates `base_url` at `services/search/google.py:27` (pre-flight)
- **DuckDuckGo**: Validates each result URL at `services/search/duckduckgo.py:26`

If a URL fails validation, it is logged and skipped. URLs that raise `UnsafeURLError` are not included in results.

## Circuit Breaker

Search providers use the shared circuit breaker from `services/circuit_breaker.py`. The circuit breaker:
- Tracks failures in a sliding window (120 seconds by default)
- Opens after 5 failures (configurable)
- Transitions to half-open after 60 seconds
- Allows 1 probe call in half-open state

Usage in providers:
```python
from services.circuit_breaker import get_breaker

breaker = get_breaker(f"search_{self.provider_id}")
if not breaker.can_execute():
    return []

try:
    results = self._do_search(query, max_results)
    breaker.record_success()
    return results
except Exception as e:
    breaker.record_failure()
    raise
```

## Provider Selection

### Get Single Provider

```python
from services.search import get_search_provider

provider = get_search_provider("google")  # specific provider
provider = get_search_provider()  # default from config
```

### Get with Fallback Chain

```python
from services.search import get_search_provider_with_fallback

provider = get_search_provider_with_fallback()  # uses fallback chain
```

The fallback chain is managed by `ProviderManager` in `services/provider_base.py`. Configuration in `providers.yaml` determines the primary provider and fallback order.

### Configuration Structure

In `providers.yaml`, define the search section:

```yaml
search:
  provider: "searxng"
  fallback:
    - "duckduckgo"
    - "google"
  searxng:
    enabled: true
    # ... provider-specific config
```

## Backward Compatibility

The `search_web()` function provides a simple interface:

```python
from services.search import search_web

results = search_web("AI news", max_results=5)
# Returns list of SearchResult namedtuples
```

## Known Issues

### Fixed Issues

- **Google health_check() placement** (wave1_3): The `health_check()` method was originally defined at module level in `services/search/google.py`, outside the class. This has been fixed — it's now properly defined inside `GoogleSearchProvider`.

- **DuckDuckGo SSRF validation** (wave4_1): DuckDuckGo results were not being validated against private IP ranges. This has been fixed — each result URL now goes through `validate_url_safe()`.

### Design Considerations

- All providers use `ThreadPoolExecutor` for non-blocking I/O (20s timeout per search)
- Providers return empty list on failure rather than raising exceptions
- Health check implementations vary slightly between providers (SearXNG checks `/healthz`, Google makes a test API call, DuckDuckGo does a trivial search)