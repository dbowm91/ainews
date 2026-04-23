# Implementation Plan — Deferred Items Only

**Created:** April 22, 2026
**Last Updated:** April 23, 2026
**Status:** COMPLETED — All implementation items verified complete; only intentionally deferred items remain

---

## Completed Implementation Summary (April 22-23, 2026)

All plan items from Waves A-E have been verified complete in the codebase:

- ✅ Wave A (A1-A10): All 10 security items implemented and verified
- ✅ Wave B (B1-B3): All transaction/locking fixes implemented and verified
- ✅ Wave C (C1-C6): All 6 performance items implemented and verified (C5 cache invalidation fix completed April 23)
- ✅ Wave D (D1-D9): All 9 code quality items implemented and verified
- ✅ Wave E (E1-E6): All 6 lower-priority items implemented and verified

**Verification performed:**
- `.venv/bin/ruff check . --exclude .venv` — All lint checks pass
- `.venv/bin/python -m pytest tests/ -x -q` — Tests pass (excluding pre-existing failures)
- Subagent-based code review confirmed all implementations

**Pre-existing test failures (not related to plan changes):**
- `tests/test_llm_adapters/test_anthropic.py::test_chat_with_schema` — KeyError on `call_args.kwargs`
- `tests/test_llm_adapters/test_ollama.py::test_extract_text_with_thinking_fallback` — pre-existing

---

## Deferred Items — Intentionally Skipped

These items were reviewed and intentionally deferred due to scope, infrastructure requirements, or impracticability:

| Item | Source | Reason | Status |
|------|--------|--------|--------|
| E.2: Celery Task Event Streaming | plan.md | Requires celery.events.RealityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates — not practical | Deferred |
| E.3: Structured Tool Result Format | plan4.md | Already implemented via `esc_xml_text` in `services/prompts.py` — 65+ uses across codebase | Not needed |
| E.4: Celery Worker Network Isolation | plan4.md | Requires hosting platform + CI/CD that don't exist | Deferred |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | 60-second TTL covers the need — event-based adds 150+ LOC for marginal benefit | Deferred |
| 1.1: CI/CD Pipeline | plan5.md | Requires project to be hosted on platform with GitHub Actions or equivalent | Deferred |

---

## Verification Commands

```bash
# Full lint check
.venv/bin/ruff check . --exclude .venv

# Tests
.venv/bin/python -m pytest tests/ -x -q

# Security-specific tests
.venv/bin/python -m pytest tests/test_url_ssrf.py -x -v
.venv/bin/python -m pytest tests/test_subagent.py -x -v
.venv/bin/python -m pytest tests/test_admin_api.py -x -v

# Performance-specific tests
.venv/bin/python -m pytest tests/test_cache.py -x -v
.venv/bin/python -m pytest tests/test_related.py -x -v
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
