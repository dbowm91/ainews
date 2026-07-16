# Architecture Overview

ainews is an autonomous AI-powered tech news aggregation and newsletter system. It crawls multiple news sources, uses LLMs to research and write condensed articles, and delivers personalized newsletters to subscribers.

This document provides a **bird's-eye view** of the entire system. Each module links to a dedicated deep-dive document for detailed exploration.

---

## Module Index

### Core Application Modules

| Module | Source | Deep Dive | Description |
|--------|--------|-----------|-------------|
| **Models** | `models/` | [models.md](models.md) | SQLAlchemy models: Article, Source, Newsletter, Subscriber, PipelineRun, TrendMemory, AdminUser, QualityReport, Webhook, AuditLog, Tag, SearchQuery, ShareConfig |
| **Schemas** | `schemas/` | [schemas.md](schemas.md) | Pydantic validation: pipeline config, source adapter config, LLM response schemas, task input validation, topic definitions |
| **Adapters** | `adapters/` | [adapters.md](adapters.md) | Source fetchers: RSS (feedparser), API (JSON + JSONPath), Web (CSS scraping). Registry pattern with `@register_adapter` |
| **Services** | `services/` | [services.md](services.md) | Business logic: LLM providers, pipeline services, infrastructure services (cache, limiter, circuit breaker, email, webhooks) |
| **Tasks** | `tasks/` | [tasks.md](tasks.md) | Celery tasks: crawl, extract, select, research, write, edit, newsletter, cleanup, retry, scheduler, embeddings |
| **Routes** | `routes/` | [routes.md](routes.md) | Flask blueprints: public (feeds, subscribe, links), admin (dashboard, articles, sources, pipelines, review), admin API (`/api/v1/*`) |
| **Utils** | `utils/` | [utils.md](utils.md) | Pure utilities: URL validation (SSRF protection), text escaping, datetime parsing, hashing, HTML processing, security |

### Pipeline & AI Modules

| Module | Source | Deep Dive | Description |
|--------|--------|-----------|-------------|
| **Pipeline** | `tasks/`, `services/` | [pipeline.md](pipeline.md) | Article processing pipeline: crawl → extract → select → research → write → edit → done. Newsletter generation: reader → writer → editor → HTML → email |
| **Subagent** | `services/subagent/` | [subagent.md](subagent.md) | Tool-enabled LLM agents: 14 built-in tools, runner with tool-calling loop, chain system with conditions, middleware chain |
| **LLM Providers** | `services/llm/` | [llm-providers.md](llm-providers.md) | Multi-provider architecture: OpenAI-compatible, Anthropic, Gemini, Ollama. Dynamic fallback chain, circuit breakers, retry with backoff |
| **Search Providers** | `services/search/` | [search-providers.md](search-providers.md) | Web search: DuckDuckGo (default), Google CSE, SearxNG. Article search: Hybrid (FTS5 + vector), SQLite FTS5 |
| **Prompts** | `prompts/` | [prompts.md](prompts.md) | LLM prompt templates: selector, researcher, writer, editor, newsletter (3-stage). Context truncation, XML escaping, A/B experiment variants |

### Infrastructure & Configuration

| Module | Source | Deep Dive | Description |
|--------|--------|-----------|-------------|
| **Configuration** | `config.py`, `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml` | [config.md](config.md) | YAML configs validated by Pydantic, Redis-backed caching, environment variables, Celery beat schedule |
| **Infrastructure** | `extensions.py`, `services/` | [infrastructure.md](infrastructure.md) | Redis (broker, cache, rate limiting), SQLite (WAL mode), Celery (task queue + beat), email (SMTP pooling), health checks, circuit breakers, metrics |
| **Operator CLI** | `ainews_cli/` | — | CLI commands: onboarding, provider/source/topic/pipeline management, service lifecycle, config, diagnostics, backup/restore, update, channel management, uninstall |
| **Update Engine** | `ainews_cli/update/` | — | Channel-aware updates: check, plan, apply with pre-update backup, staged activation, auto-rollback on health failure |
| **Channel Manager** | `ainews_cli/channel/` | — | Release channel management: stable/prerelease/main with version pinning and transactional metadata writes |
| **Uninstall** | `ainews_cli/uninstall/` | — | Safe uninstall: path ownership validation, app-only or purge modes, dry-run, lifecycle integration |

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.12 |
| Web Framework | Flask 3.1.3 |
| ASGI Wrapper | Granian (via asgiref) |
| Database | SQLite (WAL) |
| ORM | Flask-SQLAlchemy 3.1.1 + SQLAlchemy |
| Migrations | Flask-Migrate 4.1.0 (Alembic) |
| Task Queue | Celery 5.6.2 with Redis broker |
| Cache/Message Broker | Redis 6.x |
| LLM Providers | Ollama, OpenAI, Anthropic, Gemini, DeepSeek, Groq, OpenRouter, xAI, TogetherAI, Fireworks, Cerebras, ZAI, MiniMax, OpenCode |
| Search | DuckDuckGo, Google CSE, SearxNG, SQLite FTS5, Hybrid (FTS5 + vector) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| HTML Parsing | BeautifulSoup4, lxml, trafilatura, readability-lxml |
| Validation | Pydantic 2.12.5 |
| Security | Flask-Talisman (CSP), Flask-WTF (CSRF), Flask-Limiter, pyotp (2FA) |
| Email | smtplib (connection pool) |
| RSS | feedparser 6.0.12 |
| Frontend | HTMX, vanilla JS, CSS custom properties, service worker (PWA) |
| Testing | pytest 8.x, pytest-cov, pytest-xdist |
| Linting | ruff, mypy |
| Observability | OpenTelemetry (OTLP), structured logging |

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                External Systems                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐     │
│  │ RSS Feeds │  │ REST APIs │  │ Web Pages │  │ LLM APIs  │  │ SMTP Mail │     │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘     │
└────────┼──────────────┼──────────────┼──────────────┼──────────────┼────────────┘
         │              │              │              │              │
         ▼              ▼              ▼              │              │
