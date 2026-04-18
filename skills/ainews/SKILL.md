---
name: ainews
description: "ainews AI news pipeline — Flask backend, Celery workers, LLM pipeline (select→research→write→edit), subagent system, SQLite/WAL, Granian ASGI. Triggers: pipeline, celery, newsletter, article, source, subscriber, admin, config, health, metrics."
---

## Overview

ainews is an AI-curated news pipeline with a Flask backend, Celery workers, and a 4-stage LLM pipeline: select → research → write → edit. Articles are crawled from RSS/API sources, processed through pipeline stages with circuit breakers and rate limiting, then served via public feeds and email newsletters.

**Tech stack:**
- Flask (WSGI behind Granian ASGI adapter)
- Celery + Redis broker
- SQLite (WAL mode) with Flask-SQLAlchemy
- LLM providers via OpenAI-compatible adapter
- HTML email newsletter generation

## Pipeline Stages

```
pending → selecting → selected → researching → writing → written → editing → done/failed
```

Each stage is a Celery task in `tasks/` with:
- Stage lock (Redis, prevents concurrent same-stage processing)
- Rate limiter slot (Redis, per-provider concurrency)
- Circuit breaker (per-request, shared across fallback providers)
- Retry budget (`retry_count`, `total_retries`)
- Degradation on exhaustion → applies fallback draft

**Stage task files:**
| File | Stage |
|------|-------|
| `tasks/select.py` | selector |
| `tasks/research.py` | researcher |
| `tasks/write.py` | writer |
| `tasks/edit.py` | editor |
| `tasks/pipeline.py` | Shared helpers: `run_stage()`, `_dispatch_next()`, `_assign_tags()` |
| `tasks/scheduler.py` | Scheduled publishing |
| `services/pipeline_failure.py` | `_handle_stage_failure()`, retry budget logic |
| `services/pipeline_degradation.py` | `degrade_stage()`, `_finalize()`, `_apply_fallback()` |

## Database

SQLite (WAL mode) is intentional — workload is read-heavy (articles written once by Celery, served thousands of times by Flask). PostgreSQL adds operational overhead with no benefit at this scale.

**Key models:**
- `Article` — main article record with `pipeline_status`, `final_article` JSON field
- `Source` — RSS/API feed sources with health tracking (`consecutive_failures`, `disabled_at`)
- `Subscriber` — newsletter subscribers with topic preferences
- `PipelineRun` / `PipelineLog` — pipeline execution audit trail
- `TopicNote` — manual editor notes per topic
- `TrendMemory` — LLM-judged persistent memory entries

## LLM Providers

All providers implement `BaseLLMProvider` from `services/llm/base.py`. Registered in `providers.yaml`.

**Key files:**
- `services/llm/__init__.py` — provider registry, `get_provider_for_role()`, circuit breaker
- `services/llm/openai.py` — OpenAI + OpenAI-compatible (MiniMax, DeepSeek, Zai)
- `services/llm/anthropic.py` — native Anthropic API
- `services/llm/base.py` — `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`
- `services/llm/errors.py` — error classification (rate limit, auth, server error, timeout)

**Timeouts:** OpenAI uses `_client_kwargs["timeout"]=120.0`; Anthropic uses `self._timeout=120.0` passed to client constructor. All LLM calls should have explicit timeouts.

## Subagent System

`services/subagent.py` runs lightweight synchronous subagent tasks within pipeline stages. NOT a general-purpose agent framework.

**Key functions:**
- `run_subagent()` — single-step with timeout
- `run_subagent_with_tools()` — tool calling (max 5 iterations)
- `run_subagent_chain()` — multi-step with conditional execution

**Prompt data escaping:** All `prompt_data` is automatically escaped via `_escape_prompt_data()` before `template.format()`. This prevents XML-breaking injection.

**Condition evaluation:** `run_subagent_chain()` uses AST-based parsing (NOT `eval()`) with allowlisted operators. Blocks dunder access.

## Celery Tasks

Celery tasks run outside Flask app context — do NOT use `current_app.config.get()`. Use `get_config_with_default()` from `services/config_utils.py` instead.

