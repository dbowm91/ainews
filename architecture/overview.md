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
├── services/               # Business logic layer
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
│   └── health.py           # Health check with degradation
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
│   ├── partials/           # Reusable components
│   ├── macros/             # Jinja macros
│   └── errors/             # Error pages (404, 500, 429)
│
├── static/                 # Static assets
│   ├── css/                # Stylesheets
│   ├── js/                 # JavaScript (app.js, share-a11y.js)
│   └── svg/                # Icons and images
│
├── tests/                  # Test suite (87+ files)
│   ├── conftest.py         # Shared fixtures
│   ├── factories.py        # Test data factories
│   └── test_*.py           # Test modules by component
│
├── migrations/             # Alembic database migrations
├── scripts/                # Utility scripts (backup, deploy, dev)
├── plans/                  # Implementation plans
├── docs/                   # Additional documentation
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
| **Adapters** | `utils/`, `schemas/` | `services/`, `models/` |
| **Services** | `models/`, `schemas/` | `adapters/` (TYPE_CHECKING OK) |
| **Tasks** | `services/`, `models/`, `schemas/` | `adapters/` (except `tasks/crawl.py`) |
| **Routes** | `models/`, `schemas/`, `services/` | `adapters/` |

**TYPE_CHECKING exception:** Services may use `TYPE_CHECKING` imports from adapters for type hints only (e.g., `from adapters.base import RawItem`).

**Known intentional layer violations (do not fix):**
- `schemas/common.py` imports from `services.config_cache`
- `services/subagent/tools.py` imports from `models` and `extensions`
- `tasks/crawl.py` imports directly from `adapters.base`

---

## Data Flow Summary

### 1. Source Ingestion

```
Sources (RSS/API/Web)         sources.yaml definitions
       │
       ▼
Adapters.fetch_and_parse()    adapters/{rss,api,web}.py
       │
       ▼
process_item task              tasks/extract.py
       │
       ├── extract_content()      trafilatura/readability
       ├── deduplicate()          URL + title matching
       └── create Article record
       │
       ▼
dispatch to select_article     tasks/select.py
```

### 2. Article Processing Pipeline

```
select_article                 tasks/select.py
       │  LLM scores 1-10, assigns experiment group
       ▼
research_article               tasks/research.py
       │  LLM builds research brief with web search + context
       │  Subagent: web_search, related_articles, trend_memory
       ▼
write_article                  tasks/write.py
       │  LLM writes condensed article (Smart Brevity format)
       ▼
edit_article                   tasks/edit.py
       │  Subagent contextualization + LLM editing
       │  Tag assignment + validation
       ▼
finalize                       tasks/pipeline.py
       │  Trend memory update + webhook dispatch
       ▼
done ✓
```

### 3. Newsletter Generation

```
generate_daily_newsletters     tasks/newsletter.py (scheduled 8:00 AM ET)
       │
       ├── fetch_articles()        DONE status, last 24h, impact_score > 0
       │
       ├── executive_summary       3-stage LLM pipeline:
       │   ├── reader              Extract themes/highlights
       │   ├── writer              Generate summary
       │   └── editor              Polish for clarity
       │
       ├── main_newsletter         HTML email with preamble + articles
       │
       └── _send_emails_parallel() Batch size: 500, retry: 3 attempts
```

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

---

## Key Configuration Files

| File | Purpose | Deep Dive |
|------|---------|-----------|
| `pipeline.yaml` | Pipeline stages, newsletter settings, subagent config, schedules, experiments | [config.md](config.md) |
| `providers.yaml` | LLM provider definitions (16 providers), search provider definitions | [config.md](config.md) |
| `sources.yaml` | News source definitions with adapter types and URLs | [config.md](config.md) |
| `topics.yaml` | Topic definitions for article classification | [config.md](config.md) |
| `config.py` | Flask configuration classes + Celery beat schedule | [config.md](config.md) |

---

## Security Architecture

| Feature | Implementation | Location |
|---------|---------------|----------|
| Fail-Closed | Production startup validates all secrets | `app.py` |
| TOTP 2FA | Admin users with 8 backup codes | `models/auth.py`, `services/totp.py` |
| Session Binding | IP + User-Agent validation | `routes/admin/__init__.py` |
| HMAC Webhooks | Timestamp replay protection | `services/webhooks.py` |
| SSRF Protection | URL validation + DNS rebinding detection | `utils/url.py`, `adapters/session.py` |
| Encrypted Secrets | Webhook secrets at rest (Fernet/AES-128-CBC) | `services/webhooks.py` |
| Login Lockout | Redis Lua script with in-memory fallback | `routes/admin/__init__.py` |
| Task Signing | HMAC task signature verification | `services/task_security.py` |
| XSS Prevention | Template `|e` filter, bleach HTML sanitization | `templates/`, `services/article.py` |
| CSP | Nonce-based script-src, strict directives | `app.py` |

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
- **[subagent.md](subagent.md)** — Tool registry (9 built-in tools), runner with tool loop, chain system with conditions, middleware, error handling
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
