# Review: Subagent System

**Reviewed:** 2026-05-31
**Source:** `architecture/subagent.md`
**Reviewer:** Subagent 3 (LLM & Search Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Structure
- `services/subagent/` directory exists with all 10 Python files — **VERIFIED**
- `__init__.py`, `chain.py`, `conditions.py`, `config.py`, `middleware.py`, `prompt_templates.py`, `registry.py`, `runner.py`, `tools.py`, `utils.py`

### Tool Registry (`registry.py`)
- `_TOOL_REGISTRY: dict[str, ToolDefinition] = {}` — **VERIFIED** (`registry.py:15`)
- `_TOOL_REGISTRY_LOCK = threading.Lock()` — **VERIFIED** (`registry.py:16`)
- `_get_all_tools_cached()` uses `@functools.lru_cache(maxsize=1)` — **VERIFIED** (`registry.py:29`)
- `initialize_tool_registry()` only registers when `_TOOL_REGISTRY` is empty (line 60: `if not _TOOL_REGISTRY:`) — **VERIFIED** (`registry.py:60`)

### Tool List (14 Tools)
All 14 tools verified in `tools.py:306-603`:
1. `get_topic_note` — **VERIFIED** (`tools.py:310-327`)
2. `context_notes` — **VERIFIED** (`tools.py:329-346`)
3. `related_articles` — **VERIFIED** (`tools.py:348-373`)
4. `get_trend_memory` — **VERIFIED** (`tools.py:375-400`)
5. `get_article_by_id` — **VERIFIED** (`tools.py:402-418`)
6. `search_articles` — **VERIFIED** (`tools.py:420-437`)
7. `get_source_health` — **VERIFIED** (`tools.py:439-449`)
8. `get_topic_gap_report` — **VERIFIED** (`tools.py:451-471`)
9. `get_source_performance` — **VERIFIED** (`tools.py:473-492`)
10. `get_quality_report` — **VERIFIED** (`tools.py:494-510`)
11. `find_dedupe_candidates` — **VERIFIED** (`tools.py:512-536`)
12. `estimate_stage_cost` — **VERIFIED** (`tools.py:538-558`)
13. `web_search` — **VERIFIED** (`tools.py:567-584`)
14. `get_search_provider` — **VERIFIED** (`tools.py:586-601`)

### Subagent Runner (`runner.py`)
- `run_subagent()` signature: `(task_type, stage, prompt_data, response_model, article_id=None)` — **VERIFIED** (`runner.py:209-215`)
- `run_subagent_with_tools()` includes `tools` parameter — **VERIFIED** (`runner.py:334-341`)
- `SubagentResponse` schema: `synthesis`, `used_fallback`, `fallback_stages` — **VERIFIED** (`schemas/llm_responses.py:164-173`)

### Chain System
- `SubagentChainStep` schema in `schemas/pipeline.py` — **VERIFIED** (`schemas/pipeline.py:108-112`)
- `SubagentChainConfig` schema in `schemas/pipeline.py` — **VERIFIED** (`schemas/pipeline.py:115-118`)
- Chains use `provider.chat()` directly (no tool calling) — **VERIFIED** (`chain.py:121-128`)

### Middleware
- `LoggingMiddleware`, `TimingMiddleware`, `ErrorHandlingMiddleware` — **VERIFIED** (`middleware.py:18-80`)
- Chain order: Logging → Timing → ErrorHandling (applied in reverse via `apply_middleware()`) — **VERIFIED** (`middleware.py:83-91`)
- `ErrorHandlingMiddleware` re-raises exceptions (does NOT return error dicts) — **VERIFIED** (`middleware.py:70-80`)

### Self-Correction
- Self-correction on validation failure in `_run_subagent_core()` — **VERIFIED** (`runner.py:88-109`)
- `self_corrected` flag (actually `corrected` variable) tracks correction state — **VERIFIED** (`runner.py:69`)
- Retries with `max_retries + 1` total attempts — **VERIFIED** (`runner.py:125-131`)

### Configuration
- `max_iterations` default: 5, ge=1, le=20 — **VERIFIED** (`schemas/pipeline.py:105`)
- Config from `pipeline.yaml` under `subagent` section — **VERIFIED** (`schemas/pipeline.py:121-134`)

### Helper Functions
- `_format_subagent_prompt()` in `utils.py` — **VERIFIED** (`utils.py:31-42`)
- Prompt templates in `prompt_templates.py` — **VERIFIED** (`prompt_templates.py:7-43`)
- Conditions AST-based evaluation in `conditions.py` — **VERIFIED** (`conditions.py:128-157`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 290 | Configuration example shows `tool_timeout: 30.0` | `SubagentStageConfig` in `schemas/pipeline.py:93-105` has NO `tool_timeout` field. Timeout is `timeout_seconds` (int, default 120). | HIGH |
| 291 | Configuration example shows `default_model: "ollama-local"` | `SubagentConfig` in `schemas/pipeline.py:121-134` has NO `default_model` field. Model is configured per-stage via `SubagentStageConfig.model` or via `RoleConfig`. | HIGH |
| 140 vs 204 | Doc says Chain schemas are in `runner.py` (line 140) then contradicts itself saying they're in `schemas/pipeline.py` (line 204) | Schemas ARE in `schemas/pipeline.py` (lines 108-118). The line 140 claim is incorrect. | MEDIUM |
| 332 | Doc says "Retries with exponential backoff (`stage_config.max_retries + 1` attempts, default 2)" | `SubagentStageConfig.max_retries` default is 1 (`schemas/pipeline.py:101`), so `max_retries + 1` = 2 total attempts. The doc says "default 2" which is correct for total attempts, but could be clearer. | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | No actual bugs found in the documented architecture. The doc accurately describes the subagent implementation. | — | — | — |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | The YAML configuration example (lines 287-301) includes fields (`tool_timeout`, `default_model`) that don't exist in the actual `SubagentStageConfig` or `SubagentConfig` schemas | documentation | P1 |
| 2 | `SubagentConfig` schema has `default`, `research`, `edit`, `chains` fields — not documented | documentation | P2 |
| 3 | `SubagentStageConfig` has `task_template`, `tools`, `max_iterations` fields — partially documented | documentation | P2 |
| 4 | `_run_subagent_core()` is a significant internal function not documented in the architecture | documentation | P2 |
| 5 | `config.py` with `_get_subagent_provider_and_config()` and `_subagent_executor` ThreadPoolExecutor — not documented | documentation | P3 |
| 6 | `prompt_templates.py` only has 2 inline templates (`research_synthesis`, `edit_contextualization`) — doc implies more exist | documentation | P3 |
| 7 | `conditions.py` AST evaluation has a security model (allowed ops/names) not documented | documentation | P3 |
| 8 | The doc doesn't mention that `run_subagent()` uses `StageAwareToolSelector` for tool selection (line 276-282) | documentation | P3 |
| 9 | `SubagentConfig` is NOT `SubagentStageConfig` — the doc correctly notes this on line 140 but the distinction could be clearer | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 287-301 | Configuration YAML example with `tool_timeout` and `default_model` fields | These fields don't exist in `SubagentStageConfig` or `SubagentConfig` schemas. `timeout_seconds` is an int (not float), and model is configured per-stage or via `RoleConfig`. | rewrite |
| 140 | Doc says Chain schemas are in `runner.py` | Schemas are defined in `schemas/pipeline.py:108-118`, not in `runner.py` or `chain.py` (doc corrects this on line 204 but the initial claim at 140 is wrong) | remove/update |

---

## Summary

- Verified: 35 claims
- Incorrect: 4 claims (2 HIGH, 1 MEDIUM, 1 LOW)
- Bugs: 0 (HIGH: 0, MEDIUM: 0, LOW: 0)
- Improvements: 9
- Stale items: 2

The document is highly accurate for the core subagent system (tool registry, runner, middleware, chain, conditions). The main issues are: (1) the YAML configuration example includes non-existent fields (`tool_timeout`, `default_model`), (2) the schema location is contradicted within the document itself, and (3) several internal components (`_run_subagent_core`, `config.py`, `StageAwareToolSelector`) are not documented. The tool list, middleware chain, and self-correction mechanisms are all accurately described.
