# Developer Onboarding Guide

Welcome to the ainews development team. This guide will help you set up your local development environment and understand the codebase structure.

## Local Development Setup

### Prerequisites

- Python 3.12+
- Redis (running locally)
- Git

### 1. Clone and Install

```bash
git clone https://github.com/yourorg/ainews.git
cd ainews
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
FLASK_CONFIG=development
SECRET_KEY=dev-secret-key-change-in-production
ADMIN_PASSWORD=<run: python scripts/hash_password.py>
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### 3. Database Setup

```bash
# Initialize the database
flask db upgrade

# Or run all migrations
alembic upgrade head
```

### 4. Start Services

```bash
# Terminal 1: Start Redis (if not running)
redis-server

# Terminal 2: Start Celery worker
source .venv/bin/activate
celery -A celery_app worker --loglevel=info

# Terminal 3: Start Celery beat (for scheduled tasks)
celery -A celery_app beat --loglevel=info

# Terminal 4: Start Flask app
source .venv/bin/activate
flask run
```

Or use the dev script:

```bash
bash scripts/dev.sh
```

### 5. Verify Installation

```bash
curl http://localhost:5000/health
```

You should see:

```json
{"status": "ok", "checks": {...}}
```

---

## Code Structure

```
ainews/
├── app.py                  # Flask app factory
├── config.py               # Configuration classes
├── logging_config.py       # Logging setup
├── celery_app.py           # Celery app initialization
├── celery_support.py       # Celery support utilities
├── constants.py            # Shared constants
├── extensions.py           # Flask extensions (db, redis, etc.)
├── models.py               # SQLAlchemy models
├── routes/                 # Flask route handlers
│   ├── admin/             # Admin panel routes
│   └── public/            # Public-facing routes
├── services/              # Business logic services
│   ├── health.py          # Health check service
│   ├── limiter.py         # Rate limiting
│   ├── metrics.py         # Application metrics
│   └── ...
├── schemas/               # Data schemas and validators
│   ├── llm.py            # LLM provider configuration
│   ├── topic.py          # Topic/category definitions
│   └── ...
├── tasks/                # Celery tasks
│   ├── crawl.py          # Web crawling tasks
│   ├── pipeline.py       # Article processing pipeline
│   └── ...
├── migrations/           # Database migrations
├── scripts/              # Utility scripts
├── templates/            # Jinja2 templates
├── static/               # CSS, JS, images
└── tests/                # Test suite
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `routes/` | HTTP request handlers |
| `services/` | Business logic and external integrations |
| `tasks/` | Celery background tasks |
| `models.py` | Database schema |
| `schemas/` | Configuration and data validation |

---

## Common Development Tasks

### Running Tests

```bash
# Run all tests
.venv/bin/python -m pytest

# Run with coverage
.venv/bin/python -m pytest --cov=. --cov-report=term-missing

# Run specific test file
.venv/bin/python -m pytest tests/test_pipeline.py

# Run with verbose output
.venv/bin/python -m pytest -v
```

### Running Linters

```bash
# Run ruff linter
.venv/bin/ruff check .

# Fix auto-fixable issues
.venv/bin/ruff check --fix .

# Run with exclusions
.venv/bin/ruff check . --exclude .venv
```

### Database Migrations

```bash
# Create a new migration
flask db revision --autogenerate -m "Description of changes"

# Upgrade to latest
flask db upgrade

# Downgrade one step
flask db downgrade

# Show current version
flask db current
```

### Adding a New LLM Provider

Providers are defined in `providers.yaml`. For OpenAI-compatible providers, add a new entry:

```yaml
  - id: myprovider
    type: openai
    enabled: false
    config:
      api_key: "${MYPROVIDER_API_KEY}"
      base_url: "https://api.myprovider.com/v1"
      model: "my-model"
      max_tokens: 4096
```

For non-standard providers, create an adapter in `services/llm/`:

```python
# services/llm/myprovider.py
from services.llm.base import BaseLLMProvider, LLMResponse

class MyProviderAdapter(BaseLLMProvider):
    def chat_structured(self, messages, response_model, **kwargs) -> LLMResponse:
        # Implementation
        pass
```

### Adding a New Pipeline Stage

1. Add stage constant in `constants.py`:
```python
class PipelineStatus:
    NEW_STAGE = "new_stage"
```

2. Add task in `tasks/`:
```python
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def new_stage(self, article_id: int):
    # Implementation
    pass
```

3. Update pipeline in `tasks/pipeline.py` to call the new stage.

---

## Debugging Tools

### Logging

Structured JSON logging is used in production. For development, set `LOG_FORMAT=text`:

```bash
export LOG_FORMAT=text
flask run
```

Request IDs are included in all logs for tracing.

### Flask Debug Mode

```bash
export FLASK_DEBUG=1
flask run
```

Enables debugger and auto-reload.

### SQLAlchemy Query Logging

```bash
export SQLALCHEMY_ECHO=1
flask run
```

Logs all SQL queries.

### Celery Task Inspection

```bash
# View active tasks
celery -A celery_app inspect active

# View registered tasks
celery -A celery_app inspect registered

# View workers
celery -A celery_app inspect stats
```

