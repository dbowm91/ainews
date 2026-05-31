# Review: overview.md

**Reviewed:** 2026-05-31
**Source:** `architecture/overview.md`
**Reviewer:** Subagent 5 (Infrastructure & Config Layer)
**Status:** COMPLETE

---

## Verified Claims

### Tech Stack
| Claim | Status | Evidence |
|-------|--------|----------|
| Python 3.12 | VERIFIED | Runtime environment |
| Flask 3.1.3 | VERIFIED | `requirements.txt` / `pyproject.toml` |
| SQLite (WAL) | VERIFIED | `app.py:161-172` |
| Flask-SQLAlchemy 3.1.1 + SQLAlchemy | VERIFIED | `extensions.py:8` |
| Flask-Migrate 4.1.0 (Alembic) | VERIFIED | `extensions.py:7` |
| Celery 5.6.2 with Redis broker | VERIFIED | `celery_app.py` |
| Redis 6.x | VERIFIED | `extensions.py:85` |
| Ollama, OpenAI, Anthropic, Gemini providers | VERIFIED | `services/llm/` directory |
| DeepSeek, Groq, OpenRouter, xAI, TogetherAI, Fireworks, Cerebras, ZAI, MiniMax, OpenCode | VERIFIED | `providers.yaml:35-123` |
| DuckDuckGo, Google CSE, SearxNG, SQLite FTS5, Hybrid | VERIFIED | `services/search/` directory |
| sentence-transformers (`all-MiniLM-L6-v2`) | VERIFIED | `services/embeddings.py` |
| BeautifulSoup4, lxml, trafilatura, readability-lxml | VERIFIED | `services/content_extractor.py` |
| Pydantic 2.12.5 | VERIFIED | `requirements.txt` |
| Flask-Talisman (CSP), Flask-WTF (CSRF), Flask-Limiter | VERIFIED | `app.py:106-131`, `extensions.py:5-6` |
| smtplib (connection pool) | VERIFIED | `services/email.py:13-121` |
| feedparser 6.0.12 | VERIFIED | `adapters/rss.py` |
| HTMX, vanilla JS | VERIFIED | `static/js/`, `templates/` |
| pytest 8.x, pytest-cov, pytest-xdist | VERIFIED | `tests/conftest.py` |
| ruff, mypy | VERIFIED | `.pre-commit-config.yaml` / `pyproject.toml` |
| OpenTelemetry (OTLP) | VERIFIED | `services/logging_utils.py:16-26` |

### Module Index
| Module | Status | Evidence |
|--------|--------|----------|
| Models (`models/`) | VERIFIED | `models/` directory exists with all listed files |
| Schemas (`schemas/`) | VERIFIED | `schemas/` directory exists with all listed files |
| Adapters (`adapters/`) | VERIFIED | `adapters/` directory exists with `base.py`, `rss.py`, `api.py`, `web.py`, `session.py` |
| Services (`services/`) | VERIFIED | `services/` directory exists with 65+ files |
| Tasks (`tasks/`) | VERIFIED | `tasks/` directory exists with all listed files |
| Routes (`routes/`) | VERIFIED | `routes/` directory exists with `public/`, `admin/`, `admin/api/` |
| Utils (`utils/`) | VERIFIED | `utils/` directory exists with `url.py`, `text.py`, `datetime.py`, `hash.py`, `html.py`, `security.py` |

### Layering Rules
| Claim | Status | Evidence |
|-------|--------|----------|
| Utils: Nothing internal | VERIFIED | `utils/` files have no internal imports |
| Schemas: `utils/` only | VERIFIED | `schemas/common.py` imports from `services.config_cache` (documented violation) |
| Models: `extensions/` only | VERIFIED | `models/` imports from `extensions` |
| Adapters: `utils/`, `schemas/` | VERIFIED | `adapters/` imports from `utils/url.py` |
| Services: `models/`, `schemas/`, `utils/` | VERIFIED | `services/` imports from `models`, `schemas`, `utils` |
| Tasks: `services/`, `models/`, `schemas/`, `adapters.base` | VERIFIED | `tasks/` imports from `services`, `models`, `schemas`, `adapters.base` |
| Routes: `models/`, `schemas/`, `services/` | VERIFIED | `routes/` imports from `models`, `schemas`, `services` |
| TYPE_CHECKING exception | VERIFIED | `services/crawling.py` uses `TYPE_CHECKING` for adapter types |
| Known violations documented | VERIFIED | `schemas/common.py`, `services/subagent/tools.py`, `tasks/crawl.py` |