┌────────────────────────────────────────────────┐    │              │
│              Adapters Layer                      │    │              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────┐│    │              │
│  │  RSSAdapter  │ │  APIAdapter  │ │WebAdapter││    │              │
│  └──────┬───────┘ └──────┬───────┘ └────┬─────┘│    │              │
└─────────┼────────────────┼──────────────┼──────┘    │              │
          │                │              │           │              │
          ▼                ▼              ▼           │              │
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Services Layer                                        │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Pipeline Services                                                      │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐          │    │
│  │  │ Researcher │ │   Writer   │ │   Editor   │ │  Crawling  │          │    │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  AI Systems                                                             │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐          │    │
│  │  │ LLM Provs  │ │  Subagent  │ │   Trend    │ │  Search    │          │    │
│  │  │ (fallback) │ │  (14 tools)│ │  Memory    │ │  Providers │          │    │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Infrastructure Services                                                │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │    │
│  │  │  Cache   │ │ Limiter  │ │Circuit Br│ │ Webhooks │ │  Email   │    │    │
│  │  │(Redis L2)│ │(Redis)   │ │(Redis)   │ │(HMAC+TLS)│ │ (SMTP)   │    │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
          │                │              │
          ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Orchestration Layer                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │   Celery Tasks   │  │   Celery Beat    │  │    Flask App     │              │
│  │ (pipeline stages)│  │   (14 schedules) │  │ (routes + admin) │              │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘              │
└───────────┼─────────────────────┼─────────────────────┼────────────────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Data Layer                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │  SQLite (WAL)    │  │  Redis (broker)  │  │  YAML Configs    │              │
│  │  articles,       │  │  queue, locks,   │  │  pipeline,       │              │
│  │  sources,        │  │  cache, rate     │  │  providers,      │              │
│  │  newsletters     │  │  limiting        │  │  sources, topics │              │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Source Ingestion (every 30 min)

```
Celery Beat → run_all_sources()
  → Creates PipelineRun record
  → Celery chord: one crawl_source() per source (parallel)
     → Loads SourceConfig from sources.yaml
     → Instantiates adapter (RSS/API/Web) from registry
     → adapter.fetch_and_parse() → list[RawItem]
     → Deduplicates by external_id
     → Dispatches process_item() per new item
  → aggregate_crawl_results() callback
```

### 2. Article Extraction

```
process_item(item_config, run_id)
  → Validates input via ProcessItemTask schema
  → Extracts content from URL if text too short (trafilatura)
  → Checks for duplicates by normalized URL + title
  → Creates Article record (pipeline_status="pending")
  → Dispatches select_article
```

### 3. Article Processing Pipeline

```
select_article                    tasks/select.py
       │  LLM scores 1-10, assigns experiment group
       │  Quality gate: low confidence → REVIEW
       ▼
research_article                  tasks/research.py
       │  Web search + synthesis via subagent
       │  Related articles, topic notes, trend memory
       │  LLM builds ResearchBrief
       │  Quality gate: degenerate brief → REVIEW
       ▼
write_article                     tasks/write.py
       │  Trend memory context
       │  LLM writes CondensedArticle (Smart Brevity)
       │  Quality gate: short body/no points/citations → REVIEW
       ▼
edit_article                      tasks/edit.py
       │  Subagent contextualization (topic notes + related articles)
       │  LLM refines article
       │  Tag assignment, validation, quality report
       │  Quality gate: validation failure → REVIEW
       ▼
finalize                          edit.py:_post_finalize_article
       │  Set DONE status, record SLA metric
       │  Propose trend memory
       │  Trigger webhook, enqueue embedding
       ▼
done ✓
```

### 4. Newsletter Generation (daily at 8 AM)