**Scheduled tasks** (in `config.py:CELERY_BEAT_SCHEDULE`):
- `run-all-sources` — crawl all sources every 30 min
- `retry-stuck-articles` — retry/dead-letter stuck articles every 60 min
- `generate-newsletters` — daily at 8:00 AM
- `cleanup-old-logs` — daily at 3:00 AM
- `cleanup-old-versions` — daily at 3:45 AM (article version cleanup)
- `consolidate-trend-memory` — daily at 3:30 AM
- `cleanup-expired-verifications` — every 15 min
- `publish-scheduled-articles` — every 5 min
- `cleanup-stale-limiter-slots` — every 5 min

**Lock pattern:** Distributed locks use task's `self.request.id` as lock value so retries can re-acquire.

## ASGI Deployment

`run.py` exports `WsgiToAsgi(flask_app)` as module-level `app` for Granian. Flask remains WSGI internally. Do NOT remove the wrapper.

## Config System

**Config access pattern (Celery-safe):**
```python
from services.config_utils import get_config_with_default

def _get_something() -> int:
    return get_config_with_default("SOME_CONFIG_KEY", SOME_DEFAULT)
```

**Config validation:** `services/config_unified.py:validate_config()` validates pipeline, topic, source, and LLM provider configs. Returns `(is_valid, errors)` tuple. Reload via `POST /admin/api/config/reload`.

## Health Check Degradation

`services/health.py` returns "unhealthy" for DB errors (core broken), "degraded" for Redis/Celery/limiter errors (non-core). `HealthResult.is_healthy` returns True for both "ok" and "degraded".

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | WSGI/ASGI app entry point |
| `app.py` | Flask app factory |
| `config.py` | Flask config classes, Celery beat schedule |
| `extensions.py` | Flask extensions (db, redis, limiter) |
| `models.py` | SQLAlchemy models |
| `constants.py` | Constants including `PipelineStatus` enum |
| `services/prompts.py` | `esc_xml_text()`, `esc_xml_attr()` for LLM prompt escaping |
| `services/url.py` | URL validation (SSRF prevention), DNS cache |
| `services/cache.py` | ResponseCache (L1 in-memory + L2 Redis) |
| `services/limiter.py` | ModelLimiter (Redis-based rate limiting) |
| `services/config_utils.py` | `get_config_with_default()` for Celery-safe config |
| `services/config_cache.py` | Config cache with mtime-based invalidation |
| `services/config_unified.py` | Unified config loading + validation |
| `services/pipeline_monitor.py` | Redis minute-bucket stage metrics |
| `services/health.py` | Health check with degradation |
| `services/logging_utils.py` | PipelineLogger, `log_pipeline_event()`, `log_article_event()` |
| `services/article_validation.py` | `ValidationError(ValueError)`, `validate_final_article()` |
| `routes/admin/__init__.py` | Admin blueprint, `@require_auth`, login lockout |
| `routes/admin/api/` | Admin API endpoints (health, config, pipeline, articles, webhooks) |
| `routes/public/feeds.py` | Public feed routes, RSS generation |
| `routes/decorators.py` | `commit()` helper, `commit_or_rollback()` context manager |
| `tasks/newsletter.py` | Newsletter generation and email delivery |
| `tasks/extract.py` | Article extraction from crawled content |
| `tasks/retry.py` | `retry_stuck` task, dead-letter handling |
| `tasks/cleanup.py` | Log cleanup, trend memory consolidation |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |

## Security Notes

- **XSS**: LLM-generated content in templates must use `|e` filter
- **Prompt injection**: Prompt data auto-escaped via `_escape_prompt_data()`
- **SSRF**: All URLs validated via `validate_url_safe()` before fetching
- **Session fixation**: Admin login uses `session.clear()` before setting `session["admin"]`
- **eval() replacement**: Subagent conditions use AST-based parser
- **Webhook secrets**: Masked in API responses via `_mask_secret()`
- **Redis credentials**: Preserved via `urlparse`/`urlunparse` when switching DBs
- **RSS XML**: Headlines/descriptions escaped with `html.escape()` before insertion
- **Login lockout**: Redis Lua script for atomic check-and-record; in-memory fallback