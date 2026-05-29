# Architecture Overview

ainews is an autonomous AI-powered tech news aggregation and newsletter system. It crawls multiple news sources, uses LLMs to research and write condensed articles, and delivers personalized newsletters to subscribers.

---

## Module Index

This document provides a **bird's-eye view** of the system architecture. Each module below links to its detailed deep-dive document.

### Core Application Modules

| Module | Deep Dive | Description |
|--------|-----------|-------------|
| [Models](models.md) | `models/` | SQLAlchemy database models (Article, Source, Newsletter, etc.) |
| [Schemas](schemas.md) | `schemas/` | Pydantic validation models for config, LLM responses, tasks |
| [Adapters](adapters.md) | `adapters/` | Source fetchers (RSS, API, Web) with SSRF protection |
| [Services](services.md) | `services/` | Business logic, LLM interactions, infrastructure services |
| [Tasks](tasks.md) | `tasks/` | Celery tasks implementing the article pipeline |
| [Routes](routes.md) | `routes/` | Flask blueprints (public, admin, admin API) |
| [Utils](utils.md) | `utils/` | Pure utility functions (URL, text, datetime, hash, HTML, security) |

### Pipeline & AI Modules

| Module | Deep Dive | Description |
|--------|-----------|-------------|
| [Pipeline](pipeline.md) | — | Article processing pipeline stages and newsletter generation |
| [Subagent](subagent.md) | `services/subagent/` | Tool-enabled LLM agents for context and research |
| [LLM Providers](llm-providers.md) | `services/llm/` | Multi-provider LLM architecture with fallback chain |
| [Search Providers](search-providers.md) | `services/search/` | Web search and article search providers |
| [Prompts](prompts.md) | `prompts/` | LLM prompt templates for pipeline stages |

### Infrastructure & Configuration

| Module | Deep Dive | Description |
|--------|-----------|-------------|
| [Configuration](config.md) | `config.py`, `pipeline.yaml`, `providers.yaml` | Config system, validation, and YAML files |
| [Infrastructure](infrastructure.md) | Redis, SQLite, Celery, email | Core infrastructure services and patterns |

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
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
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
│  │  │ (fallback) │ │  (tools)   │ │  Memory    │ │  Providers │          │    │
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
│  │ (pipeline stages)│  │   (scheduler)    │  │ (routes + admin) │              │
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

## Directory Structure

