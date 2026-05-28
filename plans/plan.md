# AINews Consolidated Implementation Plan

**Status:** COMPLETED
**Last Updated:** 2026-05-28
**Source:** Consolidated from 7 architecture review files

---

## Overview

This plan consolidates findings from architecture reviews across all modules. All items have been verified complete as of 2026-05-28.

---

## Phase 1: Critical Bug Fixes — COMPLETE

| Item | File | Status |
|------|------|--------|
| 1.1 Missing `UnsafeURLError` import | `routes/admin/sources.py` | DONE |
| 1.2 `generate_daily_newsletters` missing `@shared_task` | `tasks/newsletter.py` | DONE |
| 1.3 `validate_url_safe()` exception type mismatch | `utils/url.py` + callers | DONE |
| 1.4 `ErrorHandlingMiddleware` behavior mismatch | `services/subagent/middleware.py` | DONE |
| 1.5 `ModelLimiter` wrong metrics method | `services/limiter.py` | DONE |

## Phase 2: Documentation Corrections — Function Signatures — COMPLETE

| Item | File | Status |
|------|------|--------|
| 2.1.1–2.1.4 | `architecture/llm-providers.md` | DONE |
| 2.2.1–2.2.5 | `architecture/search-providers.md` | DONE |
| 2.3.1–2.3.4 | `architecture/adapters.md` | DONE |
| 2.4.1–2.4.17 | `architecture/infrastructure.md` | DONE |
| 2.5.1–2.5.6 | `architecture/prompts.md` | DONE |
| 2.6.1 | `architecture/tasks.md` | DONE |

## Phase 3: Schema & Model Documentation Corrections — COMPLETE

| Item | File | Status |
|------|------|--------|
| 3.1–3.8 | `architecture/models.md` | DONE |
| 3.9.1–3.9.4 | `architecture/schemas.md` | DONE |

## Phase 4: Route Documentation Corrections — COMPLETE

| Item | File | Status |
|------|------|--------|
| 4.1–4.7 | `architecture/routes.md` | DONE |

## Phase 5: Adapter & Utils Documentation — COMPLETE

| Item | File | Status |
|------|------|--------|
| 5.1–5.3 | `architecture/adapters.md`, `architecture/utils.md` | DONE |
| 5.4 | `architecture/utils.md` | DONE |
| 5.5 | `architecture/utils.md` | DONE |

## Phase 6: Service Documentation — COMPLETE

| Item | File | Status |
|------|------|--------|
| 6.1–6.5 | `architecture/infrastructure.md`, `architecture/overview.md` | DONE |

## Phase 7: Pipeline & Subagent Documentation — COMPLETE

| Item | File | Status |
|------|------|--------|
| 7.1–7.10 | `architecture/pipeline.md` | DONE |

## Phase 8: Low Priority Items — COMPLETE

| Item | File | Status |
|------|------|--------|
| 8.1–8.6 | Various | DONE |

---

## Verification Checklist

All items verified and complete:

- [x] `routes/admin/sources.py` imports `UnsafeURLError`
- [x] `tasks/newsletter.py` has `@shared_task` on `generate_daily_newsletters`
- [x] `validate_url_safe()` documentation matches actual exception behavior (now raises `UnsafeURLError` for all cases)
- [x] All function signatures match actual code (verified in Wave 2)
- [x] All return types match actual implementations (verified in Wave 2)
- [x] All default values match actual defaults (verified in Wave 2)
- [x] All class names match actual class names (verified in Wave 2)
- [x] All route paths match actual route definitions (verified in Wave 4)
- [x] All field names match actual schema fields (verified in Wave 3)
- [x] All method names match actual method names (verified in Wave 2)
- [x] Provider count updated (14 total, 1 enabled)
- [x] Redis DB allocation corrected (DB 0 = broker, DB 1 = config cache, DB 15 = limiter)
- [x] `ruff check . --exclude .venv` passes (2 pre-existing S311 warnings in adapters/web.py only)
- [x] `validate_url_safe()` exception documentation in `architecture/utils.md` corrected (item 5.4)

---

## Notes

- **APIAdapter/WebAdapter close() Design:** These adapters intentionally have no-op `close()` because they share the global session. RSSAdapter owns its own session and closes it properly. This is BY DESIGN.
- **utils/url.py and services/url.py Duplication:** Intentional for layering — `utils/url.py` is for adapters, `services/url.py` is for services with config support. `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py`.
- **DeepSeek is NOT a search provider:** DeepSeek is only a regex pattern in `services/trend_detector.py` and `adapters/base.py`. Do NOT list it as a search provider.
- **SubagentConfig has no top-level `enabled` field:** The `enabled` field is on `SubagentStageConfig`, not `SubagentConfig`.
- **Task name is `retry_stuck`:** The Celery task defined at `tasks/retry.py:78` is named `retry_stuck`. The beat schedule key may be different (`retry-stuck-articles`).
- **Config cache is two-tier:** L1 (in-memory, 500 entries) + L2 (Redis, DB 1).
- **Limiter uses Redis DB 15:** Not DB 0 or DB 2.
- **PipelineLog uses `meta` not `metadata`:** Due to SQLAlchemy reserved name restriction.

---

*Plan consolidated: 2026-05-28*
*All claims verified against codebase on 2026-05-28*
*Implementation completed: 2026-05-28*
