# Architecture Review: `architecture/overview.md` (2026-05-07)

## Executive Summary

The `architecture/overview.md` document accurately describes the system architecture in most
areas. However, significant **layering violations** exist where services and adapters mutually
import from each other, contradicting the stated design principles. Additionally, several
SSRF/security utilities are incorrectly placed in `services/` instead of `utils/`.

---

## 1. VERIFICATION OF MAJOR CLAIMS

### 1.1 Directory Structure ✅ VERIFIED

All stated directories exist and contain the expected files:

| Directory | Status | Evidence |
|-----------|--------|----------|
| `models/` | ✅ | article.py, source.py, tag.py, newsletter.py, pipeline.py, auth.py, etc. |
| `services/` | ✅ | researcher.py, writer.py, editor.py, newsletter_pipeline.py, llm/, subagent/ |
| `adapters/` | ✅ | rss.py, api.py, web.py, base.py, session.py |
| `routes/` | ✅ | admin/, public/ blueprints |
| `tasks/` | ✅ | pipeline.py, crawl.py, extract.py, select.py, research.py, write.py, edit.py |
| `schemas/` | ✅ | pipeline.py, source.py, llm.py, llm_responses.py, tasks.py |
| `utils/` | ✅ | url.py, text.py |
| `prompts/` | ✅ | selector.txt, researcher.txt, writer.txt, editor.txt, subagent_*.txt |
| `tests/` | ✅ | test_*.py test files |

**Discrepancy Found**: Directory structure diagram (lines 178-196) does not show
`extensions.py` which is a key file.

### 1.2 Module Index Accuracy ✅ VERIFIED

All modules in the index exist and have the described functionality.

### 1.3 System Diagram Components ✅ VERIFIED

All components in the system diagram exist:
- **Adapters**: RSSAdapter (`adapters/rss.py`), APIAdapter (`adapters/api.py`), WebAdapter (`adapters/web.py`)
- **Services**: Researcher (`services/researcher.py`), Writer (`services/writer.py`), Editor (`services/editor.py`), Subagent (`services/subagent/`)
- **Pipeline**: `select_article` → `research_article` → `write_article` → `edit_article` → `finalize`

### 1.4 Infrastructure Components ✅ VERIFIED

| Component | Status | Evidence |
|-----------|--------|----------|
| **Granian (ASGI)** | ✅ VERIFIED | Dockerfile line 18: `granian>=1.0.0,<2`; `run.py` exports `WsgiToAsgi(flask_app)` |
| **Celery + Redis** | ✅ VERIFIED | `celery_app.py`; `docker-compose.yml` lines 42-95 |
| **SQLite (WAL)** | ✅ VERIFIED | `app.py` lines 161-173 sets WAL pragma |
| **Redis (Rate Limiting)** | ✅ VERIFIED | `services/limiter.py` uses Redis pub/sub |
| **SMTP Email** | ✅ VERIFIED | `services/email.py` with connection pooling |

### 1.5 Data Flow Summary ✅ VERIFIED

#### Source Ingestion (lines 76-93)
- `Adapters.fetch_and_parse()` exists in `adapters/base.py` lines 56-69
- `process_item` task in `tasks/extract.py` handles extract → deduplicate → dispatch
- Uses `trafilatura`/`readability` for content extraction (line 87 comment matches code)

#### Article Processing Pipeline (lines 95-115)
- `select_article` → LLM scores 1-10 (`tasks/select.py`)
- `research_article` → LLM builds research brief (`tasks/research.py`)
- `write_article` → Smart Brevity format (`tasks/write.py`)
- `edit_article` → contextualization + tag assignment (`tasks/edit.py`)
- `finalize_article` → trend memory update + webhook dispatch (`services/pipeline_degradation.py`)

#### Newsletter Generation (lines 117-131)
- Scheduled at 8:00 AM ET via `generate_daily_newsletters` (`tasks/newsletter.py`)
- 3-stage executive summary: reader → writer → editor (lines 124 matches code)
- Batch size 500/retry (line 130 matches `services/email.py`)

### 1.6 Key Configuration Files ✅ VERIFIED

| File | Status |
|------|--------|
| `pipeline.yaml` | ✅ EXISTS - controls stage configs, newsletter, subagent, schedules |
| `providers.yaml` | ✅ EXISTS - ollama-local (enabled), openai/anthropic/gemini (disabled), search providers |
| `sources.yaml` | ✅ EXISTS - hackernews, techcrunch, arstechnica, theverge |
| `topics.yaml` | ✅ EXISTS |
| `config.py` | ✅ EXISTS - Development, Production, Testing configs |

