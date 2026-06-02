# Search Providers Architecture Review

## Summary

The `architecture/search-providers.md` document is **largely accurate** with minor discrepancies. The two-class hierarchy (BaseSearchProvider for web, SearchProvider for article) is correctly documented. All five search providers exist and are properly registered. A few discrepancies were found: the `search_articles` subagent tool uses direct SQL LIKE queries instead of the SearchProvider abstraction, and the YAML example is structurally correct but semantically confusing.

---

## Verified Claims

### Two Separate Class Hierarchies

- **BaseSearchProvider** (`services/search/base.py:18`) - abstract base for external web search
- **SearchProvider** (`services/search/base.py:43`) - abstract base for internal database-backed article search
- Both have distinct registries: `@register_search_provider` (base.py:31) and `@register_db_search_provider` (base.py:126)

### Web Search Providers

| Provider | File | Registration | Status |
|----------|------|--------------|--------|
| DuckDuckGoSearchProvider | `services/search/duckduckgo.py:45` | `@register_search_provider("duckduckgo")` | Enabled (default) |
| GoogleSearchProvider | `services/search/google.py:58` | `@register_search_provider("google")` | Disabled |
| SearXNGSearchProvider | `services/search/searxng.py:58` | `@register_search_provider("searxng")` | Disabled |

### Article Search Providers

| Provider | File | Registration | Status |
|----------|------|--------------|--------|
| SQLiteFTSProvider | `services/search/sqlite_fts.py:52` | `@register_db_search_provider("sqlite_fts")` | Internal |
| HybridSearchProvider | `services/search/hybrid.py:97` | `@register_db_search_provider("hybrid")` | Enabled |

### SearchResult Dataclass

```python
# services/search/base.py:10-15
@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""
```

### Provider Registration Decorators

- `@register_search_provider` - exported at `services/search/base.py:31`
- `@register_db_search_provider` - exported at `services/search/base.py:126`

### Hybrid Search Implementation

The `HybridSearchProvider` (`services/search/hybrid.py:97`) correctly implements:
- FTS5 search via internal `SQLiteFTSProvider` (`hybrid.py:102`)
- Vector similarity via `sentence-transformers` (`services/embeddings.py`)
- `cosine_similarity()` function (`hybrid.py:43-66`)
- `reciprocal_rank_fusion()` function (`hybrid.py:69-94`)
- Score combination with `vector_weight` parameter (`hybrid.py:256-321`)
- Embedding model: `all-MiniLM-L6-v2` (verified via `services/embeddings.py`)

### Entry Points

| Function | Location | Correct |
|----------|----------|---------|
| `search_web()` | `services/search/__init__.py:45` | ✅ |
| `get_search_provider()` | `services/search/__init__.py:35` | ✅ |
| `get_article_search_provider()` | `services/search/__init__.py:57` | ✅ |
| `get_db_search_provider()` | `services/search/base.py:114,126` | ✅ |

### DeepSeek NOT a Search Provider

Confirmed: No DeepSeek search provider exists in `services/search/`. DeepSeek only appears as an LLM provider regex pattern (`r"\bdeepseek\b"`) in `services/trend_detector.py` and as an LLM provider config in `providers.yaml:35-42`.

### File Structure

All files listed in the architecture document exist:
- `services/search/__init__.py` ✅
- `services/search/base.py` ✅
- `services/search/duckduckgo.py` ✅
- `services/search/google.py` ✅
- `services/search/searxng.py` ✅
- `services/search/hybrid.py` ✅
- `services/search/sqlite_fts.py` ✅
- `services/search/session.py` ✅

---

## Discrepancies Found

### 1. `search_articles` Tool Uses SQL LIKE Instead of SearchProvider

- **Claim**: "`search_articles` tools use providers" (architecture/search-providers.md:272)
- **Reality**: The subagent tool `_context_tool_search_articles` (`services/subagent/tools.py:127-142`) uses direct SQL `ILIKE` query on `Article.original_title`, NOT the `SearchProvider` abstraction
- **Severity**: Minor
- **Location**: `services/subagent/tools.py:127-142`
- **Suggested fix**: Update documentation to note that `search_articles` subagent tool uses direct SQL query for simplicity, while programmatic article search uses `get_article_search_provider()`

