# Consolidated Implementation Plan

**Created:** April 25, 2026
**Last Updated:** April 25, 2026
**Status:** COMPLETED -- All implementation items verified complete

---

## Deferred Items (Do Not Implement Without Explicit Direction)

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
| Trend memory admin UI | Nice-to-have |
| Public API rate limiting | AGENTS.md says don't add `@limiter.limit()` |
| Pagination cursor-based | Works for current scale |
| Global LLM circuit breaker | Per-provider sufficient |
| Batch duplicate detection | Current approach sufficient |
| Redis pool segregation | Hasn't hit limits |
| CSS minification | CDN handles gzip |
| Announcement banner | Only if needed |
| Tool expansion/validation | Low ROI |
| Admin route fragmentation | Current split acceptable |
| Tool registry auto-init | Optional |
| Input/output token separation | Requires provider changes |
| Provider logprobs confidence | Complex, not universal |
| Ollama tool-calling | Not all models support |
| Full editor with tools | Higher effort |
| Persistent DuckDuckGo instance | Rate limits make pooling less impactful |

---

## Implementation Summary

All Batch A, B, C, D items from the original plan have been implemented and verified:

- **Batch A (Quick wins/UI)**: Precompiled regex, silent exception logging, subagent thread pool, cost pricing, search clear button, base font size (15px), date format filter, beat schedule reload, traced_stage integration, threshold config
- **Batch B (Testing/Performance)**: Mock fixes, test helpers, session pooling, duplicate detection limit, database index
- **Batch C (Security/Architecture)**: Secret rotation, audit logging, request size limits, state machine, docker compose, CI/CD pipeline
- **Batch D (Agent-harness)**: Subagent tools, fallback handling, context injection, quality gates, type hints

*Consolidated April 25, 2026*