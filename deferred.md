# Deferred Items

Items skipped from `plan.md` due to lower ROI relative to implementation effort.

---

## 5.1 Missing Type Hints

**Effort:** 2-3 hours
**Impact:** Low (code quality only, no functional change)
**Scope:** Add return type hints to all public service functions

### Tasks
- Audit `services/*.py` for public functions missing return annotations
- Add `-> None`, `-> str`, `-> dict`, etc. where obvious
- Add parameter types where not inferred from Pydantic models or Flask
- Run `mypy --ignore-missing-imports` to validate (optional)

### Files
- `services/related.py`
- `services/email.py`
- `services/article.py`
- `services/crawling.py`
- `services/utils.py`
- `services/llm/base.py`
- `services/llm/__init__.py`
- `services/cache.py`
- `services/metrics.py`

### Notes
- Do NOT add types to route handlers (Flask decorators obscure signatures)
- Focus on functions called by multiple consumers (pipeline, routes, tasks)
- Skip trivial one-liner helpers

---

## 6.1 API Documentation (OpenAPI)

**Effort:** 6-8 hours
**Impact:** Medium (onboarding, external consumers)
**Scope:** OpenAPI 3.0 spec + Swagger UI

### Tasks
1. Install `apispec` + `flask-apispec` or write `openapi.yaml` manually
2. Document all public endpoints:
   - `GET /` (article list with pagination)
   - `GET /article/{id}` (article detail)
   - `GET /feed` (RSS)
   - `GET /feed/{category}` (RSS by topic)
   - `POST /subscribe`
   - `POST /unsubscribe/{token}`
   - `GET /health`
3. Document all admin API endpoints:
   - `GET /admin/api/health`
   - `GET /admin/api/task/{id}`
   - `POST /admin/api/config/reload`
   - `GET /admin/api/metrics`
4. Add Swagger UI at `/docs` (behind auth or public read-only)
5. Include auth requirements (session cookie for admin, CSRF for POST)

### Files
- `openapi.yaml` (new)
- `routes/public.py` (docstrings)
- `routes/admin/api.py` (docstrings)
- `app.py` (register Swagger UI)

### Notes
- Use `apispec` with marshmallow schemas for auto-generation
- Keep spec in sync with tests via a validation test
- Do NOT expose admin endpoints in public docs

---

## 6.2 Developer Documentation

**Effort:** 4-5 hours
**Impact:** Medium (onboarding, contributor experience)
**Scope:** Architecture docs, pipeline stages, contribution guide

### Tasks
1. Create `docs/architecture.md`:
   - System diagram (Flask + Celery + Redis + SQLite)
   - Request flow (public vs admin)
   - Pipeline stages (crawl → extract → select → research → write → edit)
   - Newsletter generation flow
2. Create `docs/pipeline.md`:
   - Stage descriptions with input/output
   - LLM provider selection and fallback
   - Circuit breaker behavior
   - Retry and dead-letter logic
3. Create `docs/contributing.md`:
   - Setup instructions (venv, .env, flask db upgrade)
   - Running tests (`pytest tests/ -x -q`)
   - Linting (`ruff check .`)
   - Adding a new source adapter
   - Adding a new LLM provider
4. Create `docs/troubleshooting.md`:
   - Common errors (circuit open, Redis unavailable, SQLite locked)
   - Log locations and log level config
   - How to reprocess stuck articles
5. Update `README.md` with links to docs

### Files
- `docs/architecture.md` (new)
- `docs/pipeline.md` (new)
- `docs/contributing.md` (new)
- `docs/troubleshooting.md` (new)
- `README.md` (update)

### Notes
- Use Mermaid diagrams for architecture (GitHub renders them)
- Keep examples concrete (actual config snippets, curl commands)
- Reference AGENTS.md conventions for AI coding agents
