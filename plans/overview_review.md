# Architecture Overview Review - Improvement Plan

**Review Date:** 2026-05-22
**Module Reviewed:** `architecture/overview.md`
**Reviewer:** Architecture Review Agent

---

## Summary

The `architecture/overview.md` document is largely accurate and well-structured. Directory structure, pipeline stages, and configuration files all match the implementation. Some documented claims need correction or clarification.

---

## Verified Claims (Verified Accurate)

| Claim | Evidence |
|-------|----------|
| Directory structure (`app.py`, `config.py`, `celery_app.py`, `models/`, `adapters/`, `services/`, `routes/`, `tasks/`, `schemas/`, `utils/`) | All verified at correct locations |
| RSSAdapter, APIAdapter, WebAdapter in `adapters/` | `adapters/rss.py`, `adapters/api.py`, `adapters/web.py` all exist and use `@register_adapter` decorator |
| Services submodules (`llm/`, `subagent/`, `search/`) | All verified in `services/` directory |
| Subagent system at `services/subagent/` | Confirmed at `services/subagent/__init__.py` |
| Admin API at `/api/v1/` prefix | `routes/admin/__init__.py:15` registers `admin_api_bp` with `url_prefix="/api/v1"` |
| Source config uses `config` field (not `adapter_config`) | `schemas/source.py:112` confirms `SourceConfig.config` dict field |
| StageConfig is a stub with only `tools` field | `schemas/pipeline.py:147` confirms `StageConfig(tools: list[str])` |
| NewsletterBrief has `themes`, `highlights`, `connections` (no `preamble`/`footer`/`articles`) | `schemas/llm_responses.py:142-148` confirms |
| Dynamic fallback chain from `providers.yaml` | `services/llm/__init__.py` iterates enabled providers |
| 14 Celery Beat scheduled tasks | `config.py:146-203` defines 14 tasks |
| Rate limiter pattern (finally block, `provider_id or rc.provider`) | Documented in `AGENTS.md`, used in `tasks/pipeline.py` |
| TrendMemory.observation is actually `signal` | `models/context.py:32` uses `signal` field |
| `Source.last_fetch_at` is actually `last_crawled` | `models/source.py:18` confirms `last_crawled` column |
| `Article.finalized_at` doesn't exist | `models/article.py` has `published_at` (line 54), no `finalized_at` |
| TOTP 2FA with 8 backup codes | `services/totp.py`, `models/auth.py` confirm backup codes |
| Fail-closed security | `config.py:254-278` `ProductionConfig.validate()` raises RuntimeError |
| SSRF protection via SSRFSafeRedirectHandler | `adapters/session.py:16-55` implements redirect validation |
| URL validation layering (services vs utils) | `services/url.py` and `utils/url.py` both exist |

---

## Discrepancies and Issues

### 1. CRIT - Layering Violation: `services/crawling.py` imports from `adapters`

**File:** `services/crawling.py:15`
```python
from adapters.base import RawItem
```

**Issue:** The document states Adapters layer "Cannot Import from services" and Services layer "Cannot Import from adapters". However, `services/crawling.py` imports `RawItem` from `adapters.base` at runtime. While there's a `TYPE_CHECKING` block (lines 12-15), this only affects type checking - the runtime import still occurs when the function executes.

**Impact:** Violates clean layering architecture. Services should not depend on adapters.

**Recommendation:** Move the import inside the function that needs it, or refactor to avoid the dependency entirely.

---

### 2. CRIT - Layering Violation: `tasks/crawl.py` imports from `adapters`

**File:** `tasks/crawl.py:34`
```python
from adapters.base import get_adapter_class
```

**Issue:** The document states Tasks layer "Can Import from services". However, `tasks/crawl.py` imports directly from `adapters.base`. The documented rule is: Tasks → Services only.

**Impact:** Violates documented layering rules. Tasks should only access adapters through services layer.

**Recommendation:** Add a wrapper in `services/crawling.py` that provides adapter access, or create a service method that tasks can call.

---

### 3. MED - `utils/url.py` Not Pure

**File:** `utils/url.py:130-194`

**Issue:** The document says `utils/url.py` contains "Pure utility functions with minimal dependencies". However, `validate_url_safe()` has global mutable state: `_dns_cache`, `_dns_cache_lock`, `_dns_executor`. The function performs actual DNS resolution with caching.

**Status:** Already documented in `AGENTS.md` ("utils/url.py Not Pure - global mutable state"), but NOT documented in `architecture/overview.md`.

**Recommendation:** Add a note in "Known Architecture Notes" section:
```markdown
- **utils/url.py Not Pure**: Despite docstring claims, `utils/url.py` has global mutable state 
  (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). `validate_url_safe()` performs actual 
  DNS resolution with caching.
```

