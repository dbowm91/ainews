# Implementation Plan - Consolidated

**Date:** April 28, 2026
**Status:** Partially Completed (April 29, 2026)
**Total Items:** 85+ actionable items
**Strategy:** Execute sequentially by Wave. Items within a Wave (unless noted) can be executed in parallel by multiple subagents.

---

## April 29, 2026 Implementation Update

The following items were completed on April 29, 2026:

**Wave 1 (COMPLETED):**
- W1.1: Subagent tool registry names fixed (web_search, context_notes, related_articles)
- W1.2: IPv4-mapped IPv6 SSRF bypass fixed in url.py
- W1.3: HTTP redirect SSRF prevention (allow_redirects=False + SSRFSafeRedirectHandler)
- W1.4: Service worker scope corrected to '/'
- W1.5-W1.6: Already correct in codebase
- W1.7: LLM provider exception handling hardened (KeyboardInterrupt/SystemExit)
- W1.8: Dead verify_task() removed from cleanup_old_article_versions

**Wave 2 (COMPLETED):**
- W2.1: LLM provider URL validation added to OllamaProvider and OpenAIProvider
- W2.2: DNS cache TTL reduced from 60s to 5s
- W2.3: @validate_csrf_json added to HTMX endpoints
- W2.4: Password hashing strengthened with scrypt n=131072 and complexity validation

**Wave 3 (COMPLETED):**
- W3.1: Project root cleaned (.DS_Store, dump.rdb removed)
- W3.2: requirements.txt and requirements-dev.txt removed
- W3.3: SQLAlchemy 2.0 migration (Query.get() → db.session.get(), first_or_404 → db.first_or_404())
- W3.4: Exception logging improved (added debug/exc_info to silent handlers)

**Wave 4 (PARTIAL):**
- W4.1: pytest-timeout added, Redis mocking fixed in test_admin_auth.py
- W4.4: Mypy implementation deferred (20h effort)

**Wave 5 (PARTIAL):**
- W5.3: record_stage_result and record_throughput added to crawl.py
- W5.1, W5.4, W5.6: Deferred

**Wave 6 (PARTIAL):**
- W6.4: Meta descriptions added to topic.html and tag.html
- W6.1, W6.2, W6.3: Deferred

**Wave 7 (PARTIAL):**
- W7.2: Session binding to IP/User-Agent implemented
- W7.1, W7.3: Deferred

**Wave 8 (PARTIAL):**
- W8.3: Coverage config updated to exclude tests
- W8.2: Deferred

---

---

