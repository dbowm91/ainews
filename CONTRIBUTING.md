# Contributing to ainews//

## Prerequisites

- Python 3.12+
- Redis (for Celery workers and caching)
- SQLite (included with Python)

## Local Setup

```bash
# Clone and enter the repo
git clone <repo-url> && cd ainews

# Create virtual environment and install dependencies
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your config (SECRET_KEY, ADMIN_PASSWORD, SMTP settings, etc.)

# Run database migrations
.venv/bin/flask db upgrade

# Start the development server
.venv/bin/python run.py
```

## Running Tests

```bash
# Run the full test suite
.venv/bin/python -m pytest tests/ -x -q

# Run a specific test file
.venv/bin/python -m pytest tests/test_article.py -x -q

# Run with verbose output
.venv/bin/python -m pytest tests/ --tb=short -q
```

## Linting

```bash
# Check code style
.venv/bin/ruff check . --exclude .venv

# Auto-fix issues
.venv/bin/ruff check . --exclude .venv --fix
```

All code must pass `ruff check` with zero errors before submitting.

## Code Conventions

See [AGENTS.md](AGENTS.md) for detailed conventions. Key points:

- **Logging**: Use `%-formatting` in logger calls, not f-strings
- **Database**: Wrap `db.session.commit()` in try/except with rollback
- **Redis**: Catch `redis.exceptions.RedisError`, not bare `Exception`
- **LLM prompts**: XML-escape external content with `esc_xml_text()` / `esc_xml_attr()` from `services/prompts.py`
- **URL validation**: Use `validate_url_safe()` from `services/url.py` for SSRF protection
- **Constants**: Single source of truth in `constants.py`

## Architecture

```
├── app.py              # Flask app factory
├── config.py           # Configuration classes
├── models.py           # SQLAlchemy models
├── routes/             # HTTP route handlers
│   ├── admin/          # Admin panel routes
│   └── public.py       # Public-facing routes
├── services/           # Business logic
├── tasks/              # Celery task definitions
├── schemas/            # Pydantic schemas and config loading
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, JS, static assets
└── tests/              # Pytest test suite
```

## Pipeline

The article pipeline flows: **select → research → write → edit → done** (or **review**).

Each stage runs as an independent Celery task. Pipeline status is tracked in the `Article.pipeline_status` column using constants from `PipelineStatus` in `constants.py`.

## Submitting Changes

1. Create a feature branch from `main`
2. Make your changes following the conventions above
3. Run linting and tests to verify
4. Submit a pull request with a clear description of the changes