```
generate_daily_newsletters        tasks/newsletter.py
       │  Acquires Redis lock + idempotency key
       │  Fetches DONE articles (24h window, ordered by impact_score)
       │
       ├── Per-topic newsletter generation (Celery group):
       │   ├── executive_summary    3-stage LLM pipeline:
       │   │   ├── reader          Analyze articles for themes
       │   │   ├── writer          Generate summary
       │   │   └── editor          Polish for clarity
       │   ├── Generate email-safe HTML
       │   └── Send to subscribers (Celery group, batches of 500)
       │
       └── Record delivery metrics, fire webhooks
```

---

## Layering Rules

Strict separation of concerns maintains modularity:

| Layer | Can Import | Cannot Import |
|-------|-----------|---------------|
| **Utils** | Nothing internal | Everything |
| **Schemas** | `utils/` | `services/`, `models/`, `adapters/` |
| **Models** | `extensions/` | `services/`, `adapters/`, `schemas/` |
| **Adapters** | `utils/`, `schemas/` | `services/`, `models/` |
| **Services** | `models/`, `schemas/`, `utils/` | `adapters/` (TYPE_CHECKING OK) |
| **Tasks** | `services/`, `models/`, `schemas/`, `adapters.base` | — |
| **Routes** | `models/`, `schemas/`, `services/` | `adapters/` |

**TYPE_CHECKING exception:** Services may use `TYPE_CHECKING` imports from adapters for type hints only.

**Known intentional layer violations (do not fix):**
- `schemas/common.py` imports from `services.config_cache`
- `services/subagent/tools.py` imports from `models` and `extensions`
- `tasks/crawl.py` imports directly from `adapters.base`

### Module Dependency Graph

```
                    utils/
                       ^
                    schemas/
                       ^
                    models/
                       ^
                    adapters/  (imports schemas, utils/url)
                       ^
                    services/  (imports models, schemas, utils)
                       ^
                    tasks/     (imports services, models, schemas, adapters.base)
                       ^
                    routes/    (imports services, models, schemas, extensions)
```

---

## Key Configuration Files

| File | Purpose | Deep Dive |
|------|---------|-----------|
| `pipeline.yaml` | Pipeline stages, newsletter settings, subagent config, memory, experiments, schedules | [config.md](config.md) |
| `providers.yaml` | LLM provider definitions (14 providers), search provider definitions | [config.md](config.md) |
| `sources.yaml` | News source definitions with adapter types and URLs | [config.md](config.md) |
| `topics.yaml` | Topic definitions for article classification | [config.md](config.md) |
| `config.py` | Flask configuration classes + Celery beat schedule | [config.md](config.md) |

---

## Security Architecture

| Feature | Implementation | Location |
|---------|---------------|----------|
| Fail-Closed | Production startup validates all secrets | `app.py` |
| TOTP 2FA | Admin users with 8 backup codes | `models/auth.py`, `services/totp.py` |
| Session Binding | IP + User-Agent validation | `routes/decorators.py` |
| HMAC Webhooks | Timestamp replay protection | `services/webhooks.py` |
| SSRF Protection | URL validation + DNS rebinding detection | `utils/url.py`, `adapters/session.py` |
| Encrypted Secrets | Webhook secrets at rest (Fernet) | `services/webhooks.py` |
| Login Lockout | Redis Lua script with in-memory fallback | `routes/admin/__init__.py` |
| Task Signing | HMAC task signature verification | `services/task_security.py` |
| XSS Prevention | Template `\|e` filter, bleach HTML sanitization | `templates/`, `services/article.py` |
| CSP | Nonce-based script-src, strict directives | `app.py` |
| Prompt Injection | XML escaping for LLM prompt data | `utils/text.py` (`esc_xml_text`, `esc_xml_attr`) |
| URL Safety | `safe_href` Jinja2 filter validates URLs | `templates/` |

---

## Resilience Patterns

| Pattern | Purpose | Implementation |
|---------|---------|---------------|
| Circuit Breaker | Prevent cascading failures on LLM/search providers | `services/circuit_breaker.py` — CLOSED → OPEN → HALF_OPEN state machine |
| Rate Limiter | Concurrency control per LLM provider/model | `services/limiter.py` — Redis Lua scripts, pub/sub wait |
| Response Cache | Reduce duplicate LLM calls and DB queries | `services/cache.py` — L1 (memory LRU) + L2 (Redis) with stampede protection |
| Retry with Backoff | Handle transient LLM errors | `services/llm/base.py` — Exponential backoff, max retries |
| Dead Letter Queue | Recover stuck articles | `tasks/retry.py` — Classify stuck → retry/degrade/dead-letter |
| Graceful Degradation | Continue when LLM stages fail | `services/pipeline_degradation.py` — Fallback content, review routing |
| Quality Gates | Catch degenerate LLM output | Each stage has `_is_degenerate_*()` check → routes to REVIEW |
| Distributed Locks | Prevent duplicate task execution | Redis SET NX EX with Lua scripts |

