# Tasks & Pipeline Conventions

Contextual conventions for agents working in the `tasks/` directory.

## Celery Task Conventions

- All Celery tasks should include `acks_late=True` and `task_reject_on_worker_lost=True` in their decorator to ensure task is not lost on worker crash.
- Use `CELERY_TASK_MAX_RETRIES` and `CELERY_TASK_DEFAULT_RETRY_DELAY` constants for configuring task retries to ensure consistency across the worker fleet.
- Beat-scheduled tasks need HMAC verification via `verify_task()` from `services/task_security.py`.
- Internal pipeline tasks (research, write, edit) do NOT need HMAC verification as they are dispatched internally.
- External task arguments must be validated with Pydantic schemas in `schemas/tasks.py` (SelectArticleTask, GenerateNewsletterTask, SendEmailTask, CleanupArticleVersionsTask, ProcessItemTask).

## Redis Patterns

- Use Lua scripts for atomic lock/release operations to prevent race conditions.
- Use `blpop` instead of polling for stampede protection in `ResponseCache`.
- Avoid naming local variables `redis` to prevent shadowing the module import; use `redis_client` or `r`.

## State Machine for Pipeline

Use `constants.py:VALID_TRANSITIONS` for atomic state changes. NEVER assign `article.pipeline_status` directly in tasks; use `_transition_article_status()` to ensure validation and audit logging.

## Pipeline & Tasks

- **Write Status Transition Fix:** `tasks/write.py` has been fixed to prevent premature status transitions; it now correctly ensures an article is in the `RESEARCHED` state before moving to `WRITING`, and `WRITTEN` after completion.
- **Dead Letter Queue:** Managed via `/admin/dead-letters` UI.
- **E2E Latency Tracking:** `pipeline.e2e_duration_seconds` histogram records total pipeline latency from crawl to finalization.
- **Redis TTL Refresh:** L1 cache hits refresh Redis TTL via `self._redis.expire()` in `ResponseCache.get()`.
- **A/B Experiment System:** Config in `pipeline.yaml` under `experiments:` section with prompt variants for writer/editor, deterministic 70/15/15 split across control/variant_a/variant_b. Assignment via `_assign_experiment_group(article_id, salt)` in `tasks/select.py`, variant selection in `services/writer.py` and `services/editor.py`.
- **Soft Time Limit Persistence:** When Celery soft timeout occurs in pipeline stages, `pipeline.py` persists failure state (last_error, retry_count, total_retries) to DB before re-raising. Articles retain current `pipeline_status` to retry in-place from the timed-out stage, not from the beginning.

## Newsletter Tasks

- **Newsletter Webhooks:** `newsletter.py` fires `newsletter.failed` webhook on delivery failure, `newsletter.sent` webhook with correct `newsletter.id` (ORM model) in payload.