## Wave 1: Critical Bugs (Must Fix First - Sequential Execution)
**Status: COMPLETED April 29, 2026**
These items cause runtime crashes or security vulnerabilities. Fix before any other work.

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 1 | Fix `_acquire_stage_lock` fail-open bug | tasks/pipeline.py:108-117 | 5 min | Change `except` block to raise `RedisError` instead of returning `True` to enforce fail-closed behavior. |
| 2 | Fix `generate_daily_newsletters` fail-open | tasks/newsletter.py:414-417 | 5 min | Change `lock_status = 2` on `RedisError` to raise the exception, preventing concurrent task execution. |
| 3 | Fix unsafe `.env` sourcing | scripts/deploy.sh:183 | 15 min | Extract variables safely (e.g., using `export $(grep -v '^#' .env | xargs)`) instead of `source`. |
| 4 | Fix file permissions (777 on sensitive files) | scripts/*.sh, config files | 15 min | Update scripts to 755 (`chmod 755`) and configuration files to 644/600. |
| 5 | Redis security - no password in Docker Compose | docker-compose.yml | 10 min | Add a `REDIS_PASSWORD` environment variable and configure `requirepass` in the Redis service command. |
| 6 | Fix Version Creation Order | tasks/edit.py:333 | 30 min | Move `create_article_version` call to *before* `article.final_article = result_json` modification. |
| 7 | Fix providers.yaml Env Var Resolution | schemas/llm.py:58-59 | 1 hr | Update `_load_providers_config_from_file` to call `resolve_env_vars(raw)` before Pydantic instantiation. |

---

## Wave 2: High Priority Security & Observability (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 8 | Fix Wrong Celery Healthcheck | docker-compose.yml | 15 min | Replace `redis-cli ping` with `celery -A celery_app inspect ping` for Celery worker/beat healthchecks. |
| 9 | Replace placeholder GitHub URL | 8 files | 30 min | Grep for placeholder URLs and replace with the correct repository URL. |
| 10 | Add file permission validation at startup | services/*.py | 1 hr | Add `os.stat()` checks for critical configs/scripts during app initialization; warn if world-writable. |
| 11 | Update `install.sh` to set proper permissions | scripts/install.sh | 30 min | Add `chmod` commands post-installation to secure the application directory. |
| 12 | Embed Lua script for atomic lock release | routes/admin/__init__.py | 1 hr | Replace `GET` -> `DEL` with a Lua script (like `_NEWSLETTER_LOCK_SCRIPT`) for login lockout memory. |
| 13 | Fix Prometheus Histogram Metrics | services/metrics.py | 1 hr | Ensure `pipeline.stage_duration_seconds` buckets match expected duration ranges. |
| 14 | Configure OpenTelemetry Exporter | services/logging_utils.py | 1 hr | Initialize `OTLPSpanExporter` if `OTEL_EXPORTER_OTLP_ENDPOINT` is defined in environment. |
| 15 | Add Missing Database Indexes | migrations/*, models.py | 1 hr | Add indexes on queried fields (e.g. `source_id`, `pipeline_status`); generate Alembic migration. |
| 16 | Fix N+1 Query: Article.metrics | routes/admin/dashboard.py | 30 min | Use `joinedload(Article.metrics)` in dashboard queries. |
| 17 | Remove unused query in Newsletter tasks | tasks/newsletter.py | 15 min | Delete redundant `Article.query` calls not used in the final newsletter generation. |

---

## Wave 3: Frontend / Accessibility (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 24 | Fix Skip-Link Focus Visibility | static/css/critical.css | 30 min | Remove `outline: none` on `.skip-link:focus` so keyboard users see the focus ring. |
| 25 | Admin Logout Hidden on Mobile | static/css/*.css | 30 min | Fix media query hiding `.nav-meta` on small screens so logout remains accessible. |
| 26 | Mobile Hamburger Menu Keyboard Accessibility | static/js/app.js, templates/base.html | 1 hr | Add `role="button"`, `tabindex="0"`, `aria-expanded`, and Escape key listener. |
| 27 | Search Input Focus Loss | routes/public/*.py, templates | 1 hr | Add `hx-preserve` or use Alpine/Vanilla JS to maintain focus during HTMX swap. |
| 28 | Search UX Improvements | static/css/articles.css, templates | 1 hr | Add `minlength` attribute, tooltip, and `.htmx-indicator` CSS for the loading spinner. |
| 29 | Share Dropdown Keyboard Navigation | static/js/app.js | 1 hr | Add an `Escape` key event listener to close the dropdown and return focus to the trigger button. |
| 30 | Article Card Focus Styles | static/css/articles.css | 30 min | Add `:focus-within` styling to the article card to highlight when links inside are focused. |

---

## Wave 4: Documentation Updates (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 18-23 | Fix API and Development docs | docs/*.md | 1.5 hr | Correct LLM paths, decorators, HTTP basic auth references, and endpoint URLs based on source code. |
| 33-37 | Add missing configuration/architecture | docs/*.md, README.md | 2 hr | Add A/B testing configs, cost tracking details, and fix ASGI/WSGI architecture references. |
| 38-49 | Component and Component Docs | docs/components/*.md | 3 hr | Create missing markdown files for pagination/search, fix dead links, update beat schedule counts. |

---

## Wave 5: Backend & Docker Improvements (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 50 | Convert Dockerfile to Multi-Stage Build | Dockerfile | 2 hrs | Separate build dependencies (gcc, pip wheels) from the final runtime image to reduce size. |
| 51 | Add Resource Limits to docker-compose.yml | docker-compose.yml | 30 min | Add `deploy.resources.limits` (cpus, memory) for all services. |
| 52 | Fix Plaintext Password Fallback | scripts/install.sh | 30 min | Ensure password hashes are never stored in plaintext if the hashing Python script fails. |
| 53 | Add Validation Checks to `install.sh` | scripts/install.sh | 30 min | Remove `|| true` on critical commands like `apt-get install` to fail early. |
| 54 | Align Granian Worker Count | Dockerfile, systemd/ainews-web.service | 15 min | Ensure both define the same number of workers (e.g., 4) for consistency. |
| 57 | Fix `backup.sh` Fallback Method | scripts/backup.sh | 1 hr | Use SQLite `.backup` command exclusively instead of `cp` to prevent corruption. |
| 58 | Update `verify_backup.sh` Tables | scripts/verify_backup.sh | 30 min | Update the table list to include all 18 tables instead of just 5. |

---

## Wave 6: Performance Improvements (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 65 | Fix Cache Invalidation Gaps | routes/admin/*.py | 1 hr | Change `invalidate_prefix("pub:rss")` to `invalidate_prefix("pub:rss_feed")` to match actual keys. |
| 66 | Fix Sitemap TTL Mismatch | routes/public/feeds.py | 30 min | Align `expires_in` parameter of `@cache.cached` with the sitemap XML `<ttl>` tag. |
| 68 | Add Stampede Protection to ConfigCache | services/config_cache.py | 1 hr | Implement `SET NX EX` distributed lock pattern (similar to `ResponseCache.get_or_set()`). |
| 70 | Add Date Filter to `find_related_articles_dicts` | services/related.py | 30 min | Add a `filter(Article.created_at >= 30_days_ago)` to match the primary `find_related_articles` method. |
| 71-73 | Fix ThreadPoolExecutor Issues | services/*.py | 2 hr | Add `.shutdown(cancel_futures=True)` to executors in `finally` blocks to prevent thread leaks. |

---

## Wave 7: Code Quality & Type Safety (Parallelizable)

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 77 | Type Stub Installation | pyproject.toml | 30 min | Add `types-redis`, `types-requests`, etc., to dev dependencies for strict mypy compliance. |
| 79-82 | Fix Type Mismatches | models.py, config.py, services/*.py | 4 hr | Resolve `Optional` warnings and Union type errors in `content_extractor.py` and adapters. |
| 84 | Refactor `_evaluate_condition` bitwise bug | services/subagent.py:1015 | 4 hrs | Replace `operator.and_`/`or_` with `all()`/`any()` for logical AST operations with >2 operands. |
| 87 | Fix Silent Exception Handling | services/*.py, routes/*.py | 1 hr | Add `logger.error("Failed: %s", e)` inside empty `except Exception: pass` blocks. |
| 93 | Standardize PipelineLogger formatting | services/logging_utils.py | 1 hr | Replace f-strings with %-formatting (`logger.info("Msg %s", val)`) per project conventions. |

---

## Wave 8: AI Agent / Pipeline Improvements (Partial Parallelization)
*Note: These items require design and careful implementation due to high impact.*

| ID | Item | Files | Effort | Implementation Context |
|----|------|-------|--------|------------------------|
| 98 | Dynamic stage lists | services/pipeline_monitor.py | 30 min | Use `VALID_TRANSITIONS` keys instead of a hardcoded list of stages. |
| 99 | Cache subagent tool registry | services/subagent.py | 1 hr | Instantiate tools once at module level or use an LRU cache to avoid rebuilding per call. |
| 102 | Error-type-specific retry strategies | services/*.py | 2 hrs | Add `autoretry_for` specific exceptions with varying `retry_backoff` parameters in Celery tasks. |
| 104 | Dead letter root cause aggregation | services/pipeline_monitor.py | 3 hrs | Parse failure reasons from `ainews:pipeline:counters:{stage}:{minute}:failure:{reason}` to show in dashboard. |
| 110 | Batch API integration | services/llm/*.py | 2-3 wks | Implement OpenAI Batch API for low-priority tasks (e.g. background reprocessing). |
| 111 | Cost-tier model routing | services/llm/*.py | 2-3 wks | Route simple tasks (e.g. basic categorization) to cheaper models based on `experiments` config. |

---

## Verification Commands
(Run these before committing code to verify quality standards)

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
.venv/bin/python -m mypy . --exclude .venv
```