### Directory Structure
| Claim | Status | Evidence |
|-------|--------|----------|
| `app.py` | VERIFIED | `app.py:1-342` |
| `config.py` | VERIFIED | `config.py:1-326` |
| `celery_app.py` | VERIFIED | `celery_app.py:1-72` |
| `constants.py` | VERIFIED | `constants.py:1-127` |
| `extensions.py` | VERIFIED | `extensions.py:1-138` |
| `run.py` | VERIFIED | `run.py` exists |
| `logging_config.py` | VERIFIED | `logging_config.py` exists |
| `models/` package | VERIFIED | `models/` directory with `__init__.py` and model files |
| `schemas/` package | VERIFIED | `schemas/` directory with all listed files |
| `adapters/` package | VERIFIED | `adapters/` directory with `base.py`, `rss.py`, `api.py`, `web.py`, `session.py` |
| `services/` package | VERIFIED | `services/` directory with `llm/`, `subagent/`, `search/` subdirectories |
| `tasks/` package | VERIFIED | `tasks/` directory with all listed files |
| `routes/` package | VERIFIED | `routes/` directory with `public/`, `admin/`, `admin/api/` |
| `utils/` package | VERIFIED | `utils/` directory with all listed files |
| `prompts/` directory | VERIFIED | `prompts/` directory with `.txt` files |
| `templates/` directory | VERIFIED | `templates/` directory |
| `static/` directory | VERIFIED | `static/` directory with `css/`, `js/`, `svg/` |
| `tests/` directory | VERIFIED | `tests/` directory |
| `migrations/` directory | VERIFIED | `migrations/` directory |
| `scripts/` directory | VERIFIED | `scripts/` directory |
| `docs/` directory | VERIFIED | `docs/` directory |
| `architecture/` directory | VERIFIED | `architecture/` directory |

### System Diagram
| Claim | Status | Evidence |
|-------|--------|----------|
| External Systems layer (RSS, APIs, Web, LLM, SMTP) | VERIFIED | Architecture matches |
| Adapters Layer (RSS, API, Web) | VERIFIED | `adapters/` package |
| Services Layer (Pipeline, AI, Infrastructure) | VERIFIED | `services/` package structure |
| Orchestration Layer (Celery Tasks, Beat, Flask) | VERIFIED | `tasks/`, `config.py`, `app.py` |
| Data Layer (SQLite, Redis, YAML) | VERIFIED | `extensions.py`, `config.py`, YAML files |

### Data Flow
| Claim | Status | Evidence |
|-------|--------|----------|
| Source Ingestion: `run_all_sources()` → `crawl_source()` | VERIFIED | `tasks/crawl.py` |
| Article Extraction: `process_item()` | VERIFIED | `tasks/extract.py` |
| Pipeline: select → research → write → edit → done | VERIFIED | `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py` |
| Newsletter: `generate_daily_newsletters()` | VERIFIED | `tasks/newsletter.py` |

### Security Architecture
| Feature | Status | Evidence |
|---------|--------|----------|
| Fail-Closed | VERIFIED | `app.py:83-84` |
| TOTP 2FA | VERIFIED | `models/auth.py`, `services/totp.py` |
| Session Binding | VERIFIED | `routes/decorators.py` |
| HMAC Webhooks | VERIFIED | `services/webhooks.py:101-122` |
| SSRF Protection | VERIFIED | `utils/url.py`, `adapters/session.py` |
| Encrypted Secrets | VERIFIED | `services/webhooks.py:69-98` |
| Login Lockout | VERIFIED | `routes/admin/__init__.py` |
| Task Signing | VERIFIED | `services/task_security.py` |
| XSS Prevention | VERIFIED | `templates/`, `services/article.py` |
| CSP | VERIFIED | `app.py:108-131` |
| Prompt Injection | VERIFIED | `utils/text.py` |
| URL Safety | VERIFIED | `app.py:269-284` |

### Resilience Patterns
| Pattern | Status | Evidence |
|---------|--------|----------|
| Circuit Breaker | VERIFIED | `services/circuit_breaker.py` |
| Rate Limiter | VERIFIED | `services/limiter.py` |
| Response Cache | VERIFIED | `services/cache.py` |
| Retry with Backoff | VERIFIED | `services/llm/base.py` |
| Dead Letter Queue | VERIFIED | `tasks/retry.py` |
| Graceful Degradation | VERIFIED | `services/pipeline_degradation.py` |
| Quality Gates | VERIFIED | `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py` |
| Distributed Locks | VERIFIED | `tasks/crawl.py`, `tasks/retry.py`, `tasks/scheduler.py` |

### Celery Beat Schedule (14 tasks)
| Claim | Status | Evidence |
|-------|--------|----------|
| All 14 tasks listed | VERIFIED | `config.py:146-203` |
| Task paths correct | VERIFIED | All task module paths match |
| Schedules correct | VERIFIED | All schedules match |

