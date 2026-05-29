# AINews Implementation Plan

**Status:** COMPLETED
**Completed:** 2026-05-29

## Summary

All planned work has been completed and verified against the codebase.

### Wave 1: Code Bug Fixes — 4/4 completed
- W1-1: Article import added to `routes/admin/api/replay.py`
- W1-2: Redis pubsub leak fixed in `services/cache.py`
- W1-3: SSRFSafeRedirectHandler returns redirect-modified request in `adapters/session.py`
- W1-4: ProcessItemTask.topics validator added (max 20 items) in `schemas/tasks.py`

### Wave 2: Documentation Corrections — All groups completed
- Groups 2A-2L: Architecture docs corrected across models, schemas, routes, services, pipeline, subagent, search-providers, llm-providers, tasks, prompts, config, overview, and utils.

### Wave 3: Feature Enhancements — All 10 phases completed
- Phase 3.1: Quality reports and citation verification
- Phase 3.2: Source intelligence and performance dashboard API
- Phase 3.3: Topic gap and source recommendation tool
- Phase 3.4: Pipeline rescue/replay console API
- Phase 3.5: Hybrid search exposure
- Phase 3.6: Cost-aware LLM telemetry
- Phase 3.7: Read-only subagent tool expansion (14 tools)
- Phase 3.8: Alerting layer
- Phase 3.9: Newsletter intelligence
- Phase 3.10: Documentation cleanup

## Post-Plan Fixes (2026-05-29)

After verification, 3 issues were found and fixed:
1. `tests/test_pipeline_replay.py`: Missing `import pytest` (5 tests using `pytest.raises` would fail)
2. `tests/test_newsletter_performance.py`: Missing `admin_headers` fixture and `Subscriber` import (refactored to use `auth_client`)
3. `architecture/config.md`: Incorrect Google env var names (`GOOGLE_SEARCH_API_KEY` → `GOOGLE_API_KEY`, `GOOGLE_SEARCH_CX` → `GOOGLE_CSE_ID`)

## Key Architecture Notes

- **Tool count is 14** (12 context + 2 search), NOT 9. Verified at `services/subagent/tools.py:306-603`.
- **SSRF protection** lives in `utils/url.py` (adapters) and `services/url.py` (services with config support).
- **PipelineLog uses `meta`** not `metadata` (SQLAlchemy reserved name restriction).
- **Config cache is two-tier:** L1 (in-memory, 500 entries) + L2 (Redis, DB 1).
- **Limiter uses Redis DB 15.** Not DB 0 or DB 2.
- **DeepSeek is NOT a search provider** — only a regex pattern.
- **SubagentConfig has no top-level `enabled` field** — the `enabled` field is on `SubagentStageConfig`.
