# AINews Consolidated Implementation Plan

**Status:** COMPLETED
**Last Updated:** 2026-05-09
**Goal:** All items from architecture review completed.

---

## Executive Summary

This plan consolidates action items from 9 architecture review documents. All items have been verified as completed in code or properly deferred with documentation updates.

### Priority Summary

| Priority | Count | Items |
|----------|-------|-------|
| HIGH | 10 | Critical bugs that affect functionality |
| MEDIUM | 18 | Documentation fixes, improvements |
| LOW | 14 | Cleanup, minor documentation fixes |

---

## Progress Tracking

All items marked COMPLETED were verified against the codebase. Items marked N/A were decisions that required removing from documentation or confirming something was already correct.

| Item | Status | Completed Date | Notes |
|------|--------|----------------|-------|
| BUG-1.1 | COMPLETED | 2026-05-09 | Fixed in tasks/newsletter.py - idempotency_key defined in scope |
| BUG-1.3 | COMPLETED | 2026-05-09 | Added SELECTING, SELECTED, WRITTEN to PipelineStatus and VALID_TRANSITIONS |
| BUG-1.5 | COMPLETED | 2026-05-09 | _try_stage_work now returns actual model used; limiter.release uses provider_id |
| BUG-1.6 | COMPLETED | 2026-05-09 | Code already handled correctly with 'if provider_id:' guard |
| BUG-1.7 | COMPLETED | 2026-05-09 | Removed redirect counter reset on success in SSRFSafeRedirectHandler |
| BUG-1.8 | COMPLETED | 2026-05-09 | Added logger.warning for date parsing failures in WebAdapter |
| BUG-1.9 | COMPLETED | 2026-05-09 | Split trafilatura exception handling - ImportError separate from ValueError/AttributeError |
| BUG-1.10 | COMPLETED | 2026-05-09 | Added api_tokens_bp registration in app.py |
| BUG-1.11 | COMPLETED | 2026-05-09 | require_auth now returns JSON 401 for /api* routes |
| BUG-1.13 | COMPLETED | 2026-05-09 | Removed duplicate import of load_providers_config |
| TASK-2.2 | COMPLETED | 2026-05-09 | Documented missing endpoints in architecture/routes.md |
| TASK-2.3 | COMPLETED | 2026-05-09 | MemoryConfig documentation updated to match actual code |
| TASK-2.4 | COMPLETED | 2026-05-09 | NewsletterConfig documentation updated - no enable_topic_newsletters or batch_size |
| TASK-2.5 | COMPLETED | 2026-05-09 | SourceConfig adapter_config → config: dict[str, Any] |
| TASK-2.6 | COMPLETED | 2026-05-09 | Removed non-existent version field from documentation |
| TASK-2.8 | COMPLETED | 2026-05-09 | SelectionResult confidence - documented as str with pattern |
| TASK-2.9 | COMPLETED | 2026-05-09 | RelatedArticle/ExternalSource field names corrected |
| TASK-2.10 | COMPLETED | 2026-05-09 | DirectQuote: quote vs text, attribution vs source - docs updated |
| TASK-2.11 | COMPLETED | 2026-05-09 | NewsletterArticle: headline vs title, tags vs key_points - docs updated |
| TASK-2.12 | COMPLETED | 2026-05-09 | Cleaned up __all__ exports in utils/url.py |
| TASK-2.13 | COMPLETED | 2026-05-09 | Global mutable DNS cache documented in AGENTS.md |
| TASK-2.14 | N/A | - | adapter_config on Source model never implemented - removed from docs |
| TASK-2.15 | COMPLETED | 2026-05-09 | Decision: No GIN index - embedding stored as text for caching |
| TASK-2.16 | COMPLETED | 2026-05-09 | Decision: IP/User-Agent binding IS implemented in require_auth decorator |
| TASK-2.17 | COMPLETED | 2026-05-09 | Pipeline status values updated in documentation |
| TASK-2.18 | COMPLETED | 2026-05-09 | API adapter lacks pagination - documented in adapters.md |
| TASK-2.19 | COMPLETED | 2026-05-09 | WebAdapter uses listing_url (singular) - docs updated |
| TASK-2.20 | COMPLETED | 2026-05-09 | BaseLLMProvider interface updated to match actual code |
| TASK-2.21 | COMPLETED | 2026-05-09 | limiter.release uses provider_id (actual) not rc.provider (configured) |
| TASK-2.22 | COMPLETED | 2026-05-09 | Subagent tool mapping table updated with actual canonical names |
| TASK-2.23 | COMPLETED | 2026-05-09 | Chain config from pipeline.yaml documented with SubagentChainConfig schema |
| TASK-3.1 | COMPLETED | 2026-05-09 | Stage vs Status glossary added to pipeline.md |
| TASK-3.2 | COMPLETED | 2026-05-09 | Actual stage flow documented (selection integrated into research) |
| TASK-3.7 | COMPLETED | 2026-05-09 | Blueprint structure documented (admin_bp vs admin_api_bp) |
| TASK-3.15 | COMPLETED | 2026-05-09 | Two-tier retry system documented |
| TASK-3.16 | COMPLETED | 2026-05-09 | Degradation behavior for disabled stages documented |
| TASK-4.2 | COMPLETED | 2026-05-09 | __all__ exports cleaned up in utils/url.py |
| TASK-4.4 | COMPLETED | 2026-05-09 | YAML config examples updated to use listing_url |
| TASK-4.8 | N/A | - | _finalize_subagent_result IS used (called at runner.py:498) - not dead code |
| TASK-4.10 | N/A | - | tasks→services import is allowed (tasks are orchestrators) - acceptable |

---

## Verified Non-Bugs (Plan Corrections)

The following items in the original plan were INCORRECTLY marked as bugs:
- **BUG-1.2**: `redis_client` IS accessible in finally block - NOT A BUG
- **BUG-1.12**: Slot leak pattern is correct - NOT A BUG (already noted in plan)
- **TASK-2.1**: API path prefix is correctly documented in AGENTS.md - NO FIX NEEDED
- **TASK-2.7**: `impact_summary` field EXISTS in SelectionResult - NO FIX NEEDED

---

## Key Files for Reference

- `tasks/pipeline.py` - Pipeline orchestration, stage execution, limiter release
- `tasks/newsletter.py` - Newsletter generation, locking, idempotency
- `constants.py` - VALID_TRANSITIONS, PipelineStatus enum
- `adapters/session.py` - SSRFSafeRedirectHandler
- `adapters/web.py` - WebAdapter, date parsing, trafilatura
- `routes/admin/__init__.py` - require_auth decorator
- `routes/admin/api_tokens.py` - api_tokens_bp (now registered)
- `services/llm/__init__.py` - Provider config, no longer has duplicate import
- `schemas/pipeline.py` - Config schemas
- `architecture/` - Architecture documentation

---

*End of file*
