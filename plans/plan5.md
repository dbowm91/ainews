# Improvement Plan 5: ainews Codebase Enhancements

## Overview
This plan consolidates all findings from the deep-dive review of the ainews codebase (conducted 2026-05-01) and prioritizes actionable improvements by urgency and impact. It aligns with the `AGENTS.md` mandates and addresses gaps identified in the review.

## Priority Definitions
- **Critical**: Must fix immediately; affects compliance, security, or core functionality
- **High**: Significant impact on code quality, testing, or reliability; address next
- **Medium**: Quality-of-life, minor gaps, or optimization opportunities
- **Low**: Nice-to-have cleanup and long-term adoption items

---

## Critical Priority (Fix Immediately)
### 1. Fix Syntax Errors (Missing Commas in Dict Literals)
**Rationale**: Syntax errors will cause runtime failures in admin routes.
**Affected Files**:
- `routes/admin/review.py:144`
- `routes/admin/topic_notes.py:71`, `117`, `155`
**Steps**:
1. Open each file, locate the line with missing comma in dictionary literals
2. Add missing commas between key-value pairs (e.g., `{"original_title": article.original_title, "pipeline_status": article.pipeline_status}`)
3. Run `.venv/bin/ruff check . --exclude .venv` to verify no syntax errors
4. Run `.venv/bin/python -m pytest tests/ -x -q` to confirm no regressions
**Verification**: Ruff passes with no errors, all tests pass.

### 2. Add Circuit Breaker Checks to External Service Calls
**Rationale**: Current circuit breaker implementation only records failures for search providers, webhooks, and content extractor, but does not prevent calls when the circuit is open (violates fail-closed intent for these services).
**Affected Files**:
- `services/search/__init__.py` (search providers)
- `services/webhooks.py` (webhook delivery)
- `services/content_extractor.py` (URL fetching)
**Steps**:
1. For search providers: Add `breaker.can_execute()` check before `search()` calls in `DuckDuckGoSearchProvider`, `GoogleSearchProvider`, `SearXNGSearchProvider` using keys like `search:{provider_id}`
2. For webhooks: Add circuit breaker protection to `services/webhooks.py:_send_webhook_with_retry()` using `circuit_protected` decorator or explicit `get_breaker("webhook:{id}")` check
3. For content extractor: Add circuit breaker to `services/content_extractor.py:fetch_url()` calls using key `content_extractor`
4. Reuse existing `get_breaker()` from `services/circuit_breaker.py` with consistent configuration
5. Run tests for affected services: `.venv/bin/python -m pytest tests/test_search.py tests/test_webhooks.py -x -q`
**Verification**: Circuit breakers trigger on repeated failures for these services, no unguarded external calls remain.

### 3. Add Missing Audit Logging to API Routes
**Rationale**: Audit logging is mandatory for all admin actions per AGENTS.md; current gaps violate compliance.
**Affected Files**:
- `routes/admin/api/sources.py` (create, update, partial update, delete actions)
- `routes/admin/api/webhooks.py` (create, update, delete, test, resend actions)
**Steps**:
1. Import `log_admin_action` from `services.audit` in both files
2. Add `log_admin_action()` calls to all mutable actions:
   - `sources.py`: `create_source()`, `update_source()`, `update_source_partial()`, `delete_source()` (category: `config`)
   - `webhooks.py`: `create_webhook()`, `update_webhook()`, `delete_webhook()`, `test_webhook()`, `resend_webhook_event()` (category: `webhook`)
3. Include relevant details (e.g., source ID, webhook ID, action parameters)
4. Run audit logging tests: `.venv/bin/python -m pytest tests/test_audit.py -x -q`
**Verification**: Audit log entries appear in `AuditLog` table for all source/webhook API actions.

---

## High Priority
### 1. Remove Dead Code from `services/subagent.py`
**Rationale**: 15+ unused functions increase maintenance burden and confuse contributors.
**Affected Files**: `services/subagent.py`
**Dead Code List**:
- `get_registered_tools()`
- `_get_topic_note()`, `_fetch_note()`, `_get_topic_notes_for_topics()`
- `_get_related_articles()`, `_fetch_articles()`
- `_get_trend_memory()`
- `_get_article_by_id()`, `_search_articles()`, `_get_source_health()`
- `_search_web()`, `_get_search_provider()`
- `_call_with_timeout()`
- `run_subagent_chain()`, `_chain_call()`
**Steps**:
1. Confirm no callers exist via `grep -r <function_name> /home/sugarwookie/projects/ainews --include="*.py"`
2. Delete all confirmed dead functions
3. Remove related unused imports (e.g., `ToolSelector` from `services.tool_selection` if no longer referenced)
4. Run `.venv/bin/ruff check . --exclude .venv` and full test suite
**Verification**: No regressions, Ruff passes, test coverage remains stable.