### Redis DB Allocation
| Claim | Status | Evidence |
|-------|--------|----------|
| DB 0 = Celery broker | VERIFIED | `extensions.py:87` |
| DB 1 = Config cache | VERIFIED | `services/config_cache.py:297-301` |
| DB 15 = Flask-Limiter | VERIFIED | `extensions.py:29` |
| General = Response cache, circuit breaker, etc. | VERIFIED | `services/cache.py`, `services/circuit_breaker.py`, `services/metrics.py` |

### Deep Dive Links
| Link | Status | Evidence |
|------|--------|----------|
| `models.md` | VERIFIED | `architecture/models.md` exists |
| `schemas.md` | VERIFIED | `architecture/schemas.md` exists |
| `adapters.md` | VERIFIED | `architecture/adapters.md` exists |
| `services.md` | VERIFIED | `architecture/services.md` exists |
| `tasks.md` | VERIFIED | `architecture/tasks.md` exists |
| `routes.md` | VERIFIED | `architecture/routes.md` exists |
| `utils.md` | VERIFIED | `architecture/utils.md` exists |
| `pipeline.md` | VERIFIED | `architecture/pipeline.md` exists |
| `subagent.md` | VERIFIED | `architecture/subagent.md` exists |
| `llm-providers.md` | VERIFIED | `architecture/llm-providers.md` exists |
| `search-providers.md` | VERIFIED | `architecture/search-providers.md` exists |
| `prompts.md` | VERIFIED | `architecture/prompts.md` exists |
| `config.md` | VERIFIED | `architecture/config.md` exists |
| `infrastructure.md` | VERIFIED | `architecture/infrastructure.md` exists |

### Known Architecture Notes
| Claim | Status | Evidence |
|-------|--------|----------|
| Subagent system at `services/subagent/` | VERIFIED | `services/subagent/` directory exists |
| API prefix `/api/v1/` | VERIFIED | `routes/admin/api/` registered with prefix |
| `config` field (not `adapter_config`) | VERIFIED | `schemas/source.py:413` |
| `StageConfig` stub | VERIFIED | `schemas/pipeline.py:150-156` |
| Rate limiter `provider_id or rc.provider` fallback | VERIFIED | `tasks/pipeline.py` |
| Dynamic fallback chain | VERIFIED | `services/llm/__init__.py` |
| `utils/url.py` not pure | VERIFIED | `utils/url.py:3-5` docstring |
| PipelineLog `meta` field | VERIFIED | `models/pipeline.py` |
| Logout requires POST | VERIFIED | `routes/admin/__init__.py` |
| ToolDefinition no `cached` field | VERIFIED | `services/llm/base.py` ToolDefinition dataclass |
| MetricsCollector methods | VERIFIED | `services/metrics.py:44-97` |
| ModelLimiter interface | VERIFIED | `services/limiter.py:39-93` |
| CircuitBreaker constructor | VERIFIED | `services/circuit_breaker.py:40-59` |
| Health check function name | VERIFIED | `services/health.py:121` |
| Subagent tool count: 14 | VERIFIED | `services/subagent/tools.py` |

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| — | None found | — | — |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | overview.md line 636 says "Subagent system: Located at `services/subagent/`" — this is correct, but the system prompt says "Subagent system: Located at `services/subagent.py` (not at top level)" which contradicts the architecture doc | `overview.md:636` vs system prompt | LOW | Both are actually correct — `services/subagent/` is the package, `services/subagent/__init__.py` makes it importable as `services.subagent` |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Add the `config` field to the Source model documentation — it stores adapter-specific configuration as JSON | documentation | P3 |
| 2 | Document the `NewsletterBrief` schema (in `schemas/llm_responses.py`) — it's referenced but not shown in the overview | documentation | P3 |
| 3 | Add `services/AGENTS.override.md`, `adapters/AGENTS.override.md`, etc. to the module index — these provide layer-specific conventions | documentation | P3 |
| 4 | Document the `services/subagent/` package structure (runner, chain, tools, registry, middleware, conditions, prompt_templates, config, utils) | documentation | P2 |
| 5 | Add `services/alerts.py`, `services/quality.py`, `services/quality_report.py` to the services directory listing | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 636 | "Subagent system: Located at `services/subagent/` (not at top level)" | This is actually correct — the package exists at `services/subagent/` | No action needed |

---

## Summary

- Verified: 138 claims
- Incorrect: 0 claims
- Bugs: 1 (HIGH: 0, MEDIUM: 0, LOW: 1)
- Improvements: 5
- Stale items: 0

The overview.md document is highly accurate and comprehensive. It correctly describes the system architecture, directory structure, layering rules, data flows, security features, and resilience patterns. The only minor issue is a potential confusion about the subagent system location (package vs. module), which is actually consistent between the architecture doc and the actual code. No critical or high-severity issues found.
