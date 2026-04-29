# Implementation Plan - Consolidated

**Date:** April 29, 2026
**Status:** IN PROGRESS - Pending Items from All Plans
**Total Items:** 85+ completed + ~65 pending items across all waves
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## Prior Plan Status

### Already Completed (plan.md)
All waves 1-8 completed April 29, 2026:
- Wave 1-8: All 85+ actionable items implemented or verified as not needed
- Deferred: Item 77 (Type Stub Installation), Items 110-111 (Batch API/Cost-tier)

---

## CRITICAL ISSUES (Appearing Across Multiple Plans)

> **These issues appear in plan2.md (P0-1, P0-2), plan3.md (S1, S2), plan4.md (Issues 1-2), and plan7.md (P2).** They must be fixed first before any other work.

### FAIL-OPEN BUG: Redis Lock Fail-Closed Violation

| Location | Issue | Fix |
|----------|-------|-----|
| `tasks/pipeline.py:108-117` | `_acquire_stage_lock` returns `True` on RedisError (allows concurrent stage execution) | Return `False` (fail-closed) |
| `tasks/newsletter.py:414-417` | Sets `lock_status = 2` on Redis error (pretends lock acquired) | Raise `RedisError` instead |

**Reference Pattern:** `services/redis_utils.py:31-48` already implements correct fail-closed behavior:
```python
except redis.exceptions.RedisError:
    logger.error("Redis unavailable for publish_scheduled lock, refusing to proceed")
    raise
```

**Testing:** `tests/test_pipeline_e2e.py` needs update to verify fail-closed behavior (test with Redis unavailable).

---

## WAVE 1: Critical Bugs & Security (Week 1)

### Phase 1.1: Fail-Open Bugs (CRITICAL)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-P1 | Fix fail-open stage lock in pipeline | `tasks/pipeline.py:108-117` | 15 min |
| W1-P2 | Fix fail-open newsletter lock | `tasks/newsletter.py:414-417` | 15 min |

### Phase 1.2: AuthError Fix (MEDIUM - Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-P3 | Fix AuthError "transient" log message | `tasks/pipeline.py:187` | 15 min |

**Details:** AuthError is logged as "transient error" but upstream (`services/llm/base.py:148`) it raises immediately without retry. The log message is misleading - should log at warning level with "non-retryable auth error" or similar.

### Phase 1.3: Version Creation Order (CRITICAL - Plan5/Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-P4 | Fix Version Creation Order in Edit Pipeline | `tasks/edit.py:332-335` | 1 hour |

**Details:** `create_article_version()` called AFTER modifying `article.final_article`, capturing NEW state instead of OLD. Create BEFORE modification to capture previous state for rollback.

### Phase 1.4: Session Fixation Prevention (HIGH - Plan3)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-S3 | Session Fixation Prevention | `routes/admin/auth.py:55-58` | 1 hour |

**Issue:** `session.clear()` doesn't regenerate session ID (potential session fixation).

**Options:**
- **Option A:** Flask-Session with server-side sessions (requires Redis)
- **Option B:** Delete old cookie in response (simpler, no new deps)
- **Option C:** Document and accept current risk

### Phase 1.5: Webhook Secret Decryption (HIGH - Plan2)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-P5 | Webhook Secret Decryption Silent Failure | `services/webhooks.py:325-340` | 1 hour |

**Details:** Returns empty string on decryption failure in two places, silently breaking auth.

---

## WAVE 2: Pipeline & LLM Provider Improvements (Week 2)

### Phase 2.1: State Machine Consistency (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-P1 | Use `_transition_article_status()` Consistently | `tasks/write.py:134`, `tasks/research.py:225` | 1 hour |

**Details:** Direct assignments bypass validation and audit logging. Use `_transition_article_status()` instead. Note: `_dispatch_next()` at lines 131/222 handles REVIEW routing - use it or `_transition_article_status()` for proper state machine compliance.

### Phase 2.2: Missing Logging (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-P2 | Add `_log_pipeline()` Before Early Return at Quality Gate | `tasks/research.py:222-223` | 30 min |

