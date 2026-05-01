# Code Quality Improvement Plan - ainews

**Date**: 2026-05-01
**Status**: Final - Review Complete
**Current Grade**: B+
**Target Grade**: A-

---

## Executive Summary

The ainews codebase is a mature, well-structured Flask application with 309K+ lines of Python, 947 tests, and solid production patterns. Deep-dive investigation of 15 code quality items identified:

| Priority | Items | Key Metrics |
|----------|-------|---------------|
| **High** | 3 | 214 bare exceptions, 120s->60s test runtime, 15-20% type coverage |
| **Medium** | 6 | 20 complex functions, 1196-line subagent.py, 29 B904 issues, 62% coverage |
| **Low** | 6 | 13k docstring issues, 61 unused noqas, 161MB .venv.bak |

This plan provides specific file locations, code examples, and effort estimates for each fix.

---

## 1. High Priority Items (Complete First)

### 1.1 Replace Bare `except Exception` (BLE001) - 214 Instances

**Investigation Result:**
- 214 bare exception handlers across codebase
- Primary issue: Masks bugs, catches `KeyboardInterrupt`/`SystemExit`
- Categories: LLM services (25), tasks (50+), routes (40+), services (60+), adapters (2)

**Remediation Plan:**

| Phase | Scope | Effort | Timeline |
|-------|-------|--------|----------|
| 1 | LLM services (`services/llm/*.py`) | Medium (25 instances) | Week 1 |
| 2 | Subagent services (`services/subagent.py`) | High (13 instances) | Week 2 |
| 3 | Task modules (`tasks/*.py`) | Medium (50+ instances) | Week 3 |
| 4 | Route handlers (`routes/*.py`) | Medium (40+ instances) | Week 4 |

**Example Fix:**
```python
# Before (Current)
try:
    resp = self.client.chat.completions.create(model=model, ...)
except Exception as e:
    raise _handle_openai_error(e)

# After (Recommended)
try:
    resp = self.client.chat.completions.create(model=model, ...)
except (openai.OpenAIError, httpx.HTTPError, ConnectionError, TimeoutError) as e:
    raise _handle_openai_error(e) from e
```

**Suggested Exception Types by Module:**
- `services/llm/*.py`: `openai.OpenAIError`, `anthropic.AnthropicError`, `google.genai.errors.ClientError`, `ollama.ResponseError`, `httpx.HTTPError`
- `tasks/*.py`: `SQLAlchemyError`, `redis.exceptions.RedisError`, `SoftTimeLimitExceeded`, `ProviderTimeoutError`
- `routes/*.py`: `ValidationError`, `SQLAlchemyError`, `KeyError`, `ValueError`
- `services/*.py`: `SQLAlchemyError`, `redis.exceptions.RedisError`, `smtplib.SMTPException`
- `adapters/*.py`: `requests.RequestException`, `ConnectionError`, `TimeoutError`

---

### 1.2 Fix Test Suite Timeout

**Investigation Result:**
- Timeout caused by LLM adapter tests triggering retry logic with `time.sleep()` (5 tests = ~20 seconds)
- 947 tests total, cumulative execution exceeds 120s
- `pytest-xdist` already installed but not configured

**Root Cause:**
`services/llm/base.py` lines 119-171 (`_retry_with_backoff` method) retries 3 times with 1s, 2s, 4s delays = ~7s per failed test × 5 tests = ~35s wasted

**Remediation Plan:**

**Fix 1: Mock Retry Logic (Week 1) - HIGH PRIORITY**

Create `tests/test_llm_adapters/conftest.py`:
```python
"""Auto-mock retry logic for LLM adapter tests."""
from unittest.mock import patch
import pytest

@pytest.fixture(autouse=True)
def _disable_retry_delay():
    """Disable retry delays in LLM adapter tests."""
    with patch("services.llm.base.BaseLLMProvider._retry_with_backoff") as mock_retry:
        # Make _retry_with_backoff call the function directly without delays
        mock_retry.side_effect = lambda func, model, *args, **kwargs: func(*args, **kwargs)
        yield
```

