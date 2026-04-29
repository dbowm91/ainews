# Implementation Plan - Consolidated

**Date:** April 28, 2026
**Status:** In Progress - April 29, 2026 Session
**Total Items:** 85+ actionable items
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## April 29, 2026 Implementation Update

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

**Previously Completed (April 29, 2026 Session 1):**
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

## Remaining Items by Wave

### Wave 2: High Priority Security & Observability
Items 8-17 from original plan are COMPLETED.

### Wave 3: Frontend / Accessibility
Items 24-30 remain incomplete:

| ID | Item | Files | Effort | Notes |
|----|------|-------|--------|-------|
| 24 | Fix Skip-Link Focus Visibility | static/css/critical.css | 30 min | |
| 25 | Admin Logout Hidden on Mobile | static/css/*.css | 30 min | |
| 26 | Mobile Hamburger Menu Keyboard Accessibility | static/js/app.js, templates/base.html | 1 hr | |
| 27 | Search Input Focus Loss | routes/public/*.py, templates | 1 hr | |
| 28 | Search UX Improvements | static/css/articles.css, templates | 1 hr | |
| 29 | Share Dropdown Keyboard Navigation | static/js/app.js | 1 hr | |
| 30 | Article Card Focus Styles | static/css/articles.css | 30 min | |

### Wave 4: Documentation Updates
Items 18-23, 33-37, 38-49 remain incomplete:

| ID | Item | Files | Effort |
|----|------|-------|--------|
| 18-23 | Fix API and Development docs | docs/*.md | 1.5 hr |
| 33-37 | Add missing configuration/architecture | docs/*.md, README.md | 2 hr |
| 38-49 | Component and Component Docs | docs/components/*.md | 3 hr |

### Wave 5: Backend & Docker Improvements

| ID | Item | Files | Effort | Notes |
|----|------|-------|--------|-------|
| 50 | Convert Dockerfile to Multi-Stage Build | Dockerfile | 2 hrs | |
| 51 | Add Resource Limits to docker-compose.yml | docker-compose.yml | 30 min | |
| 52 | Fix Plaintext Password Fallback | scripts/install.sh | 30 min | install.sh still stores plaintext on failure |
| 53 | Add Validation Checks to `install.sh` | scripts/install.sh | 30 min | apt-get update lacks error handling |
| 57 | Fix `backup.sh` Fallback Method | scripts/backup.sh | 1 hr | Still uses `cp` fallback |
| 58 | Update `verify_backup.sh` Tables | scripts/verify_backup.sh | 30 min | Only checks 5 tables, not 17 |

### Wave 6: Performance Improvements

| ID | Item | Files | Effort | Notes |
|----|------|-------|--------|-------|
| 66 | Fix Sitemap TTL Mismatch | routes/public/feeds.py | 30 min | No `<ttl>` tag; cache TTL != HTTP header |
| 68 | Add Stampede Protection to ConfigCache | services/config_cache.py | 1 hr | Missing `SET NX EX` distributed lock |
| 71-73 | Fix ThreadPoolExecutor Issues | services/*.py | 2 hr | Module-level executors - verified not needed |

**Note on Items 71-73:** The module-level executors in content_extractor.py, article.py, search providers, and subagent.py are designed for reuse. They properly handle timeout/cancellation within their functions. No shutdown in finally blocks needed.

### Wave 7: Code Quality & Type Safety

| ID | Item | Files | Effort | Notes |
|----|------|-------|--------|-------|
| 77 | Type Stub Installation | pyproject.toml | 30 min | Deferred |

### Wave 8: AI Agent / Pipeline Improvements

| ID | Item | Files | Effort | Notes |
|----|------|-------|--------|-------|
| 99 | Cache subagent tool registry | services/subagent.py | 1 hr | Global registry exists but initialize_tool_registry() rebuilds |
| 102 | Error-type-specific retry strategies | services/*.py | 2 hrs | retry_backoff_max=300 is uniform across tasks |
| 104 | Dead letter root cause aggregation | services/pipeline_monitor.py | 3 hrs | Reason tracking exists, no aggregation display |
| 110 | Batch API integration | services/llm/*.py | 2-3 wks | Deferred |
| 111 | Cost-tier model routing | services/llm/*.py | 2-3 wks | Deferred |

---

## Verification Commands
(Run these before committing code to verify quality standards)

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python -m mypy . --exclude .venv
```
