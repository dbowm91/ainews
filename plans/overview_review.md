# Architecture Overview Review

**Date:** 2026-05-21
**Reviewed Document:** `architecture/overview.md`
**Codebase Commit:** Recent (checked)

---

## Executive Summary

The architecture document at `architecture/overview.md` is **largely accurate** but has several discrepancies and areas needing clarification. The core architecture (layers, modules, data flows) matches implementation well. Most discrepancies are minor documentation issues.

---

## Verified Correct

### Module Index (All 9 Modules Exist)
| Module | Location | Status |
|--------|----------|--------|
| Models | `models/` | Verified - 14 model files |
| Services | `services/` | Verified - 60+ files with subdirectories (llm, search, subagent) |
| Adapters | `adapters/` | Verified - api.py, base.py, rss.py, session.py, web.py |
| Routes | `routes/` | Verified - admin/ and public/ subdirectories |
| Tasks | `tasks/` | Verified - 16 task files |
| Schemas | `schemas/` | Verified - 14 schema files |
| Utils | `utils/` | Verified - 6 utility files (datetime, hash, html, security, text, url) |
| Subagent | `services/subagent/` | Verified - 13 files |
| Pipeline | `services/newsletter_pipeline.py` | Verified - exists alongside pipeline stages in tasks/ |

### Configuration Files (All Exist)
| File | Location | Status |
|------|----------|--------|
| `pipeline.yaml` | Root | Verified |
| `providers.yaml` | Root | Verified (14 LLM providers + 3 search providers) |
| `sources.yaml` | Root | Verified |
| `topics.yaml` | Root | Verified |
| `config.py` | Root | Verified |

### Directory Structure
- `app.py`, `celery_app.py`, `extensions.py`, `constants.py` - all exist at root
- `prompts/` - exists at root with 12 template files
- `scripts/` - exists with 10 utility scripts
- `templates/` - exists with admin/ and public/ subdirectories
- `tests/` - exists with 93 test files

### Data Flow Descriptions
1. **Source Ingestion** - Correct flow: Sources → Adapters → process_item task → Article record
2. **Article Processing Pipeline** - Correct: select → research → write → edit → finalize
3. **Newsletter Generation** - Correct: generate_daily_newsletters with executive_summary, main_newsletter, topic_newsletters

### Security Architecture Claims

| Claim | Implementation | Status |
|-------|---------------|--------|
| Fail-Closed | `config.py:ProductionConfig.validate()` checks all secrets at startup | Verified |
| TOTP 2FA | `services/totp.py` - 8 backup codes via `generate_backup_codes()` | Verified |
| Session Binding | `routes/admin/__init__.py:79-86` - IP + User-Agent validation | Verified |
| HMAC Webhooks | `services/webhooks.py:101-122` - `_sign_payload()` with timestamp replay protection | Verified |
| SSRF Protection | `utils/url.py:243-262` - `validate_url_safe()` with DNS resolution | Verified |
| Encrypted Secrets | `services/webhooks.py:69-98` - Fernet encryption at rest | Verified |
| Login Lockout | `routes/admin/__init__.py:104-303` - Redis-based with in-memory fallback | Verified |

### Layering Rules

| Layer | Rule | Verification |
|-------|------|--------------|
| Adapters | Cannot import services | Verified - only comment about layering violation in base.py |
| Services | Cannot import adapters | Verified - `services/crawling.py:13` uses TYPE_CHECKING pattern |
| Tasks | Can import services | Verified - tasks heavily import from services |
| Routes | Cannot import adapters | Verified - routes only import models/schemas/services |

### Infrastructure Components
- **Web Server:** Granian mentioned in docs, actual implementation uses ASGI
- **Task Queue:** Celery + Redis - Verified in config.py
- **Database:** SQLite with WAL mode - Verified in app.py:163-172
- **Cache:** Redis - Used throughout
- **Email:** SMTP with connection pooling - Verified in services/email.py

---

## Discrepancies Found

### 1. Directory Structure Root Prefix
**Doc says:** `ainews/` as root prefix for all paths
**Actual:** Files are directly in project root (no `ainews/` subdirectory)

```
Doc:     ainews/app.py
Actual:  app.py

Doc:     ainews/models/
Actual:  models/
```

### 2. Provider Count Mismatch
**Doc says:** "14 providers" in providers.yaml header
**Actual:** 14 LLM providers + 3 search providers = 17 total providers
```
LLM: ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode = 14
Search: duckduckgo, google, searxng = 3
```

### 3. Subagent Location Clarification
**Doc says:** "Subagent system is located at `services/subagent/` (not at top level)"
**Status:** This note IS present in the doc (line 163) - correct

### 4. "Session Binding" vs "Session Hijacking Detection"
**Doc term:** "Session Binding"
**Actual term:** The code detects session hijacking via IP + User-Agent mismatch and invalidates session
**Severity:** Minor - semantic difference, functionality matches