```
ainews/
├── app.py                  # Flask application factory
├── config.py               # Configuration classes (Dev, Prod, Test) + beat schedule
├── celery_app.py           # Celery application setup + FlaskTask base
├── constants.py            # PipelineStatus enum, shared constants
├── extensions.py           # Flask extensions (db, redis, limiter)
├── run.py                  # WSGI/ASGI entry point (Granian)
├── logging_config.py       # Structured JSON logging + OpenTelemetry
│
├── models/                 # SQLAlchemy models
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
│   └── share.py            # ShareConfig
│
├── schemas/                # Pydantic models
│   ├── pipeline.py         # PipelineRootConfig, RoleConfig, SubagentConfig
│   ├── source.py           # SourceConfig, RSSConfig, APIConfig, WebConfig
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
│   ├── base.py             # BaseSourceAdapter + registry
│   ├── rss.py              # RSS/Atom feed adapter
│   ├── api.py              # REST API adapter
│   ├── web.py              # Web scraping adapter
│   └── session.py          # Shared HTTP session + SSRF protection
│
├── services/               # Business logic layer (65+ files)
│   ├── llm/                # LLM provider implementations
│   │   ├── __init__.py     # Provider registry + fallback chain
│   │   ├── base.py         # BaseLLMProvider + ToolDefinition
│   │   ├── openai.py       # OpenAI + OpenAI-compatible providers
│   │   ├── anthropic.py    # Anthropic Claude
│   │   ├── gemini.py       # Google Gemini
│   │   ├── ollama.py       # Local Ollama
│   │   ├── errors.py       # Error classification
│   │   └── json_utils.py   # JSON parsing for LLM responses
│   ├── subagent/           # Tool-enabled LLM agents
│   │   ├── runner.py       # run_subagent(), tool loop
│   │   ├── chain.py        # Multi-step chains with conditions
│   │   ├── tools.py        # Built-in tool implementations
│   │   ├── registry.py     # Tool registry
│   │   ├── middleware.py    # Logging, timing, error handling
│   │   └── conditions.py   # AST-based condition evaluation
│   ├── search/             # Search providers
│   │   ├── duckduckgo.py   # DuckDuckGo (default)
│   │   ├── hybrid.py       # FTS5 + vector similarity
│   │   ├── google.py       # Google Custom Search
│   │   └── searxng.py      # Self-hosted SearxNG
│   ├── researcher.py       # Research prompt builder
│   ├── writer.py           # Writer prompt builder
│   ├── editor.py           # Editor prompt builder
│   ├── crawling.py         # Source management, dedup
│   ├── content_extractor.py# trafilatura + readability
│   ├── trend_memory.py     # LLM-judged trend insights
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
│   ├── health.py           # Health check with degradation
│   ├── metrics.py          # Application metrics (Prometheus)
│   ├── cost_tracker.py     # LLM cost tracking
│   ├── alerts.py           # Deterministic health alerting
│   ├── quality.py          # Quality assessment (LLM-as-judge)
│   ├── quality_report.py   # Citation + claim verification
│   ├── related.py          # Related article finding
│   ├── source_intelligence.py # Source health analytics
│   ├── topic_gap.py        # Topic gap detection
│   ├── dedup_service.py    # Deduplication candidate finding
│   ├── subscribers.py      # Subscriber management
│   ├── audit.py            # Audit logging
│   ├── task_security.py    # HMAC task signing
│   ├── totp.py             # TOTP 2FA
│   ├── config_cache.py     # Redis config cache (mtime-based)
│   ├── config_unified.py   # Unified config access
│   └── config_utils.py     # Celery-safe config helper
│
├── tasks/                  # Celery tasks
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
│   ├── public/             # Public-facing routes
│   │   ├── feeds.py        # Article feeds, RSS, search
│   │   ├── subscribe.py    # Subscription management
│   │   └── links.py        # Short URLs, share tracking
│   ├── admin/              # Admin interface
│   │   ├── __init__.py     # Login, lockout, session mgmt
│   │   ├── dashboard.py    # Dashboard with stats
│   │   ├── articles.py     # Article CRUD + versions
│   │   ├── pipelines.py    # Pipeline monitoring
│   │   ├── sources.py      # Source management
│   │   ├── newsletters.py  # Newsletter management
│   │   ├── review.py       # Article review queue
│   │   ├── webhooks.py     # Webhook management
│   │   ├── trend_memory.py # Trend memory UI
│   │   ├── api_tokens.py   # API token management
│   │   └── api/            # Admin JSON API (/api/v1/*)
│   └── decorators.py       # @require_auth, commit(), commit_or_rollback()
│
├── utils/                  # Pure utility functions
│   ├── url.py              # SSRF protection, URL normalization, DNS cache
│   ├── text.py             # XML escaping, truncation, HTML sanitization
│   ├── datetime.py         # Date parsing and formatting
│   ├── hash.py             # HMAC hash generation/verification
│   ├── html.py             # HTML processing, trafilatura fallback
│   └── security.py         # Token generation, constant-time compare
│
├── prompts/                # LLM prompt templates
│   ├── selector.txt        # Article selection/scoring
│   ├── researcher.txt      # Research brief compilation
│   ├── writer.txt          # Smart Brevity article writing
│   ├── editor.txt          # Editorial review
│   ├── newsletter_reader.txt  # Newsletter theme analysis
│   ├── newsletter_writer.txt  # Newsletter summary writing
│   └── newsletter_editor.txt  # Newsletter review
│
├── templates/              # Jinja2 templates
│   ├── base.html           # Public site layout
│   ├── base_admin.html     # Admin layout
│   ├── admin/              # Admin templates
│   ├── partials/           # Reusable components (HTMX partials)
│   ├── macros/             # Jinja macros
│   └── errors/             # Error pages (404, 500, 429)
│
├── static/                 # Static assets
│   ├── css/                # Stylesheets (CSS custom properties, dark/light theme)
│   ├── js/                 # JavaScript (HTMX, theme, toast, app)
│   └── svg/                # Topic icons and UI icons
│
├── tests/                  # Test suite (97+ files)
│   ├── conftest.py         # Shared fixtures
│   ├── factories.py        # Test data factories
│   ├── mock_redis.py       # MockRedis for testing
│   ├── helpers/            # Pipeline test helpers
│   └── test_*.py           # Test modules by component
│
├── migrations/             # Alembic database migrations
├── scripts/                # Utility scripts (backup, deploy, dev)
├── plans/                  # Implementation plans
├── docs/                   # Additional documentation
├── architecture/           # Architecture documentation (this directory)
│
├── providers.yaml          # LLM + search provider definitions
├── pipeline.yaml           # Pipeline stage + newsletter + subagent config
├── sources.yaml            # News source definitions
├── topics.yaml             # Topic definitions for classification
└── openapi.yaml            # API specification
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

**TYPE_CHECKING exception:** Services may use `TYPE_CHECKING` imports from adapters for type hints only (e.g., `from adapters.base import RawItem`).

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

## Data Flow Summary

### 1. Source Ingestion (every 30 min)

```
Celery Beat -> run_all_sources()
  -> Creates PipelineRun record
  -> Celery chord: one crawl_source() per source (parallel)
     -> Loads SourceConfig from sources.yaml
     -> Instantiates adapter (RSS/API/Web) from registry
     -> adapter.fetch_and_parse() -> list[RawItem]
     -> Deduplicates by external_id
     -> Dispatches process_item() per new item
  -> aggregate_crawl_results() callback