**Details:** Quality gate review routing returns early without `_log_pipeline()` call. The logging exists at lines 232-240 for success path but not at early return.

### Phase 2.3: Env Var Resolution (Plan5/Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-P3 | Fix Missing Env Var Resolution in LLMProvidersConfig | `schemas/llm.py:58-59` | 2 hours |

**Details:** `_load_providers_config_from_file()` does NOT call `resolve_env_vars()` on raw YAML. Env var placeholders like `${MINIMAX_API_KEY}` may not resolve correctly.

### Phase 2.4: Per-Stage Circuit Breaking (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-L1 | Implement Per-Stage Circuit Breaking | `services/llm/__init__.py:62-66` | 2 hours |

**Details:** Circuit keyed by provider+model only, so failures in research block ALL stages using that provider. Should be keyed by stage too.

### Phase 2.5: Retry-After Header (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-L2 | Add Retry-After Header Support | `services/llm/base.py:155-167` | 1 hour |

**Details:** Exponential backoff ignores `Retry-After` header from rate limit responses.

### Phase 2.6: Configurable Limits (Plan8)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-P4 | Make `_MAX_STAGE_FAILURES` Configurable | `services/pipeline_failure.py:12` + `constants.py` + `config.py` | 30 min |

**Pattern:** Follow `MAX_STAGE_RETRIES` implementation in constants.py + config.py.

---

## WAVE 3: Subagent & Search Improvements (Week 3)

### Phase 3.1: Subagent Optimizations (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W3-S1 | Move Provider Fetch Outside Retry Loop | `services/subagent.py:936-938` | 30 min |
| W3-S2 | Make max_iterations Configurable | `services/subagent.py:722` | 30 min |
| W3-S3 | Move random Import to Module Level | `services/subagent.py:563, 737, 764, 959` | 30 min |

### Phase 3.2: Search & Analytics (Plan5/Plan2)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W3-P1 | Search Analytics Query Fix | `routes/admin/api/search.py:20` | 1 hour |
| W3-P2 | Missing Tag Feed Cache | `routes/public/feeds.py:172` | 2 hours |

### Phase 3.3: N+1 Query Prevention (Plan2)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W3-P3 | N+1 Query Future-Proofing in find_duplicate_titles | `services/article.py:335` | 1 hour |

---

## WAVE 4: Email & Newsletter Improvements (Week 4)

### Phase 4.1: Email Standards (Plan5)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W4-P1 | Email Plain-Text Alternative Missing | `services/email.py:187` | 2 hours |
| W4-P2 | List-Unsubscribe Header Missing (RFC 8058) | `services/email.py` | 1 hour |

### Phase 4.2: Newsletter Subject (Plan5)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W4-P3 | Newsletter Subject Line Generation | `services/newsletter.py:175-189` | 3-4 hours |

**Details:** Subjects are hardcoded ("Top Stories") not AI-generated from content.

### Phase 4.3: Source CRUD API (Plan5)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W4-P4 | Source CRUD API Missing | `routes/admin/api/` | 4 hours |

---

## WAVE 5: Frontend Improvements (Week 5-6)

### Phase 5.1: Accessibility (HIGH - Plan6)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| F2 | RSS Link Icon - replace `[rss]` text with SVG | `templates/base.html:47` | 1 hour |
| F3 | Theme Toggle Accessibility - missing aria-pressed | `templates/partials/theme_toggle.html` | 0.5 hours |
| F4 | External Link Indicators - verify SVG icon works correctly | `templates/partials/article_card.html:56` | 0.5 hours |
| F9 | Pipeline Bar Accessibility - missing role="progressbar" | `templates/admin/dashboard.html:23-37` | 1 hour |

**Note:** External link indicator already has SVG icon - verify in testing that it's visible and accessible.

### Phase 5.2: Mobile & UX (HIGH - Plan6)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| F12 | Mobile Nav Close Behavior - verify checkbox pattern works | `templates/base.html:38-49` | 0.5 hours |
| F1 | Search Visibility on Mobile | `static/css/utilities.css:69` | 2 hours |
| F13 | Horizontal Scroll Fade Indicators | `static/css/layout.css:212-217` | 1.5 hours |

