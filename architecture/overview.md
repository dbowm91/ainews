# Architecture Overview

ainews is an autonomous AI-powered tech news aggregation and newsletter system. It crawls multiple news sources, uses LLMs to research and write condensed articles, and delivers personalized newsletters to subscribers.

---

## Module Index

This document provides a **birds-eye view** of the system architecture. Each module below links to its detailed deep-dive document.

| Module | File | Description |
|--------|------|-------------|
| [Overview](overview.md) | This file | System architecture index |
| [Models](models.md) | `models/` | SQLAlchemy database models |
| [Adapters](adapters.md) | `adapters/` | Source fetchers (RSS, API, Web) |
| [Services](services.md) | `services/` | Business logic and LLM providers |
| [Tasks](tasks.md) | `tasks/` | Celery tasks for pipeline |
| [Routes](routes.md) | `routes/` | Flask blueprints |
| [Schemas](schemas.md) | `schemas/` | Pydantic validation models |
| [Pipeline](architecture/pipeline.md) | — | Newsletter generation flow |
| [Subagent](architecture/subagent.md) | `services/subagent/` | Tool-enabled LLM agents |
| [Utils](utils.md) | `utils/` | Pure utility functions |

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Systems                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  RSS Feeds  │  │  REST APIs  │  │  Web Pages  │  │  SMTP Mail  │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
└─────────┼────────────────┼────────────────┼────────────────┼──────────────┘
          │                │                │                │
          ▼                ▼                ▼                │
┌─────────────────────────────────────────────────────────────────────────────┐
│                               Adapters Layer                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           │
│  │    RSSAdapter    │  │    APIAdapter    │  │    WebAdapter    │           │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘           │
└───────────┼────────────────────┼────────────────────┼───────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Services Layer                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Researcher  │  │    Writer    │  │    Editor    │  │   Subagent   │     │
│  │  (research)  │  │   (write)    │  │   (edit)     │  │   (tools)    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │                 │             │
│         └─────────────────┴────────┬────────┴─────────────────┘             │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐              │
│         │                          ▼                          │              │
│         │              Newsletter Pipeline                     │              │
│         │   (select → research → write → edit → finalize)     │              │
│         └──────────────────────────┬──────────────────────────┘              │
│                                    │                                        │
│  ┌─────────────────────────────────┼─────────────────────────────────┐       │
│  │                                 │                                 │       │
│  ▼                                 ▼                                 ▼       │
│ ┌──────────┐               ┌──────────────┐                ┌────────────┐   │
│ │  Models  │               │    Routes    │                │   Tasks    │   │
│ │   (DB)   │               │   (Flask)    │                │  (Celery)  │   │
│ └──────────┘               └──────────────┘                └────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │       Infrastructure Layer        │
                    │  ┌─────────┐  ┌─────────────┐    │
                    │  │  Redis  │  │   SQLite    │    │
                    │  │(broker) │  │    (DB)     │    │
                    │  └─────────┘  └─────────────┘    │
                    └─────────────────────────────────┘
