# Wave Implementation & Documentation Fixes

Conventions for managing multi-wave implementations, parallel subagent work, and documentation alignment in this codebase.

## Branch Management Rules

1. **Separate Branches:** Each subagent task should use a dedicated branch to avoid merge conflicts
2. **Branch Naming:** `feat/description` where description is concise
3. **Merge Strategy:** Use `git merge --no-ff` to preserve task branch history when merging into integration branches

## Verification

Before merging subagent work:
- Run linter: `.venv/bin/ruff check . --exclude .venv`
- Run tests: `.venv/bin/python -m pytest tests/ -x -q`
- Review diff for unintended changes
- Ensure only task-related files are modified

## Lessons Learned (2026-05-05)

### Test Infrastructure Issues
Some tests fail due to **MagicMock objects being JSON serialized** - this is a test infrastructure issue, not a code bug. When `_dispatch_next` is imported from `services.pipeline_utils` but called from `tasks.pipeline`, the mock patch target matters:

```python
# WRONG - patches where function is defined, not where it's used
patch("services.pipeline_degradation._dispatch_next")

# CORRECT - patches where function is looked up at runtime
patch("tasks.pipeline._dispatch_next")  # if tasks.pipeline imports it
# or
patch("services.pipeline_utils._dispatch_next")  # if that's where it's used
```

### Layer Violations
- `adapters/` should NOT import from `services/`
- Utils should contain pure helper functions with no external dependencies
- RawItem dataclass moved to `schemas/item.py` as Pydantic model

### Pre-existing Test Failures
Before starting a new wave, always check if tests were already failing:
```bash
git stash
.venv/bin/python -m pytest tests/ -x -q  # see if tests pass without your changes
git stash pop
```

### Lessons Learned (2026-05-06)

**Critical Bugs Fixed:**
- `adapters/web.py` line 35-37 had syntax corruption (`u/a`) - fixed with proper conditional
- `adapters/base.py` imported from `services.trend_detector` violating layering - moved to local `_classify_topics()` function
- `adapters/web.py` imported `MIN_CONTENT_LENGTH` from `services.config_unified` - added constant to adapter

**SQLAlchemy Reserved Names:**
- `metadata` is reserved by SQLAlchemy - use `meta` instead for JSON fields

**Limiter Release Fix:**
- Early return in `run_stage()` released limiter with `model=None` creating wrong Redis key
- Should use `rc.model` from config since it's available at that point

**Log Call Argument Order:**
- `_log_pipeline(run_id, stage, level, message, *args, article_id=None)` - verify correct order when calling

### Lessons Learned (2026-05-08)

**Architecture Review Process:**
- All 10 architecture docs reviewed with subagents
- Generated detailed review plans in `plans/review_*.md`
- Fixed critical bug: missing `import random` in `adapters/web.py`

**Documentation Fixes Applied:**
- overview.md: Fixed subagent location (services/subagent/), added all 14 LLM providers
- adapters.md: Fixed SSRFSafeRedirectHandler inheritance, clarified javascript:/data: blocking
- pipeline.md: Fixed editor/researcher max_tokens, added complete selector config, clarified dynamic fallback chain
- subagent.md: Fixed run_subagent_with_tools signature, replaced non-existent Chain classes, fixed usage example
- routes.md: Removed /api/v1 prefix (endpoints at root), added missing endpoints, added /share note
- tasks.md: Added all 14 Celery Beat tasks with accurate schedules
- utils.md: Fixed format_date (relative time), validate_url_safe (str return, raises UnsafeURLError)
- schemas.md: Fixed PipelineRootConfig, ResearchBrief, CondensedArticle, NewsletterBrief, task schemas

**Key Findings from Review:**
- Subagent location: `services/subagent/` not top-level `subagent/`
- API endpoints: Root-level (`/articles`) not prefixed (`/api/v1/articles`)
- StageConfig: Only has `tools` field, actual config in `RoleConfig`/`SubagentStageConfig`
- ResearchBrief: Much more complex structure with nested models not simple fields
- ExecutiveSummary: Only has `summary` field, not the 6 documented fields
- Celery Beat: 14 tasks exist, only 5 were documented

**How to run architecture review:**
1. Run 10 subagents in parallel, each reviewing one module
2. Each subagent writes detailed findings to `plans/review_*.md`
3. Fix critical bugs immediately (e.g., missing imports)
4. Update documentation to match implementation
5. Commit each wave separately to enable easy rollback

### Wave 8 Completion (2026-05-08)

All documentation drift items from Waves 5-8 have been completed:

