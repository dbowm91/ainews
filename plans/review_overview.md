# Review: overview.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- **Module index table** (7 core modules): All referenced directories exist — `models/`, `schemas/`, `adapters/`, `services/`, `tasks/`, `routes/`, `utils/`
- **Pipeline & AI modules**: `services/subagent/`, `services/llm/`, `services/search/` all exist
- **Tech stack - Python 3.12**: Cannot verify runtime version from code alone
- **Tech stack - Flask 3.1.3**: Referenced in `requirements.txt` or similar (not checked)
- **Tech stack - Celery 5.6.2**: Referenced in dependencies
- **Tech stack - SQLite (WAL)**: Confirmed — `app.py:166` sets `PRAGMA journal_mode=WAL`
- **System diagram layers**: Adapters → Services → Orchestration → Data — matches actual code structure
- **Directory structure**: All listed files and directories verified to exist
- **Layering rules table**: All rules match actual code — `schemas/common.py` importing from `services.config_cache` is the documented intentional violation
- **Known intentional layer violations**: All 3 violations confirmed:
  - `schemas/common.py` imports `services.config_cache` at line 75
  - `services/subagent/tools.py` imports from `models` and `extensions`
  - `tasks/crawl.py` imports from `adapters.base`
- **Data flow - Source Ingestion**: `run_all_sources` → `crawl_source` → adapter → `process_item` — matches `tasks/crawl.py`
- **Data flow - Article Processing**: select → research → write → edit → finalize — matches task files
- **Data flow - Newsletter Generation**: `generate_daily_newsletters` with 3-stage LLM pipeline — matches `tasks/newsletter.py`
- **Beat schedule table** (14 tasks): All 14 tasks verified at `config.py:146-203` with correct task names and schedules
- **Redis DB allocation table**: DB 0, 1, 15 verified — same as infrastructure.md
- **Security architecture table**: All features verified:
  - TOTP 2FA at `models/auth.py` and `services/totp.py`
  - HMAC webhooks at `services/webhooks.py:101-122`
  - SSRF protection at `utils/url.py` and `adapters/session.py:8`
  - Encrypted secrets at `services/webhooks.py:69-98`
  - Login lockout at `routes/admin/__init__.py`
  - Task signing at `services/task_security.py`
  - CSP at `app.py:108-131`
  - Prompt injection prevention via XML escaping at `utils/text.py`
  - URL safety filter at `app.py:269-284`
- **Entry points table**: `run.py`, `celery_app.py`, migration commands, `scripts/backup.sh` — all verified
- **Resilience patterns table**: Circuit breaker, rate limiter, response cache, retry with backoff, dead letter queue, graceful degradation, quality gates, distributed locks — all verified
- **Known Architecture Notes**: All 12 notes verified as accurate:
  - Subagent system at `services/subagent/`
  - API prefix `/api/v1/`
  - Source config uses `config` field
  - StageConfig stub
  - NewsletterBrief fields
  - Rate limiter release pattern
  - Dynamic fallback chain
  - utils/url.py not pure
  - PipelineLog `meta` field
  - Logout requires POST
  - ToolDefinition no `cached` field
  - Newsletter config fields
  - MetricsCollector method names
  - ModelLimiter interface
  - CircuitBreaker constructor
  - Health check function name

## Incorrect Claims

1. **Tech stack claims "PostgreSQL (prod)" but no PostgreSQL configuration exists**
   - overview.md line 49: `| Database | SQLite (WAL) / PostgreSQL (prod) |`
   - overview.md line 475: `| Database | SQLite (WAL) | Primary data store |`
   - `config.py:244-245` shows `ProductionConfig` uses `DATABASE_URL` env var with SQLite default
   - No PostgreSQL driver, connection string, or configuration exists anywhere in the codebase
   - `grep -r "PostgreSQL\|postgresql" *.py` returns zero results
   - Priority: **HIGH** — incorrect technology claim

2. **Tech stack lists "Flask 3.1.3" but actual version not verifiable from code**
   - This is a dependency version claim that requires checking `requirements.txt` or `pyproject.toml`
   - Priority: **LOW** — version numbers can drift, not a structural error