```

---

## Directory Structure

```
ainews/
├── app.py                  # Flask application factory
├── config.py               # Configuration classes (Dev, Prod, Test)
├── celery_app.py           # Celery application setup
├── constants.py            # Pipeline status values, shared constants
├── extensions.py           # Flask extensions (db, limiter, redis)
├── models/                 # SQLAlchemy models (article, source, newsletter, etc.)
├── services/               # Business logic (NO adapter imports)
│   ├── llm/               # LLM provider implementations
│   ├── subagent/          # Tool-enabled LLM agents
│   └── search/            # Search provider implementations
├── adapters/               # Source adapters (NO service imports)
├── routes/                 # Flask blueprints
│   ├── admin/             # Admin interface + JSON API at /api/v1
│   └── public/            # Public-facing routes
├── tasks/                  # Celery tasks (pipeline stages, cleanup, etc.)
├── schemas/                # Pydantic models (validation, configuration)
├── utils/                  # Pure utilities (url, text, datetime, hash, html, security)
├── templates/              # Jinja templates
├── prompts/                # LLM prompt templates
├── scripts/                # Utility scripts
├── tests/                  # Test suite
├── plans/                  # Implementation plans
├── sources.yaml            # News source definitions
├── pipeline.yaml           # Pipeline stage configurations
├── providers.yaml          # LLM/search provider definitions
└── topics.yaml             # Topic definitions for article classification
```

---

## Layering Rules

Strict separation of concerns maintains modularity:

| Layer | Can Import | Cannot Import |
|-------|-----------|---------------|
| **Adapters** | `utils/` | `services/`, `models/` |
| **Services** | `models/`, `schemas/` (TYPE_CHECKING for type hints only) | `adapters/` |
| **Tasks** | `services/` | — |
| **Routes** | `models/`, `schemas/`, `services/` | `adapters/` |

**TYPE_CHECKING exception:** Services may use `TYPE_CHECKING` imports from adapters for type hints only (e.g., `from adapters.base import RawItem`). This allows static type analysis without creating runtime imports between layers.

**Known intentional layer violations (do not fix):**
- `schemas/common.py` imports from `services.config_cache` (documented in schemas.md)
- `services/subagent/tools.py` imports from `models` and `extensions` (documented in AGENTS.md)
- `tasks/crawl.py` imports directly from `adapters.base` (documented in AGENTS.md)

---

## Data Flow Summary

### 1. Source Ingestion

```
Sources (RSS/API/Web)
    │
    ▼
Adapters.fetch_and_parse()
    │
    ▼
process_item task
    │
    ├── extract_content()     # trafilatura/readability
    ├── deduplicate()         # URL + title matching
    └── create Article record
    │
    ▼
dispatch to select_article
```

### 2. Article Processing Pipeline

```
select_article
    │  LLM scores 1-10
    ▼
research_article
    │  LLM builds research brief with web search + context
    ▼
write_article
    │  LLM writes condensed article (Smart Brevity format)
    ▼
edit_article
    │  LLM edits + contextualization via subagent tools
    │  Tag assignment + validation
    ▼
finalize_article
    │  Trend memory update + webhook dispatch
    ▼
done
```

### 3. Newsletter Generation

```
generate_daily_newsletters (scheduled 8:00 AM ET)
    │
    ├── fetch_articles()      # DONE status, last 24h, impact_score > 0
    │
    ├── executive_summary     # reader → writer → editor (3-stage)
    │
    ├── main_newsletter       # built from articles
    │
    └── topic_newsletters     # per-topic groupings
        │
        └── email_dispatch    # batched (500/retry)