**Note:** Mobile nav uses checkbox toggle pattern - verify it works correctly for user flow.

### Phase 5.3: Visual Consistency (MEDIUM - Plan6)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| F14 | Animation Consistency - missing transition | `static/css/components.css:292-312` | 0.5 hours |
| F8 | Sticky Table Header Visibility | `static/css/pages.css:510-515` | 0.5 hours |
| F10 | Error State Contrast | `static/css/components.css` | 0.5 hours |
| F15 | Focus Outline Standardization | Multiple CSS files | 1 hour |
| F18 | Empty State Improvements | `templates/partials/feed.html:62-76` | 1.5 hours |

### Phase 5.4: New Features (MEDIUM - Plan6)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| F5 | Bookmarking System | Client-side, localStorage | 4 hours |
| F6 | Article Read State Tracking | Client-side, localStorage | 3 hours |
| F11 | Share Counts Display | `models.py:239-258` | 2 hours |
| F7 | Date Grouping in Feed | `templates/partials/feed.html` | 3 hours |

### Phase 5.5: Loading & Preview (LOW - Plan6)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| F16 | Bulk Operations Loading Feedback | `templates/admin/partials/articles_table.html:7-35` | 2 hours |
| F17 | Hover Previews | No existing implementation | 6 hours |

---

## WAVE 6: Observability & Metrics (Week 6-7)

### Phase 6.1: Structured Reason Labels (Plan8)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W6-P1 | Structured Reason Labels for Degradation | `services/pipeline_degradation.py:88-93` | 30 min |

**Details:** Add structured reason codes like `"per_stage_retries_exceeded"` instead of freeform log_message.

### Phase 6.2: Pipeline Metrics (Plan8)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W6-P2 | E2E Pipeline Latency Histogram | `services/pipeline_degradation.py` or `tasks/edit.py` | 1 hour |
| W6-P3 | Pipeline Backlog API | New route `/admin/api/pipeline/backlog` | 1 hour |
| W6-P4 | Queue Depth via Celery Inspect | 1 route | 30 min |

### Phase 6.3: Subagent Context Caching (Plan8)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W6-P5 | Subagent Context Caching | `services/subagent.py` + `services/cache.py` | 2 hours |

**Details:** `_get_topic_note()`, `_get_related_articles()`, `_get_trend_memory()` always hit DB/Redis. Wrap with `ResponseCache` using 5-15 min TTL.

### Phase 6.4: Low-Priority Polish (Plan8)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W6-P6 | Retry Jitter at Stage Limiter | `tasks/pipeline.py:154-160` | 30 min |
| W6-P7 | Stuck Article Detection | Backlog route | 30 min |

---

## WAVE 7: Documentation (Week 7-8)

### Phase 7.1: Operations & Troubleshooting (HIGH - Plan9)

| Item | Description | Target | Current→Target |
|------|-------------|---------|-----------------|
| D1 | Expand Operations Guide | `docs/operations.md` | 155→300+ lines |
| D2 | Expand Troubleshooting Guide | `docs/troubleshooting.md` | 441→550+ lines |

### Phase 7.2: Configuration & Deployment (MEDIUM - Plan9)

| Item | Description | Target | Current→Target |
|------|-------------|---------|-----------------|
| D3 | Expand Configuration Guide | `docs/configuration.md` | 396→500+ lines |
| D4 | Expand Deployment Guide | `docs/deployment.md` | 789→820+ lines |
| D5 | Expand Pipeline Guide | `docs/pipeline.md` | 109→180+ lines |

### Phase 7.3: Integration Guides (MEDIUM - Plan9)

| Item | Description | Target | Current→Target |
|------|-------------|---------|-----------------|
| D6 | Expand Webhook Guide | `docs/webhooks.md` | 110→150+ lines |
| D6b | Expand Subagent Guide | `docs/subagent.md` | 224→260+ lines |
| D7 | Expand Trend Memory Guide | `docs/trend-memory.md` | 218→250+ lines |
| D8 | Add SLA Metrics Guide | `docs/sla-metrics.md` (NEW) | NEW |

