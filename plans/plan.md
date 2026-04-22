# Implementation Plan — Deferred Items

**Created:** April 22, 2026
**Last Updated:** April 22, 2026
**Status:** OPEN - Deferred items remain

---

## Executive Summary

AINews implementation is complete. All implementation waves (1-7) have been completed and verified. The following items remain deferred due to infrastructure requirements or complexity.

---

## Deferred Items

| Item | Source | Reason |
|------|--------|--------|
| E.1: Celery Task Input Schema Validation | plan4.md | Add Pydantic schemas for task entry points — larger refactor |
| E.2: Celery Task Event Streaming | plan.md | Requires significant infrastructure work (celery.events.RealityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates) |
| E.3: Structured Tool Result Format | plan4.md | Refactor tool results from raw strings to JSON — makes injection harder |
| E.4: Celery Worker Network Isolation | plan4.md | Run workers on isolated network segment |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | Requires identifying all article state transitions |
| 1.1: CI/CD Pipeline | plan5.md | Requires project to be hosted on platform with GitHub Actions or equivalent |
| 6.2: EXPLAIN ANALYZE Script | plan5.md | Low priority, informational |

---

## Completed Implementation Summary

All implementation waves (1-7) have been completed:

### Wave 1: Quick Security Fixes ✅
- DNS Cache TTL reduced to 60s
- Session fixation prevention (session.regenerate_id())
- Subagent chain escaping (_escape_prompt_data)
- Token validation for unsubscribe/verify
- Tool result sanitization (esc_xml_text)
- short_id regex validation
- Failed login audit logging

### Wave 2: Webhook & CSRF Fixes ✅
- Webhook CSRF validation on PUT/DELETE
- HTMX CSRF pattern (hx-headers)

### Wave 3: Search Provider SSRF Validation ✅
- validate_url_safe() added to searxng and google search providers

### Wave 4: Larger Security Infrastructure ✅
- Celery Task HMAC Signing (applied to run_all_sources, generate_daily_newsletters, select_article)
- Redis AUTH support (REDIS_PASSWORD env var)
- Webhook Replay Protection (timestamp in signature)

### Wave 5: Performance Improvements ✅
- ResponseCache L1 Read Eviction (sampled stale eviction)
- ConfigCache L1 Eviction (time-based)
- Related Articles SQL Scoring (tag matching pushed to SQL)
- Newsletter Streaming (generator-based, not materializing full list)
- Search Query Async Logging (threading-based fire-and-forget)
- Sitemap Pagination (SITEMAP_LIMIT config)
- created_at Index (migration 022_articles_created_at_index)

### Wave 6: Infrastructure & Code Quality ✅
- E501 Line Length (ruff configured with line-length=200)

### Wave 7: Follow-up Security & Webhook Improvements ✅
- Webhook trigger_event Integration
- ModelLimiter SoftTimeout Handler
- Webhook Secret Encryption
- Webhook Idempotency Key
- Category CSS Escaping
- Webhook Attempt Tracking
- Bulk Audit Logging
- Config Cache API Key Isolation

---

## Critical Implementation Notes

### Session Security
- `session.regenerate_id()` must be called AFTER `session.clear()` but BEFORE setting any session data
- CSRF tokens stored by Flask-WTF are in a separate signed cookie, not affected by `session.clear()`

### Celery Task HMAC Signing
- Applied to orchestrator tasks: `run_all_sources`, `generate_daily_newsletters`, `select_article`
- Internal tasks (crawl_source, send_single_email) called via `.s()` signatures don't need additional verification
- Tasks called by Celery Beat that take no arguments (cleanup, publish_scheduled) don't require HMAC signing

### Newsletter Memory Management
- Subscriber iteration uses generator pattern with yield_per(500) to avoid materializing full list
- Count obtained via separate query for progress reporting

---

## Database Notes

- SQLite WAL mode configured in `app.py:153-159`
- All new SQL filters must be verified with `EXPLAIN` to confirm index usage
- Cascade rules enforced at SQLAlchemy model level (SQLite doesn't support ALTER TABLE for FK)
- Test Jaccard similarity threshold with real article titles after pre-filtering changes
- Migration 022 adds `ix_articles_created_at` index for duplicate detection queries

---

## Rollback Plan

If any change causes issues:
1. Revert the specific file change: `git checkout -- <file>`
2. Run tests to confirm restoration
3. Re-analyze before re-applying
4. For model changes, generate downgrade migration
5. Clear relevant Redis keys (config cache, locks): `ainews:cache:*`, `ainews:llm:*`
6. For Celery task changes, ensure workers pick up changes (may need restart)
7. For template changes, clear any template cache
8. For env var changes, remove new env vars (CELERY_TASK_SECRET, REDIS_PASSWORD, etc.)

---

## Verification Commands

```bash
# Full lint check (F/E/W codes)
.venv/bin/ruff check . --exclude .venv

# Tests
.venv/bin/python -m pytest tests/ -x -q

# Combined pre-commit style
.venv/bin/ruff check . --exclude .venv && .venv/bin/python -m pytest tests/ -x -q

# Security-specific tests
.venv/bin/python -m pytest tests/test_url_ssrf.py -x -v
.venv/bin/python -m pytest tests/test_subagent.py -x -v
.venv/bin/python -m pytest tests/test_admin_api.py -x -v
.venv/bin/python -m pytest tests/test_llm_adapters/ -x -v

# Performance-specific tests
.venv/bin/python -m pytest tests/test_cache.py -x -v
.venv/bin/python -m pytest tests/test_related.py -x -v
.venv/bin/python -m pytest tests/test_newsletter.py -x -v
.venv/bin/python -m pytest tests/test_article.py -x -v
.venv/bin/python -m pytest tests/test_search.py -x -v
```

---

## Key Test Files by Area

| Area | Test File |
|------|-----------|
| DNS/URL validation | `tests/test_url_ssrf.py` |
| Subagent | `tests/test_subagent.py` |
| Cleanup tasks | `tests/test_cleanup.py` |
| LLM adapters | `tests/test_llm_adapters/` |
| Admin API | `tests/test_admin_api.py` |
| Search/FTS | `tests/test_search.py`, `tests/test_fts.py` |
| Cache | `tests/test_cache.py` |
| Related articles | `tests/test_related.py` |
| Newsletter | `tests/test_newsletter.py` |
| Article | `tests/test_article.py` |
| Public routes | `tests/test_public.py` |

---

*End of plan*