# Code Quality Improvement Plan

**Generated**: 2026-04-23  
**Status**: Planned (not started)  
**Total Issues**: 6 categories

---

## Executive Summary

This plan addresses code quality issues identified during a comprehensive code review of the ainews codebase. The codebase is well-structured with solid security practices, but several areas for improvement were identified.

| Priority | Category | Issues | Effort |
|----------|----------|--------|--------|
| High | Template XSS Prevention | **2 confirmed** | Low |
| Medium | Exception Handling | 3 | Low-Medium |
| Low | Deprecated Imports | ~5 migrations | Low |
| Low | Code Documentation | 2 | Low |

---

## Priority 1: High Priority (Security)

### 1.1 Template HTML Escaping Audit

**Rationale**: XSS prevention via HTML escaping is critical for user safety. All user-generated or LLM-generated content rendered in templates must be escaped.

**Current State**: Most templates use `|e` filter correctly. Need to verify a few locations.

**Findings** (verified via code review):

| File | Line | Field | Status | Required |
|------|------|-------|--------|----------|
| `templates/article.html` | 3 | `{{ article.original_title }}` | **CONFIRMED MISSING** | `{{ article.original_title|e }}` |
| `templates/partials/condensed_article.html` | 88 | `{{ article.writer_model }}` | **MISSING** | `{{ article.writer_model|e }}` |
| `templates/partials/related_articles.html` | 10 | `{{ rel.original_title|e }}` | Correct | — |
| `templates/partials/article_card.html` | 23 | `{{ article.original_title|e }}` | Correct | — |
| `templates/partials/cards.html` | — | Uses `article_card.html` | Correct | — |

**Action Items**:
- [ ] Fix `templates/article.html:3` — add `|e` filter to `article.original_title`
- [ ] Fix `templates/partials/condensed_article.html:88` — add `|e` filter to `article.writer_model`
- [ ] Confirm all LLM-generated fields (`final_article`, `headline`, `tldr`) are escaped in all templates

**Effort**: 15 minutes  
**Risk**: None (adding escaping is safe, removing would be risky)

**Note on `<title>` tag**: While `<title>` content is primarily parsed as text (not HTML), escaping is still recommended for consistency and to prevent potential issues with special characters in titles.

---

## Priority 2: Medium Priority

### 2.1 Bare `except Exception:` Patterns

**Rationale**: PEP 760 proposes disallowing bare `except:` in future Python versions. Using `except Exception:` is safer than bare `except:` but should still be specific where possible.

**Current State**: 46 locations use `except Exception:`, most appropriately.

**Analysis by Pattern Type**:

| Location | Pattern | Should Change? | Rationale |
|----------|---------|---------------|-----------|
| `services/article.py:39` | Fire-and-forget async logging | No | Intentional — errors discarded |
| `services/article.py:124` | FTS5 fallback to ILIKE | **No (keep as-is)** | Intentional graceful degradation |
| `adapters/web.py:117` | Trafilatura fallback | Consider adding logging | Currently silent `pass` |
| `routes/decorators.py:29` | CSRF validation | No | Correct — validates token |
| `models.py:29` | `decode_short_url` | **Yes** | Can be more specific |
| Multiple locations | Audit logging fallbacks | Acceptable | Non-critical operations |

**Specific Changes Recommended**:

1. **`models.py:29`** — `decode_short_url`:
   ```python
   # Current
   except Exception:
       return None

   # Recommended
   except (ValueError, TypeError):
       return None
   ```
   The `short_url` library raises `ValueError` for invalid codes.

2. **`adapters/web.py:117`** — Add logging:
   ```python
   # Current
   except Exception:
       pass

   # Recommended
   except Exception as e:
       logger.debug("Trafilatura extraction failed: %s", e)
       pass
   ```

3. **`services/utils.py:61`** and similar — Verify these are appropriate.

**Effort**: 1-2 hours (mostly verification)  
**Risk**: Low (changing to specific exceptions may cause some errors to propagate instead of being silently handled)

---

### 2.2 Database Commit Error Handling

**Rationale**: Consistent error handling prevents inconsistent state.

**Current State**: Generally good. Uses `SQLAlchemyError` for db commits and `commit_or_rollback()` helper.

**Analysis**:
- 168 `db.session.commit()` calls found
- ~40% use explicit `except SQLAlchemyError` with rollback
- ~30% use `commit_or_rollback()` context manager
- ~30% in tests (acceptable)

**Recommended Pattern**:
```python
# Preferred for route handlers (returns JSON error)
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    return jsonify({"error": "Message"}), 500

# Preferred for Celery tasks (re-raises for retry)
with commit_or_rollback():
    db.session.commit()
```

**Findings**:

| File | Pattern | Status | Recommendation |
|------|---------|--------|-----------------|
| `routes/admin/api/articles.py:32` | `except SQLAlchemyError` | Good | — |
| `routes/admin/api/articles.py:75` | `except SQLAlchemyError` | Good | — |
| `routes/admin/api/articles.py:148` | `except Exception` | Should be `SQLAlchemyError` | Change |
| `tasks/pipeline.py:244` | `except SQLAlchemyError` | Good | — |