| Item | Fix Applied |
|------|-------------|
| `pipeline.md` hardcoded fallback chain (lines 239-241) | Replaced with dynamic chain explanation |
| `pipeline.md` backfill_embeddings | Added Scheduled Tasks section with backfill-embeddings (2 AM) |
| `models.md` finalized_at (line 61) | Removed from Article model example |

**Commits:**
- `docs/pipeline-wave8-fix`: docs(pipeline): fix hardcoded fallback chain diagram, add backfill schedule
- `docs/models-wave8-fix`: docs(models): remove finalized_at from Article model example
- Merged to `dev/unified-implimentation` via octopus merge

### Wave Review Session (2026-05-09)

**Issue Found and Fixed: SSRF Import Layering Violation**

Adapters were incorrectly importing from `services.url` instead of `utils.url`:

| File | Before | After |
|------|--------|-------|
| `adapters/rss.py:12` | `from services.url import` | `from utils.url import` |
| `adapters/api.py:11` | `from services.url import` | `from utils.url import` |
| `adapters/web.py:15` | `from services.url import` | `from utils.url import` |
| `adapters/session.py:8` | `from services.url import` | `from utils.url import` |

**Why this matters:** Per architecture layering rules, adapters (infrastructure) should NOT import from services (business logic). Both `services/url.py` and `utils/url.py` have `validate_url_safe` and `UnsafeURLError`, but only `utils/url.py` is the correct import for adapters.

**Documentation Fix: utils.md return type**

Changed `architecture/utils.md:19` from `def validate_url_safe(url: str) -> bool:` to `def validate_url_safe(url: str) -> str:` with note that it returns the validated URL string. The function raises `UnsafeURLError` on invalid URLs, so the return type should be `str` (the validated URL).

**Verification Complete:**
- Wave 5: Both bugs (limiter slot leak, _log_pipeline args) verified fixed
- Wave 6: SSRF layering fix applied, TYPE_CHECKING pattern and review stage verified
- Wave 7: All 4 tasks verified (StageConfig, utils modules, no DeepSeek, RSS gaps)
- Wave 8: All 6 documentation items verified correct (minor return type fix in utils.md)

### Wave 9 Completion (2026-05-09)

All items from plans/plan.md completed. Summary of changes:

**Wave A - Bug Fixes (10 bugs):**
| Bug | Fix |
|-----|-----|
| BUG-1.1 | Defined `idempotency_key` in `_generate_daily_newsletters_core()` scope |
| BUG-1.3 | Added `SELECTING`, `SELECTED`, `WRITTEN` to `PipelineStatus` and `VALID_TRANSITIONS` |
| BUG-1.5 | `_try_stage_work` returns actual model used; `limiter.release` uses `provider_id` |
| BUG-1.6 | Already handled correctly with `if provider_id:` guard |
| BUG-1.7 | Removed redirect counter reset on success in `SSRFSafeRedirectHandler` |
| BUG-1.8 | Added `logger.warning` for date parsing failures in `WebAdapter._parse_date()` |
| BUG-1.9 | Split trafilatura exception handling - `ImportError` separate from `ValueError/AttributeError` |
| BUG-1.10 | Added `api_tokens_bp` registration in `app.py` |
| BUG-1.11 | `require_auth` now returns JSON 401 for `/api*` routes |
| BUG-1.13 | Removed duplicate import of `load_providers_config` |

**Wave B-D - Documentation & Implementation Fixes:**
- TASK-2.3 through TASK-2.23: All schema, routes, and architecture documentation updated
- TASK-2.14, 2.15, 2.16, 2.18: Decisions documented (feature not implemented → docs removed, or feature exists → documented)

**Wave E - Medium Priority Documentation:**
- TASK-3.1, 3.2, 3.7, 3.15, 3.16: Stage vs status glossary, blueprint structure, retry system, degradation behavior

**Wave F - Cleanup:**
- TASK-4.2, 4.4: `__all__` exports cleaned, YAML config examples updated
- TASK-4.8, 4.10: Verified as not issues (dead code was live, tasks→services allowed)

**Key Branches Created:**
- `fix/bug-1-1-newsletter-lock-nameerror`
- `fix/bug-1-3-missing-selecting-selected`
- `fix/bug-1-5-1-6-pipeline-limiter`
- `fix/bug-1-7-ssrf-redirect-bug`
- `fix/bug-1-8-1-9-webadapter`
- `fix/bug-1-10-1-11-api-tokens`
- `fix/bug-1-13-duplicate-import`
- Subagent branches for Wave B, C, E, F

**Commits:**
- All bug fixes committed to separate branches
- Documentation fixes committed via subagents
- `plans/plan.md` marked COMPLETED
- `AGENTS.md` updated to mark all bugs as FIXED