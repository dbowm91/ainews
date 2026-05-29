# Review: Search Providers Architecture

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- File structure in `services/search/` matches documentation — all files exist: `__init__.py`, `base.py`, `duckduckgo.py`, `google.py`, `searxng.py`, `hybrid.py`, `sqlite_fts.py`, `session.py`
- DuckDuckGo is default/enabled — `providers.yaml:128-131` (`enabled: true`), `providers.yaml:151` (`default_search_provider: duckduckgo`)
- Hybrid FTS5 + vector is enabled — `providers.yaml:146-149` (`enabled: true`)
- Google is disabled — `providers.yaml:133-138` (`enabled: false`)
- SearxNG is disabled — `providers.yaml:140-144` (`enabled: false`)
- `SearchResult` dataclass: `title`, `url`, `snippet`, `source=""` — `services/search/base.py:9-14`
- `BaseSearchProvider` abstract class with `search()` method — `services/search/base.py:17-22`
- Provider registry exists via `ProviderManager` — `services/search/base.py:26`, `services/search/__init__.py:34-37`
- `get_search_provider()` function — `services/search/__init__.py:34-37`
- `search_web()` function — `services/search/__init__.py:44-52`
- `get_article_search_provider()` function — `services/search/__init__.py:56-58`
- DeepSeek is NOT a search provider — confirmed no DeepSeek references in `services/search/*.py`
- DuckDuckGo uses `duckduckgo_search` library — `services/search/duckduckgo.py:20`
- DuckDuckGo timeout: 20 seconds via `future.result(timeout=20)` — `services/search/duckduckgo.py:52`
- Google requires API key and CSE ID — `services/search/google.py:69`
- SearxNG requires host config — `services/search/searxng.py:62`
- Hybrid uses `all-MiniLM-L6-v2` embedding model — `services/embeddings.py:15`
- `SearchProvider` abstract base for database search — `services/search/base.py:42-96`
- `SQLiteFTSProvider` exists — `services/search/sqlite_fts.py` (referenced in `services/search/hybrid.py:19`)
- Search providers are exposed as subagent tools — `services/subagent/tools.py:563-601` (`web_search`, `get_search_provider`)
- Circuit breaker integration on search providers — `services/search/duckduckgo.py:18`, `google.py:23`, `searxng.py:18`

## Incorrect Claims

- **Google provider env var names**
  - Priority: HIGH
  - Doc at lines 86-87 says `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_CX`. Actual env vars in `providers.yaml:137-138` are `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`. The Google provider code also uses `cse_id` field name (`services/search/google.py:63`), not `cx`.

- **Search provider config section name**
  - Priority: MEDIUM
  - Doc at lines 147-161 shows config under a `search:` key. Actual config in `providers.yaml:127` is `search_providers:` (plural). This is misleading for anyone trying to configure the system.

- **Hybrid provider base class**
  - Priority: LOW
  - Doc at line 63 says `HybridSearchProvider(SearchProvider)`. This is correct — it extends `SearchProvider` (the database search base), NOT `BaseSearchProvider` (the web search base). The doc accurately reflects this, but the distinction between `BaseSearchProvider` and `SearchProvider` should be clearer.

## Bugs Found

- **DuckDuckGo DDGS timeout mismatch**
  - Priority: LOW
  - Doc says "Timeout: 20 seconds" but the DDGS context manager timeout is 15 seconds (`services/search/duckduckgo.py:24`), while the future timeout is 20 seconds (`services/search/duckduckgo.py:52`). The effective timeout is 15 seconds for the API call, 20 seconds for the wrapper.

- **Search provider fallback logging**
  - Priority: LOW
  - `services/search/__init__.py:44-52` catches exceptions and returns empty list, but doesn't log which provider was attempted. Could make debugging harder.

## Improvement Opportunities

- **Document SSRF protection in search session**
  - Priority: MEDIUM
  - `services/search/session.py:17-46` implements `SSRFSafeRedirectHandler` that validates redirect targets against SSRF protection. This is a significant security feature not documented.

- **Document URL validation in DuckDuckGo results**
  - Priority: MEDIUM
  - `services/search/duckduckgo.py:29-40` validates each result URL via `validate_url_safe()` and filters out blocked URLs. Important security behavior.

- **Document `SearchProviderManager` for database search**
  - Priority: LOW
  - `services/search/base.py:99-126` implements a separate manager for database search providers (`SearchProvider`), distinct from the web search `ProviderManager`. Undocumented.

- **Document `SearchPage` and `SearchResultItem`**
  - Priority: LOW
  - `services/search/hybrid.py:25-38` defines `SearchResultItem` and `SearchPage` dataclasses used by `search_articles()`. Not documented.

- **Document `reciprocal_rank_fusion()`**
  - Priority: LOW
  - `services/search/hybrid.py:67-92` implements RRF for combining result lists. Available but not documented.

- **Document search circuit breaker names**
  - Priority: LOW
  - Each search provider registers a named circuit breaker: `search_duckduckgo`, `search_google`, `search_searxng` — useful for monitoring.

## Stale Content

- **None detected**
  - All referenced files, classes, and functions exist and are current.
