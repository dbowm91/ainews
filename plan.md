# Implementation Plan - Consolidated & Refined

**Date:** April 29, 2026
**Status:** ALL WAVES COMPLETED
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## Completed Work
All items from Waves 1-8 are COMPLETED, including security hardening, LLM provider optimizations, core performance improvements, email deliverability, frontend accessibility, observability, and backend refinements.

---

## WAVE 1: Critical Fixes & Security Hardening (Highest Priority) - COMPLETED

**Focus:** Eliminating fail-open vulnerabilities and fixing critical data integrity issues.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W1.1** | Fix fail-open stage lock in pipeline | `tasks/pipeline.py:108-117` | ✅ COMPLETED |
| **W1.2** | Fix fail-open newsletter lock | `tasks/newsletter.py:414-417` | ✅ COMPLETED |
| **W1.3** | Fix Version Creation Order in Edit Task | `tasks/edit.py:332-335` | ✅ COMPLETED |
| **W1.4** | Session Fixation Prevention | `routes/admin/auth.py:55-58` | ✅ COMPLETED |
| **W1.5** | Webhook Secret Decryption Safety | `services/webhooks.py:325-340` | ✅ COMPLETED |
| **W1.6** | AuthError Transient Log Fix | `tasks/pipeline.py:187` | ✅ COMPLETED |

---

## WAVE 2: Pipeline Stability & Config (Priority 2) - COMPLETED

**Focus:** Hardening the state machine and improving configuration robustness.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W2.1** | Consistent State Transitions | `tasks/write.py`, `tasks/research.py` | ✅ COMPLETED |
| **W2.2** | Quality Gate Logging | `tasks/research.py:222-223` | ✅ COMPLETED |
| **W2.3** | LLM Config Env Var Resolution | `schemas/llm.py:58-59` | ✅ COMPLETED |
| **W2.4** | Per-Stage Circuit Breaking | `services/llm/__init__.py:62-66` | ✅ COMPLETED |
| **W2.5** | Retry-After Header Support | `services/llm/base.py:155-167` | ⚠️ DEFERRED (exponential backoff used, not Retry-After parsing) |
| **W2.6** | Configurable Failure Limits | `services/pipeline_failure.py` | ✅ COMPLETED |

---

## WAVE 3: Subagent & Search Improvements - COMPLETED

**Focus:** Optimizing subagent performance and fixing search analytics.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W3.1** | Provider Fetch Optimization | `services/subagent.py` | ✅ COMPLETED |
| **W3.2** | Configurable Subagent Iterations | `services/subagent.py:722` | ✅ COMPLETED |
| **W3.3** | Subagent Self-Correction Loop | `services/subagent.py` | ✅ COMPLETED |
| **W3.4** | Search Analytics Query Fix | `routes/admin/api/search.py` | ✅ COMPLETED |
| **W3.5** | Tag Feed Caching | `routes/public/feeds.py:172` | ✅ COMPLETED |

---

## WAVE 4: Email & Newsletter Features - COMPLETED

**Focus:** Improving email deliverability and AI-generated subjects.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W4.1** | Email Plain-Text Alternative | `services/email.py:207-218` | ✅ COMPLETED (multipart/alternative with plain-text attached) |
| **W4.2** | List-Unsubscribe Header | `services/email.py` | ✅ COMPLETED |
| **W4.3** | AI-Generated Newsletter Subject | `services/newsletter.py` | ✅ COMPLETED |
| **W4.4** | LLM Content Sanitization | `services/article.py` | ✅ COMPLETED |
| **W4.5** | Source CRUD API | `routes/admin/api/` | ✅ COMPLETED |

---

## WAVE 5: Frontend & Accessibility - COMPLETED

**Focus:** Polishing the UI and adding user-facing state.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W5.1** | RSS Icon Replacements | `templates/base.html:47`, `static/svg/rss.svg` | ✅ COMPLETED (SVG icon with CSS flexbox styling) |
| **W5.2** | Mobile Nav UX | `templates/base.html` | ✅ COMPLETED |
| **W5.3** | Client-side Bookmarking | `static/js/app.js:395-462`, `static/css/articles.css` | ✅ COMPLETED (localStorage-based bookmark toggle with UI) |
| **W5.4** | Article Read State | `static/js/app.js` | ✅ COMPLETED |

---

## WAVE 6: Observability & Metrics - COMPLETED

**Focus:** Deeper insights into pipeline performance.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W6.1** | E2E Latency Histograms | `tasks/edit.py` | ✅ COMPLETED |
| **W6.2** | Pipeline Backlog API | `routes/admin/api/pipeline.py:85-136` | ✅ COMPLETED (`/api/pipeline/backlog` returns up to 100 active articles with stuck status) |
| **W6.3** | Subagent Context Caching | `services/subagent.py` | ✅ COMPLETED |
| **W6.4** | HTMX CSRF Header Audit | `templates/admin/` | ✅ COMPLETED |

---

## WAVE 7: Backend Refinement & Quality - COMPLETED

**Focus:** Database optimizations and schema improvements.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **W7.1** | SQLite Busy Timeout | `config.py` | ✅ COMPLETED |
| **W7.2** | Retry Count Indexes | `models.py:156-159` | ✅ COMPLETED (ix_articles_total_retries, ix_articles_retry_count, ix_articles_degradation_count) |
| **W7.3** | Config Validation Errors | `services/config_unified.py` | ✅ COMPLETED |
| **W7.4** | DNS Timeout Cancellation | `services/url.py:143-149` | ✅ COMPLETED |

---

## WAVE 8: Documentation & Future Work - COMPLETED

**Focus:** Operational readiness and subscriber management.

| Item | Description | Location | Status |
|------|-------------|----------|--------|
| **D1** | Operations & Troubleshooting | `docs/` | ✅ COMPLETED |
| **D2** | Subscriber Sunset Policy | `services/subscribers.py` | ✅ COMPLETED |

---

## Verification Protocol

For every Wave, execute:
1. `ruff check .`
2. `pytest tests/ -x -q` (Ensuring no regressions in core pipeline).
3. Manual verification of the specific fix (e.g., simulate Redis outage for W1.1).
