# Architecture Review: `architecture/overview.md` vs Codebase

## Verification Results

### VERIFIED Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| **Directory Structure** | VERIFIED | All directories exist: `models/`, `services/`, `adapters/`, `routes/`, `tasks/`, `schemas/`, `utils/`, `prompts/`, `tests/` |
| **Key Config Files** | VERIFIED | `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`, `config.py` all exist |
| **Infrastructure - Granian** | VERIFIED | Referenced in `systemd/ainews-web.service` |
| **Infrastructure - Celery + Redis** | VERIFIED | `celery_app.py`, `docker-compose.yml` uses Redis as broker |
| **Infrastructure - SQLite** | VERIFIED | `config.py` uses SQLite with WAL mode pragma in `app.py` |
| **Module Index Accuracy** | VERIFIED | All modules listed exist with described functionality |
| **System Diagram Components** | VERIFIED | RSSAdapter, APIAdapter, WebAdapter exist; Researcher, Writer, Editor services exist; Models (DB), Routes (Flask), Tasks (Celery) exist |
| **Data Flow: Source Ingestion** | VERIFIED | `process_item` task in `tasks/extract.py` handles fetch -> extract -> deduplicate -> dispatch |
| **Data Flow: Article Pipeline** | VERIFIED | `select_article` -> `research_article` -> `write_article` -> `edit_article` -> `finalize_article` flow implemented in `tasks/` |
| **Data Flow: Newsletter Generation** | VERIFIED | `generate_daily_newsletters` in `tasks/newsletter.py` with 3-stage executive summary (reader -> writer -> editor) |
| **Security: TOTP 2FA** | VERIFIED | `services/totp.py` has `generate_secret()`, `verify_token()`, `verify_backup_code()`, `consume_backup_code()` with 8 backup codes |
| **Security: Session Binding** | VERIFIED | `routes/admin/__init__.py` lines 73-84 check IP and User-Agent match stored session values |
| **Security: HMAC Webhooks** | VERIFIED | `services/webhooks.py` lines 101-122 implement `_sign_payload()` with timestamp for replay protection |
| **Security: SSRF Protection** | VERIFIED | `services/url.py` has `validate_url_safe()` with private IP blocklist and DNS resolution validation |
| **Security: Encrypted Webhook Secrets** | VERIFIED | `services/webhooks.py` lines 69-98 implement Fernet encryption (`_encrypt_secret()`, `_decrypt_secret()`) |
| **Security: Login Lockout** | VERIFIED | `routes/admin/__init__.py` lines 102-301 implement Redis-based lockout with in-memory fallback |
| **Security: Fail-Closed** | VERIFIED | `config.py` `ProductionConfig.validate()` lines 253-278 raises `RuntimeError` for missing/invalid secrets |
| **LLM Provider Config** | VERIFIED | `providers.yaml` defines ollama-local (enabled), openai, anthropic, gemini (disabled) plus 10 other providers |
| **Search Providers** | VERIFIED | `providers.yaml` defines duckduckgo (enabled), google, searxng (disabled) |

### DISCREPANCIES

| Issue | Severity | Description |
|-------|----------|-------------|
| **Layering Violation: Services imports Adapters** | HIGH | `services/crawling.py` line 13: `from adapters.base import RawItem` violates the architecture rule "Services should NOT import from adapters". The document claims this restriction exists but it is not enforced. |
| **Layering Violation: Adapters imports Services** | HIGH | Multiple adapters import from `services/` despite architecture claiming "Adapters should NOT contain business logic or import from services": |
| | | - `adapters/base.py` line 80: `from services.trend_detector import classify` |
| | | - `adapters/web.py` line 14: `from services.url import validate_url_safe` |
| | | - `adapters/api.py` line 11: `from services.url import validate_url_safe` |
| | | - `adapters/session.py` line 8: `from services.url import UnsafeURLError, validate_url_safe` |
| | | - `adapters/rss.py` line 12: `from services.url import validate_url_safe` |
| **SSRF Import from services rather than utils** | MEDIUM | SSRF protection (`validate_url_safe`) lives in `services/url.py` but should be in `utils/url.py` since it's a pure utility with no business logic. Adapters importing from `services.url` violates layering. |
| **Directory Structure Missing `extensions.py`** | LOW | Document shows `extensions.py` in description but not in the Directory Structure tree diagram |