**Action Items**:
- [ ] Change `routes/admin/api/articles.py:148` to `except SQLAlchemyError`
- [ ] Review remaining `except Exception` near `db.session.commit()` for `SQLAlchemyError`

**Effort**: 30 minutes  
**Risk**: Low

---

### 2.3 short_url Library Exception Handling

**Rationale**: More specific exception handling improves debugging.

**Current State**: `decode_short_url` catches all exceptions silently.

**Action Item**:
```python
def decode_short_url(code: str) -> int | None:
    try:
        return _short_encoder.decode_url(code)
    except ValueError:  # Invalid base-N number
        return None
    except TypeError:   # Non-string input
        return None
```

**Effort**: 10 minutes  
**Risk**: Very Low

---

## Priority 3: Low Priority

### 3.1 Deprecated Imports

**Rationale**: Future-proofing against Python version changes. PEP 560/586 updated typing imports.

**Current State**: Migration files use deprecated `typing.Sequence` and `typing.Union`.

**Affected Files**:
- `migrations/versions/001_initial.py:9`
- `migrations/versions/002_dedup_index.py:9`
- `migrations/versions/003_fts5.py:9`
- (and similar pattern in other migrations)

**Recommended Fix**:
```python
# Old (deprecated)
from typing import Sequence, Union

# New
from collections.abc import Sequence
```

**Note**: Ruff UP035 rule flags these: `.venv/bin/ruff check . --select=UP035 --exclude .venv`

**Effort**: 20 minutes  
**Risk**: Very Low (migrations are read-only after initial run)

---

### 3.2 Async Logging Error Handling

**Rationale**: Fire-and-forget patterns should log failures for debugging.

**Location**: `services/article.py:39`

**Current**:
```python
def _async_log():
    try:
        ...
    except Exception:
        pass  # Silent failure
```

**Recommendation**: Consider adding structured logging for monitoring:
```python
logger.debug("Search query logging failed", extra={"query": query[:50]})
```

**Effort**: 15 minutes  
**Risk**: Very Low

---

## Implementation Order

| # | Task | Priority | Effort | Description |
|---|------|----------|--------|-------------|
| 1 | Fix XSS-001: article.html title | High | 5 min | Add `|e` filter to `original_title` in `<title>` |
| 2 | Fix XSS-002: condensed_article.html | High | 5 min | Add `|e` filter to `writer_model` |
| 3 | Fix COMMIT-001: SQLAlchemyError | Medium | 5 min | Change `except Exception` to `except SQLAlchemyError` |
| 4 | Fix EXCEPT-001: short_url | Medium | 10 min | Narrow exception to `(ValueError, TypeError)` |
| 5 | Fix EXCEPT-002: trafilatura logging | Low | 10 min | Add debug logging before `pass` |
| 6 | Fix IMPORT-001: deprecated imports | Low | 20 min | Update typing imports in migrations |
| 7 | Optional: async logging | Low | 15 min | Add debug logging for fire-and-forget |

**Total estimated time**: ~70 minutes

---

## Testing Requirements

1. After template changes: Run `pytest tests/test_routes.py -v` to verify pages render correctly
2. After exception handling changes: Run relevant unit tests
3. Before committing: `.venv/bin/ruff check . --exclude .venv`
4. Full test run: `.venv/bin/pytest tests/ -x -q` (847 tests)

**Test Coverage for Changes**:

| Change | Relevant Tests |
|--------|----------------|
| Template escaping | `tests/test_routes.py` |
| Exception handling | `tests/test_validation.py`, `tests/test_article_validation.py` |
| Database commits | Integration tests via conftest |
| Deprecated imports | None (migration files not tested) |

---

## Rollback Plan

- Template changes: Revert `|e` filter additions
- Exception handling: Revert to `except Exception:`
- Migration changes: Not applicable (migrations are versioned)

---

## Appendix A: Issue Summary Table

| ID | Category | Severity | File | Line | Description |
|----|----------|----------|------|------|-------------|
| XSS-001 | XSS | **HIGH** | templates/article.html | 3 | Confirmed: Missing `|e` filter on `article.original_title` in `<title>` |
| XSS-002 | XSS | **HIGH** | templates/partials/condensed_article.html | 88 | Confirmed: Missing `|e` filter on `article.writer_model` |
| EXCEPT-001 | Exception | Medium | models.py | 29 | Broad exception in `decode_short_url` |
| EXCEPT-002 | Exception | Medium | adapters/web.py | 117 | Silent exception in trafilatura fallback |
| COMMIT-001 | DB | Medium | routes/admin/api/articles.py | 148 | Should use `SQLAlchemyError` |
| IMPORT-001 | Future | Low | migrations/*.py | ~9 | Deprecated `typing.Sequence` imports |

---

## Appendix B: Reference Resources

- [PEP 760 – No More Bare Excepts](https://peps.python.org/pep-0760/)
- [Real Python: Exception Handling Best Practices](https://realpython.com/ref/best-practices/exception-handling/)
- Project conventions: `AGENTS.md`

---

## Approval

- [ ] Ready for implementation
- [ ] Priority acknowledged
- [ ] Security review completed (for high-priority items)