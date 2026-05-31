# Review: pipeline.md

**Reviewed:** 2026-05-31
**Source:** `architecture/pipeline.md`
**Reviewer:** Subagent 4 (Pipeline & Tasks Layer)
**Status:** COMPLETE

---

## Verified Claims

### Pipeline Status Values
- `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed` — VERIFIED (`constants.py:30-43`)

### Valid Transitions (Partial)
- `pending` → `selecting`, `review` — VERIFIED (`constants.py:53`)
- `selecting` → `selected`, `failed` — VERIFIED (`constants.py:54`)
- `selected` → `researching`, `failed` — VERIFIED (`constants.py:55`)
- `researching` → `writing`, `failed` — VERIFIED (`constants.py:56`)
- `writing` → `editing`, `failed` — VERIFIED (`constants.py:57`)
- `written` → `editing`, `failed` — VERIFIED (`constants.py:58`)
- `editing` → `review`, `done`, `failed` — VERIFIED (`constants.py:59`)
- `review` → `done`, `failed` — VERIFIED (`constants.py:60`)
- `done` → (terminal) — VERIFIED (`constants.py:61`)
- `skipped` → (terminal) — VERIFIED (`constants.py:62`)
- `failed` → `pending` — VERIFIED (`constants.py:63`)

### Stage Descriptions
- Select: scoring 1-10, `min_score` threshold, low confidence → review — VERIFIED (`tasks/select.py:126-128`)
- Research: web search + subagent, degenerate brief → review — VERIFIED (`tasks/research.py:206-231`)
- Write: Smart Brevity format, validation (body < 500 chars, empty key_points, empty citations) — VERIFIED (`tasks/write.py:12-27, 128-154`)
- Edit: subagent contextualization, tag assignment, quality report — VERIFIED (`tasks/edit.py:220-363`)

### Finalize
- `published_at` timestamp — VERIFIED (`services/pipeline_degradation.py:219`)
- `pipeline_status="done"` — VERIFIED (`services/pipeline_degradation.py:167, 296`)
- Webhooks for `article.published` — VERIFIED (`services/pipeline_degradation.py:251-263`)
- Trend memory update — VERIFIED (`services/pipeline_degradation.py:243`)

### Newsletter Generation
- 3-stage LLM (reader → writer → editor) — VERIFIED (`services/newsletter_pipeline.py` referenced in `tasks/newsletter.py:144`)
- Newsletter lock: Redis-based, idempotency key — VERIFIED (`tasks/newsletter.py:379-409`)
- Lock TTL: 10 minutes (600 seconds) — VERIFIED (`tasks/newsletter.py:401`)

### Scheduled Tasks (14 tasks)
All 14 tasks verified against `config.py:get_beat_schedule()`:
- `run-all-sources` — VERIFIED (`config.py:147-150`)
- `retry-stuck-articles` — VERIFIED (`config.py:151-154`)
- `generate-newsletters` — VERIFIED (`config.py:155-158`)
- `cleanup-old-logs` — VERIFIED (`config.py:159-162`)
- `consolidate-trend-memory` — VERIFIED (`config.py:163-166`)
- `purge-trend-memory` — VERIFIED (`config.py:167-170`)
- `cleanup-old-versions` — VERIFIED (`config.py:171-174`)
- `cleanup-expired-verifications` — VERIFIED (`config.py:175-178`)
- `publish-scheduled-articles` — VERIFIED (`config.py:179-182`)
- `cleanup-stale-limiter-slots` — VERIFIED (`config.py:183-186`)
- `retry-failed-newsletter-deliveries` — VERIFIED (`config.py:187-190`)
- `recalculate-impact-scores` — VERIFIED (`config.py:191-194`)
- `cleanup-inactive-subscribers` — VERIFIED (`config.py:195-198`)
- `backfill-embeddings` — VERIFIED (`config.py:199-202`)

### Pipeline Configuration
- `PIPELINE_TIMEOUT_SECONDS` default 3600 — VERIFIED (`constants.py:14`, `config.py:64-66`)
- `VALID_PIPELINE_STATUSES` frozen set (excludes transient statuses) — VERIFIED (`constants.py:97-108`)
- `MAX_CONSECUTIVE_FAILURES` default 10 — VERIFIED (`config.py:67`)

