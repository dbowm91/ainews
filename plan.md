# Master Implementation Plan

## Wave 1: Critical Fixes & Stability (Immediate)
*Focus: Stability, immediate security risks, and core pipeline fixes.*

- 1.1 **Fix Failing Audit Test**: In `services/audit.py`, handle `RuntimeError` when `db.session` is accessed outside app context (affects `test_log_admin_action_logs`).
- 1.2 **P1 Security Fixes**: Upgrade `lxml >= 6.1.0` in `pyproject.toml`. Harden `Dockerfile` (permissions, non-root user).
- 1.3 **Fix Limiter Blocking**: In `services/limiter.py`, replace `time.sleep()` in `acquire` (lines 81, 108) with Redis pub/sub wait to prevent worker starvation. [P]
- 1.4 **Reconcile AGENTS.md**: Update `AGENTS.md` to truthfully reflect 100+ remaining lint errors.
- 1.5 **Fix Critical BLE001**: Replace `except Exception:` with specific types in `tasks/` and `routes/admin/api/articles.py`. [P]

## Wave 2: Performance & Reliability (High Priority)
*Focus: Pipeline throughput and defense-in-depth.*

- 2.1 **LLM Async & Batching**: Implement thread pools for LLM calls in pipeline tasks; add support for OpenAI Batch API for non-urgent stages. [P]
- 2.2 **SSRF Hardening**: Add IP normalization (decimal/hex handling) in `services/url.py`.
- 2.3 **MultiFernet Webhooks**: Refactor `services/webhooks.py` to use `cryptography.fernet.MultiFernet` for simpler key rotation. [P]
- 2.4 **Semantic Search Opt.**: Add limits and pre-filtering to `semantic_search_trends` in `services/trend_memory.py` to avoid OOM. [P]
- 2.5 **Test Coverage P0-P1**: Add tests for `decorators.py`, `article_fallback.py`, and security flows. [P]
- 2.6 **Security Docs Fix**: Update `docs/security.md` to reflect `scrypt` usage (matching `scripts/hash_password.py`). [P]

## Wave 3: Quality & Optimization (Medium Priority)
*Focus: Long-term maintainability and system efficiency.*

- 3.1 **Mypy Adoption (P1-3)**: Install stubs (Flask, SQLAlchemy) and fix 80+ core type errors.
- 3.2 **DB Query Consolidation**: Use conditional aggregation for COUNT queries in dashboard/trends. [P]
- 3.3 **Index Optimization**: Add `original_title` index and remove redundant pipeline status indexes. [P]
- 3.4 **Article Lazy Loading**: Change `Article.metrics` relationship to `lazy="selectin"`. [P]
- 3.5 **Prompt File Caching**: Add `@lru_cache` to `load_prompt_file` in `services/prompts.py`. [P]
- 3.6 **Audit Sanitization**: Review `log_admin_action` calls and truncate/redact sensitive data in `details`.
- 3.7 **Key Rotation Docs**: Create `docs/key_rotation.md` with standard procedures. [P]

## Wave 4: Infrastructure & Polish (Long-term)
*Focus: Documentation, DX, and observability.*

- 4.1 **OpenAPI Specification**: Create static or semi-automated OpenAPI spec for core endpoints. [P]
- 4.2 **A/B Experiment Docs**: Document the deterministic assignment and variant selection logic. [P]
- 4.3 **Docker Hardening**: Multi-stage builds, non-root users, and healthchecks in `Dockerfile`. [P]
- 4.4 **Mypy Phase 4**: Enable `disallow_untyped_defs = true` per module.
- 4.5 **Inline Lua Scripts**: Move `login_lockout.lua` directly into Python code like other scripts. [P]
- 4.6 **Observability Fixes**: Fix OTel defaults and add `is_fully_healthy` semantics. [P]

## Implementation History
*Summary of previously completed waves.*

- Wave 1 (Critical Fixes & Security): W1.1-W1.6
- Wave 2 (Pipeline Stability): W2.1-W2.6 (including W2.5 Retry-After Header Support)
- Wave 3 (Subagent & Search): W3.1-W3.5
- Wave 4 (Email & Newsletter): W4.1-W4.5
- Wave 5 (Frontend & Accessibility): W5.1-W5.4
- Wave 6 (Observability & Metrics): W6.1-W6.4
- Wave 7 (Backend Refinement): W7.1-W7.4
- Wave 8 (Documentation): D1-D2
