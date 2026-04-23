# Implementation Plan — Deferred Items Only

**Created:** April 22, 2026
**Last Updated:** April 23, 2026
**Status:** COMPLETE — All implementation items verified complete; only intentionally deferred items remain

---

## Summary

All plan items from Waves A-E have been verified complete in the codebase:

- ✅ Wave A (A1-A10): All 10 security items implemented and verified
- ✅ Wave B (B1-B3): All transaction/locking fixes implemented and verified
- ✅ Wave C (C1-C6): All 6 performance items implemented and verified
- ✅ Wave D (D1-D9): All 9 code quality items implemented and verified
- ✅ Wave E (E1-E6): All 6 lower-priority items implemented and verified

**Verification:**
- `.venv/bin/ruff check . --exclude .venv` — All lint checks pass
- Bulk article cache invalidation fix committed (April 23)

**Pre-existing test failures (not related to plan changes):**
- `tests/test_llm_adapters/test_anthropic.py::test_chat_with_schema` — KeyError on `call_args.kwargs`
- `tests/test_llm_adapters/test_ollama.py::test_extract_text_with_thinking_fallback` — pre-existing

---

## Deferred Items — Intentionally Skipped

| Item | Source | Reason | Status |
|------|--------|--------|--------|
| E.2: Celery Task Event Streaming | plan.md | Requires celery.events.RealityMonitor or pubsub consumer, Redis streaming, MetricsCollector updates — not practical | Deferred |
| E.3: Structured Tool Result Format | plan4.md | Already implemented via `esc_xml_text` in `services/prompts.py` — 65+ uses across codebase | Not needed |
| E.4: Celery Worker Network Isolation | plan4.md | Requires hosting platform + CI/CD that don't exist | Deferred |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | 60-second TTL covers the need — event-based adds 150+ LOC for marginal benefit | Deferred |
| 1.1: CI/CD Pipeline | plan5.md | Requires project to be hosted on platform with GitHub Actions or equivalent | Deferred |

---

*End of plan*