### Phase 7.4: Supplementary (LOW - Plan9)

| Item | Description | Target | Current→Target |
|------|-------------|---------|-----------------|
| D9 | Add Cost Alerting Guide | `docs/cost-tracking.md` | 174→210+ lines |
| D10 | Add API Workflow Guide | `docs/api.md` | 646→720+ lines |

---

## WAVE 8: Backend Improvements (Week 8-9)

### Phase 8.1: Config Validation (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W8-P1 | Improve ValidationError Handling | `services/config_unified.py:194-229` | 1 hour |
| W8-P2 | Add Source Config Type Validation | `schemas/source.py:109` | 1 hour |

### Phase 8.2: Code Quality (Plan7)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W8-P3 | Add Retry Count Indexes | `models.py` | 1 hour |
| W8-P4 | Investigate Circuit Breaker Recovery Timeout | `services/llm/__init__.py` | 1 hour |
| W8-P5 | Consider Provider-Level Model Fallback | Config | 2 hours |

### Phase 8.3: Performance (Plan5/Plan2)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W8-P6 | PRAGMA optimize Scheduling | SQLite config | 1 hour |
| W8-P7 | Redis Connection Pool Metrics | Prometheus metrics | 2 hours |
| W8-P8 | DNS Timeout Missing future.cancel() | `services/url.py:143-149` | 30 min |
| W8-P9 | Redundant DB Query in Dashboard | `routes/admin/dashboard.py:131-132` | 30 min |

### Phase 8.4: Subscriber & Future (Plan5)

| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W8-P10 | Subscriber Sunset Policy | - | 2 hours |
| W8-P11 | Adaptive Tool Selection for Subagent | `services/subagent.py` | 4 hours |

---

## DEFERRED ITEMS

| Item | Description | Reason |
|------|-------------|--------|
| W8-P12 | LLM Content HTML Sanitization (`bleach` library) | 3 hours effort |
| W8-P13 | Test Coverage Gaps (audit.py, search.py, pipeline_utils.py) | 4-6 hours effort |
| Item 77 | Type Stub Installation | Low priority |
| Items 110-111 | Batch API integration, Cost-tier model routing | 2-3 weeks each |

---

## CSP Improvements (Plan3)

### HIGH Priority
| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W1-S4 | CSP - Remove data: from img-src | `app.py:114` | 30 min |

### MEDIUM Priority
| Item | Description | Location | Est. Effort |
|------|-------------|----------|-------------|
| W2-S5 | CSP - Add Missing Directives (frame-ancestors, upgrade-insecure-requests) | `app.py:110-133` | 1 hour |
| W2-S6 | Input Validation - Category/Status | `routes/public/feeds.py`, `routes/admin/articles.py` | 1 hour |

### LOW - Verified Secure (No changes needed)
| Item | Status | Notes |
|------|--------|-------|
| S7-S16 | VERIFIED SECURE | Redis Lua Script, Dynamic Import Allowlist, LLM Prompt Injection, SQL Injection, Content Length Limits, SSRF Protection, HMAC Task Signing, Password Hashing, Webhook Encryption, CSP Script Nonce |

---

## Dependencies & Implementation Notes

### Critical Dependencies
1. **Fail-open bugs (W1-P1, W1-P2)** must be fixed before any pipeline work
2. **Env var resolution (W2-P3)** allows removing redundant adapter code after fix
3. **Version creation order (W1-P4)** affects rollback code - verify before changing

### Parallelization Guidance
- **Wave 1:** Phase 1.1 fixes (P1, P2) independent; Phase 1.5 (P5) standalone
- **Wave 2:** Phase 2.1-2.2 can parallel (different files); Phase 2.3-2.5 can parallel
- **Wave 3:** Phase 3.1 S1-S3 sequential (same file); P2 standalone
- **Wave 5:** F5/F6 can share localStorage infrastructure
- **Wave 7:** D1/D2 independent; D3/D4/D5 independent; D6/D7/D8 independent

### Verification Commands
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python -m mypy . --exclude .venv
```