---

## 2. SECURITY ARCHITECTURE VERIFICATION

| Claim | Status | Evidence |
|-------|--------|----------|
| **Fail-Closed** | ✅ VERIFIED | `config.py` lines 253-278 `ProductionConfig.validate()` raises RuntimeError |
| **TOTP 2FA** | ✅ VERIFIED | `services/totp.py` with 8 backup codes |
| **Session Binding** | ✅ VERIFIED | IP + User-Agent validation in routes |
| **HMAC Webhooks** | ✅ VERIFIED | `services/webhooks.py` lines 49-98 with timestamp replay protection |
| **SSRF Protection** | ⚠️ PARTIAL | `services/url.py` validates URLs but is incorrectly placed in services |
| **Encrypted Secrets** | ✅ VERIFIED | Fernet encryption in `services/webhooks.py` lines 69-98 |
| **Login Lockout** | ✅ VERIFIED | Redis-based in routes with in-memory fallback |

---

## 3. DISCREPANCIES FOUND

### 3.1 CRITICAL: Layering Violations

**Architecture Claim** (lines 189-190):
> `services/` - Business logic (NO adapter imports)
> `adapters/` - Source adapters (NO service imports)

**Actual Violations Found**:

#### Violation 1: Adapters import from Services
| File | Line | Import | Issue |
|------|------|--------|-------|
| `adapters/session.py` | 8 | `from services.url import UnsafeURLError, validate_url_safe` | session.py is infrastructure, not business logic |
| `adapters/rss.py` | 12 | `from services.url import validate_url_safe` | SSRF check is utility, not service |
| `adapters/api.py` | 11 | `from services.url import validate_url_safe` | SSRF check is utility |
| `adapters/web.py` | 14 | `from services.url import UnsafeURLError, validate_url_safe` | SSRF check is utility |

#### Violation 2: Services import from Adapters
| File | Line | Import | Issue |
|------|------|--------|-------|
| `services/crawling.py` | 13 | `from adapters.base import RawItem` | services should not know about adapter types |

**Impact**: 
- The `services/url.py` module contains the SSRF protection (`validate_url_safe`), which is a **pure utility function** with no business logic. It should be in `utils/url.py`.
- By placing SSRF utilities in `services/`, all adapters must import from services, directly violating the architecture docs.
- The `adapters/base.py` file correctly imports from `utils/url.py` for `normalize_url`, showing the intended pattern.

### 3.2 MEDIUM: SSRF Utility Misplaced

`validate_url_safe()` and `UnsafeURLError` are in `services/url.py` but are pure utilities:

```python
# services/url.py lines 178-191 - This is a pure function:
def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP."""
    # No business logic - pure validation
```

The correct place is `utils/url.py` alongside `normalize_url()` and `is_valid_url()`.

### 3.3 LOW: Directory Structure Diagram Missing Files

- `extensions.py` not shown in directory structure (line 178-196)
- `services/subagent/` not explicitly listed in directory structure

---

## 4. BUGS AND ISSUES

### 4.1 Layering Violation Bug (HIGH)

**Severity**: HIGH

**Problem**: The architecture doc explicitly forbids services→adapters and adapters→services imports,
but the codebase violates this in both directions.

**Root Cause**: SSRF protection (`validate_url_safe`) was placed in `services/url.py` instead of
`utils/url.py`. Since adapters need SSRF validation, they must import from services, which
violates the layering.

**Recommended Fix**:
1. Move `validate_url_safe` and `UnsafeURLError` from `services/url.py` to `utils/url.py`
2. Add `UnsafeURLError` export to `utils/url.py`
3. Update all adapter files to import from `utils.url` instead of `services.url`
4. Remove the `from services.url import validate_url_safe` pattern from adapters
5. Keep `normalize_url`, `normalize_title`, `TRACKING_PARAMS` in `utils/url.py` as-is
6. Update `services/url.py` to import from `utils/url.py` for backward compatibility

**Files to Modify**:
- `utils/url.py` - Add `validate_url_safe`, `UnsafeURLError`
- `services/url.py` - Remove duplicate SSRF code, re-export from utils
- `adapters/session.py` - Update import
- `adapters/rss.py` - Update import  
- `adapters/api.py` - Update import
- `adapters/web.py` - Update import

