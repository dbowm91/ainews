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

This document provides a **birds-eye view** of the system. For detailed reviews of each module, see the corresponding deep-dive documents:

| Module | Description | Deep Dive | Review Plan |
|--------|-------------|-----------|-------------|
| [Models](models.md) | SQLAlchemy database models for all entities | [models.md](models.md) | [models_review.md](../plans/models_review.md) |
| [Services](services.md) | Business logic, LLM providers, pipeline orchestration | [services.md](services.md) | [services_review.md](../plans/services_review.md) |
| [Adapters](adapters.md) | Source fetchers (RSS, API, Web) following adapter pattern | [adapters.md](adapters.md) | [adapters_review.md](../plans/adapters_review.md) |
| [Routes](routes.md) | Flask blueprints for public and admin interfaces | [routes.md](routes.md) | [routes_review.md](../plans/routes_review.md) |
| [Tasks](tasks.md) | Celery tasks implementing the newsletter pipeline | [tasks.md](tasks.md) | [tasks_review.md](../plans/tasks_review.md) |
| [Schemas](schemas.md) | Pydantic validation models for configuration and responses | [schemas.md](schemas.md) | [schemas_review.md](../plans/schemas_review.md) |
| [Utils](utils.md) | Pure utility functions with minimal dependencies | [utils.md](utils.md) | [utils_review.md](../plans/utils_review.md) |
| [Subagent](subagent.md) | Tool-enabled LLM agents for contextualization | [subagent.md](subagent.md) | [subagent_review.md](../plans/subagent_review.md) |
| [Pipeline](pipeline.md) | Newsletter generation and article processing flow | [pipeline.md](pipeline.md) | [pipeline_review.md](../plans/pipeline_review.md) |

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

Note: `services/subagent/` contains the subagent system (not at top level).

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
│   ├── subagent/            # Tool-enabled LLM agents (NOT at top level)
│   ├── llm/                 # LLM provider implementations
│   └── search/              # Search provider implementations
├── adapters/               # Source adapters (NO service imports)
├── routes/                 # Flask blueprints
│   ├── admin/              # Admin interface + API
│   └── public/             # Public-facing routes
├── tasks/                  # Celery tasks
├── schemas/                # Pydantic models
├── utils/                  # Pure utilities
├── prompts/                # LLM prompt templates
├── scripts/                # Utility scripts
├── templates/               # Jinja templates
└── tests/                  # Test suite
```

## Review Plan

Each module has a corresponding deep-dive review plan in the [`plans/`](../plans/) directory:

- [Models Review Plan](../plans/models_review.md) - Database schema, relationships, indexes
- [Adapters Review Plan](../plans/adapters_review.md) - Source fetching, SSRF protection, error handling
- [Services Review Plan](../plans/services_review.md) - Business logic, LLM providers, circuit breakers
- [Routes Review Plan](../plans/routes_review.md) - Endpoints, security, authentication
- [Tasks Review Plan](../plans/tasks_review.md) - Celery tasks, stage transitions, rate limiting
- [Schemas Review Plan](../plans/schemas_review.md) - Pydantic models, validation
- [Utils Review Plan](../plans/utils_review.md) - Pure utilities, URL validation, security
- [Subagent Review Plan](../plans/subagent_review.md) - Tool registry, chain system, runner
- [Pipeline Review Plan](../plans/pipeline_review.md) - Newsletter generation, degradation

Each review plan documents:
- **Verified Claims**: Architecture claims confirmed by code
- **Discrepancies**: Claims that don't match implementation
- **Improvement Recommendations**: Specific improvements with priority
- **Bugs Found**: Edge cases, race conditions, layer violations
- **Layer Violations**: Clean layering violations (adapters importing services, etc.)