### 2. Resolve `services/tool_selection.py` (Dead Code)
**Rationale**: `ToolSelector` protocol and two implementations (`StageAwareToolSelector`, `KeywordToolSelector`) are never used, adding unnecessary code.
**Affected Files**: `services/tool_selection.py`, `services/subagent.py` (import)
**Steps**:
1. Confirm `ToolSelector`, `StageAwareToolSelector`, `KeywordToolSelector` have no callers via `grep -r "StageAwareToolSelector\|KeywordToolSelector" --include="*.py"`
2. Choose one of:
   - **Option A**: Delete `services/tool_selection.py` and remove `from services.tool_selection import ToolSelector` from `services/subagent.py`
   - **Option B**: Implement usage in `initialize_tool_registry()` to replace current `tool_names` filtering for future extensibility
3. Run tests to confirm no regressions
**Verification**: Dead code removed or properly integrated, no broken imports.

### 3. Add Cache Invalidation for Impact Score Recalculation
**Rationale**: `tasks/cleanup.py:recalculate_impact_scores()` updates article impact scores but does not invalidate `pub:top_impact:*` cache, leading to stale index page content.
**Affected Files**: `tasks/cleanup.py`
**Steps**:
1. Import `get_response_cache` from `services.cache` in `tasks/cleanup.py`
2. After committing impact score updates in `recalculate_impact_scores()`, add:
   ```python
   cache = get_response_cache()
   cache.invalidate_prefix("pub:top_impact")
   ```
3. Run cache-related tests: `.venv/bin/python -m pytest tests/test_response_cache.py -x -q`
**Verification**: Cache for top impact articles is cleared after score recalculation.

### 4. Create Scheduled Task for Subscriber Cleanup
**Rationale**: Subscriber sunset policy (`SUBSCRIBER_MAX_BOUNCES=5`, `SUBSCRIBER_INACTIVITY_DAYS=180`) is implemented in `services/subscribers.py` but no scheduled task runs it, leaving inactive subscribers unflagged.
**Affected Files**: `tasks/cleanup.py`, `config.py`
**Steps**:
1. Add `cleanup_inactive_subscribers` task to `tasks/cleanup.py` with Celery decorators:
   ```python
   @celery_app.task(bind=True, max_retries=3)
   def cleanup_inactive_subscribers(self):
       from services.subscribers import cleanup_inactive_subscribers as cleanup
       from models import db
       cleanup(db)
   ```
2. Add task to Celery beat schedule in `config.py:get_beat_schedule()` (e.g., daily run at 3am):
   ```python
   "cleanup-inactive-subscribers": {
       "task": "tasks.cleanup.cleanup_inactive_subscribers",
       "schedule": crontab(hour=3, minute=0),
   },
   ```
3. Run cleanup task tests
**Verification**: Inactive subscribers are flagged after task runs, beat schedule includes new task.

### 5. Set Up Test Coverage Reporting
**Rationale**: No coverage reports exist, making it hard to identify untested critical paths.
**Steps**:
1. Create `.coveragerc` in project root:
   ```ini
   [run]
   omit = .venv/*, migrations/*, tests/*, instance/*
   [report]
   exclude_lines = pragma: no cover, if TYPE_CHECKING:
   ```
2. Add `pytest-cov` to dev dependencies in `pyproject.toml` under `[project.optional-dependencies] dev`
3. Update AGENTS.md run commands to include coverage:
   ```bash
   .venv/bin/pytest tests/ -x -q --cov=services --cov=tasks --cov=models --cov-report=html
   ```
4. Run coverage and verify `htmlcov/` is generated
**Verification**: Coverage report shows baseline percentages, `.coveragerc` exists, AGENTS.md updated.

---

