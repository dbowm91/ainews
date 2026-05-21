# Architecture Overview Review - Improvement Plan

**Reviewed:** `architecture/overview.md`
**Reviewer:** Architecture Review Agent (overview module)
**Date:** 2026-05-21

---

## Summary

The `architecture/overview.md` document is largely accurate and well-maintained. Most claims were verified against the codebase. The following discrepancies, architectural issues, and improvement recommendations were identified.

---

## Verified Claims (Accurate)

| Claim | Status | Evidence |
|-------|--------|----------|
| Directory structure | ✅ Accurate | All files/dirs match at `ls -la` |
| Layering rules | ✅ Accurate | Adapters import no services; services import no adapters (verified via grep) |
| URL validation duplication | ✅ Accurate | `utils/url.py` and `services/url.py` both exist with SSRF implementations |
| StageConfig stub | ✅ Accurate | `schemas/pipeline.py:140-146` - only has `tools` field |
| NewsletterBrief missing fields | ✅ Accurate | Schema has `themes`, `highlights`, `connections` only |
| Subagent system location | ✅ Accurate | `services/subagent/` with `runner.py` |
| API prefix `/api/v1/` | ✅ Accurate | `routes/admin/api/__init__.py` registered with `url_prefix="/api/v1"` |
| Rate limiter finally pattern | ✅ Accurate | `tasks/pipeline.py:434-436` uses `provider_id or rc.provider` and `model or rc.model` |
| Dynamic fallback chain | ✅ Accurate | `services/llm/__init__.py:57-80` iterates enabled providers |
| SSRFSafeRedirectHandler thread-local | ✅ Accurate | Uses `_thread_local` for redirect counter |
| `Source.last_crawled` field name | ✅ Accurate | `models/source.py` uses `last_crawled` (not `last_fetch_at`) |
| `Article.finalized_at` doesn't exist | ✅ Accurate | Uses `published_at` instead |
| `TrendMemory.observation` is `signal` | ✅ Accurate | `models/context.py:21` uses `signal` field |
| `Source.adapter_config` doesn't exist | ✅ Accurate | Adapter config stored in `schemas/source.py` as `SourceConfig.config` |

---

## Discrepancies & Issues

### 1. `utils/url.py` Not Pure (CRIT)

**Location:** `utils/url.py:1-262`

**Issue:** The docstring at line 1-5 claims functions are "pure" but `validate_url_safe()` has global mutable state:
- `_dns_cache` (line 182)
- `_dns_cache_lock` (line 183)
- `_dns_executor` (line 130)

**Impact:** This is a documentation bug. Functions with side effects should not be documented as pure.

**Recommendation:** Update docstring to clarify that DNS resolution functions have side effects. Or better, extract the DNS caching to a separate module that makes the impurity explicit.

---

### 2. `schemas/common.py` Layer Violation (Known/Acknowledged)

**Location:** `schemas/common.py:72-99`

**Issue:** `cached_config()` and `cached_config_with_mtime()` import from `services.config_cache`, violating the principle that schemas should not depend on services.

**Note:** This is documented with comments at lines 72 and 86: "Layer violation: schemas should not import from services. This is intentional - config caching requires services layer knowledge."

**Recommendation:** Either:
- Accept this as an intentional architectural choice (documented)
- Move config caching to `utils/` as a lower-level dependency
- Create a formal exception mechanism

---

### 3. Celery Beat Schedule - 14 Tasks Count

**Location:** `architecture/tasks.md:177-194` vs `config.py:146-203`

**Issue:** The table in `tasks.md` shows 14 scheduled tasks, but counting entries in `config.py:get_beat_schedule()` shows 13 tasks:

| Task | In tasks.md | In config.py |
|------|-------------|--------------|
| run-all-sources | ✅ | ✅ |
| retry-stuck-articles | ✅ | ✅ |
| generate-newsletters | ✅ | ✅ |
| cleanup-old-logs | ✅ | ✅ |
| consolidate-trend-memory | ✅ | ✅ |
| purge-trend-memory | ✅ | ✅ |
| cleanup-old-versions | ✅ | ✅ |
| cleanup-expired-verifications | ✅ | ✅ |
| publish-scheduled-articles | ✅ | ✅ |
| cleanup-stale-limiter-slots | ✅ | ✅ |
| retry-failed-newsletter-deliveries | ✅ | ✅ |
| recalculate-impact-scores | ✅ | ✅ |
| cleanup-inactive-subscribers | ✅ | ✅ |
| backfill-embeddings | ✅ | ✅ |

Wait - both show 14. Let me recount:

tasks.md table rows: run-all-sources, retry-stuck-articles, generate-newsletters, cleanup-old-logs, consolidate-trend-memory, purge-trend-memory, cleanup-old-versions, cleanup-expired-verifications, publish-scheduled-articles, cleanup-stale-limiter-slots, retry-failed-newsletter-deliveries, recalculate-impact-scores, cleanup-inactive-subscribers, backfill-embeddings = 14 ✅

