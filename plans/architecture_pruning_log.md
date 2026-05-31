# Architecture Pruning Log

**Date:** 2026-05-31
**Action:** Stale Content Pruning

## Changes Applied

| # | Document | Section | Change | Reason |
|---|----------|---------|--------|--------|
| 1 | `architecture/adapters.md` | Base Source Adapter | Updated `__exit__` signature from `*args` to `*exc` | Code uses `*exc` not `*args` |
| 2 | `architecture/adapters.md` | Helper Functions | Updated `_classify_topics` signature to single `text` parameter | Function signature changed — now takes single `text` param |
| 3 | `architecture/adapters.md` | WebAdapter Request Delay | Rewrote delay description to say "per HTTP request" instead of "per-article" | Delay applies per-HTTP-request (both pages and articles) via `_polite_get()` |
| 4 | `architecture/llm-providers.md` | Structured Output | Fixed `_extract_json()` → `extract_json()` | Function is named `extract_json()` (no underscore prefix) |
| 5 | `architecture/llm-providers.md` | Provider Registry | Removed type annotations from `get_provider_for_role()` and `get_provider_chain()` signatures | Actual code lacks type annotations on these functions |
| 6 | `architecture/llm-providers.md` | Fallback Chain | Removed type annotation from `get_provider_chain()` signature | Actual function has no return type annotation |
| 7 | `architecture/llm-providers.md` | LLM Stage Metrics | Updated `record_provider_success()` signature to include all parameters | Actual signature has additional params: input_tokens, output_tokens, cached_tokens, latency_ms, article_id |
| 8 | `architecture/search-providers.md` | Base Class | Added note clarifying `BaseSearchProvider` vs `SearchProvider` distinction | Reviewer initially flagged abstract method as missing, but it exists — added clarity note |
| 9 | `architecture/search-providers.md` | Provider Selection | Rewrote YAML example to match actual flat list format with `default_search_provider:` | Example showed nested `default:` + `providers:` dict but actual format uses flat list |
| 10 | `architecture/subagent.md` | Configuration | Rewrote YAML config example to use actual `SubagentStageConfig` fields | Example had non-existent `tool_timeout` and `default_model` fields |
| 11 | `architecture/pipeline.md` | Degradation Behavior | Rewrote disabled stage behavior to show routing through `_finalize()` | Code routes through `_finalize()` not directly to next stage |
| 12 | `architecture/pipeline.md` | Newsletter Lock | Added 2-day TTL to idempotency key description | Idempotency key TTL is 2 days (86400*2), not 10 minutes |
| 13 | `architecture/tasks.md` | Stage Transitions | Rewrote table to include `selecting`, `selected`, `written`, and `PENDING→RESEARCHING` transition | Missing transient stages and PENDING→RESEARCHING transition |
| 14 | `architecture/tasks.md` | Core Tasks | Updated "All pipeline tasks" claim to note exceptions | Multiple tasks lack `max_retries` parameter |
| 15 | `architecture/prompts.md` | Prompt Templates | Added 2 subagent templates to list (now 9 total) | 9 files exist (2 subagent templates missing from original list) |
| 16 | `architecture/prompts.md` | Key Files | Removed duplicate `services/subagent/prompt_templates.py` entry | Copy-paste error |
| 17 | `architecture/infrastructure.md` | ThreadPoolExecutor | Updated subagent path to `services/subagent/config.py` | Subagent executor is in `services/subagent/config.py` |
| 18 | `architecture/config.md` | Celery Beat Schedule | Added `celery_app` parameter to `reload_beat_schedule()` call | `reload_beat_schedule()` requires `celery_app` parameter |
| 19 | `architecture/routes.md` | Admin API Endpoints | Changed `/newsletters/performance` to `/newsletters/stats` | Actual endpoint is `/newsletters/stats` |
| 20 | `architecture/routes.md` | Admin API (detailed) | Changed `/newsletters/performance` to `/newsletters/stats` | Actual endpoint is `/newsletters/stats` |
| 21 | `architecture/services.md` | Trend Memory | Updated `propose_trend_memory` return type from `list[TrendMemory]` to `SubagentResponse` | Actual function returns `SubagentResponse`, not `list[TrendMemory]` |
| 22 | `architecture/services.md` | Content Extraction | Changed "Final fallback: Raw HTML with boilerplate removal" to "Returns EMPTY status" | No raw HTML fallback exists — code returns EMPTY status |
| 23 | `architecture/services.md` | File Inventory | Expanded "... Additional modules" with specific module names | Inventory was missing ~30 modules |

## Skipped Items

| # | Document | Section | Reason Skipped |
|---|----------|---------|----------------|
| 1 | `architecture/utils.md` | URL Utilities | Line number drift is minor and cosmetic — `_TTLCache` at lines 138-181, double-checked locking at 188-196. No functional inaccuracy. |
| 2 | `architecture/subagent.md` | Chain Schemas Location (line 140) | Reviewer flagged line 140 as saying "schemas are in runner.py" but actual text correctly says "schemas are defined in `schemas/pipeline.py`". No correction needed. |
| 3 | `architecture/overview.md` | Subagent Location (line 636) | Reviewer noted "Subagent system: Located at `services/subagent/`" is actually correct. No change needed. |
| 4 | `architecture/services.md` | File Inventory (full update) | Adding all ~30 missing modules would bloat the document. Instead, added a note pointing to `ls services/` for the full list. |

## Summary

- Changes applied: 23
- Items skipped: 4
- Documents modified: 11