**Fix 2: Configure pytest-xdist (Week 1)**

Update `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "--durations=10 -n auto"
```

**Fix 3: Mark Incompatible Tests (Week 1)**

Add to `tests/test_circuit_breaker.py` and `tests/test_concurrent_access.py`:
```python
@pytest.mark.no_xdist
class TestCircuitBreakerMetrics:
    ...
```

**Expected Outcome:** Test suite runs in <60 seconds (from 120+ seconds)

---

### 1.3 Add Missing Type Annotations (3,000+ Issues)

**Investigation Result:**
- Current annotation coverage: ~15-20%
- Schemas well-annotated (90%), services/routes poorly annotated (5-20%)
- mypy 1.20.2 installed, configured but not enforcing (`disallow_untyped_defs = false`)

**Current mypy Configuration (`pyproject.toml` lines 68-78):**
```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false    # <-- Key: Not enforcing
ignore_missing_imports = true
exclude = [
    "migrations/",
    ".venv/",
    "instance/",
]
```

**Remediation Plan (Gradual Rollout):**

| Phase | Scope | Timeline |
|-------|-------|----------|
| 1 | `schemas/*.py` (already 90% done) | Week 1 |
| 2 | `models.py`, `app.py`, `services/article.py`, `services/cache.py` | Week 2-3 |
| 3 | `services/*.py` (core services) | Week 4-6 |
| 4 | `routes/*.py` (API endpoints) | Week 7-8 |
| 5 | Enable `disallow_untyped_defs = true` | Week 9+ |

**mypy Configuration for Gradual Rollout:**

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false      # Keep disabled during transition
check_untyped_defs = true          # But still check untyped defs
ignore_missing_imports = true
show_error_codes = true
show_column_numbers = true

# Exclude patterns for gradual adoption
exclude = [
    "migrations/",
    ".venv/",
    "instance/",
    "tests/",           # Exclude tests initially
]

# Phase 2: Enforce for well-annotated modules
[[tool.mypy.overrides]]
module = [
    "schemas.*",
    "services.llm.*",
]
disallow_untyped_defs = true
```

**Good Annotation Pattern (from `schemas/common.py`):**
```python
from __future__ import annotations
from typing import Any, Callable, TypeVar

T = TypeVar("T", bound=BaseModel)

def resolve_env_var(val: str, required: bool = False) -> str:
    """Resolve a single ${ENV_VAR} placeholder."""
    ...

def load_yaml_file(path: str | Path) -> dict[str, Any]:
    ...
```

---

## 2. Medium Priority Items (Complete Second)

### 2.1 Refactor High Complexity Functions (C901 >15) - 20 Functions

**Investigation Result:**
- 20 functions exceed complexity threshold of 15 (range: 15-34)
- Top offenders: `_evaluate_condition` (34), `_eval_node` (29), `create_app` (29)

**Functions Requiring Refactoring (Priority Order):**

| Rank | Function | Complexity | File | Refactoring Approach |
|------|----------|------------|------|-------------------|
| 1 | `_evaluate_condition` | 34 | `services/subagent.py:1077` | Strategy pattern / dispatch dict for AST node types |
| 2 | `_eval_node` | 29 | `services/subagent.py:1096` | Extract node evaluators to separate functions |
| 3 | `create_app` | 29 | `app.py:61` | Extract env-specific setup, error handlers, template filters |
| 4 | `_build_context_tools` | 28 | `services/subagent.py:46` | Extract to `ContextToolBuilder` class |
| 5 | `run_stage` | 27 | `tasks/pipeline.py:210` | Extract exception categorization helper |
| 6 | `get_article_ids` | 27 | `routes/admin/api/articles.py:20` | Extract query builder to shared service |
| 7 | `get_prometheus` | 23 | `services/metrics.py:207` | Extract metric collection with fallback |
| 8 | `articles` | 21 | `routes/admin/articles.py:79` | Share query builder with `get_article_ids` |
| 9 | `bulk_article_operations` | 20 | `routes/admin/api/articles.py:354` | Use dispatch pattern for actions |
| 10 | `get_metrics` | 20 | `services/metrics.py:121` | Apply same helper as `get_prometheus` |

**Example Refactoring (Dispatch Pattern for `bulk_article_operations`):**
```python
# Before: Large if/elif chain
def bulk_article_operations():
    action = data['action']
    if action == 'delete':
        ...
    elif action == 'set_status':
        ...
    # ... 5 more branches