---

## Infrastructure

| Component | Technology | Purpose | Deep Dive |
|-----------|------------|---------|-----------|
| Web Server | Granian (ASGI) | High-performance Python HTTP server | [infrastructure.md](infrastructure.md) |
| Task Queue | Celery + Redis | Async task processing + scheduling | [infrastructure.md](infrastructure.md) |
| Database | SQLite (WAL) | Primary data store | [infrastructure.md](infrastructure.md) |
| Cache | Redis | Rate limiting, distributed locks, caching | [infrastructure.md](infrastructure.md) |
| Email | SMTP | Newsletter delivery with connection pooling | [infrastructure.md](infrastructure.md) |
| LLM | Multi-provider | Ollama, OpenAI, Anthropic, Gemini, etc. | [llm-providers.md](llm-providers.md) |
| Search | Multi-provider | DuckDuckGo, Hybrid (FTS5+vector) | [search-providers.md](search-providers.md) |

### Redis DB Allocation

| DB | Purpose |
|----|---------|
| 0 | Celery broker (from `CELERY_BROKER_URL`) |
| 1 | Config cache (via `CONFIG_CACHE_REDIS_URL`) |
| 15 | Flask-Limiter storage (derived from broker URL) |
| General | Response cache, circuit breaker state, pipeline counters, metrics, limiter slots |

---

## Celery Beat Schedule

| Beat Name | Task | Schedule |
|-----------|------|----------|
| `run-all-sources` | `tasks.crawl.run_all_sources` | Every 30 minutes |
| `retry-stuck-articles` | `tasks.retry.retry_stuck` | Every 60 minutes |
| `generate-newsletters` | `tasks.newsletter.generate_daily_newsletters` | Daily at 8:00 AM |
| `cleanup-old-logs` | `tasks.cleanup.cleanup_old_pipeline_logs` | Daily at 3:00 AM |
| `consolidate-trend-memory` | `tasks.cleanup.consolidate_trend_memory` | Daily at 3:30 AM |
| `purge-trend-memory` | `tasks.cleanup.purge_trend_memory` | Daily at 3:45 AM |
| `cleanup-old-versions` | `tasks.cleanup.cleanup_old_article_versions` | Daily at 3:45 AM |
| `cleanup-expired-verifications` | `tasks.cleanup.cleanup_expired_verifications` | Every 15 minutes |
| `publish-scheduled-articles` | `tasks.scheduler.publish_scheduled_articles` | Every 5 minutes |
| `cleanup-stale-limiter-slots` | `tasks.cleanup.cleanup_stale_limiter_slots` | Every 5 minutes |
| `retry-failed-newsletter-deliveries` | `tasks.newsletter.retry_failed_newsletter_deliveries` | Every 2 hours |
| `recalculate-impact-scores` | `tasks.cleanup.recalculate_impact_scores` | Daily at 4:00 AM |
| `cleanup-inactive-subscribers` | `tasks.subscribers.cleanup_inactive_subscribers` | Daily at 1:00 AM |
| `backfill-embeddings` | `tasks.embeddings.backfill_embeddings` | Daily at 2:00 AM |

Schedule is reloadable at runtime via `POST /api/v1/config/reload`.

---

## External Integrations

### LLM Providers (via `providers.yaml`)

| Provider | Type | Status |
|----------|------|--------|
| ollama-local | Local | **Enabled** (default) |
| openai | OpenAI-compatible | Disabled |
| anthropic | Native Anthropic | Disabled |
| gemini | Native Google | Disabled |
| deepseek | OpenAI-compatible | Disabled |
| groq | OpenAI-compatible | Disabled |
| openrouter | OpenAI-compatible | Disabled |
| xai | OpenAI-compatible | Disabled |
| togetherai | OpenAI-compatible | Disabled |
| fireworks | OpenAI-compatible | Disabled |
| cerebras | OpenAI-compatible | Disabled |
| zai | OpenAI-compatible | Disabled |
| minimax | OpenAI-compatible | Disabled |
| opencode | OpenAI-compatible | Disabled |

### Search Providers

| Provider | Status |
|----------|--------|
| duckduckgo | **Enabled** (default) |
| hybrid (FTS5 + vector) | **Enabled** |
| google | Disabled (requires API key) |
| searxng | Disabled (self-hosted) |

---

## Entry Points

| Entry Point | Command | Purpose |
|-------------|---------|---------|
| Development server | `python run.py` | Start Flask dev server |
| Database migrations | `flask db upgrade` | Run Alembic migrations |
| Celery worker | `celery -A celery_app worker` | Process pipeline tasks |
| Celery beat | `celery -A celery_app beat` | Run scheduled tasks |
| Password hashing | `python scripts/hash_password.py` | Generate admin password hash |
| Installer | `scripts/install.sh` | Channel-aware release installer |
| Operator CLI | `ainews` | Onboarding, providers, sources, topics, pipeline, lifecycle, config, doctor, backup, restore, update, channel, uninstall |