### 4.2 services/crawling.py Imports from Adapters (HIGH)

**Severity**: HIGH

**Location**: `services/crawling.py` line 13

**Problem**:
```python
from adapters.base import RawItem
```

Services should not import from adapters. The `RawItem` schema is in `schemas/item.py` and
should be used instead for type hints.

### 4.3 Circular Dependency Risk (MEDIUM)

**Severity**: MEDIUM

The current architecture has a potential circular dependency:
- Adapters need SSRF validation (in services)
- Services may need to validate URLs (but this is mostly adapter concern)

By moving SSRF to utils, we break this cycle and enforce proper layering.

---

## 5. IMPROVEMENT RECOMMENDATIONS

### 5.1 Immediate: Fix Layering Violations

**Priority**: HIGH

1. **Move SSRF to utils** (`utils/url.py`)
   - Add `UnsafeURLError` class
   - Add `validate_url_safe()` function
   - Update `is_valid_url()` in utils to use the new function

2. **Update adapter imports**
   - Change all `from services.url import ...` to `from utils.url import ...`
   - Files: `session.py`, `rss.py`, `api.py`, `web.py`

3. **Update services/crawling.py**
   - Remove `from adapters.base import RawItem`
   - Use `from schemas.item import RawItem` instead

4. **Maintain backward compatibility**
   - Have `services/url.py` re-export from `utils/url.py` for any external consumers

### 5.2 Add Linting Enforcement (HIGH)

**Priority**: HIGH

Add import-linter or custom ruff rules to enforce layering:

```toml
# pyproject.toml or ruff.toml
[tool.importlinter]
layers = [
    { name = "adapters", include_files = ["adapters/**/*.py"] },
    { name = "services", include_files = ["services/**/*.py"] },
    { name = "utils", include_files = ["utils/**/*.py"] },
]
rules = [
    { name = "no_adapters_in_services", from = "adapters", to = "services" },
    { name = "no_services_in_adapters", from = "services", to = "adapters" },
]
```

### 5.3 Update Directory Structure (LOW)

**Priority**: LOW

Add to `architecture/overview.md` directory structure:
```
├── extensions.py           # Flask extensions (db, limiter, redis)
├── services/subagent/      # Tool-enabled LLM agents (documented separately)
```

### 5.4 Update Schema Documentation (LOW)

**Priority**: LOW

The `schemas.md` file shows old field names for Article model. The actual model has:
- `original_title` not `title`
- `original_url` not `url`
- `selector_result` (JSON) not individual columns

---

## 6. SUMMARY OF FINDINGS

| Category | Count | Severity |
|----------|-------|---------|
| Verified Claims | 18 | - |
| Layering Violations | 5 | HIGH |
| Misplaced Utilities | 1 | MEDIUM |
| Missing Documentation | 2 | LOW |

### Must Fix

1. Move SSRF utilities (`validate_url_safe`, `UnsafeURLError`) from `services/url.py` to `utils/url.py`
2. Update all adapter files to import SSRF from `utils.url`
3. Fix `services/crawling.py` to not import from `adapters.base`

### Should Fix

4. Add `extensions.py` and `services/subagent/` to directory structure diagram

### Architecture Decision Needed

5. Should `services/url.py` be deprecated/removed entirely, or kept as re-export for backward compat?

---

## File Reference Index

| Path | Purpose | Relevant Lines |
|------|---------|----------------|
| `adapters/base.py` | Base adapter + SSRF utility usage | 10 (utils import correct) |
| `adapters/session.py` | SSRF import from services | 8 (VIOLATION) |
| `adapters/rss.py` | SSRF import from services | 12 (VIOLATION) |
| `adapters/api.py` | SSRF import from services | 11 (VIOLATION) |
| `adapters/web.py` | SSRF import from services | 14 (VIOLATION) |
| `services/url.py` | SSRF utilities (should be in utils) | 132-191 |
| `services/crawling.py` | Imports from adapters | 13 (VIOLATION) |
| `utils/url.py` | URL normalization (correct location) | 30-93 |
| `services/limiter.py` | Redis rate limiter | 32-160 |
| `services/totp.py` | TOTP 2FA implementation | 7-49 |
| `services/webhooks.py` | HMAC + encrypted secrets | 69-122 |
| `config.py` | Fail-closed production validation | 253-278 |
