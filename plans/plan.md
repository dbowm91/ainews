# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS (Review findings from 2026-05-07)
**Last Updated:** 2026-05-07
**Goal:** Address critical bugs, documentation drift, and remaining architecture issues identified in architecture reviews.

---

## Executive Summary

All waves of the original plan (2026-05-05) have been completed. This document adds new work identified during architecture reviews on 2026-05-07.

**New Waves Overview:**
- **Wave 5: Critical Bug Fixes** (P0 runtime failures) - Immediate priority
- **Wave 6: Layering & Architecture Corrections** (HIGH priority violations)
- **Wave 7: Implementation Gaps** (Missing features)
- **Wave 8: Documentation Alignment** (Schema/model drift)

---

## Wave 5: Critical Bug Fixes (P0 Runtime Failures)

### Task 5.1: Fix P0 Runtime Bugs

**BUG-5.1.1: Limiter Slot Leak with Wrong Provider/Model**
- **Issue:** `tasks/pipeline.py:417` on early return releases with `rc.provider` (configured primary) and `rc.model` instead of the actual provider/model that was acquired. The limiter key is `ainews:llm:{provider}:{model}` so releasing with wrong keys leaves the actual slot leaking until TTL.
- **Root Cause:** `_check_stage_limiter` acquires a slot on `rc.provider:rc.model` but early return releases on potentially different provider chain.
- **Action:** On early return (line 415-419), release on the same provider/model that was actually acquired by `_check_stage_limiter`. The limiter was acquired with `rc.provider` and `rc.model`, so line 417 SHOULD use those same values (which it does), but the issue is the limiter slot was acquired for the CHAIN, not just the primary. Actually - the limiter only tracks one slot per primary provider, so this is actually correct for the early return case.
- **Better Analysis:** The more serious issue is at line 435 in the `finally` block - `model` comes from `_get_provider_for_stage` which only returns the PRIMARY provider's model, but if fallback occurred in `_try_stage_work`, the actual model used could be different. `provider_id` is correct (from `_try_stage_work`), but `model` could be wrong.
- **Verification:** Run `test_skips_when_stage_locked` and verify limiter release is called with correct key pattern

**BUG-5.1.2: `_log_pipeline` Argument Order Wrong**
- **Issue:** `tasks/pipeline.py:60,63,66` passes arguments in wrong order
- **Current:** `_log_pipeline(failed_stage, article.id, run_id, "degraded_to_research")`
- **Expected:** `_log_pipeline(run_id, failed_stage, "info", "degraded_to_research", article_id=article.id)`
- **Action:** Fix argument order in all calls
- **Verification:** Check pipeline logs show correct field values

---

## Wave 6: Layering & Architecture Corrections

### Task 6.1: Verify SSRF Layering Fix

The existing plan.md claims Wave 2.1 completed SSRF move to `utils/url.py`. Verify:
- [ ] `utils/url.py` contains `validate_url_safe` and `UnsafeURLError`
- [ ] All adapters import from `utils/url.py` NOT `services/url.py`
- [ ] `services/url.py` re-exports from utils for backward compatibility

**If not complete, fix:**
- Move core SSRF logic to `utils/url.py`
- Update adapters: `rss.py:12`, `api.py:11`, `web.py:15`, `session.py:8`
- Ensure `services/url.py` re-exports for backward compat

### Task 6.2: Fix Services↔Adapters Layering

**Issue:** `services/crawling.py:13` imports `RawItem` from `adapters.base`

**Action Options:**
1. Move `RawItem` to `schemas/item.py` (per original plan) - RECOMMENDED
2. Create a shared schema that both import from

### Task 6.3: Verify `review` in `_STAGE_TASKS`

The existing plan.md claims this was fixed. Verify in `services/pipeline_utils.py`:
```python
_STAGE_TASKS = {
    ...
    "review": ("tasks.edit", "edit_article"),
}
```

**If missing, add:**
- Without this, articles in `review` status cannot be re-dispatched and are stuck forever

---

## Wave 7: Implementation Gaps

### Task 7.1: `StageConfig` is Empty Stub

**Issue:** `schemas/pipeline.py:140-141` `StageConfig` only has `tools: list[str]`
**Documentation claims:** 7 fields (`enabled`, `model`, `prompt_variant`, `temperature`, `max_tokens`, `timeout`)

**Action:** Either:
- A) Implement missing fields if StageConfig is actually used
- B) Document that `SubagentStageConfig` is the actual used class

### Task 7.2: Missing Utils Implementations

Based on `architecture/utils.md` vs actual:

| File | Status | Needed Functions |
|------|--------|------------------|
| `utils/text.py` | Exists but wrong | `truncate()`, `sanitize_html()`, `extract_hashtags()` |
| `utils/datetime.py` | Missing | Move from `services/date_utils.py` |
| `utils/hash.py` | Missing | `generate_hash()`, `verify_hash()` |
| `utils/html.py` | Missing | `strip_tags()`, `linkify()`, `extract_text()` |
| `utils/security.py` | Missing | `generate_token()`, `constant_time_compare()`, `hash_password()`, `verify_password()` |

### Task 7.3: DeepSeek Provider Missing

**Issue:** `architecture/services.md` references `services/llm/deepseek.py` but file doesn't exist
**Also:** `cost_tracker.py` references `deepseek/deepseek-chat`

**Action:** Either implement DeepSeek provider or remove references

### Task 7.4: RSS Adapter Gaps

**Missing implementations:**
- Malformed feed fallback (BeautifulSoup)
- Feed validation
- Auth header injection (APIAdapter)