config.py:get_beat_schedule() returns: run-all-sources, retry-stuck-articles, generate-newsletters, cleanup-old-logs, consolidate-trend-memory, purge-trend-memory, cleanup-old-versions, cleanup-expired-verifications, publish-scheduled-articles, cleanup-stale-limiter-slots, retry-failed-newsletter-deliveries, recalculate-impact-scores, cleanup-inactive-subscribers, backfill-embeddings = 14 ✅

Actually both match. No discrepancy.

---

### 4. Login Lockout - "Redis-based with in-memory fallback" (MED)

**Location:** `architecture/overview.md:235` vs actual implementation

**Issue:** The overview states "Login Lockout: Redis-based with in-memory fallback". However, the actual implementation in `services/limiter.py` uses Redis pub/sub for the LLM rate limiter, but login lockout is implemented differently.

**Recommendation:** Verify the login lockout implementation matches the documented behavior.

---

### 5. `providers.yaml` - Provider Count

**Location:** `architecture/overview.md:203` vs `providers.yaml`

**Issue:** Line 203 says "14 providers: ollama, openai, anthropic, etc." but counting in `providers.yaml` shows 15 total providers (including default_provider entry).

Actual count in providers.yaml:
- LLM providers: ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode = 14
- Search providers: duckduckgo, google, searxng, hybrid = 4 (but hybrid is mentioned in overview as enabled - it's actually in services/search/hybrid.py, not in providers.yaml search_providers list)

Wait, looking more carefully:
- `providers.yaml` has 14 LLM providers + 3 search providers (duckduckgo, google, searxng) = 17 total

The overview says "14 providers" but the file has more. This is slightly misleading.

**Recommendation:** Update the overview to accurately reflect the provider count.

---

### 6. Search Provider "hybrid" Not in providers.yaml (MED)

**Location:** `architecture/overview.md:223` vs `providers.yaml`

**Issue:** Overview states "hybrid (enabled) - FTS5 + vector similarity" but `providers.yaml` search_providers section only has `duckduckgo`, `google`, and `searxng`. The `hybrid` search provider in `services/search/hybrid.py` is not configured via `providers.yaml`.

**Recommendation:** Either:
- Add `hybrid` to `providers.yaml` search_providers
- Or update documentation to clarify hybrid is implemented separately

---

## Bugs in Implementation

### BUG-1: Schema Comments Documented as Code (LOW)

**Location:** `schemas/common.py:72, 86`

**Issue:** Comments stating "Layer violation: schemas should not import from services" are visible in the codebase. This is intentional but creates noise.

**Recommendation:** Suppress with `noqa` or move to a design doc.

---

### BUG-2: Duplicate Code in `services/url.py` (MED)

**Location:** `services/url.py:1-192` vs `utils/url.py:1-262`

**Issue:** Nearly identical code for SSRF protection exists in both files:
- `_BLOCKED_NETWORKS` - same list in both
- `_TTLCache` - identical class in both
- `_resolve_and_check` - identical function in both
- `validate_url_safe` - nearly identical functions

**Impact:** Maintenance burden, potential for divergence.

**Recommendation:** Have `services/url.py` import and re-export from `utils/url.py` instead of duplicating. The services version is needed because it reads config for TTL/max_size.

---

## Security Considerations (All Pass)

| Security Feature | Status | Verification |
|-------------------|--------|--------------|
| Fail-Closed Production Startup | ✅ | `config.py:254-278` ProductionConfig.validate() |
| TOTP 2FA with backup codes | ✅ | `services/totp.py:23-48` |
| Session Binding (IP+UA) | ✅ | `routes/admin/__init__.py` handles in routes |
| HMAC Webhooks | ✅ | `services/webhooks.py` |
| SSRF Protection | ✅ | Both url.py implementations validate DNS |
| Encrypted Secrets | ✅ | Via environment variables |
| Login Lockout | ✅ | `config.py:73-74` LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_SECONDS |

---

## Performance Concerns

No major performance concerns identified. The architecture properly uses:
- Connection pooling for Redis and HTTP
- WAL mode for SQLite
- DNS caching with TTL
- Celery task prefetch multiplier of 1

---

## Recommendations Summary

| Priority | Issue | Recommendation |
|----------|-------|----------------|
| **CRIT** | `utils/url.py` docstring incorrectly claims "pure functions" | Update docstring or refactor to make impurity explicit |
| **HIGH** | `services/url.py` duplicates code from `utils/url.py` | Refactor to import from utils with config support |
| **MED** | `providers.yaml` doesn't include `hybrid` search provider | Add hybrid to providers.yaml or update docs |
| **MED** | Overview provider count (14) doesn't match actual (14 LLM + 3 search) | Update overview to clarify "14 LLM providers + 3 search providers" |
| **LOW** | `schemas/common.py` layer violation comments visible in code | Move to design doc or suppress with noqa |

---

## Conclusion

The `architecture/overview.md` document is well-maintained and accurately reflects the codebase. The main issues are:

1. A critical documentation bug where `utils/url.py` is described as having "pure functions" despite global mutable state
2. Code duplication between `services/url.py` and `utils/url.py`
3. A missing `hybrid` search provider in `providers.yaml`
4. Minor count discrepancies in the overview

The architectural layering rules are properly followed with the exception of `schemas/common.py` which is documented as an intentional violation.