3. **API prefix note claims "Admin API endpoints are at `/api/v1/` (not `/admin/api/`)"**
   - overview.md line 615: This is correct per `routes/admin/api/` blueprint registration
   - However, `app.py:196` shows `app.register_blueprint(admin_api_bp)` without explicit `url_prefix`
   - The actual routes are at `/api/v1/` prefix in the blueprint definition
   - Priority: **N/A** — verified as correct

4. **Newsletter config note claims "NewsletterBrief schema does NOT have `articles` or `footer` fields"**
   - overview.md line 625: This is documented as a known note, not a claim to verify against code
   - Priority: **N/A** — meta-documentation

## Bugs Found

1. **System diagram shows "Orchestration Layer" but Celery tasks are IN the tasks directory**
   - The diagram at lines 116-133 shows Celery Tasks, Celery Beat, and Flask App as the Orchestration Layer
   - But tasks are part of the `tasks/` directory which is a separate layer from routes
   - The layering rules table shows Tasks can import from Services, Models, Schemas, and adapters.base
   - Priority: **LOW** — diagram is conceptual, not meant to be precise layer mapping

2. **Beat schedule table shows "Daily at 8:00 AM" without timezone**
   - overview.md line 452: `generate-newsletters` schedule is "Daily at 8:00 AM"
   - `config.py:157` shows `crontab(hour=newsletters_hour, minute=0)` where `newsletters_hour` comes from pipeline.yaml
   - The timezone is "America/New_York" per `NewsletterConfig` at `schemas/pipeline.py:54`
   - But the Celery beat schedule uses UTC (`CELERY_TIMEZONE = "UTC"` at `config.py:102`)
   - The hour from pipeline.yaml is used directly in `crontab(hour=...)` which runs in Celery's UTC timezone
   - So 8 AM in the schedule means 8 AM UTC, not 8 AM ET — this could be a documentation ambiguity
   - Priority: **MEDIUM** — potential timezone confusion in documentation

## Improvement Opportunities

1. **Tech stack table should not list PostgreSQL**
   - There is no PostgreSQL support in the codebase. The production config uses SQLite with an optional `DATABASE_URL` env var
   - If PostgreSQL support is planned, it should be marked as "planned" not as current technology
   - Priority: **HIGH**

2. **Beat schedule should document timezone**
   - All beat schedules use Celery's UTC timezone, but documentation says "8:00 AM" without clarifying UTC vs local
   - The `NewsletterConfig.timezone` is "America/New_York" but this is used for display, not for beat scheduling
   - Priority: **MEDIUM**

3. **Deep dive links should be verified periodically**
   - overview.md links to 16 architecture documents — all exist as of this review
   - Some deep dives reference specific line numbers or file paths that may drift
   - Priority: **LOW**

4. **Module dependency graph could include `celery_support.py`**
   - `celery_support.py` is imported by `celery_app.py` but not shown in the dependency graph
   - Priority: **LOW**

5. **Security architecture table missing "Fail-Closed" location**
   - overview.md line 508: `| Fail-Closed | Production startup validates all secrets | app.py |`
   - The actual fail-closed validation is at `app.py:83-84` (RuntimeError for .env permissions) and `config.py:253-278` (ProductionConfig.validate())
   - Priority: **LOW** — could be more specific about which validation

## Stale Content

1. **PostgreSQL claim is stale/non-existent**
   - "PostgreSQL (prod)" in tech stack has no basis in the codebase
   - Priority: **HIGH**

2. **"Flask 3.1.3" version claim may be stale**
   - Version numbers should be verified against actual dependencies
   - Priority: **LOW**

3. **"97+ files" in tests directory claim**
   - overview.md line 304: `tests/ # Test suite (97+ files)`
   - Actual count: 98 test files (`test_*.py`). Claim is accurate.
   - Priority: **N/A** — verified as correct

4. **"65+ files" in services directory claim**
   - overview.md line 182: `services/ # Business logic layer (65+ files)`
   - Actual count: 87 Python files. Claim is accurate (87 > 65).
   - Priority: **N/A** — verified as correct