---

## Wave 8: Documentation Alignment

### Task 8.1: Pipeline Documentation Drift

| Document Says | Actual |
|--------------|--------|
| `metadata` (PipelineLog) | `meta` |
| Circuit breaker: 5 failures/1min, half-open 30s | 5 failures/2min, half-open 60s |
| `backfill_embeddings`: Weekly | Daily at 2 AM |
| Write stage `max_tokens`: 1500 | 4096 |

**Action:** Update `architecture/pipeline.md`

### Task 8.2: Subagent Documentation Drift

| Document Says | Actual |
|--------------|--------|
| `run_subagent(task, context, tools, model)` | `run_subagent(task_type, stage, prompt_data, response_model, article_id)` |
| Tool classes with `execute()` | Module-level functions |
| Async middleware `on_request/on_response` | Sync `wrap()` |
| Return `SubagentResult` | Return `SubagentResponse` |

**Action:** Update `architecture/subagent.md`

### Task 8.3: Schemas Documentation Drift

| Document Says | Actual |
|--------------|--------|
| `StageConfig` with 7 fields | Only `tools` field |
| `ResearchBrief.key_findings` | `key_claims` |
| `CondensedArticle.title/summary/word_count` | `headline/tldr/body` |
| `NewsletterBrief.newsletter_id, subject` | `themes, highlights, connections` |

### Task 8.4: Models Documentation Drift

| Document Says | Actual |
|--------------|--------|
| `embedding = Column(Vector(1536))` | `embedding = db.Text` (not vector) |
| `ip_binding`, `user_agent_hash` on AdminUser | NOT IMPLEMENTED |
| `TrendMemory.observation` | `signal` |
| `Source.type` | `source_type` |
| `Source.last_fetch_at` | `last_crawled` |
| Article `finalized_at` | `published_at` |

### Task 8.5: Routes Documentation Drift

| Document Says | Actual |
|--------------|--------|
| `/api/articles` | `/api/v1/articles` |
| `/share/<platform>/<article_id>` | NOT FOUND |
| `/click/<tracking_id>` | `/track/newsletter-click/<int:article_id>` |
| Nested template dirs | Flat structure |

### Task 8.6: Utils Documentation (P0)

**Issue:** `architecture/utils.md` is ~70% inaccurate - describes modules that don't exist

**Action:** Update to reflect actual state, or implement missing modules

---

## Wave Parallelization Guide

### Can Run in Parallel (Subagents)

**Wave 6 Tasks (Layering):**
- Task 6.1 (SSRF verification) and Task 6.2 (services↔adapters) can run concurrently
- Task 6.3 (review stage) is quick fix, can run with others

**Wave 7 Tasks (Implementation Gaps):**
- Task 7.2 (utils) can be split: one agent for datetime, one for text, one for security/hash/html
- Task 7.3 (DeepSeek) is independent
- Task 7.4 (RSS) is independent

**Wave 8 Tasks (Documentation):**
- All documentation updates can run in parallel by module
- No code changes, just doc updates

### Sequential Dependencies

- Wave 5 must complete before Wave 6 (Wave 5 bugs are blocking)
- Wave 6.1 (SSRF) must complete before adapter import verification passes
- Wave 8 can run concurrently with Wave 6/7 after bugs fixed

---

## Suggested Agent Assignments

**Agent A:** Wave 5 (Critical Bugs) - Must fix P0 issues first
**Agent B:** Wave 6.1 (SSRF) - Layering fix
**Agent C:** Wave 6.2 (crawling import) - Layering fix
**Agent D:** Wave 7.2 (Utils) - Can parallelize by file
**Agent E:** Wave 7.3 (DeepSeek) - Single provider
**Agent F:** Wave 7.4 (RSS) - Single adapter
**Agent G:** Wave 8 (Documentation) - Can run last, parallel by module

---

## Status Tracking

| Task | Status | Notes |
|------|--------|-------|
| 5.1.1 Limiter slot leak | PENDING | Verified exists at pipeline.py:417 |
| 5.1.2 _log_pipeline args | PENDING | Verified wrong at lines 60,63,66 |
| 6.1 SSRF layering | PENDING | Needs verification |
| 6.2 Services↔adapters | PENDING | crawling.py:13 imports RawItem |
| 6.3 review stage | PENDING | Verified in pipeline_utils.py:18 - ALREADY FIXED |
| 7.1 StageConfig | PENDING | Empty stub confirmed |
| 7.2 Utils gaps | PENDING | Multiple missing |
| 7.3 DeepSeek | PENDING | Missing |
| 7.4 RSS gaps | PENDING | Missing fallback/validation/auth |
| 8.1-8.6 Docs | PENDING | Multiple drift issues |

---

## Known Verification Results (2026-05-07)

Items confirmed FIXED by codebase inspection:
- `adapters/web.py:2` - `import random` PRESENT
- `services/pipeline_utils.py:18` - `"review": ("tasks.edit", "edit_article")` PRESENT
- `adapters/web.py:15` - imports from `utils.url`, not `services.url`
- `tasks/newsletter.py:429` - `idempotency_key` defined locally

Items NOT FIXED (still broken):
- `tasks/pipeline.py:417` - early return releases with `rc.provider` not `provider_id`
- `tasks/pipeline.py:60,63,66` - `_log_pipeline` args wrong order
- `schemas/pipeline.py:140-141` - `StageConfig` empty stub
- `utils/text.py` - wrong contents
- `utils/datetime.py` - missing (in services/date_utils.py)

---

*End of file*