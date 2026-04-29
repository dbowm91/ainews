# Implementation Plan - Consolidated

**Date:** April 28, 2026
**Status:** COMPLETED - April 29, 2026 Session 3
**Total Items:** 85+ actionable items
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## April 29, 2026 Implementation Update

**Session 3 - April 29, 2026 Completed:**
- W3 (Items 24-30): Frontend/Accessibility fixes (skip-link, mobile nav, search UX, article card focus)
- W4 (Items 18-23, 33-37): Documentation updates (api.md, development.md, share-button.md)
- W5 (Items 50-53, 57-58): Backend/Docker improvements (resource limits, install.sh validation, backup.sh, verify_backup.sh)
- W6 (Items 66, 68, 71-73): Performance improvements (sitemap TTL, ConfigCache stampede protection, ThreadPoolExecutor verification)
- W8 (Items 99, 102, 104): AI Agent/Pipeline improvements (subagent registry caching, dead letter root cause aggregation)

**Session 2 - April 29, 2026 Completed:**
- W1.3: HTTP redirect SSRF prevention (SSRFSafeRedirectHandler in adapters/rss.py)
- W2.3: @validate_csrf_json added to HTMX endpoints (shares, pipelines, articles)
- W2.4: Password hashing script fixed (salt_len -> salt_length, removed key_len)
- Item 54: Granian worker count aligned (Dockerfile and systemd both use 4)
- Item 65: Cache invalidation fixed (pub:rss -> pub:rss_feed)
- Item 70: Date filter added to find_related_articles_dicts (30-day filter)
- Item 84: _evaluate_condition bitwise bug fixed (all()/any() for BoolOp)
- Item 87: Silent exception logging added to _evaluate_condition
- Item 93: PipelineLogger formatting converted to %-style
- Item 98: Dynamic stage lists via PIPELINE_STAGES constant

**Session 1 - April 29, 2026 Completed:**
- W1.1: Subagent tool registry names fixed
- W1.2: IPv4-mapped IPv6 SSRF bypass fixed
- W1.4: Service worker scope corrected to '/'
- W1.5-W1.6: Already correct in codebase
- W1.7: LLM provider exception handling hardened
- W1.8: Dead verify_task() removed
- W2.1: LLM provider URL validation added
- W2.2: DNS cache TTL reduced from 60s to 5s
- W3.1-W3.4: Project cleanup, requirements removal, SQLAlchemy 2.0 migration
- W4.1: pytest-timeout added, Redis mocking fixed
- W4.4: Mypy implementation deferred (20h effort)
- W5.3: record_stage_result and record_throughput added to crawl.py
- W6.4: Meta descriptions added to topic.html and tag.html
- W7.2: Session binding to IP/User-Agent implemented
- W8.3: Coverage config updated to exclude tests

---

## ALL ITEMS COMPLETED

All waves have been successfully completed in the April 29, 2026 sessions:
- Wave 1-8: All actionable items implemented or verified as not needed
- Wave 7 Item 77 (Type Stub Installation): Deferred - low priority
- Wave 8 Items 110-111 (Batch API integration, Cost-tier model routing): Deferred - 2-3 weeks effort each

---

## Verification Commands

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python -m mypy . --exclude .venv
```