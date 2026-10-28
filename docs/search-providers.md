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

Search providers are configured under the top-level `search_providers:` key in
`providers.yaml` (loaded by `schemas/search.py`). Each entry has the same shape
as the LLM providers (`id`, `type`, `enabled`, `config`), and the active
provider is selected by the `default_search_provider:` key.

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

  - id: eggsearch
    type: eggsearch
    enabled: false
    config:
      config_path: null # Set an explicit absolute path only after qualified SDK installation.

  - id: hybrid
    type: hybrid
    enabled: true
    config: {}  # FTS5 + vector similarity search

default_search_provider: duckduckgo
```

### DuckDuckGo (`services/search/duckduckgo.py`)

Uses the `duckduckgo_search` library. No API key required.

**Configuration** (`providers.yaml`):
```yaml
search_providers:
  - id: duckduckgo
    type: duckduckgo
    enabled: true
    config: {}
```

**Features**:
- No API key needed
- Uses `DDGS().text()` for text search

### Google (`services/search/google.py`)

Uses Google Custom Search API.

**Configuration** (`providers.yaml`):
```yaml
search_providers:
  - id: google
    type: google
    enabled: true
    config:
      api_key: "${GOOGLE_API_KEY}"
      cse_id: "${GOOGLE_CSE_ID}"
```

**Environment Variables**:
- `GOOGLE_API_KEY`: Google API key with Custom Search API enabled
- `GOOGLE_CSE_ID`: Google Custom Search Engine ID (CSE)

### SearXNG (`services/search/searxng.py`)

Self-hosted meta-search engine that aggregates results from multiple search backends.

**Configuration** (`providers.yaml`):
```yaml
search_providers:
  - id: searxng
    type: searxng
    enabled: true
    config:
      host: "http://localhost:8888"
```

**Features**:
- Most privacy-friendly option (self-hosted)
- Uses `/healthz` endpoint for health checks
- Validates search URL before calling

### Eggsearch (`services/search/eggsearch.py`)

Eggsearch is an **opt-in, qualification-only** external metasearch adapter. Version `0.4.4` is published and pinned as an optional extra, not a default dependency: install it with `uv sync --extra eggsearch` or `pip install '.[eggsearch]'`. It does not launch an MCP sidecar, and the Python binding is imported lazily. The provider remains disabled in sample configuration. Do not enable it for production until the qualification record's outstanding security and rollout gates pass. For isolated testing, provide a readable absolute `config_path` and explicitly enable the provider in `providers.yaml`; do not use a working-directory-relative or developer-local path. Search failures are represented by `search_web_detailed()` as `failed`; valid empty responses remain `empty`. The compatibility `search_web()` API continues to return lists.

Eggsearch result cards are structured data and undergo HTTP(S)/SSRF URL validation. Provider IDs and source IDs are preserved in `SearchResult.metadata`; publication timestamps are preserved only when timezone-aware and parseable. Requested freshness is not proof of enforcement. Eggsearch's own `web_fetch` is not used; source hydration must continue through `services/safe_fetch.py`.

**Release status:** published 0.4.4 ARM64/x86_64 artifacts and tool fingerprint are verified locally. The macOS symlink-containment test failure, full platform/clean-host matrix, runtime fallback, and live corpus A/B/canary remain unqualified. Keep Eggsearch disabled until the linked roadmap and qualification record show the gates passed.

### Hybrid (`services/search/hybrid.py`)

Internal full-text and vector search across published articles (SQLite FTS5 + vector similarity).
Always available with no external API key.

```yaml
search_providers:
  - id: hybrid
    type: hybrid
    enabled: true
    config: {}
```

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

In `providers.yaml`, search providers are defined under the top-level `search_providers:` key:

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

default_search_provider: duckduckgo
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