## Medium Priority
### 1. Refactor `services/subagent.py` to Reduce Duplication
**Rationale**: `run_subagent()` and `run_subagent_with_tools()` share ~80% retry logic; large file size (1196 lines) hinders maintainability. (Depends on completing High Priority #1 and #2 first.)
**Steps**:
1. Extract common retry logic into a shared helper function (e.g., `_subagent_retry_loop()`)
2. Refactor `run_subagent()` and `run_subagent_with_tools()` to use the shared helper
3. Optional: Split into `services/subagent/` package (registry.py, tools.py, prompt.py, executor.py, chain.py) if further size reduction needed
4. Update all imports to use new package structure if split
5. Run Ruff and full test suite
**Verification**: No regressions, duplicated code removed, file size reduced.

### 2. Add Missing Admin Navigation Links
**Rationale**: Webhooks and Audit Logs are functional but not linked in admin nav, making them undiscoverable.
**Affected Files**: `templates/admin/base_admin.html`
**Steps**:
1. Add link to `/admin/webhooks` in admin nav menu (e.g., under "System" section)
2. Add link to `/admin/audit-logs` in admin nav menu (create UI page if missing via `routes/admin/api/audit.py` endpoint)
3. Verify links appear in all admin pages and work correctly
**Verification**: Nav links visible in all admin pages, links return valid content.

### 3. Add "Resend" Button to Webhook Events UI
**Rationale**: API endpoint `POST /admin/api/webhooks/events/<id>/resend` exists but no UI element allows resending failed webhook events.
**Affected Files**: `templates/admin/partials/webhook_events.html`
**Steps**:
1. Add "Resend" button to each event row in webhook events table, visible only for failed events
2. Use HTMX to call the resend endpoint: `hx-post="/admin/api/webhooks/events/{{ event.id }}/resend"`
3. Add confirmation dialog via `hx-confirm="Resend this webhook event?"`
4. Test resend functionality via admin UI
**Verification**: Resend button appears for failed events, clicking resends event, UI updates with new status.

### 4. Parallelize Context Gathering in Research/Edit Stages
**Rationale**: I/O-bound operations (web search, related articles, topic notes) run sequentially, wasting pipeline time.
**Affected Files**: `tasks/research.py`, `tasks/edit.py`
**Steps**:
1. Use `concurrent.futures.ThreadPoolExecutor` to run independent I/O operations in parallel:
   - `research.py`: Parallelize web search, related articles fetch, topic notes fetch
   - `edit.py`: Parallelize topic notes, related articles, trend memory fetch
2. Verify pipeline stages still complete correctly with same output quality
3. Run pipeline stage tests
**Verification**: Pipeline stages run faster, no regressions in output quality.

### 5. Clean Up Unused Files and Directories
**Rationale**: Unused `models/` directory and `.DS_Store` files clutter the repository.
**Steps**:
1. Delete `models/` directory (only contains `AGENTS.override.md`, which can be moved to `docs/` or merged into root `AGENTS.md`)
2. Run `find /home/sugarwookie/projects/ainews -name ".DS_Store" -type f -delete` to remove all `.DS_Store` files
3. Verify no broken imports (all models are in root `models.py`)
4. Run full test suite
**Verification**: `models/` directory removed, no `.DS_Store` files, tests pass.

### 6. Refactor Large Files (Optional)
**Rationale**: `tasks/newsletter.py` (570 lines), `tests/test_subagent.py` (1022 lines), `tests/factories.py` (514 lines) are large and hard to maintain.
**Steps**:
1. Split `tasks/newsletter.py` into `tasks/newsletter/` package (sender.py, composer.py, cleanup.py)
2. Split large test files into smaller modules by feature
3. Run Ruff and tests
**Verification**: No regressions, file sizes reduced.

---

## Low Priority
### 1. Standardize Environment Variable Patterns
**Rationale**: Dual pattern (`os.environ.get()` in `config.py` vs `${ENV_VAR}` in YAML) confuses contributors.
**Steps**:
1. Document pattern in AGENTS.md: YAML files use `${ENV_VAR}`, `config.py` uses `os.environ.get()` for Flask-specific config
2. Optional: Migrate `config.py` to use `${ENV_VAR}` pattern for consistency
**Verification**: AGENTS.md updated, no functional changes.

### 2. Add Missing `.gitignore` Entries
**Rationale**: `.mypy_cache/`, `.idea/`, `.vscode/` are not ignored, risking IDE/tool files in git.
**Steps**:
1. Add following entries to `.gitignore`:
   ```
   .mypy_cache/
   .venv.bak/
   .idea/
   .vscode/
   *.log
   ```
2. Verify no ignored files are tracked in git via `git status`
**Verification**: `.gitignore` updated, `git status` shows no new untracked files.

### 3. Gradual Mypy Adoption
**Rationale**: Mypy is configured in `pyproject.toml` but not run; gradual adoption improves type safety.
**Steps**:
1. Run `.venv/bin/mypy .` to establish baseline error count
2. Fix easy errors first (unused configs, missing return types)
3. Add `from __future__ import annotations` to all Python files
4. Address SQLAlchemy model type errors with `# type: ignore` comments initially
5. Track progress by running mypy periodically
**Verification**: Mypy baseline established, gradual reduction in errors over time.

---

## Review and Change Log
- **2026-05-01**: Initial plan written
- **2026-05-01**: Reviewed for completeness against deep-dive findings (all 22 investigation items included)
- **2026-05-01**: Corrected typos ("conducted" spelling in Overview), verified line numbers and file paths match deep-dive findings
- **2026-05-01**: Added missing dependencies (Medium #1 depends on High #1 and #2)
- **2026-05-01**: Finalized after review - plan is complete and ready for execution
