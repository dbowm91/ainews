# Implementation Plan - Consolidated & Refined

**Date:** May 10, 2026
**Status:** IN PROGRESS
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## Completed Work
All items from Waves 1-8 of the original implementation phase (April 18-19, 2026) are COMPLETED, including security hardening, LLM provider optimizations, and core performance improvements.

---

## WAVE 1: Critical Fixes & Security Hardening (Highest Priority)

**Focus:** Eliminating fail-open vulnerabilities and fixing critical data integrity issues.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W1.1** | Fix fail-open stage lock in pipeline | `tasks/pipeline.py:108-117` | `_acquire_stage_lock` currently returns `True` on `RedisError`. It MUST return `False` or raise to prevent race conditions when Redis is down. |
| **W1.2** | Fix fail-open newsletter lock | `tasks/newsletter.py:414-417` | `except redis.exceptions.RedisError` sets `lock_status = 2` (acquired). Change to raise or return 0 (skipped) to prevent concurrent newsletter generation. |
| **W1.3** | Fix Version Creation Order in Edit Task | `tasks/edit.py:332-335` | `create_article_version()` is called AFTER modifying `article.final_article`. Move it BEFORE modification to capture the state before AI editing. |
| **W1.4** | Session Fixation Prevention | `routes/admin/auth.py:55-58` | Ensure `session.clear()` is called immediately before setting `session["admin"] = True` on successful login. |
| **W1.5** | Webhook Secret Decryption Safety | `services/webhooks.py:325-340` | `_get_webhook_secret_from_db` returns `""` on decryption failure. This silently breaks auth. Should raise a specific error to allow the dispatcher to skip or retry. |
| **W1.6** | AuthError Transient Log Fix | `tasks/pipeline.py:187` | `AuthError` is logged as "transient error" but is actually terminal. Update log message to "non-retryable authentication error". |

**Parallelization:** W1.1-W1.2 (sequential in one task), W1.3, W1.4, W1.5-W1.6 can all be executed in parallel.

---

## WAVE 2: Pipeline Stability & Config (Priority 2)

**Focus:** Hardening the state machine and improving configuration robustness.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W2.1** | Consistent State Transitions | `tasks/write.py`, `tasks/research.py` | Replace direct `article.pipeline_status = ...` assignments with `_transition_article_status()` to ensure validation and audit logging. |
| **W2.2** | Quality Gate Logging | `tasks/research.py:222-223` | Add `_log_pipeline()` call before the early return at the quality gate to ensure the "review" routing is captured in logs. |
| **W2.3** | LLM Config Env Var Resolution | `schemas/llm.py:58-59` | `_load_providers_config_from_file` does not call `resolve_env_vars()` on raw YAML. Ensure `${VAR}` placeholders are resolved before schema validation. |
| **W2.4** | Per-Stage Circuit Breaking | `services/llm/__init__.py:62-66` | Key the circuit breaker by `provider+model+stage`. Currently, failure in one stage (e.g., research) can block all stages using that provider. |
| **W2.5** | Retry-After Header Support | `services/llm/base.py:155-167` | Update `_retry_with_backoff` to respect `Retry-After` headers if present in 429/503 responses. |
| **W2.6** | Configurable Failure Limits | `services/pipeline_failure.py` | Move `_MAX_STAGE_FAILURES = 3` to `constants.py` and make it configurable via `Config`. |

**Parallelization:** W2.1-W2.2, W2.3, W2.4-W2.5, W2.6 can all be executed in parallel.

---

## WAVE 3: Subagent & Search Improvements

**Focus:** Optimizing subagent performance and fixing search analytics.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W3.1** | Provider Fetch Optimization | `services/subagent.py` | Move `get_provider_for_role` call outside the retry loop to avoid redundant Redis/DB hits. |
| **W3.2** | Configurable Subagent Iterations | `services/subagent.py:722` | Replace hardcoded `10` iterations with a value from `pipeline.yaml`. |
| **W3.3** | Search Analytics Query Fix | `routes/admin/api/search.py` | Fix the query at line 20 that incorrectly aggregates search counts. |
| **W3.4** | Tag Feed Caching | `routes/public/feeds.py:172` | Implement caching for the tag-specific RSS feeds. |

---

## WAVE 4: Email & Newsletter Features

**Focus:** Improving email deliverability and AI-generated subjects.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W4.1** | Email Plain-Text Alternative | `services/email.py:187` | Generate and include a plain-text alternative in `MIMEMultipart('alternative')` for all outgoing emails. |
| **W4.2** | List-Unsubscribe Header | `services/email.py` | Add `List-Unsubscribe` and `List-Unsubscribe-Post` headers (RFC 8058) to newsletter emails. |
| **W4.3** | AI-Generated Newsletter Subject | `services/newsletter.py` | Use LLM to generate a catchy subject line based on the top stories in the newsletter instead of "Top Stories". |
| **W4.4** | Source CRUD API | `routes/admin/api/` | Implement missing API endpoints for programmatic source management. |

---

## WAVE 5: Frontend & Accessibility

**Focus:** Polishing the UI and adding user-facing state.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W5.1** | RSS Icon Replacements | `templates/base.html` | Replace `[rss]` text with the project-standard SVG icon. |
| **W5.2** | Mobile Nav UX | `templates/base.html` | Fix behavior where clicking a nav link doesn't close the mobile overlay on some browsers. |
| **W5.3** | Client-side Bookmarking | `static/js/app.js` | Implement localStorage-based bookmarking for users to save articles locally. |
| **W5.4** | Article Read State | `static/js/app.js` | Track read articles in localStorage and dim their titles in the feed. |

---

## WAVE 6: Observability & Metrics

**Focus:** Deeper insights into pipeline performance.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W6.1** | E2E Latency Histograms | `tasks/edit.py` | Record total pipeline latency (from crawl to finalization) using `pipeline.e2e_duration_seconds`. |
| **W6.2** | Pipeline Backlog API | `routes/admin/api/` | New endpoint to report the count of articles in each status. |
| **W6.3** | Subagent Context Caching | `services/subagent.py` | Wrap DB-heavy context lookups (`_get_topic_note`, `_get_related`) in short-lived `ResponseCache`. |

---

## WAVE 7: Backend Refinement & Quality

**Focus:** Database optimizations and schema improvements.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **W7.1** | Retry Count Indexes | `models.py` | Add indexes to `total_retries` and `status` columns for efficient cleanup and dashboard queries. |
| **W7.2** | Config Validation Errors | `services/config_unified.py` | Improve the detail returned when a YAML config fails validation (show path/line if possible). |
| **W7.3** | DNS Timeout Cancellation | `services/url.py:143-149` | Ensure `future.cancel()` is called on DNS lookup timeouts to prevent thread leak. |

---

## WAVE 8: Documentation & Future Work

**Focus:** Operational readiness and subscriber management.

| Item | Description | Location | Implementation Context |
|------|-------------|----------|------------------------|
| **D1** | Operations & Troubleshooting | `docs/` | Expand `operations.md` and `troubleshooting.md` with common error signatures and recovery steps. |
| **D2** | Subscriber Sunset Policy | `services/subscribers.py` | Implement logic to flag/remove subscribers after N bounces or 6 months of inactivity. |

---

## Verification Protocol

For every Wave, execute:
1. `ruff check .`
2. `pytest tests/ -x -q` (Ensuring no regressions in core pipeline).
3. Manual verification of the specific fix (e.g., simulate Redis outage for W1.1).
