# Consolidated Implementation Plan

**Status:** COMPLETED — All waves 1-9 implemented and verified (April 27, 2026)

---

## Deferred Items (Do Not Implement)

These items were intentionally deferred as lower priority or not needed at this time.

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
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
| Search highlighting (FTS5) | Significant architectural change |
| Keyboard navigation ARIA feed | Complex, low signal |
| Reader counts display | Simple but low signal |
| Beat task last-run display | Nice to have |
| Theme toggle keyboard shortcut | Minor convenience |
| Newsletter dry-run styling | Minor |
| Docker healthchecks | Low priority |
| ThreadPool executor lazy init + atexit | Medium effort, low production impact |
| Notification system (AdminPreference model) | Significant new feature |
| Subagent topic scope isolation | Medium effort, needs design |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage |
| Search result caching | Nice-to-have optimization |
| Search provider fallback chain | Nice-to-have optimization |
| Config version coordination | High complexity |
| Audit log decorator | Nice-to-have |

---

## Items Removed During Implementation

These items were identified during implementation but removed for the reasons noted.

| Item | Reason |
|------|--------|
| aggregate_crawl_results autoretry | Already had `autoretry_for=(ConnectionError, TimeoutError)` at line 198 |
| RSS adapter socket timeout | Per-request `timeout=cfg.request_timeout` at line 38 provides actual timeout |
| Subagent chain template resolution "result unused" | Verified: result IS used via `prompt_data_escaped` in `.format()` call |
| `_find_overlapping_low_entries` dead code removal | Low priority, just dead code, no functional impact |
| wave5_6: Add autoretry to aggregate_crawl_results | Already implemented (see above) |

---

## Implementation Summary (April 26-27, 2026)

All 9 waves were implemented and verified:

- **Wave 1**: 7 critical fixes (pipeline stats field, extract task state machine, Google health_check indentation, ast.Call security, safe_href narrowing, dockerignore, dead letters table)
- **Wave 2**: 6 state machine/validation fixes (PENDING→REVIEW transition, rollback handling, state machine in set_status, SoftTimeLimitExceeded handlers, webhook return False on DB error, yield_per for subscribers)
- **Wave 3**: 7 subagent/LLM provider fixes (initialize_tool_registry signature, tool error handling, AuthError in fallback tuple, provider retry loop, backoff formula, previous in allowed names, single-brace template detection)
- **Wave 4**: 6 search/circuit breaker fixes (DuckDuckGo SSRF, configurable LLM failure threshold, record_success/failure methods, search circuit breaker helpers, retry_backoff=True, retry logic in adapters)
- **Wave 5**: 6 performance/cache fixes (blpop→polling, joinedload in metrics, stage failure key clearing, pub:related invalidation, _evict_stale in get, retry_stuck autoretry)
- **Wave 6**: 9 UI/UX improvements (sort parameter, date filters, pagination params, sort dropdown, select all matching, hx-push-url, collapsible what-to-watch, view original link, aria-haspopup removal)
- **Wave 7**: 7 documentation files (subagent.md, trend-memory.md, search-providers.md, context-service.md, pipeline-failure-tracking.md, newsletter-pipeline.md, cost-tracking.md)
- **Wave 8**: 5 deployment script improvements (install.sh flags, deploy.sh git validation, nginx alias fix, docker healthchecks, env password instructions)
- **Wave 9**: 7 PWA/UI additions (manifest.json, service-worker.js, SW registration, reading_time calculation, reading_time display, webhook payload + resend, dead letters pagination)

**Total items implemented: 55 actionable items across 9 waves**

---

*Last updated: April 27, 2026*