# Search Providers Documentation Review

**Document:** `architecture/search-providers.md`
**Review Date:** 2026-05-29

---

## Verified Claims

| Claim | Location | Status |
|-------|----------|--------|
| All search provider files in `services/search/`: `duckduckgo.py`, `google.py`, `searxng.py`, `hybrid.py`, `sqlite_fts.py`, `session.py` | `services/search/` | ✅ VERIFIED |
| `DuckDuckGoProvider` is default/enabled | `services/search/__init__.py:36` (used as fallback) | ✅ VERIFIED |
| `HybridSearchProvider` (FTS5 + vector similarity) is enabled | `services/search/__init__.py:7` (imported), `hybrid.py:95` | ✅ VERIFIED |
| Google and SearxNG disabled by default | `google.py:69-71` (checks `_is_configured()`), `searxng.py` (always available but not default) | ✅ VERIFIED |
| `SearchResult` dataclass fields: `title`, `url`, `snippet`, `source` | `services/search/base.py:9-14` | ✅ VERIFIED |
| Provider registry functions: `get_search_provider()`, `search_web()`, `get_article_search_provider()` | `services/search/__init__.py:34-58` | ✅ VERIFIED |
| `DuckDuckGoProvider.search()` uses `duckduckgo_search` library with 20s timeout | `services/search/duckduckgo.py:47-64` | ✅ VERIFIED |
| `HybridSearchProvider` uses `all-MiniLM-L6-v2` embeddings (via `sentence-transformers`) | `services/embeddings.py` (imported in `hybrid.py:11-15`) | ✅ VERIFIED |
| `cosine_similarity()` function exists | `services/search/hybrid.py:41-64` | ✅ VERIFIED |
| `reciprocal_rank_fusion()` function exists | `services/search/hybrid.py:67-92` | ✅ VERIFIED |
| DeepSeek is NOT a search provider (only a regex pattern) | grep confirms: `adapters/base.py:122`, `services/trend_detector.py:21`, `tests/test_llm_adapters/test_shared.py:218` | ✅ VERIFIED |
| `search_providers:` (plural) is the correct YAML key | `architecture/search-providers.md:147` | ✅ VERIFIED |
| Subagent tools use search providers (`web_search`, `get_search_provider`) | `services/subagent/tools.py:188-215,567-603` | ✅ VERIFIED |
| `BaseSearchProvider` abstract class with `search()` method | `services/search/base.py:17-22` | ✅ VERIFIED |
| `SearchProvider` abstract class (for DB-backed search) with `search()`, `index_article()`, `delete_article()`, `search_admin()`, `hybrid_search()` | `services/search/base.py:42-96` | ✅ VERIFIED |

---

## Incorrect Claims

### 1. Architecture Diagram Lists `session.py` (LOW)
**Location:** `architecture/search-providers.md:16`

**Claim:**
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

**Issue:** `session.py` exists at `services/search/session.py` but this is NOT an HTTP session management file for search. It is actually the SSRFSafeRedirectHandler used for web crawling. The search providers (`duckduckgo.py`, `google.py`, `searxng.py`) use `services/search/session.py:get_session()` for HTTP requests, but this is the shared crawl session, not a search-specific session.

**Priority:** LOW — functionally correct (search providers use it) but mischaracterized as "Search HTTP session management"

---

### 2. Hybrid Provider "Enabled" Status (NEEDS CLARIFICATION)
**Location:** `architecture/search-providers.md:72`

**Claim:** "Status: **Enabled**"

**Issue:** Being imported and registered doesn't mean it's the default web search provider. The YAML config shows:
```yaml
search_providers:
  default: duckduckgo
  providers:
    duckduckgo:
      enabled: true
    hybrid:
      enabled: true
```

Both are "enabled" but `duckduckgo` is the **default** for web search. The `hybrid` provider is for **internal article search** (`get_article_search_provider()`), not web search. The doc at line 14 correctly says "Hybrid FTS5 + vector similarity (enabled)" but the table at line 72 saying "Status: **Enabled**" without clarifying it's for article search, not web search, is ambiguous.

**Priority:** LOW — clarification needed

---

## Bugs Found

### 1. Hybrid Provider Used for Web Search (DOCUMENTATION BUG ONLY)
**Location:** `services/search/__init__.py:55-57`

```python
# Database search provider (FTS5)
def get_article_search_provider() -> SearchProvider:
    """Get the configured database search provider (e.g., SQLite FTS5)."""
    return get_db_search_provider()
```

**Issue:** The doc says `get_article_search_provider()` returns "Hybrid or SQLite FTS" but it actually always returns the provider registered as `"sqlite_fts"` via `get_db_search_provider()`. The `HybridSearchProvider` is registered as `"hybrid"` in `hybrid.py:95` but is NOT what `get_article_search_provider()` returns.

However, looking at `services/search/hybrid.py:349`:
```python
provider = get_db_search_provider("hybrid")
```

The `search_articles()` function in `hybrid.py:329` DOES use the hybrid provider. So `get_article_search_provider()` → `get_db_search_provider()` → which returns the `hybrid` provider (if configured as default) or `sqlite_fts`.

Actually, the `_db_search_manager` in `base.py` defaults to `"sqlite_fts"` (`base.py:113`), not `"hybrid"`. But `hybrid.py:349` explicitly requests `"hybrid"`.

This is confusing but not a bug — there are two parallel systems:
1. `_manager` (web search): duckduckgo, google, searxng
2. `_db_search_manager` (article search): sqlite_fts, hybrid

**Priority:** INFORMATIONAL — the dual-system architecture is confusing but functional

---

## Improvement Opportunities

### 1. Clarify Dual-Provider System
The architecture has two parallel provider systems that aren't clearly distinguished:
- **Web search** (`BaseSearchProvider`): duckduckgo, google, searxng — used by `search_web()`
- **Article search** (`SearchProvider`): sqlite_fts, hybrid — used by `search_articles()`

The doc should make this distinction explicit.

---

### 2. Document `search_articles()` Function Location
The doc says "Article search: Uses `get_article_search_provider()` for related article lookup" (line 178) but the actual implementation of `search_articles()` is at `services/search/hybrid.py:329`, not in `__init__.py`.

---

### 3. Document `search_web()` Returns Empty List on Failure
The current behavior of `search_web()` is to return `[]` on error (`services/search/__init__.py:44-52`). This should be documented.

---

## Summary

The search providers documentation is mostly accurate. All provider files and their implementations are correctly identified. The main issues are:
1. **Mischaracterization of `session.py`** — it's the crawl session, not a search-specific session (LOW)
2. **Hybrid "enabled" status needs clarification** — it's for article search, not web search (LOW)

DeepSeek NOT being a search provider is correctly verified.