```

---

## Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Server | Granian (ASGI) | High-performance Python HTTP server |
| Task Queue | Celery + Redis | Async task processing and scheduling |
| Database | SQLite (WAL) | Primary data store with WAL mode |
| Cache | Redis | Rate limiting, distributed locks, caching |
| Email | SMTP | Newsletter delivery with connection pooling |

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `pipeline.yaml` | Pipeline stage configs, newsletter settings, subagent configs, schedules |
| `providers.yaml` | LLM provider definitions (16 providers: ollama, openai, anthropic, etc.) - 2 currently enabled (ollama-local, duckduckgo) |
| `sources.yaml` | News source definitions with adapter types and URLs |
| `topics.yaml` | Topic definitions for article classification |
| `config.py` | Flask configuration classes (Development, Production, Testing) |

---

## External Integrations

### LLM Providers (via `providers.yaml`)

- **ollama-local** (default, enabled) - Local Ollama instance
- **openai**, **anthropic**, **gemini**, **deepseek**, **groq**, **openrouter** (disabled)
- **xai**, **togetherai**, **fireworks**, **cerebras**, **zai**, **minimax**, **opencode** (disabled)

### Search Providers

- **duckduckgo** (default, enabled) - Web search
- **google** (disabled) - Google Custom Search
- **searxng** (disabled) - Self-hosted SearxNG
- **hybrid** (enabled) - FTS5 + vector similarity

---

## Security Architecture

- **Fail-Closed**: Production startup validates all required secrets
- **TOTP 2FA**: Admin users with 8 backup codes
- **Session Binding**: IP + User-Agent validation
- **HMAC Webhooks**: Timestamp replay protection
- **SSRF Protection**: URL allowlist validation with DNS rebinding detection
- **Encrypted Secrets**: Webhook secrets encrypted at rest
- **Login Lockout**: Redis-based with in-memory fallback

---

## Deep Dive Documents

Each module has a dedicated deep-dive document. Click any link below to explore that component in detail.

### [models.md](models.md)
- Complete file inventory and model relationships
- Article model with pipeline_status flow
- Source health tracking model
- TrendMemory embedding-based semantic tracking
- Index definitions for query performance

### [adapters.md](adapters.md)
- Adapter pattern with registry decorator
- RSS, API, and Web adapter implementations
- SSRF protection via SSRFSafeRedirectHandler
- Source configuration from sources.yaml
- Error handling conventions

### [services.md](services.md)
- LLM provider system architecture (base class, implementations)
- Circuit breaker pattern for provider fallback
- Pipeline services (researcher, writer, editor)
- Rate limiter with Redis pub/sub
- Email and webhook infrastructure
- Trend memory and content extraction

### [tasks.md](tasks.md)
- Complete task inventory by stage
- Stage transitions and quality gates
- Core tasks (crawl, extract, select, research, write, edit)
- run_stage helper for standard lifecycle
- Celery Beat schedule (14 scheduled tasks)

### [routes.md](routes.md)
- Blueprint structure (public_bp, admin_bp, admin_api_bp)
- Public routes for feeds, subscription, links
- Admin interface and JSON API endpoints at /api/v1
- Authentication with TOTP 2FA
- Template structure

### [schemas.md](schemas.md)
- Pipeline configuration schema (PipelineRootConfig)
- Source adapter configuration (RSSConfig, APIConfig, WebConfig)
- LLM response schemas (SelectionResult, ResearchBrief, CondensedArticle)
- Task validation schemas
- NewsletterBrief clarification (no preamble/footer/articles fields)

### [pipeline.md](pipeline.md)
- Complete pipeline stage details
- Newsletter generation flow (3-stage LLM: reader → writer → editor)
- Scheduled tasks (14 tasks)
- Degradation behavior
- Two-tier retry system (Celery task retry + stage failure retry)
- Circuit breaker and dynamic fallback chain

### [subagent.md](subagent.md)
- Tool registry with built-in context tools
- Tool implementations for articles, trends, search
- Subagent runner with retry and revocation checking
- Chain system with conditional branching
- Middleware for logging and timing

### [utils.md](utils.md)
- URL utilities with SSRF protection and DNS caching
- Text processing and XML escaping
- DateTime parsing and formatting
- Security and hash utilities
- HTML processing with trafilatura fallback

---

## Entry Points

| Entry Point | Purpose |
|-------------|---------|
| `python run.py` | Development server |
| `flask db upgrade` | Database migrations |
| `celery -A celery_app:celery_app worker` | Celery worker |
| `celery -A celery_app:celery_app beat` | Celery beat scheduler |
| `python scripts/hash_password.py` | Generate admin password hash |

---

## Known Architecture Notes

- **Subagent system**: Located at `services/subagent/` (not at top level)
- **API prefix**: Admin API endpoints are at `/api/v1/` (not `/admin/api/`)
- **Adapter config field**: Source config uses `config` (not `adapter_config`)
- **StageConfig stub**: `StageConfig` in schemas/pipeline.py only has `tools` field; actual config in `RoleConfig`
- **NewsletterBrief fields**: Actual model does NOT have `preamble`, `footer`, or `articles` fields
- **Rate limiter pattern**: Always release in `finally` block using `provider_id or rc.provider`
- **Dynamic fallback chain**: Provider chain determined by enabled providers in `providers.yaml`, not hardcoded
- **utils/url.py not pure**: `validate_url_safe()` and related DNS functions use global mutable state (`_dns_cache`, `_dns_executor`). Documented in utils.md.