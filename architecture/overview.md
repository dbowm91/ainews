# Architecture Overview

ainews is an autonomous AI-powered tech news aggregation and newsletter system. It crawls multiple news sources, uses LLMs to research and write condensed articles, and delivers personalized newsletters to subscribers.

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
│  │   (feedparser)   │  │   (JSONPath)     │  │  (BeautifulSoup) │           │
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
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
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

## Module Index

This document provides a **birds-eye view** of the system. Each module has a corresponding deep-dive document in this directory.

| Module | Description | Deep Dive |
|--------|-------------|-----------|
| [Models](models.md) | SQLAlchemy database models for all entities | [models.md](models.md) |
| [Services](services.md) | Business logic, LLM providers, pipeline orchestration | [services.md](services.md) |
| [Adapters](adapters.md) | Source fetchers (RSS, API, Web) following adapter pattern | [adapters.md](adapters.md) |
| [Routes](routes.md) | Flask blueprints for public and admin interfaces | [routes.md](routes.md) |
| [Tasks](tasks.md) | Celery tasks implementing the newsletter pipeline | [tasks.md](tasks.md) |
| [Schemas](schemas.md) | Pydantic validation models for configuration and responses | [schemas.md](schemas.md) |
| [Utils](utils.md) | Pure utility functions with minimal dependencies | [utils.md](utils.md) |
| [Subagent](subagent.md) | Tool-enabled LLM agents for contextualization | [subagent.md](subagent.md) |
| [Pipeline](pipeline.md) | Newsletter generation and article processing flow | [pipeline.md](pipeline.md) |

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

## Key Configuration Files

| File | Purpose |
|------|---------|
| `pipeline.yaml` | Pipeline stage configs, newsletter settings, subagent configs, schedules |
| `providers.yaml` | LLM provider definitions (ollama, openai, anthropic, etc.) |
| `sources.yaml` | News source definitions with adapter types and URLs |
| `topics.yaml` | Topic definitions for article classification |
| `config.py` | Flask configuration classes (Development, Production, Testing) |

## Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Server | Granian (ASGI) | High-performance Python HTTP server |
| Task Queue | Celery + Redis | Async task processing and scheduling |
| Database | SQLite (WAL) | Primary data store with WAL mode |
| Cache | Redis | Rate limiting, distributed locks, caching |
| Email | SMTP | Newsletter delivery with connection pooling |

## External Integrations

### LLM Providers (via `providers.yaml`)

- **ollama-local** (default, enabled) - Local Ollama instance
- **openai**, **anthropic**, **gemini**, **deepseek**, **groq**, **openrouter** (disabled)
- **xai**, **togetherai**, **fireworks**, **cerebras**, **zai**, **minimax**, **opencode** (disabled)

Note: Subagent system is located at `services/subagent/` (not at top level).

### Search Providers

- **duckduckgo** (default, enabled) - Web search
- **google** (disabled) - Google Custom Search
- **searxng** (disabled) - Self-hosted SearxNG

## Security Architecture

- **Fail-Closed**: Production startup validates all required secrets
- **TOTP 2FA**: Admin users with 8 backup codes
- **Session Binding**: IP + User-Agent validation
- **HMAC Webhooks**: Timestamp replay protection
- **SSRF Protection**: URL allowlist validation
- **Encrypted Secrets**: Webhook secrets encrypted at rest
- **Login Lockout**: Redis-based with in-memory fallback

## Directory Structure

```
ainews/
├── app.py                  # Flask application factory
├── config.py               # Configuration classes
├── extensions.py           # Flask extensions (db, limiter, redis)
├── constants.py            # Pipeline status values, shared constants
├── celery_app.py           # Celery application setup
├── pipeline.yaml           # Pipeline stage configuration
├── providers.yaml          # LLM/search provider definitions (14 providers)
├── sources.yaml            # News source definitions
├── topics.yaml             # Topic definitions for article classification
├── models/                 # SQLAlchemy models
├── services/               # Business logic (NO adapter imports)
│   ├── subagent/           # Tool-enabled LLM agents
│   ├── llm/                # LLM provider implementations
│   └── search/             # Search provider implementations
├── adapters/               # Source adapters (NO service imports)
├── routes/                 # Flask blueprints
│   ├── admin/              # Admin interface + API
│   └── public/             # Public-facing routes
├── tasks/                  # Celery tasks
├── schemas/                # Pydantic models
├── utils/                  # Pure utilities
├── prompts/                # LLM prompt templates
├── scripts/                # Utility scripts
├── templates/              # Jinja templates
└── tests/                  # Test suite
```

## Layering Rules

The codebase follows strict layering to maintain separation of concerns:

| Layer | Can Import | Cannot Import |
|-------|-----------|---------------|
| Adapters | `utils/` | `services/`, `models/` |
| Services | `models/`, `schemas/` | `adapters/` |
| Tasks | `services/` | - |
| Routes | `models/`, `schemas/`, `services/` | `adapters/` |

See individual module docs for details and known layering violations.

---

## Deep Dive Documents

Each module listed above has a dedicated deep-dive document. Use these links to explore in detail:

### [models.md](models.md)
- Complete file inventory and model relationships
- Article model with pipeline_status flow
- Source health tracking model
- TrendMemory embedding-based semantic tracking
- Index definitions for query performance

### [services.md](services.md)
- LLM provider system architecture
- Circuit breaker pattern implementation
- Pipeline services (researcher, writer, editor)
- Rate limiter with Redis pub/sub
- Email and webhook infrastructure
- Trend memory and content extraction

### [adapters.md](adapters.md)
- Adapter pattern with registry decorator
- RSS, API, and Web adapter implementations
- SSRF protection via SSRFSafeRedirectHandler
- Source configuration from sources.yaml
- Error handling conventions

### [routes.md](routes.md)
- Blueprint structure (public_bp, admin_bp, admin_api_bp)
- Public routes for feeds, subscription, links
- Admin interface and API endpoints
- Authentication with TOTP 2FA
- Template structure

### [tasks.md](tasks.md)
- Complete task inventory by stage
- Stage transitions and quality gates
- Core tasks (crawl, extract, select, research, write, edit)
- run_stage helper for standard lifecycle
- Celery Beat schedule details

### [schemas.md](schemas.md)
- Pipeline configuration schema
- Source adapter configuration (RSS, API, Web)
- LLM response schemas (SelectionResult, ResearchBrief, CondensedArticle)
- Task validation schemas

### [utils.md](utils.md)
- URL utilities with SSRF protection
- Text processing and XML escaping
- DateTime parsing and formatting
- Security and hash utilities
- HTML processing

### [subagent.md](subagent.md)
- Tool registry with built-in context tools
- Tool implementations for articles, trends, search
- Subagent runner with retry and revocation checking
- Chain system with conditional branching
- Middleware for logging and timing

### [pipeline.md](pipeline.md)
- Complete pipeline stage details
- Newsletter generation flow (3-stage LLM)
- Scheduled tasks (14 tasks)
- Degradation behavior
- Two-tier retry system
- Circuit breaker and fallback chain