### Redis CLI

```bash
# Connect to Redis
redis-cli

# View keys
KEYS *

# View task results
GET celery-result-*

# Monitor operations
MONITOR
```

---

## Architecture Overview

### Request Flow

1. **HTTP Request** → Nginx (SSL termination)
2. **Proxy Pass** → Flask via Granian (ASGI)
3. **Route Handler** → Service Layer
4. **Service Layer** → Database/Redis/Celery

### Pipeline Architecture

Articles flow through stages:

```
Research → Write → Edit → Newsletter
```

Note: `PipelineStatus.SELECTING` is deprecated and removed; selection logic is integrated into the research phase.

Each stage is a Celery task that can retry independently. On failure, the article enters a retry queue with exponential backoff.

### Data Flow

```
RSS Feed → Crawler → Extractor → Pipeline (Research/Write/Edit) → Database
                                                     ↓
                                            Newsletter Generator → Email
```

### Caching Strategy

- **Redis**: Celery broker, result backend, config cache, response cache
- **SQLite WAL**: Database with Write-Ahead Logging for concurrent reads

---

## Testing Guidelines

### Test Structure

- `tests/` mirrors the project structure
- Use factories in `tests/factories.py` for test data
- Mock Redis and Celery in unit tests

### Writing Tests

```python
def test_my_feature(app):
    with app.app_context():
        # Arrange
        article = create_article(title="Test")

        # Act
        result = my_service.process(article.id)

        # Assert
        assert result.status == "success"
```

### Fixtures

- `app` - Full Flask application
- `client` - Test client
- `db` - Database session
- `mock_redis` - Mocked Redis client
- `mock_celery_tasks` - Mocked Celery tasks

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_CONFIG` | `development` | Configuration mode |
| `SECRET_KEY` | - | Session encryption key |
| `ADMIN_PASSWORD` | - | Hashed admin password |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery message broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery results store |
| `DATABASE_URL` | `sqlite:///instance/ainews.db` | Database connection |
| `REDIS_URL` | `redis://localhost:6379/2` | Redis connection |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `DB_QUERY_LOG_LEVEL` | `WARNING` | SQL query logging level |
| `MAX_STAGE_RETRIES` | `3` | Max retries per pipeline stage |
| `MAX_TOTAL_RETRIES` | `10` | Max total retries per article |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Source disable threshold |
| `STUCK_THRESHOLD_MINUTES` | `60` | Dead letter threshold |
| `MIN_CONTENT_LENGTH` | `200` | Minimum article content |
| `VERIFICATION_EXPIRY_SECONDS` | `3600` | Email verification TTL |
| `CELERY_TASK_SECRET` | - | HMAC signing key (min 32 chars) |
| `WEBHOOK_SECRET_KEY` | - | Webhook encryption key |
| `SUBAGENT_WORKERS` | `8` | Subagent thread pool size |
| `CONTENT_EXTRACTOR_WORKERS` | `8` | Content extractor pool size |
| `SEARCH_POOL_MAXSIZE` | `10` | Search HTTP pool size |
| `SEARCH_POOL_CONNECTIONS` | `5` | Search HTTP connections |

## Adding a New LLM Provider

Providers are defined in `providers.yaml`. For OpenAI-compatible providers, add a new entry:

```yaml
  - id: myprovider
    type: openai
    enabled: false
    config:
      api_key: "${MYPROVIDER_API_KEY}"
      base_url: "https://api.myprovider.com/v1"
      model: "my-model"
      max_tokens: 4096
```

For non-standard providers, create an adapter in `services/llm/`:

```python
# services/llm/myprovider.py
from services.llm.base import BaseLLMProvider, LLMResponse

class MyProviderAdapter(BaseLLMProvider):
    def chat_structured(self, messages, response_model, **kwargs) -> LLMResponse:
        # Implementation
        pass
```

## Pipeline Architecture

Articles flow through stages:

```
research → write → edit → newsletter
    ↓        ↓       ↓
 failed   failed  failed
```

Note: `PipelineStatus.SELECTING` is deprecated and removed; selection logic is integrated into the research phase. Articles start in `pending` status and transition to `researching`.

Each stage is a Celery task with independent retry budget.

### Stage Responsibilities

| Stage | Description | Quality Gate |
|-------|-------------|------------|
| `research` | LLM evaluates newsworthiness, selects articles, compiles research brief | Min score >= 6 |
| `write` | LLM drafts condensed article in Smart Brevity style | Min 500 char body |
| `edit` | LLM reviews, polishes, assigns tags | Schema validation |

### Degradation on Failure

If a stage fails after retries:
- **Research**: Uses source text only, sets impact_score to 30
- **Write**: Generates minimal draft from extracted text
- **Edit**: Routes to REVIEW status for manual handling

---

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make changes and add tests
3. Run linting: `.venv/bin/ruff check . --exclude .venv`
4. Run tests: `.venv/bin/python -m pytest tests/ -x -q`
5. Commit with clear message: `git commit -m "Add feature: description"`
6. Push and create pull request