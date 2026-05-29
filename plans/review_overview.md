# Overview.md Review

**Reviewed:** 2026-05-29
**Source:** `architecture/overview.md`

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| Directory structure (models/, schemas/, adapters/, services/, tasks/, routes/, utils/, prompts/) | ✅ Verified | All directories exist and match |
| Module deep dive links | ✅ Verified | All linked documents exist in `architecture/` |
| Layering rules table | ✅ Verified | Matches `AGENTS.md` |
| `SubagentConfig` no top-level `enabled` | ✅ Verified | `schemas/pipeline.py:121-125` |
| `PipelineLog` uses `meta` not `metadata` | ✅ Verified | `models/pipeline.py:39` |
| `ModelLimiter` interface `acquire(provider, model, ...)` | ✅ Verified | `services/limiter.py:39-93` |
| `CircuitBreaker` requires `name` param | ✅ Verified | `services/circuit_breaker.py:40-47` |
| `run_health_checks()` not `check_health()` | ✅ Verified | `services/health.py:121` |
| Tool count is 14 | ✅ Verified | `services/subagent/tools.py:306-603` |
| Rate limiter uses Redis DB 15 | ✅ Verified | `extensions.py:29` |
| Admin API prefix `/api/v1/` | ✅ Verified | `app.py:196` |
| DeepSeek NOT a search provider | ✅ Verified | `providers.yaml:35-42` |
| `StageConfig` is a stub | ✅ Verified | `schemas/pipeline.py:141-147` |
| MetricsCollector methods | ✅ Verified | `services/metrics.py:44-97` |
| `utils/url.py` not pure (global mutable state) | ✅ Verified | `utils/url.py:4-5` docstring |
| Logout requires POST | ✅ Verified | `AGENTS.md` confirms |
| Dynamic fallback chain | ✅ Verified | `services/llm/__init__.py:57` - `get_provider_chain()` |
| `ToolDefinition` has no `cached` field | ✅ Verified | `services/llm/base.py` - ToolDefinition dataclass |
| NewsletterBrief fields | ✅ Verified | Schema doesn't have `articles`/`footer` fields |
| Redis DB allocation (0, 1, 15) | ✅ Verified | `config.py:94-96`, `extensions.py:29` |
| `api_tokens_bp` registered without prefix | ✅ Verified | `app.py:197` - routes at `/api-tokens/*` |
| `Provider` count is 14 | ✅ Verified | `providers.yaml:1-124` |
| Celery Beat Schedule 14 tasks | ✅ Verified | `config.py:146-203` |
| `login_lockout` Redis Lua script | ✅ Verified | `routes/admin/__init__.py` |

---

## Incorrect Claims

### MEDIUM: `utils/datetime.py` vs `services/date_utils` mismatch

**Doc shows (line 275):**
```
├── utils/                  # Pure utility functions
│   ├── url.py              # SSRF protection, URL normalization, DNS cache
│   ├── text.py             # XML escaping, truncation, HTML sanitization
│   ├── datetime.py         # Date parsing and formatting
```

**Actual:**
- `utils/datetime.py` exists and is correct
- But `app.py:288` template filter imports from `services.date_utils`
- This is NOT a bug - they're different modules. The doc is correct that `utils/datetime.py` exists. The `services/date_utils.py` is a separate service-layer module.

**Verdict:** This is actually correct. No bug.

---

## Bugs Found

### LOW: `providers.yaml` description "14 providers" - should clarify including search_providers

**Doc says (line 497):**
```
| `providers.yaml` | LLM provider definitions (14 providers), search provider definitions |
```

The 14 count is correct for LLM providers, but search providers are also defined in the same file (`search_providers:` section). Could clarify that 14 = LLM providers only.

---

## Improvement Opportunities

### Missing `sqlite_fts` search provider in External Integrations

**Doc shows (lines 544-551):**
```
| Provider | Status |
|----------|--------|
| duckduckgo | **Enabled** (default) |
| hybrid (FTS5 + vector) | **Enabled** |
| google | Disabled (requires API key) |
| searxng | Disabled (self-hosted) |
```

The `providers.yaml` also has a `hybrid` search provider that combines FTS5 + vector similarity. But there's also a `sqlite_fts.py` search provider at `services/search/sqlite_fts.py` that's used for internal article search but is NOT a configurable search provider. The doc's list of search providers appears complete based on what's configurable via `providers.yaml`.

### `routes/admin/api/` structure could be more explicit

The doc shows `routes/admin/api/` directory but doesn't enumerate its contents. The actual files in `routes/admin/api/`:
- alerts.py
- articles.py
- replay.py
- health.py
- config.py
- search.py
- sources.py
- newsletter.py
- topic_gap.py
- webhooks.py
- source_intelligence.py

The doc only mentions these in the deep-dive links section.

### Stale: `models.py` root file not documented

There's a `models.py` at the root level (`/home/sugarwookie/projects/ainews/models.py`) that re-exports from `models.__init__`. This is not mentioned in the directory structure.

### `logging_config.py` vs `logging_config/` directory

The doc at line 148 shows `logging_config.py` as a file, which is correct. There is no `logging_config/` directory.

---

## Stale Content

### `plans/plan.md` post-plan fixes already corrected in docs

The `plans/plan.md` mentions that `config.md` had incorrect Google env var names that were fixed. This was already applied to `architecture/config.md`. No action needed.

### `models/article.py` not `models/articles.py`

The doc at line 151 shows `models/article.py` (singular) which is correct. The doc is accurate.

---

## Priority Findings

| Priority | Finding | Location |
|----------|---------|----------|
| LOW | 14 provider count could clarify "LLM providers" | `overview.md:497` |
| LOW | `logging_config.py` vs `logging_config/` already correct | `overview.md:148` |
| INFO | `models.py` root re-export file not in directory structure | `overview.md` |
| INFO | `routes/admin/api/` contents not enumerated | `overview.md:271` |
