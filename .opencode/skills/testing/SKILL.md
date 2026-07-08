---
name: testing
description: "Testing conventions for the ainews codebase — pytest, fixtures, coverage, subagent testing, ruff/mypy."
---

## Test Structure

Tests live in `tests/` with subdirectories mirroring the main codebase:
- `tests/test_*.py` — top-level test files
- `tests/test_subagent_*.py` — subagent package tests (runner, tools, chain, templates, middleware, responses)
- `tests/test_llm_adapters/` — per-provider LLM tests
- `tests/test_routes/` — route/blueprint tests

## Running Tests

```bash
# Run all tests
.venv/bin/pytest tests/ -x -q

# Run with coverage
.venv/bin/pytest tests/ --cov --cov-report=term-missing

# Run specific test class
.venv/bin/pytest tests/test_subagent_tools.py::TestBuiltInTools -v

# Run with timeout (prevents hanging)
.venv/bin/pytest tests/ --timeout=120
```

## Key Fixtures (in `tests/conftest.py`)

- **`app`** — Flask test client with app context, Celery HMAC verification
- **`client`** — Plain Flask test client (no auth)
- **`auth_client`** — Authenticated test client with admin session set (use this for API tests)
- **`mock_redis`** — plain MagicMock for simple Redis ops
- **`mock_redis_client`** — MockRedis instance for stateful operations
- **`mock_celery_tasks`** — patches all Celery task calls

## Coverage Requirements

- **Target**: 80% overall (configured in `pyproject.toml`)
- **Subagent package**: 84% (as of 2026-05-02)
- **Fail under**: `fail_under = 80` in `[tool.coverage.report]`

### Checking Coverage

```bash
.venv/bin/pytest tests/ --cov --cov-report=term-missing
# Look for "TOTAL" line at the end
```

## Patching Patterns

### Correct Patch Targets

When patching functions in tests, patch where the function is **used**, not where it's defined:

```python
# WRONG — patches the definition, not the usage
with patch("services.subagent.tools.get_search_provider"):

# CORRECT — patch where it's looked up
with patch("services.search.get_search_provider"):
```

### Common Patch Targets

| Function | Patch Target |
|----------|--------------|
| `_context_tool_get_topic_note` uses `services.context_service.get_topic_note` | `services.context_service.get_topic_note` |
| `_context_tool_get_related_articles` uses `services.context_service.get_related_articles_for_edit` | `services.context_service.get_related_articles_for_edit` |
| `_context_tool_get_trend_memory` uses `services.trend_memory.get_memory_for_topics` | `services.trend_memory.get_memory_for_topics` |
| `_context_tool_get_article_by_id` uses `extensions.db` | `extensions.db` |
| `_context_tool_search_articles` uses `models.Article` | `models.Article` |
| `_context_tool_get_source_health` uses `extensions.db` | `extensions.db` |

## Ruff Violations

### Common Fixes Applied (2026-05-02)

- **BLE001** (bare `except Exception`): Catch specific exceptions instead:
  ```python
  # Instead of:
  except Exception as e:
  
  # Use:
  except (RuntimeError, ValueError, KeyError, AttributeError) as e:
  ```

- **RUF100** (unused `noqa`): Remove unused `noqa` comments or add referenced rule to select list in `pyproject.toml`

- **S311** (pseudo-random): Use `secrets.randbelow()` for security-critical randomness:
  ```python
  import secrets
  index = secrets.randbelow(len(my_list))
  value = my_list[index]
  ```

- **C901** (complexity >15): Refactor functions into smaller pieces. Max complexity is 15.

### Ruff Configuration

```toml
[tool.ruff.lint]
select = ["BLE001", "C901", "RUF100", "B007", "S311", "F401", "E402"]

[tool.ruff.lint.mccabe]
max-complexity = 15
```

## MyPy

- **Configured but allows failures**: `|| true` in CI
- **Usage**: 
  ```bash
  .venv/bin/mypy . --exclude .venv || true
  ```

## Test Naming Conventions

- **Test classes**: `Test<Feature>` or `Test<Feature><Subfeature>`
- **Test methods**: `test_<what_is_being_tested>_<expected_outcome>`
- **Example**: `test_get_article_by_id_success`, `test_chat_error_converted`

## Subagent Testing

When testing subagent functions that use `_build_context_tools()` or `_build_search_tools()`:

```python
with patch("services.subagent.tools.extensions") as mock_ext:
    mock_ext.db.session.get.return_value = mock_article
    result = tool.fn(article_id=123)
```

## Middleware Testing

```python
from services.subagent.middleware import LoggingMiddleware

def dummy_func(x):
    return x * 2

middleware = LoggingMiddleware()
wrapped = middleware.wrap(dummy_func)
assert wrapped(5) == 10
```

## CI Pipeline

Tests run in `.github/workflows/ci.yml`:
1. **pytest with coverage** — HTML and XML reports generated
2. **mypy** — type checking (allows failures)
3. **pip-audit** — dependency scanning
4. **trivy** — container vulnerability scanning
5. **smoke-tests** — dedicated job running production config, Celery, migration, and docs consistency smoke tests
6. **docker-build** — builds image, validates Compose config (base + Ollama override), runs image smoke test

### Smoke Test Files

| File | Layer | What it validates |
|------|-------|-------------------|
| `tests/test_smoke_production_config.py` | 1 | `ProductionConfig.validate()` rejects bad configs, accepts valid ones |
| `tests/test_smoke_migrations.py` | 2 | DB tables create cleanly on fresh SQLite |
| `tests/test_smoke_celery.py` | 3 | Celery app imports, tasks registered, config set |
| `tests/test_docs_env_consistency.py` | 7 | Required env vars documented in README and docs |

### Local Smoke Validation

```bash
# Run all smoke tests
.venv/bin/pytest tests/test_smoke_*.py tests/test_docs_env_consistency.py -v

# Docker Compose boot smoke (requires Docker)
./scripts/ci_compose_smoke.sh
```
