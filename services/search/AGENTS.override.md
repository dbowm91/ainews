# Search Services Conventions

Contextual conventions for agents working in the `services/search/` directory.

## ThreadPoolExecutor Pattern

Blocking I/O uses ThreadPoolExecutor to avoid blocking Celery workers. Applied in `searxng.py`, `google.py`, `duckduckgo.py`. Module-level singleton executor with `submit()` + `future.result(timeout=N)`.

## Architecture Review Findings (From Wave 9 Review)

### DuckDuckGo Provider Uses Library's Internal HTTP Client
`services/search/duckduckgo.py:24` uses `duckduckgo_search` library's internal HTTP client directly, not our shared `get_crawl_session()`. This bypasses the SSRFSafeRedirectHandler protection. This is a known limitation when using third-party libraries.

### Hybrid Search Function Name
The hybrid search function is `search_articles()` in `services/search/hybrid.py:329`, NOT `hybrid_search()`. Also has `cosine_similarity` (line 41) and `reciprocal_rank_fusion` (line 67).

### search_articles Subagent Tool Uses Direct SQL
The `_context_tool_search_articles` in `services/subagent/tools.py:127-142` uses direct SQL `ILIKE` query, NOT the SearchProvider abstraction. This is a known inconsistency - programmatic article search uses `get_article_search_provider()`.