---

## Directory Structure

```
ainews/
├── app.py                  # Flask application factory
├── config.py               # Configuration classes (Dev, Prod, Test) + beat schedule
├── celery_app.py           # Celery application setup + FlaskTask base
├── constants.py            # PipelineStatus enum, shared constants
├── extensions.py           # Flask extensions (db, redis, limiter)
├── run.py                  # WSGI/ASGI entry point (Granian)
├── celery_support.py       # Celery support utilities
├── logging_config.py       # Structured JSON logging + OpenTelemetry
│
├── models/                 # SQLAlchemy models
│   ├── __init__.py         # Model exports, import order matters for db.create_all()
│   ├── article.py          # Article, Citation
│   ├── source.py           # Source (health tracking)
│   ├── newsletter.py       # Newsletter, Subscriber, ArticleMetric
│   ├── pipeline.py         # PipelineRun, PipelineLog, ArticleVersion
│   ├── context.py          # TopicNote, TrendMemory
│   ├── auth.py             # ApiToken, AdminUser (TOTP 2FA)
│   ├── webhook.py          # Webhook, WebhookEvent
│   ├── tag.py              # Tag, article_tags
│   ├── search.py           # SearchQuery
│   ├── audit.py            # AuditLog
│   ├── share.py            # ShareConfig
│   ├── quality.py          # QualityReport
│   └── utils.py            # Model utility functions
├── models.py               # Re-exports from models package
├── schemas/                # Pydantic models
│   ├── __init__.py         # Package init
│   ├── pipeline.py         # PipelineRootConfig, RoleConfig, SubagentConfig
│   ├── source.py           # SourceConfig, RSSConfig, APIConfig, WebConfig
│   ├── common.py           # Shared provider definitions (imports services.config_cache)
│   ├── llm.py              # Provider definitions
│   ├── llm_responses.py    # SelectionResult, ResearchBrief, CondensedArticle
│   ├── tasks.py            # Celery task input validation
│   ├── topic.py            # Topic definitions
│   ├── search.py           # SearchConfig
│   ├── webhook.py          # Webhook schemas
│   ├── admin.py            # Admin API request validation
│   └── item.py             # RawItem (adapter output)
│
├── adapters/               # Source data fetchers
│   ├── __init__.py         # Exports APIAdapter, RSSAdapter, WebAdapter, get_adapter_class
│   ├── base.py             # BaseSourceAdapter + registry
│   ├── rss.py              # RSS/Atom feed adapter
│   ├── api.py              # REST API adapter
│   ├── web.py              # Web scraping adapter
│   └── session.py          # Shared HTTP session + SSRF protection
│
├── services/               # Business logic layer (89 .py files)
│   ├── llm/                # LLM provider implementations
│   │   ├── __init__.py     # Provider registry + fallback chain
│   │   ├── base.py         # BaseLLMProvider + ToolDefinition
│   │   ├── openai.py       # OpenAI + OpenAI-compatible providers
│   │   ├── anthropic.py    # Anthropic Claude
│   │   ├── gemini.py       # Google Gemini
│   │   ├── ollama.py       # Local Ollama
│   │   ├── errors.py       # Error classification
│   │   └── json_utils.py   # JSON parsing for LLM responses
│   ├── subagent/           # Tool-enabled LLM agents (14 tools)
│   │   ├── __init__.py     # Package init, re-exports run_subagent
│   │   ├── runner.py       # run_subagent(), run_subagent_with_tools(), tool loop
│   │   ├── config.py       # Executor setup, provider config
│   │   ├── chain.py        # Multi-step chains with conditions
│   │   ├── tools.py        # Built-in tool implementations (14 tools)
│   │   ├── registry.py     # _TOOL_REGISTRY with cached tool definitions
│   │   ├── middleware.py    # Logging, timing, error handling middleware
│   │   ├── conditions.py   # AST-based condition evaluation
│   │   ├── prompt_templates.py # Task prompt templates
│   │   └── utils.py        # Retry, task revocation helpers
│   ├── search/             # Search providers
│   │   ├── __init__.py     # Search provider registry
│   │   ├── base.py         # BaseSearchProvider, SearchProvider ABCs
│   │   ├── duckduckgo.py   # DuckDuckGo (default)
│   │   ├── hybrid.py       # FTS5 + vector similarity
│   │   ├── google.py       # Google Custom Search
│   │   ├── searxng.py      # Self-hosted SearxNG
│   │   ├── sqlite_fts.py   # SQLite FTS5 article search
│   │   └── session.py      # Shared requests.Session with SSRF-safe redirect handler
│   ├── __init__.py         # Package init
│   ├── logging_utils.py    # PipelineLogger, log_pipeline_event, log_article_event
│   ├── prompts.py          # Prompt builder, esc_xml_text, esc_xml_attr
│   ├── safe_fetch.py       # Safe HTTP fetch with SSRF protection, PinnedIPAdapter
│   ├── newsletter.py       # Newsletter service (delivery, SMTP)
│   ├── rss.py              # RSS/Atom feed utilities
│   ├── redis_utils.py      # Redis helper functions
│   ├── date_utils.py       # Date parsing and formatting
│   ├── pagination.py       # Pagination helpers
│   ├── timeout.py          # Timeout utilities
│   ├── tracing.py          # OpenTelemetry tracing helpers
│   ├── utils.py            # General utility functions
│   ├── validation.py       # Validation utilities
│   ├── stage_cost.py       # Stage cost calculation
│   ├── tool_selection.py   # Tool selection for subagents
│   ├── researcher.py       # Research prompt builder
│   ├── writer.py           # Writer prompt builder
│   ├── editor.py           # Editor prompt builder
│   ├── crawling.py         # Source management, dedup
│   ├── content_extractor.py# trafilatura + readability
│   ├── trend_memory.py     # LLM-judged trend insights
│   ├── trend_detector.py   # Trend detection logic
│   ├── embeddings.py       # Vector embeddings
│   ├── cache.py            # ResponseCache (L1 + L2 Redis)
│   ├── limiter.py          # ModelLimiter (Redis concurrency)
│   ├── circuit_breaker.py  # Provider circuit breaker
│   ├── email.py            # SMTP with connection pooling
│   ├── webhooks.py         # HMAC-signed webhook dispatch
│   ├── pipeline_monitor.py # Redis stage metrics
│   ├── pipeline_degradation.py # Graceful degradation
│   ├── pipeline_failure.py # Stage failure handling
│   ├── pipeline_replay.py  # Pipeline rescue/replay
│   ├── pipeline_utils.py   # Shared stage dispatch
│   ├── newsletter_pipeline.py # Newsletter generation pipeline
│   ├── health.py           # Health check with degradation
│   ├── metrics.py          # Application metrics (Prometheus)
│   ├── cost_tracker.py     # LLM cost tracking
│   ├── alerts.py           # Deterministic health alerting
│   ├── quality.py          # Quality assessment (LLM-as-judge)
│   ├── quality_report.py   # Citation + claim verification
│   ├── quality_report_service.py # Quality report persistence
│   ├── related.py          # Related article finding
│   ├── source_intelligence.py # Source health analytics
│   ├── topic_gap.py        # Topic gap detection
│   ├── dedup_service.py    # Deduplication candidate finding
│   ├── subscribers.py      # Subscriber management
│   ├── audit.py            # Audit logging
│   ├── task_security.py    # HMAC task signing
│   ├── totp.py             # TOTP 2FA
│   ├── api_tokens.py       # API token generation/verification
│   ├── article.py          # Article service helpers
│   ├── article_validation.py # Article quality validation
│   ├── article_fallback.py # Fallback content extraction
│   ├── article_parser.py   # Article content parsing
│   ├── dead_letter.py      # Dead letter queue handling
│   ├── degradation.py      # Degradation service
│   ├── context_service.py  # Context service
│   ├── provider_base.py    # Base provider, provider manager
│   ├── url.py              # URL validation (SSRF prevention)
│   ├── config_cache.py     # Redis config cache (mtime-based)
│   ├── config_unified.py   # Unified config access
│   └── config_utils.py     # Celery-safe config helper
│
├── tasks/                  # Celery tasks
│   ├── __init__.py         # Task exports, autoretry defaults
│   ├── crawl.py            # run_all_sources, crawl_source
│   ├── extract.py          # process_item (content extraction)
│   ├── select.py           # select_article (LLM scoring)
│   ├── research.py         # research_article (LLM brief)
│   ├── write.py            # write_article (LLM condensation)
│   ├── edit.py             # edit_article (LLM editing + tags)
│   ├── pipeline.py         # run_stage() helper, shared utilities
│   ├── newsletter.py       # generate_daily_newsletters
│   ├── retry.py            # retry_stuck (dead-letter handling)
│   ├── cleanup.py          # Maintenance tasks (logs, versions, memory)
│   ├── scheduler.py        # publish_scheduled_articles
│   ├── embeddings.py       # backfill_embeddings
│   ├── webhook.py          # dispatch_webhook_task
│   └── subscribers.py      # cleanup_inactive_subscribers
│
├── routes/                 # Flask blueprints
│   ├── __init__.py         # Blueprint registration
│   ├── decorators.py       # @require_auth, commit(), commit_or_rollback()
│   ├── public/             # Public-facing routes
│   │   ├── feeds.py        # Article feeds, RSS, search
│   │   ├── subscribe.py    # Subscription management
│   │   └── links.py        # Short URLs, share tracking
│   ├── admin/              # Admin interface
│   │   ├── __init__.py     # Login, lockout, session mgmt
│   │   ├── auth.py         # Authentication routes
│   │   ├── dashboard.py    # Dashboard with stats
│   │   ├── articles.py     # Article CRUD + versions
│   │   ├── pipelines.py    # Pipeline monitoring
│   │   ├── sources.py      # Source management
│   │   ├── newsletters.py  # Newsletter management
│   │   ├── review.py       # Article review queue
│   │   ├── webhooks.py     # Webhook management
│   │   ├── trend_memory.py # Trend memory UI
│   │   ├── shares.py       # Share management
│   │   ├── subscribers.py  # Subscriber management
│   │   ├── topic_notes.py  # Topic notes UI
│   │   ├── metrics.py      # Metrics dashboard
│   │   ├── api_tokens.py   # API token management
│   │   └── api/            # Admin JSON API at /api/v1/*
│       ├── articles.py     # Article CRUD and pipeline control
│       ├── sources.py      # Source management
│       ├── pipeline.py     # Pipeline run control
│       ├── search.py       # Search analytics
│       ├── webhooks.py     # Webhook management
│       ├── config.py       # Configuration management
│       ├── audit.py        # Audit log access
│       ├── health.py       # Health check endpoints
│       ├── alerts.py       # Alerting API
│       ├── newsletter.py   # Newsletter performance API
│       ├── quality.py      # Quality report API
│       ├── replay.py       # Pipeline replay API
│       ├── source_intelligence.py  # Source intelligence API
│       ├── topic_gap.py    # Topic gap analysis API
│       ├── utils.py        # API utility functions
│       └── __init__.py
│
├── utils/                  # Pure utility functions
│   ├── __init__.py         # Package init
│   ├── url.py              # SSRF protection, URL normalization, DNS cache
│   ├── text.py             # XML escaping, truncation, HTML sanitization
│   ├── datetime.py         # Date parsing and formatting
│   ├── hash.py             # HMAC hash generation/verification
│   ├── html.py             # HTML processing, trafilatura fallback
│   └── security.py         # Token generation, constant-time compare
│
├── prompts/                # LLM prompt templates
│   ├── README.md           # Prompt template documentation
│   ├── selector.txt        # Article selection/scoring
│   ├── researcher.txt      # Research brief compilation
│   ├── writer.txt          # Smart Brevity article writing
│   ├── editor.txt          # Editorial review
│   ├── newsletter_reader.txt  # Newsletter theme analysis
│   ├── newsletter_writer.txt  # Newsletter summary writing
│   ├── newsletter_editor.txt  # Newsletter review
│   ├── subagent_research_synthesis.txt  # Subagent research context synthesis
│   └── subagent_edit_contextualization.txt  # Subagent editorial contextualization
│
├── templates/              # Jinja2 templates
│   ├── base.html           # Public site layout
│   ├── base_admin.html     # Admin layout
│   ├── index.html          # Home page
│   ├── article.html        # Article detail page
│   ├── tag.html            # Tag page
│   ├── topic.html          # Topic page
│   ├── share_redirect.html # Share redirect page
│   ├── unsubscribe.html    # Unsubscribe page
│   ├── verify.html         # Email verification page
│   ├── admin/              # Admin templates (20 files)
│   ├── partials/           # Reusable components (HTMX partials)
│   ├── macros/             # Jinja macros
│   └── errors/             # Error pages (404, 500, 429)
│
├── static/                 # Static assets
│   ├── css/                # Stylesheets (CSS custom properties, dark/light theme)
│   ├── js/                 # JavaScript (HTMX, theme, toast, app)
│   ├── svg/                # Topic icons and UI icons
│   └── manifest.json       # PWA manifest
│
├── tests/                  # Test suite (120+ files)
│   ├── conftest.py         # Shared fixtures
│   ├── factories.py        # Test data factories
│   ├── mock_redis.py       # MockRedis for testing
│   ├── helpers/            # Pipeline test helpers
│   └── test_*.py           # Test modules by component
│
├── ainews_cli/             # Operator CLI (Typer-based, Flask-free)
│   ├── main.py             # CLI entry point, command registration
│   ├── exit_codes.py       # Stable exit codes
│   ├── context.py          # CLIContext, output formatting
│   ├── profiles.py         # Deployment/pipeline/source profiles
│   ├── schema.py           # Bootstrap YAML schema
│   ├── onboard.py          # Onboarding state machine (16 stages)
│   ├── migrations.py       # DB migration detection/execution
│   ├── backup_commands.py  # Backup/restore CLI commands
│   ├── channel/            # Channel management (show/set)
│   ├── doctor/             # System diagnostics (7 check modules)
│   ├── lifecycle/          # Service lifecycle (Docker Compose/bare metal)
│   ├── pipeline/           # Pipeline administration
│   ├── providers/          # Provider management (6 built-in adapters)
│   ├── sources/            # Source management (OPML, adapters)
│   ├── topics/             # Topic management
│   ├── update/             # Update engine (check/plan/apply/rollback/status)
│   └── uninstall/          # Safe uninstall (path ownership, purge)
│
├── ainews_config/          # Configuration engine (Flask-free)
│   ├── paths.py            # 5-level path precedence, InstallMetadata
│   ├── fields.py           # Typed field registry (80+ keys)
│   ├── loader.py           # Dotenv/YAML parsing
│   ├── validation.py       # Cross-file semantic checks
│   ├── transaction.py      # Flock-based atomic writes
│   ├── backup.py           # Backup/restore/migration framework
│   └── migrations.py       # Config schema migrations
│
├── migrations/             # Alembic database migrations (37 versions)
├── scripts/                # Utility scripts (backup, deploy, dev)
├── docs/                   # Additional documentation (38 files)
├── architecture/           # Architecture documentation (this directory)
│
├── providers.yaml          # LLM + search provider definitions
├── pipeline.yaml           # Pipeline stage + newsletter + subagent config
├── sources.yaml            # News source definitions
├── topics.yaml             # Topic definitions for classification
├── openapi.yaml            # API specification
├── docker-compose.yml      # Docker Compose configuration
└── docker-compose.ollama.yml  # Docker Compose override for Ollama
```