# After: Dispatch pattern
BULK_OPERATIONS = {
    "delete": _bulk_delete,
    "set_status": _bulk_set_status,
    "set_category": _bulk_set_category,
    "reprocess": _bulk_reprocess,
    "add_tags": _bulk_add_tags,
}

def bulk_article_operations():
    data = request.get_json(silent=True)
    validated = BulkArticleRequest(**data)
    articles = _fetch_articles(validated.article_ids)
    handler = BULK_OPERATIONS.get(validated.action)
    if handler:
        return handler(articles, validated)
    return jsonify({"error": "Invalid action"}), 400
```

---

### 2.2 Split `services/subagent.py` (1196 lines)

**Investigation Result:**
- File mixes: tool definitions, execution logic, prompt handling, condition evaluation
- Natural breakdown into 4 modules identified

**Current Structure:**
| Line Range | Component | Description |
|------------|------------|-------------|
| 1-29 | Imports | Standard libs, third-party, internal |
| 30-43 | Tool Registration | `register_tool()`, `get_registered_tools()` |
| 46-329 | Context Tools | `_build_context_tools()` with 7 embedded functions |
| 332-400 | Search Tools | `_build_search_tools()` with 2 embedded functions |
| 403-442 | Tool Initialization | `_get_all_tools_cached()`, `initialize_tool_registry()` |
| 538-717 | `run_subagent()` | Main execution without tools |
| 720-919 | `run_subagent_with_tools()` | Execution with tool calling |
| 922-1074 | `run_subagent_chain()` | Multi-step chain execution |
| 1077-1196 | Condition Evaluation | `_evaluate_condition()`, `_resolve_template_variables()` |

**Suggested Module Breakdown:**

```
services/subagent/
    __init__.py          # Public API re-exports
    tools.py             # Tool definitions and registry (~410 lines)
    executor.py          # Subagent execution functions (~535 lines)
    conditions.py        # Condition evaluation (~120 lines)
    prompts.py           # Template/prompt helpers (~90 lines)
```

**Migration Strategy:**

1. **Create Package Structure** (Week 8):
   ```bash
   mkdir -p services/subagent
   touch services/subagent/__init__.py
   ```

2. **Extract Modules** (in order):
   - `conditions.py` (simplest, no dependencies)
   - `prompts.py` (template helpers)
   - `tools.py` (tool definitions and registry)
   - `executor.py` (execution logic)

3. **Update `__init__.py`** for backward compatibility:
   ```python
   from .tools import register_tool, get_registered_tools, initialize_tool_registry
   from .executor import run_subagent, run_subagent_with_tools, run_subagent_chain
   from .conditions import _evaluate_condition
   from .prompts import _SUBAGENT_TASK_TEMPLATES, _get_task_template
   ```

4. **Update Import Statements** in:
   - `app.py` (line 271)
   - `tasks/research.py`, `tasks/edit.py`
   - `tests/test_subagent.py`, `tests/test_security_conditions.py`

---

### 2.3 Fix Exception Chaining (B904) - 29 Instances

**Investigation Result:**
- 29 instances of raising exceptions inside except blocks without `from` clause
- Preserves traceback context for debugging

**Instances by File:**

| File | Lines | Count | Priority |
|------|-------|-------|----------|
| `services/llm/anthropic.py` | 82, 135, 162, 212 | 4 | **High** |
| `services/llm/gemini.py` | 89, 140, 169, 227 | 4 | **High** |
| `services/llm/ollama.py` | 78, 124, 148, 198 | 4 | **High** |
| `services/llm/openai.py` | 86, 138, 170, 229 | 4 | **High** |
| `services/subagent.py` | 637, 834, 1028 | 3 | **High** |
| `services/timeout.py` | 58 | 1 | **High** |
| `services/webhooks.py` | 41, 338, 346 | 3 | Medium |
| `services/url.py` | 155, 158 | 2 | Medium |
| `adapters/session.py` | 40 | 1 | Medium |
| `services/search/session.py` | 43 | 1 | Medium |
| `tasks/crawl.py` | 299 | 1 | Medium |
| `schemas/admin.py` | 40 | 1 | Low |

**Example Fix:**
```python
# Before
except Exception as e:
    raise _handle_openai_error(e)