---

### 4. MED - Documented Layering Rule Doesn't Match Implementation

**Documented Rule:** Routes layer "Can Import from models, schemas, services" | "Cannot Import from adapters"

**Actual:** `routes/admin/__init__.py:308-351` imports submodules at bottom of file, and `routes/admin/__init__.py:10` imports `from services.validation import _is_password_hash`. `routes/admin/auth.py` uses admin_bp decorator from `routes/admin/__init__.py`. The routes module imports services which imports adapters via TYPE_CHECKING.

**Status:** Routes do not directly import adapters, so this is compliant. However, the import chain `routes → services → adapters (TYPE_CHECKING only)` should be explicitly documented.

**Recommendation:** Document that services may use TYPE_CHECKING imports from adapters for type hints only.

---

### 5. MED - `schemas/common.py` imports from `services.config_cache`

**File:** `schemas/common.py`

**Issue:** The document says schemas layer "Can Import from services" for config caching. However, `schemas/common.py` imports from `services.config_cache` which creates a dependency where schemas → services. This is the opposite direction of the documented Services layer rules.

**Status:** Already documented in `AGENTS.md` ("schemas/common.py Layer Violation - intentional").

**Recommendation:** Add explicit note in architecture document that this is intentional due to config caching requirements.

---

### 6. LOW - Celery Beat Schedule Count Mismatch

**Documented:** "14 scheduled tasks"

**Actual:** `config.py:146-203` defines 14 tasks in `get_beat_schedule()`:
1. run-all-sources
2. retry-stuck-articles
3. generate-newsletters
4. cleanup-old-logs
5. consolidate-trend-memory
6. purge-trend-memory
7. cleanup-old-versions
8. cleanup-expired-verifications
9. publish-scheduled-articles
10. cleanup-stale-limiter-slots
11. retry-failed-newsletter-deliveries
12. recalculate-impact-scores
13. cleanup-inactive-subscribers
14. backfill-embeddings

**Status:** Verified accurate. All 14 tasks confirmed.

---

### 7. LOW - Entry Point `python run.py` vs `flask run`

**Documented:** `python run.py` as development server entry point

**Actual:** `run.py` exists and is the correct entry point.

**Status:** Verified accurate.

---

### 8. LOW - `providers.yaml` shows 14 providers (not 14 as listed)

**Documented:** "LLM provider definitions (14 providers: ollama, openai, anthropic, etc.)"

**Actual:** `providers.yaml:1-123` lists:
- ollama-local (enabled)
- openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode (13 total)

Total: 14 providers (13 disabled + 1 enabled) - CORRECT.

---

### 9. LOW - API Authentication Documentation Gap

**Documented:** "Admin API endpoints at /api/v1/ (not /admin/api/)"

**Actual:** Verified in `routes/admin/__init__.py:15`.

**Issue:** The document doesn't mention API token authentication mechanism at `/api/v1/` endpoints. The `verify_api_token()` function at `routes/admin/__init__.py:18-44` handles Bearer token auth.

**Recommendation:** Add documentation about API token authentication pattern.

---

## Recommendations Summary

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| CRIT | services/crawling.py imports from adapters | `services/crawling.py:15` | Remove runtime import, use TYPE_CHECKING only or refactor |
| CRIT | tasks/crawl.py imports from adapters | `tasks/crawl.py:34` | Add service layer wrapper for adapter access |
| MED | utils/url.py global mutable state undocumented | `utils/url.py:130-194` | Add to "Known Architecture Notes" |
| MED | Layering rule gaps | `architecture/overview.md` | Document TYPE_CHECKING exception and routes→services→adapters chain |
| MED | schemas/common.py imports from services | `schemas/common.py` | Add note explaining intentional layer violation for config caching |
| LOW | API token auth undocumented | `routes/admin/__init__.py:18-44` | Add API token authentication to security architecture section |

---

## Bug Fixes Required

1. **`services/crawling.py:15`** - Remove `from adapters.base import RawItem` from function body. Keep only in TYPE_CHECKING block for static analysis.

2. **`tasks/crawl.py:34`** - Create service method in `services/crawling.py` that wraps `get_adapter_class()` and call that from tasks instead.

---

## Document Updates Required

1. **Layering Rules Table** - Add note:
   > Services may use TYPE_CHECKING imports from adapters for type hints only (e.g., `services/crawling.py`). Runtime imports from adapters are prohibited.

2. **Known Architecture Notes** - Add:
   > - **utils/url.py Not Pure**: Has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`)

3. **Security Architecture** - Add API token authentication section

4. **Directory Structure** - Correct `prompts/` (missing from diagram but present in file structure)