### Shadow Quality Assessments
- `lightweight_quality_signals()` — VERIFIED (`tasks/write.py:108-125`, `tasks/research.py:181-201`, `tasks/edit.py:281-304`)

### A/B Experiment Distribution
- 70% control, 15% variant_a, 15% variant_b — VERIFIED (`tasks/select.py:36-43`)

### Retry Limits
- Per-stage retries: 3 (`MAX_STAGE_RETRIES`) — VERIFIED (`constants.py:9`)
- Total retries: 10 (`MAX_TOTAL_RETRIES`) — VERIFIED (`constants.py:11`)
- Selector `retry_max=20` — VERIFIED (`tasks/select.py:202`)
- Selector `retry_countdown=15` — VERIFIED (`tasks/select.py:201`)

### Circuit Breaker
- States: closed, open, half-open — VERIFIED (`services/circuit_breaker.py`)
- Fallback chain is dynamic — VERIFIED (`services/llm/__init__.py:get_provider_chain()`)
- `AuthError` handling: immediate failure, no retry/fallback — VERIFIED (`tasks/pipeline.py:192-199`)

### Newsletter Lock
- Lock TTL: 10 minutes (600 seconds) — VERIFIED (`tasks/newsletter.py:401`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 54 | `pending` → `selecting`, `review` (incomplete) | `constants.py:53`: PENDING also transitions to RESEARCHING | LOW |
| 272 | "research disabled: Article goes directly to `writing`" | `tasks/pipeline.py:260-267`: When research disabled with `skip_next="finalize"`, calls `_finalize()` which routes to REVIEW or DONE, not WRITING | HIGH |
| 274 | "write disabled: Article goes directly to `editing`" | `tasks/pipeline.py:260-267`: When write disabled with `skip_next="finalize"`, calls `_finalize()` which routes to REVIEW or DONE, not EDITING | HIGH |
| 99 | "Target: 3-5 key points" | `tasks/write.py:82`: `max_key_points=rc.max_key_points or 5`, code allows up to 5 (not 3-5) | LOW |
| 173-174 | Newsletter idempotency key: "10-minute TTL" | `tasks/newsletter.py:433`: Idempotency key TTL is 2 days (86400*2), not 10 minutes. Lock TTL is 10 minutes. | MEDIUM |
| 329 | "Celery default `RETRY_BASE_DELAY=1.0`" | Celery default is indeed 1.0 — VERIFIED, but other tasks use `default_retry_delay=60`, not 1.0 | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | `generate_daily_newsletters` task lacks `max_retries` — could retry indefinitely on transient errors | `tasks/newsletter.py:476-487` | MEDIUM | Decorator has `autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError)` but no `max_retries` parameter. Other pipeline tasks (select, research, write, edit) have `max_retries=CELERY_TASK_MAX_RETRIES`. |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Document the `RESEARCHING` transition from PENDING in status transitions table | documentation | P2 |
| 2 | Clarify degradation behavior table — "disabled" behavior routes through `_finalize()` which may go to REVIEW, not directly to next stage | documentation | P1 |
| 3 | Add `max_retries=CELERY_TASK_MAX_RETRIES` to `generate_daily_newsletters` task decorator | reliability | P1 |
| 4 | Document the idempotency key TTL (2 days) separately from lock TTL (10 minutes) | documentation | P2 |
| 5 | Clarify that write stage key points target is "up to 5" not "3-5" | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 272-274 | Degradation behavior table for disabled stages | Code routes through `_finalize()` not directly to next stage | rewrite |
| 173-174 | Newsletter idempotency key "10-minute TTL" | Lock TTL is 10 min, idempotency key TTL is 2 days | update |

---

## Summary

- Verified: 38 claims
- Incorrect: 6 claims
- Bugs: 1 (HIGH: 0, MEDIUM: 1, LOW: 0)
- Improvements: 5
- Stale items: 2