# After
except Exception as e:
    raise _handle_openai_error(e) from e
```

**When to use `from None` vs `from err`:**
- `from err`: Preserves chain (default for debugging)
- `from None`: Suppresses original traceback (rare, when original exception is irrelevant)

---

### 2.4 Enable mypy in CI

**Investigation Result:**
- CI configuration exists (`.github/workflows/ci.yml`)
- No mypy step currently in CI
- Uses `uv` for dependency management

**Current CI Configuration:**
```yaml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      - name: Install dependencies
        run: uv sync --all-extras
      - name: Run ruff
        run: .venv/bin/ruff check . --exclude .venv
      - name: Run tests
        run: .venv/bin/python -m pytest tests/ -x -q
```

**Add mypy to CI (Phase 1: Non-Blocking, Week 1):**
```yaml
      - name: Run mypy (type checking)
        run: .venv/bin/mypy . --exclude='(\.venv|\.git|migrations|instance|tests)'
        continue-on-error: true  # Remove in Phase 3
```

**Phase 2: Targeted Enforcement (Week 5-6):**
```yaml
  type-check-targeted:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --all-extras
      - name: Run mypy on targeted modules
        run: |
          .venv/bin/mypy schemas/ services/llm/ \
            --exclude='\.venv' \
            --disallow-untyped-defs \
            --check-untyped-defs
```

---

### 2.5 Migrate to SQLAlchemy 2.0 Patterns

**Investigation Result:**
- SQLAlchemy 2.0.48, Flask-SQLAlchemy 3.1.1 installed
- **133 instances** of deprecated `Model.query` pattern
- **25 instances** of legacy `session.query(Model)`

**Current Patterns:**

| Pattern | Count | Status |
|---------|-------|--------|
| `Model.query` (e.g., `Article.query.filter(...)`) | 133 | Deprecated in SA 2.0 |
| `db.session.query(Model)` | 25 | Removed in SA 2.0 |
| `select(Model)` | 3-4 | Modern SQLAlchemy 2.0 ✅ |
| `db.session.get(Model, id)` | Some | Modern ✅ |

**Remediation Plan:**

**Phase 1: Core Models (Week 10):**
```python
# Before (Legacy 1.x)
articles = Article.query.filter_by(status='published').all()

# After (SQLAlchemy 2.0)
from sqlalchemy import select
stmt = select(Article).where(Article.status == 'published')
articles = db.session.execute(stmt).scalars().all()
```

**Phase 2: Update Relationships (Week 10):**
```python
# Before
class Article(db.Model):
    source = db.relationship("Source", backref="articles")

# After
class Article(db.Model):
    source = db.relationship("Source", back_populates="articles")

class Source(db.Model):
    articles = db.relationship("Article", back_populates="source")
