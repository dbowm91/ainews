# Ainews Codebase Test Coverage Report

## Summary

| Metric | Value |
|--------|-------|
| **Current Coverage** | **62%** |
| **Target Coverage** | **80%** (per pyproject.toml) |
| **Total Statements** | 12,228 |
| **Covered Statements** | 7,624 |
| **Missing Statements** | 4,604 |
| **Gap to Close** | ~2,158 statements needed |

**Status**: FAILING - Coverage is 18 percentage points below target.

---

## Top Modules Needing Attention

### 0% Coverage (Candidate for Exclusion or Immediate Testing)

| Module | Statements | Notes |
|--------|------------|-------|
| `run.py` | 9 | Entry point - **recommend excluding** |
| `services/quality.py` | 119 | **Not imported anywhere** - possible dead code |
| `services/date_utils.py` | 33 | Used in app.py - **needs tests** |
| `schemas/search.py` | 18 | Used in services/search - **needs tests** |

### Lowest Coverage Modules (< 50%)

| Module | Coverage | Missing | Total | Priority |
|--------|----------|---------|-------|----------|
| `tasks/newsletter.py` | 12% | 254 | 288 | HIGH - Core functionality |
| `routes/admin/subscribers.py` | 16% | 46 | 55 | MEDIUM |
| `tasks/write.py` | 16% | 52 | 62 | HIGH - Core functionality |
| `adapters/api.py` | 18% | 100 | 122 | MEDIUM |
| `adapters/web.py` | 19% | 122 | 151 | MEDIUM |
| `tasks/research.py` | 20% | 86 | 107 | HIGH - Core functionality |
| `routes/admin/api/sources.py` | 21% | 111 | 140 | MEDIUM |
| `services/writer.py` | 22% | 21 | 27 | HIGH - Core functionality |
| `routes/admin/api/audit.py` | 23% | 23 | 30 | LOW |
| `routes/admin/pipelines.py` | 23% | 59 | 77 | LOW |
| `routes/admin/sources.py` | 23% | 88 | 115 | LOW |
| `services/subscribers.py` | 23% | 47 | 61 | MEDIUM |
| `routes/admin/api/webhooks.py` | 25% | 126 | 167 | MEDIUM |
| `tasks/edit.py` | 25% | 124 | 165 | HIGH - Core functionality |
| `tasks/cleanup.py` | 27% | 131 | 179 | MEDIUM |

### Modules Near Target (70-80% Coverage)

These are closest to the 80% target and should be prioritized for quick wins:

| Module | Coverage | Missing | Total |
|--------|----------|---------|-------|
| `services/circuit_breaker.py` | 79% | 57 | 267 |
| `routes/admin/review.py` | 78% | 20 | 92 |
| `routes/admin/__init__.py` | 78% | 40 | 185 |
| `services/crawling.py` | 78% | 22 | 101 |
| `tasks/extract.py` | 76% | 37 | 157 |
| `services/search/google.py` | 75% | 15 | 59 |
| `services/llm/__init__.py` | 75% | 20 | 79 |
| `services/config_cache.py` | 74% | 56 | 216 |
| `routes/admin/dashboard.py` | 74% | 20 | 78 |
| `services/pipeline_degradation.py` | 73% | 33 | 124 |

---

## Recommended Coverage Exclusions

Add to `pyproject.toml` `[tool.coverage.run]` omit list:

```toml
[tool.coverage.run]
source = ["."]
omit = [
    ".venv/**",
    "migrations/**",
    "instance/**",
    "tests/**",
    "run.py",                    # Entry point, minimal logic
    "services/quality.py",       # Dead code (not imported)
]
```

**Note**: Before excluding `services/quality.py`, verify it's not needed. If it's intended for future use, add tests instead.

---

## Recommended Tests to Add

### 1. High Impact - Core Task Modules (Coverage 12-27%)

| Test File | Module | Est. Statements to Cover |
|-----------|--------|--------------------------|
| `tests/test_date_utils.py` | `services/date_utils.py` | 33 |
| `tests/test_search_schema.py` | `schemas/search.py` | 18 |
| `tests/test_writer.py` | `services/writer.py` | 21 |
| `tests/test_newsletter_task.py` | `tasks/newsletter.py` | 254 |
| `tests/test_write_task.py` | `tasks/write.py` | 52 |
| `tests/test_research_task.py` | `tasks/research.py` | 86 |
| `tests/test_edit_task.py` | `tasks/edit.py` | 124 |