### 5. Pipeline Stage "finalize" Not in Constants
**Doc shows:** `finalize_article` as pipeline stage
**Actual:** `constants.py` has DONE status, not "finalize" - finalize is implicit transition to DONE
**Status:** Documented in AGENTS.md - "finalize_article" is handled by the `edit` stage transitioning to DONE

### 6. routes/admin/api/ Location
**Doc says:** `routes/admin/` contains admin interface + API
**Actual:** `routes/admin/api/` subdirectory exists with separate API endpoints
**Status:** Both exist - admin_bp at /admin and admin_api_bp at /api/v1

### 7. prompts/ Directory Classification
**Doc says:** prompts/ is listed under directory structure
**Actual:** prompts/ is a directory with .txt template files, not Python module
**Status:** Correct as written

---

## Bugs Identified

### 1. Duplicate URL Validation Implementation
**Location:** `utils/url.py` and `services/url.py`
**Issue:** Both files implement nearly identical SSRF protection (same blocked networks, same DNS caching, same validation logic)
**Status:** **DOCUMENTED** in AGENTS.md - "services/url.py has duplicate implementations"
**Note:** utils/url.py is for adapters (clean layering), services/url.py has config support for services

### 2. Layer Violation in schemas/common.py
**Location:** `schemas/common.py:72-75, 86-89`
**Issue:** `cached_config()` and `cached_config_with_mtime()` import from `services.config_cache`
**Status:** **DOCUMENTED** in AGENTS.md as necessary violation with comment explaining why
**Code:**
```python
# Layer violation: schemas should not import from services.
# This is intentional - config caching requires services layer knowledge.
```

### 3. TYPE_CHECKING Import in services/crawling.py
**Location:** `services/crawling.py:12-13`
```python
if TYPE_CHECKING:
    from adapters.base import RawItem
```
**Issue:** Uses TYPE_CHECKING pattern but this appears to be the only service file importing from adapters
**Severity:** This is **correct pattern** for type hints - no runtime import
**Status:** NOT A BUG - properly uses TYPE_CHECKING to avoid layer violation

---

## Improvement Suggestions

### 1. Update Directory Structure Diagram
Remove `ainews/` prefix since project root IS the root:
```
# Current (incorrect prefix)
ainews/
├── app.py

# Suggested (correct)
.
├── app.py
```

### 2. Clarify Provider Count
Either:
- Change "14 providers" to "14 LLM providers + 3 search providers"
- Or list total count: "17 providers (14 LLM + 3 search)"

### 3. Add Note About Type Checking Imports
The layering rules table doesn't mention TYPE_CHECKING exception. Suggested addition:
> "Note: Services may use `TYPE_CHECKING` block to import adapter types for type hints only, avoiding runtime imports."

### 4. Document Pipeline Stage Naming
The architecture shows "finalize_article" but constants.py uses DONE status. Consider:
- Adding comment that `finalize` maps to DONE in the status constants
- Or clarifying in the data flow that "finalize" is part of the edit stage transition

### 5. utils/url.py Global State Documentation
The module docstring already notes global mutable state (as of MED-5 fix). This is correctly documented.

---

## Questions for Architecture

### Q1: What is the relationship between `models/` directory and `models.py` file?
**Finding:** Both exist
- `models/` directory contains SQLAlchemy model classes (source.py, article.py, etc.)
- `models.py` at root appears to be an older file

Should the architecture clarify which is the primary models location?

### Q2: Granian vs ASGI Server
The architecture mentions "Granian (ASGI)" but the actual deployment may use different ASGI servers. Should this be more generic ("ASGI server") or is Granian the recommended server?

### Q3: prompts/ Directory Classification
Is `prompts/` considered a separate module or part of another module? It's listed separately in directory structure but doesn't have an `__init__.py` or deep-dive doc.

### Q4: celery_app.py vs tasks/ Relationship
`celery_app.py` creates the Celery app but tasks are in `tasks/`. Should architecture clarify that Celery tasks are orchestrated from both `celery_app.py` and `tasks/` directory?

---

## Summary

| Category | Count | Notes |
|----------|-------|-------|
| Verified Correct | 15 | Core architecture matches implementation |
| Discrepancies | 7 | Mostly documentation clarity issues |
| Bugs | 0 | No actual bugs found (documented issues are intentional) |
| Questions | 4 | Clarifications needed |

**Overall Assessment:** The architecture document is **accurate and well-structured**. Most discrepancies are minor documentation clarity issues. The implementation correctly follows the documented layering rules, with known exceptions documented as intentional.

---

## Recommended Actions

1. **Low Priority:** Update directory structure diagrams to remove `ainews/` prefix
2. **Low Priority:** Clarify provider count in providers.yaml header comment
3. **Documentation:** Add TYPE_CHECKING exception to layering rules table
4. **Documentation:** Clarify pipeline stage "finalize" mapping to DONE status
