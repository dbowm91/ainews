# Review: Search Providers

**Reviewed:** 2026-05-31
**Source:** `architecture/search-providers.md`
**Reviewer:** Subagent 3 (LLM & Search Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Structure
- `services/search/` directory exists with all 8 documented files — **VERIFIED**
- `__init__.py`, `base.py`, `duckduckgo.py`, `google.py`, `searxng.py`, `hybrid.py`, `sqlite_fts.py`, `session.py` — all exist

### Two Separate Class Hierarchies
- Web search: `BaseSearchProvider` (external) — **VERIFIED** (`base.py:17`)
- Article search: `SearchProvider` (internal/database) — **VERIFIED** (`base.py:42`)
- Separate registries: `@register_search_provider` and `@register_db_search_provider` — **VERIFIED** (`base.py:30,125`)

### SearchResult Dataclass
- Fields: `title`, `url`, `snippet`, `source` — **VERIFIED** (`base.py:9-14`)

### Entry Points
- `search_web()` function exists — **VERIFIED** (`__init__.py:44-52`)
- `get_search_provider()` function exists — **VERIFIED** (`__init__.py:34-37`)
- `get_article_search_provider()` function exists — **VERIFIED** (`__init__.py:56-58`)
- `get_db_search_provider()` in `base.py` — **VERIFIED** (`base.py:126`)

### DuckDuckGo Provider
- Default web search provider, no API key required — **VERIFIED** (`duckduckgo.py:45-64`)
- Uses `duckduckgo_search` library — **VERIFIED** (`duckduckgo.py:20`)
- 20-second timeout via `future.result(timeout=20)` — **VERIFIED** (`duckduckgo.py:52`)
- Enabled by default — **VERIFIED** (`providers.yaml:128-131`)

### Google Provider
- Disabled, requires `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` — **VERIFIED** (`google.py:69`, `providers.yaml:133-138`)
- Uses Google Custom Search JSON API — **VERIFIED** (`google.py:32-55`)

### SearxNG Provider
- Disabled, self-hosted — **VERIFIED** (`providers.yaml:140-144`)
- Requires `host` config in providers.yaml — **VERIFIED** (`searxng.py:62`)

### SQLite FTS Provider
- `SQLiteFTSProvider` registered as `"sqlite_fts"` — **VERIFIED** (`sqlite_fts.py:52`)
- Uses SQLite FTS5 for full-text search — **VERIFIED** (`sqlite_fts.py:56-107`)
- Searches article titles and content — **VERIFIED** (`sqlite_fts.py:109-127`, indexes `headline`, `tldr`, `body`)

### Hybrid Provider
- `HybridSearchProvider` registered as `"hybrid"` — **VERIFIED** (`hybrid.py:97`)
- Enabled — **VERIFIED** (`providers.yaml:146-149`)
- Combines FTS5 + vector similarity — **VERIFIED** (`hybrid.py:111-154`)
- Delegates to `SQLiteFTSProvider` for FTS-only search — **VERIFIED** (`hybrid.py:104-109`)

### Provider Selection
- Default provider configured in providers.yaml — **VERIFIED** (`providers.yaml:151: default_search_provider: duckduckgo`)

### Integration with Subagent
- `web_search` and `search_articles` tools exposed — **VERIFIED** (`tools.py:563-601`)
- `_search_web()` calls `search_web()` — **VERIFIED** (`tools.py:188-201`)

### DeepSeek NOT a Search Provider
- DeepSeek only appears as a regex pattern in `trend_detector.py` — **VERIFIED** (`trend_detector.py:21`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 50-52 | `BaseSearchProvider` has abstract `search()` method | `BaseSearchProvider` has NO `search()` method at all. It inherits from `BaseProvider` which has no abstract search method. The `search()` method is only defined on concrete providers like `DuckDuckGoSearchProvider`. | MEDIUM |
| 134 | `SearchProvider.search()` signature shows `(query, limit=10, **kwargs)` | Signature is correct but incomplete — doc omits that `**kwargs` supports `page`, `per_page`, `category` keys (used throughout `sqlite_fts.py` and `hybrid.py`) | LOW |
| 227-241 | YAML example shows `search_providers:` with `default:` and nested `providers:` dict | Actual format uses flat list with separate `default_search_provider:` key at top level. Doc's YAML is structurally wrong. | HIGH |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | No actual bugs found in the documented architecture. The doc accurately describes the search provider implementation. | — | — | — |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | The doc's YAML example (`providers.yaml` section) shows a completely different structure than the actual file. The actual format uses a flat list under `search_providers:` with `default_search_provider:` as a separate top-level key. | documentation | P1 |
| 2 | `BaseSearchProvider` has no abstract `search()` method as documented. The search method is defined only on concrete provider classes. | documentation | P2 |
| 3 | `SearchProvider.search()` `**kwargs` parameter supports `page`, `per_page`, `category` — these are not documented | documentation | P2 |
| 4 | `SearchProviderManager` class in `base.py` is not documented (it's a separate manager for DB search providers) | documentation | P3 |
| 5 | `search_articles()` function in `hybrid.py` (line 338) is a module-level entry point not documented in the architecture | documentation | P3 |
| 6 | `SSRFSafeRedirectHandler` in `session.py` is documented but its redirect validation behavior is not described | documentation | P3 |
| 7 | The doc doesn't mention that `get_article_search_provider()` returns the SQLite FTS provider by default, not the hybrid provider | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 227-241 | YAML example for `providers.yaml` search_providers section | The example shows a nested `default:` + `providers:` dict structure, but the actual format is a flat list with `default_search_provider:` at top level | rewrite |
| 50-52 | `BaseSearchProvider` has abstract `search()` method | `BaseSearchProvider` has no `search()` method; the method is only on concrete classes | remove |

---

## Summary

- Verified: 28 claims
- Incorrect: 3 claims (1 HIGH, 1 MEDIUM, 1 LOW)
- Bugs: 0 (HIGH: 0, MEDIUM: 0, LOW: 0)
- Improvements: 7
- Stale items: 2

The document is generally accurate. The most significant issue is the YAML example (line 227-241) which shows a completely different structure than the actual `providers.yaml` file. The `BaseSearchProvider` abstract method claim is also incorrect — the method doesn't exist on the base class. All functional descriptions (DuckDuckGo, Google, SearxNG, SQLite FTS, Hybrid) are accurate.