### 2. YAML Config Example Has Semantic Confusion

- **Claim**: The YAML example (`architecture/search-providers.md:228-254`) shows `hybrid` listed under `search_providers` alongside `duckduckgo`, `google`, `searxng`
- **Reality**: The `hybrid` entry is correctly placed under `search_providers` (all article search providers are configured there), but it's confusing because `hybrid` is an article search provider, not a web search provider. The web search providers and article search providers share the same `search_providers` config section in `providers.yaml`
- **Severity**: Minor (technically correct but potentially misleading)
- **Location**: `providers.yaml:146-149`, `architecture/search-providers.md:248-251`
- **Suggested fix**: Add clarifying comment in the YAML example that `hybrid` is an article search provider, or clarify in the doc that `search_providers` YAML section contains both web and article providers

### 3. Missing `get_search_provider_with_fallback()` in Documentation

- **Claim**: Entry points listed are `search_web()`, `get_search_provider()`, `get_article_search_provider()`
- **Reality**: `get_search_provider_with_fallback()` (`services/search/__init__.py:41-42`) also exists but is not documented
- **Severity**: Minor (internal function, but still an entry point)
- **Location**: `services/search/__init__.py:41-42`
- **Suggested fix**: Either document `get_search_provider_with_fallback()` or mark it as internal

---

## Bugs Identified

No bugs found. All providers are correctly registered and functional.

---

## Improvement Opportunities

### 1. Inconsistent Article Search Integration

- **Improvement**: The `_context_tool_search_articles` in subagent tools uses direct SQL LIKE query, while `search_articles()` function in `services/search/hybrid.py:338` uses the proper SearchProvider abstraction
- **Location**: `services/subagent/tools.py:127-142`
- **Benefit**: Consistent use of SearchProvider abstraction would allow plugging in different article search backends (FTS5, Hybrid) without code changes

### 2. `search_articles` Function in hybrid.py Not Exposed via __init__.py

- **Improvement**: `search_articles()` function exists at `services/search/hybrid.py:338` but is not exported from `services/search/__init__.py`
- **Location**: `services/search/hybrid.py:338`, `services/search/__init__.py`
- **Benefit**: Would provide a proper public API for article search using the HybridSearchProvider

### 3. Session Handler Not Used by DuckDuckGo

- **Improvement**: DuckDuckGo provider uses `duckduckgo_search` library's internal HTTP client directly (`duckduckgo.py:24`), while Google and SearXNG use the shared `get_session()` from `services/search/session.py`
- **Location**: `services/search/duckduckgo.py:24`, `services/search/google.py:27-28`, `services/search/searxng.py:20-21`
- **Benefit**: Consistent session management with SSRFSafeRedirectHandler protection across all web search providers

---

## Stale Items Found

1. The document lists `get_db_search_provider()` as an entry point but the primary public API is `get_article_search_provider()` (which calls `get_db_search_provider`). This is technically correct but could be clearer.

2. The architecture diagram shows "Entry: get_article_search_provider(), get_db_search_provider()" but `get_db_search_provider` is not exported from `__init__.py` - it's only in `base.py`. Only `get_article_search_provider()` is in the public `__init__.py`.

---

## Recommendations

1. **Low Priority**: Update documentation to clarify that the `search_articles` subagent tool uses direct SQL for simplicity, while programmatic access should use `get_article_search_provider()`

2. **Low Priority**: Consider exporting `search_articles()` from `services/search/__init__.py` if it's meant to be a public API

3. **Low Priority**: Add clarification that `hybrid` is an article search provider in the YAML example to avoid confusion about its role in the `search_providers` section

4. **Informational**: The DuckDuckGo provider's use of its own HTTP client (via `duckduckgo_search` library) bypasses the SSRFSafeRedirectHandler - this is a known limitation when using third-party libraries