---

## Deep Dive Documents

Each component has a dedicated document for detailed exploration.

### Core Application

- **[models.md](models.md)** — Complete model inventory, field definitions, relationships, indexes, pipeline status flow
- **[schemas.md](schemas.md)** — Pipeline config (PipelineRootConfig), source adapter config, LLM response schemas, task validation
- **[adapters.md](adapters.md)** — Adapter pattern with registry, RSS/API/Web implementations, SSRF protection, session ownership
- **[services.md](services.md)** — LLM provider system, pipeline services, infrastructure services, layering violations
- **[tasks.md](tasks.md)** — Task inventory by stage, run_stage helper, quality gates, degradation path, Celery Beat schedule
- **[routes.md](routes.md)** — Blueprint structure, public routes, admin interface, API endpoints (`/api/v1/*`), auth, templates
- **[utils.md](utils.md)** — URL validation (SSRF + DNS cache), text escaping, datetime, hash, HTML, security utilities

### Pipeline & AI

- **[pipeline.md](pipeline.md)** — Article pipeline stages, newsletter generation flow (3-stage LLM), scheduled tasks, degradation behavior, two-tier retry system
- **[subagent.md](subagent.md)** — Tool registry (14 built-in tools), runner with tool loop, chain system with conditions, middleware, error handling
- **[llm-providers.md](llm-providers.md)** — BaseLLMProvider interface, provider implementations, fallback chain, circuit breaker, retry with backoff, cost tracking
- **[search-providers.md](search-providers.md)** — Provider registry, DuckDuckGo/Hybrid/Google/SearxNG, FTS5 article search, hybrid search
- **[prompts.md](prompts.md)** — Prompt template system, stage-specific prompts, context truncation, A/B experiment variants