```

**Files Needing Updates (Priority Order):**
1. `models.py` - `backref=` (5 locations)
2. `routes/admin/*.py` - 15+ instances of `Model.query`
3. `tasks/*.py` - Multiple instances
4. `services/*.py` - Multiple instances

---

### 2.6 Improve Test Coverage (Current: 62%, Target: 80%)

**Investigation Result:**
- Current coverage: 62% (FAILING 80% target)
- ~2,158 more statements need coverage
- Lowest coverage: `tasks/newsletter.py` (12%), `tasks/write.py` (16%)

**Modules with Low Coverage:**

| Module | Coverage | Priority | Action |
|--------|----------|----------|--------|
| `tasks/newsletter.py` | 12% | HIGH | Add tests |
| `tasks/write.py` | 16% | HIGH | Add tests |
| `tasks/research.py` | 20% | HIGH | Add tests |
| `tasks/edit.py` | 25% | HIGH | Add tests |
| `services/writer.py` | 22% | HIGH | Add tests |
| `adapters/web.py` | 19% | MEDIUM | Add tests |
| `services/quality.py` | 0% | LOW | **Delete** - dead code |

**Coverage Exclusions to Add (`pyproject.toml`):**
```toml
[tool.coverage.run]
omit = [
    ".venv/**",
    "migrations/**",
    "instance/**",
    "tests/**",
    "run.py",                    # Entry point
    "services/quality.py",       # Dead code - verify before excluding
]

[tool.coverage.report]
fail_under = 80
skip_empty = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

**Tests to Add (Phased Approach):**

| Phase | Tests | Statements | Timeline |
|-------|-------|------------|----------|
| 1 | `test_date_utils.py`, `test_search_schema.py` | ~200 | Week 2 |
| 2 | `test_write_task.py`, `test_research_task.py`, `test_edit_task.py` | ~500 | Week 4 |
| 3 | `test_article_service.py`, `test_cache_service.py` | ~300 | Week 6 |

---

## 3. Low Priority Items (Complete as Time Permits)

### 3.1 Add Missing Docstrings (13,398 Issues)

**Investigation Result:**
- Google style already established in codebase
- Priority: D102 (public methods, 789), D101 (public classes, 160)

**Issue Breakdown:**

| Rule | Description | Count | Priority |
|------|-------------|-------|----------|
| D102 | Missing docstring in public method | 789 | HIGH |
| D101 | Missing docstring in public class | 160 | HIGH |
| D103 | Missing docstring in public function | 134 | MEDIUM |
| D100 | Missing docstring in public module | 82 | MEDIUM |
| D107 | Missing docstring in `__init__` | 33 | LOW |
| D105 | Missing docstring in magic method | 24 | LOW |
| D104 | Missing docstring in public package | 10 | LOW |

**Docstring Template (Google Style):**
```python
def my_function(param1: str, param2: int = 10) -> bool:
    """Short summary of function.

    Longer description explaining what the function does.

    Args:
        param1: Description of param1.
        param2: Description of param2. Defaults to 10.

    Returns:
        Description of return value.

    Raises:
        ValueError: If param1 is empty.
    """
```

**Estimated Effort:** 25-42 hours total

---

### 3.2 Fix Unused noqa Directives (RUF100) - 61 Instances

**Investigation Result:**
- Mostly `F401` (side-effect imports) and `E501` (line length) noqas
- Auto-fixable with ruff

**Common Cases:**
```python
# Side-effect imports (F401) - keep for adapter/task registration
from adapters.api import Adapter  # noqa: F401

# Line length (E501) - no longer needed if E501 not enabled
long_line = "..."  # noqa: E501  # Can be removed
```

**Fix Command (Week 1):**
```bash
.venv/bin/ruff check --select RUF100 --fix .
```

---

### 3.3 Clean Up `.venv.bak` Directory

**Investigation Result:**
- 161MB backup directory from different machine/user (`/Users/davidbowman/projects/ainews/.venv`)
- Not referenced anywhere in project
- Safe to remove

**Fix Command (Week 1):**
```bash
# Verify not used
grep -r ".venv.bak" . --include="*.py" --include="*.cfg" --include="*.toml" 2>/dev/null

# Remove
rm -rf .venv.bak
```

**Reclaims:** 161MB disk space

---

### 3.4 Fix Unused Loop Variables (B007) - 5 Instances

**Investigation Result:**
- Variables: `count`, `i`, `neg_score`, `family`
- Simple rename to `_variable` convention

**Instances:**
| File | Line | Variable | Fix |
|------|------|----------|-----|
| `routes/admin/__init__.py` | 133 | `count` | Rename to `_count` |
| `services/llm/ollama.py` | 223 | `i` | Rename to `_i` |
| `services/prompts.py` | 199 | `neg_score` | Rename to `_neg_score` |
| `services/url.py` | 162 | `family` | Rename to `_family` |
| `tests/test_pipeline_e2e.py` | 216 | `i` | Rename to `_i` |

**Fix Command (Week 1):**
```bash
.venv/bin/ruff check --select B007 --unsafe-fixes --fix .
```

---

### 3.5 S311 `random.choice()` Usage - 1 Instance

**Investigation Result:**
- Used for User-Agent rotation in `adapters/web.py:35`
- NOT cryptographic - false positive for S311 rule
- Predictability of `random` doesn't matter here

**Current Code:**
```python
self._session.headers["User-Agent"] = (
    ua if ua != "AINewsBot/1.0" else random.choice(USER_AGENTS)
)
```

**Fix Option (Week 1):**
```python
self._session.headers["User-Agent"] = (
    ua if ua != "AINewsBot/1.0" else random.choice(USER_AGENTS)  # noqa: S311 - non-crypto use
)
```

---

## 4. Implementation Timeline

| Week | High Priority | Medium Priority | Low Priority |
|-------|---------------|----------------|-------------|
| 1 | BLE001 (LLM), Test timeout, Type annotations (Phase 1) | mypy CI (Phase 1) | RUF100, .venv.bak, B007, S311 |
| 2-3 | BLE001 (Subagent), Type annotations (Phase 2) | SQLAlchemy 2.0 (Phase 1) | Docstrings (Tier 1 start) |
| 4-6 | BLE001 (Tasks, Routes), Type annotations (Phase 3-4) | Refactor C901, Split subagent.py, B904 fixes, mypy CI (Phase 2) | Docstrings (Tier 1 continue) |
| 7-9 | Type annotations (Phase 5) | SQLAlchemy 2.0 (Phase 2-4), Test coverage (Phase 1-3), mypy CI (Phase 3) | Docstrings (Tier 2) |
| 10-12 | - | Test coverage (Phase 4) | Docstrings (Tier 3-4) |

---

## 5. Success Metrics

| Metric | Current | Target | Measurement Command |
|--------|---------|--------|-------------------|
| BLE001 instances | 214 | 0 | `ruff check --select BLE001 .` |
| Test suite runtime | 120s+ | <60s | `pytest --durations=0` |
| Type annotation coverage | 15-20% | 80%+ | mypy error count |
| C901 >15 functions | 20 | 0 | `ruff check --select C901 . \| grep ">15"` |
| Test coverage | 62% | 80% | `pytest --cov --cov-report=term` |
| B904 instances | 29 | 0 | `ruff check --select B904 .` |
| mypy errors (targeted) | 75 | 0 | `mypy schemas/ services/llm/` |

---

## 6. Key Files to Modify

| File | Changes Needed | Priority |
|------|----------------|----------|
| `services/llm/*.py` | BLE001, B904 fixes | High |
| `tests/test_llm_adapters/conftest.py` | CREATE (mock retry) | High |
| `pyproject.toml` | mypy config, pytest-xdist, coverage exclusions | High |
| `.github/workflows/ci.yml` | Add mypy step | Medium |
| `services/subagent.py` -> `services/subagent/` | Split into 4 modules | Medium |
| `models.py`, `routes/*.py`, `tasks/*.py` | SQLAlchemy 2.0 patterns | Medium |
| `app.py`, `models.py`, `services/*.py` | Type annotations | High |

---

## 7. Quick Wins (Can Do Immediately)

1. **Remove `.venv.bak`**: `rm -rf .venv.bak` (reclaims 161MB)
2. **Fix RUF100**: `.venv/bin/ruff check --select RUF100 --fix .`
3. **Fix B007**: `.venv/bin/ruff check --select B007 --unsafe-fixes --fix .`
4. **Add mypy to CI**: Add 5-line step to `.github/workflows/ci.yml`
5. **Mock LLM retries**: Create `tests/test_llm_adapters/conftest.py`

---

**Plan prepared by**: AI Agent
**Review status**: Complete - Ready for Implementation  
**Next action**: Begin implementation following timeline (Week 1 starts with Quick Wins)