```

### 2. Article Extraction (`tasks/extract.py`)

```
process_item(item_config, run_id)
  -> Validates input via ProcessItemTask schema
  -> Extracts content from URL if text too short (trafilatura)
  -> Checks for duplicates by normalized URL + title
  -> Creates Article record (pipeline_status="pending")
  -> Dispatches select_article
```

### 3. Article Processing Pipeline

```
select_article                    tasks/select.py
       │  LLM scores 1-10, assigns experiment group
       │  Quality gate: low confidence -> REVIEW
       ▼
research_article                  tasks/research.py
       │  Web search + synthesis via subagent
       │  Related articles, topic notes, trend memory
       │  LLM builds ResearchBrief
       │  Quality gate: degenerate brief -> REVIEW
       ▼
write_article                     tasks/write.py
       │  Trend memory context
       │  LLM writes CondensedArticle (Smart Brevity)
       │  Quality gate: short body/no points/citations -> REVIEW
       ▼
edit_article                      tasks/edit.py
       │  Subagent contextualization (topic notes + related articles)
       │  LLM refines article
       │  Tag assignment, validation, quality report
       │  Quality gate: validation failure -> REVIEW
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

## Key Configuration Files

| File | Purpose | Deep Dive |
|------|---------|-----------|
| `pipeline.yaml` | Pipeline stages, newsletter settings, subagent config, schedules, experiments | [config.md](config.md) |
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
| Backup | `scripts/backup.sh` | SQLite backup with verification |

---

## Deep Dive Documents

Each component has a dedicated document for detailed exploration. Click any link below.

### Core Application

- **[models.md](models.md)** — Complete model inventory, field definitions, relationships, indexes, pipeline status flow
- **[schemas.md](schemas.md)** — Pipeline config (PipelineRootConfig), source adapter config, LLM response schemas, task validation, newsletter brief clarification
- **[adapters.md](adapters.md)** — Adapter pattern with registry, RSS/API/Web implementations, SSRF protection, session ownership, error handling
- **[services.md](services.md)** — LLM provider system, pipeline services, infrastructure services, layering violations
- **[tasks.md](tasks.md)** — Task inventory by stage, run_stage helper, quality gates, degradation path, Celery Beat schedule (14 tasks)
- **[routes.md](routes.md)** — Blueprint structure, public routes, admin interface, API endpoints (/api/v1/*), auth, templates
- **[utils.md](utils.md)** — URL validation (SSRF + DNS cache), text escaping, datetime, hash, HTML, security utilities

### Pipeline & AI

- **[pipeline.md](pipeline.md)** — Article pipeline stages, newsletter generation flow (3-stage LLM), scheduled tasks, degradation behavior, two-tier retry system, circuit breaker
- **[subagent.md](subagent.md)** — Tool registry (14 built-in tools), runner with tool loop, chain system with conditions, middleware, error handling
- **[llm-providers.md](llm-providers.md)** — BaseLLMProvider interface, provider implementations, fallback chain, circuit breaker, retry with backoff, cost tracking
- **[search-providers.md](search-providers.md)** — Provider registry, DuckDuckGo/Hybrid/Google/SearxNG, FTS5 article search, hybrid search
- **[prompts.md](prompts.md)** — Prompt template system, stage-specific prompts, context truncation, A/B experiment variants

### Infrastructure & Configuration

- **[config.md](config.md)** — YAML config files, Pydantic validation, config caching, environment variables, beat schedule
- **[infrastructure.md](infrastructure.md)** — Redis patterns, SQLite WAL, Celery architecture, email delivery, health checks, rate limiting, caching

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