### 2. Medium Impact - Service Modules (Coverage 23-62%)

| Test File | Module | Est. Statements to Cover |
|-----------|--------|--------------------------|
| `tests/test_article_service.py` | `services/article.py` | 42 |
| `tests/test_cache_service.py` | `services/cache.py` | 32 |
| `tests/test_subscribers_service.py` | `services/subscribers.py` | 47 |
| `tests/test_editor.py` | `services/editor.py` | 34 |
| `tests/test_related.py` | `services/related.py` | 45 |
| `tests/test_webhooks_service.py` | `services/webhooks.py` | 60 |

### 3. Quick Wins - LLM Adapter Modules (Coverage 53-62%)

| Test File | Module | Est. Statements to Cover |
|-----------|--------|--------------------------|
| `tests/test_llm_base.py` | `services/llm/base.py` | 84 |
| `tests/test_llm_openai.py` | `services/llm/openai.py` | 54 |
| `tests/test_llm_anthropic.py` | `services/llm/anthropic.py` | 50 |

---

## Testing Strategy Recommendations

### 1. Incremental Approach (Recommended)

1. **Phase 1** (Quick Wins - ~200 statements):
   - Add tests for `services/date_utils.py` (33 stmt)
   - Add tests for `schemas/search.py` (18 stmt)
   - Add tests for `services/writer.py` (21 stmt)
   - Improve `services/circuit_breaker.py` from 79% to 85%+ (15 stmt)

2. **Phase 2** (Core Tasks - ~500 statements):
   - Add tests for `tasks/write.py`
   - Add tests for `tasks/research.py`
   - Add tests for `tasks/edit.py`

3. **Phase 3** (Services - ~300 statements):
   - Add tests for uncovered service modules
   - Improve LLM adapter coverage

### 2. Coverage Configuration Best Practices

Based on pytest-cov standards:

```toml
[tool.coverage.run]
source = ["."]
omit = [
    ".venv/**",
    "migrations/**",
    "instance/**",
    "tests/**",
    "run.py",                    # Entry points
    "*/__init__.py",             # Empty init files (optional)
]

[tool.coverage.report]
fail_under = 80
skip_empty = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "raise AssertionError",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

### 3. Focus Areas for Maximum Impact

1. **Task modules** - These contain core pipeline logic but have very low coverage
2. **Admin route modules** - Many admin APIs lack comprehensive testing
3. **Adapter modules** - Web and API adapters need more test scenarios
4. **LLM services** - Base class and provider implementations need more edge case testing

---

## Dead Code Analysis

The following module appears to be unused (not imported anywhere in the codebase):

- `services/quality.py` (119 statements, 0% coverage)

**Recommendation**: Either delete this file if it's not needed, or add tests if it's intended for future use.

---

## Commands for Ongoing Coverage Monitoring

```bash
# Run tests with coverage
.venv/bin/pytest tests/ --cov=. --cov-report=term-missing

# Generate HTML coverage report
.venv/bin/pytest tests/ --cov=. --cov-report=html
# Then open htmlcov/index.html

# Check coverage for specific module
.venv/bin/pytest tests/ --cov=services.quality --cov-report=term

# Run with fail-under to enforce threshold
.venv/bin/pytest tests/ --cov=. --cov-fail-under=80
```

---

## Current Test File Inventory

Existing test files (63 total):
- 11 test files for routes/admin
- 5 test files for LLM adapters
- 5 test files for pipeline
- 43 other test files

**Missing test files for**:
- `tasks/write.py`, `tasks/research.py`, `tasks/edit.py`, `tasks/newsletter.py`
- `services/writer.py`, `services/date_utils.py`, `services/article.py`
- `services/cache.py`, `services/subscribers.py`, `services/editor.py`
- `schemas/search.py`

---

Generated: 2026-05-01
Coverage Tool: pytest-cov (coverage.py)