---

## Bug Findings

### CRITICAL
None identified - no security vulnerabilities or data loss risks.

### HIGH

1. **Layering Violations**
   - **Location**: `services/crawling.py`, all adapter files
   - **Problem**: Bidirectional imports between services and adapters break the clean architecture
   - **Impact**: Code is harder to test, maintain, and reason about. Violates stated design principles.
   - **Fix**: Move `validate_url_safe` and `UnsafeURLError` to `utils/url.py`, then update adapter imports accordingly. Remove `services/crawling.py`'s import of `adapters.base`.

2. **Documentation Inconsistency**
   - **Location**: `architecture/overview.md` claims "Services should NOT import from adapters" and "Adapters should NOT import from services"
   - **Problem**: The actual codebase has violations of both rules
   - **Impact**: Misleading documentation for future developers
   - **Fix**: Either fix the code to match the docs, or update the docs to reflect reality

### MEDIUM

3. **SSRF Utility Misplaced**
   - **Location**: `services/url.py` contains `validate_url_safe()` which is a pure utility function
   - **Problem**: `validate_url_safe` has no business logic and should be in `utils/url.py`
   - **Impact**: Causes adapter files to violate layering by importing from services
   - **Fix**: Move to `utils/url.py` and update imports

### LOW

4. **Missing Extension in Directory Diagram**
   - **Location**: `architecture/overview.md` line 178-196
   - **Problem**: `extensions.py` is not shown in the Directory Structure diagram
   - **Impact**: Minor documentation inconsistency
   - **Fix**: Add `extensions.py` to the directory structure diagram

5. **Subagent Not in Directory Structure**
   - **Location**: `architecture/overview.md` line 178-196
   - **Problem**: `services/subagent/` is not listed in directory structure (but is documented in Module Index)
   - **Impact**: Documentation inconsistency
   - **Fix**: Add `services/subagent/` to directory structure

---

## Improvement Opportunities

1. **Enforce Layering in CI/Linting**
   - Add ruff or similar tool to detect and block imports that violate layering rules
   - Example: Create a custom ruff rule or use import-linter to enforce "services may not import from adapters"

2. **Refactor SSRF Protection**
   - Move `validate_url_safe()` and `UnsafeURLError` from `services/url.py` to `utils/url.py`
   - This would make `utils/url.py` the canonical home for all URL utilities
   - Update all adapter imports to use `utils/url.py`

3. **Move trend_detector out of services**
   - `services/trend_detector.py` is used by adapters for topic classification
   - Consider if this should be in utils or if the adapter should use a different pattern

4. **Add Architecture Decision Records (ADRs)**
   - Document why certain architectural decisions were made
   - This helps future developers understand the "why" behind the code structure

5. **Update Directory Structure Diagram**
   - Include all files mentioned in the Module Index
   - Make it consistent with the actual codebase structure

---

## Action Items

| Priority | Action | Files to Modify |
|----------|--------|-----------------|
| HIGH | Fix bidirectional imports between services and adapters | `services/crawling.py`, all adapter files |
| HIGH | Update architecture document to reflect actual layering or enforce rules | `architecture/overview.md` + code |
| MEDIUM | Move SSRF utilities to `utils/url.py` | `services/url.py`, `utils/url.py`, adapter files |
| LOW | Add `extensions.py` to directory structure diagram | `architecture/overview.md` |
| LOW | Add `services/subagent/` to directory structure diagram | `architecture/overview.md` |
| LOW | Consider adding import-linter or custom ruff rules to enforce architecture | `pyproject.toml` or `ruff.toml` |