### Infrastructure & Configuration

- **[config.md](config.md)** — YAML config files, Pydantic validation, config caching, environment variables, beat schedule
- **[infrastructure.md](infrastructure.md)** — Redis patterns, SQLite WAL, Celery architecture, email delivery, health checks, rate limiting, caching

---

## Known Architecture Notes

- **Subagent system**: Located at `services/subagent/` (not at top level)
- **API prefix**: Admin API endpoints are at `/api/v1/` (not `/admin/api/`)
- **Adapter config field**: Source config uses `config` (not `adapter_config`)
- **StageConfig stub**: `StageConfig` in schemas/pipeline.py only has `tools` field; actual config in `RoleConfig`
- **NewsletterBrief fields**: Actual model does NOT have `preamble`, `footer`, or `articles` fields
- **Rate limiter pattern**: Always release in `finally` block using `provider_id or rc.provider`
- **Dynamic fallback chain**: Provider chain determined by enabled providers in `providers.yaml`, not hardcoded
- **utils/url.py not pure**: `validate_url_safe()` uses global mutable state (`_dns_cache`, `_dns_executor`). Documented in utils.md.
- **PipelineLog meta field**: Uses `meta` (not `metadata`) due to SQLAlchemy reserved name restriction
- **Logout requires POST**: CSRF protection at `/admin/logout` — do not add GET
- **ToolDefinition**: Does NOT have a `cached` field (older documentation may suggest otherwise)
- **Newsletter config**: `NewsletterBrief` schema does NOT have `articles` or `footer` fields
- **MetricsCollector methods**: `counter_inc()`, `gauge_set()`, `histogram_observe()` — NOT `increment()`, `set_gauge()`, `observe()`
- **ModelLimiter interface**: `acquire(provider_id, model, max_concurrent)` — NOT `acquire(slots=1)`
- **CircuitBreaker constructor**: Requires `name` param — `CircuitBreaker(name, failure_threshold=5)`
- **Health check function**: `run_health_checks()` — NOT `check_health()`
- **Subagent tool count**: 14 tools (12 context + 2 search), NOT 9
