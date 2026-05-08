# Architecture Review: overview.md

**Date:** 2026-05-08  
**Reviewer:** Architecture Review Agent  
**Document:** `/Users/davidbowman/projects/ainews/architecture/overview.md`

---

## Summary

| Category | Status |
|----------|--------|
| Module Structure | Partially accurate (subagent location incorrect) |
| External Integrations | Mostly accurate (providers list incomplete) |
| Security Architecture | Implemented as documented |
| Configuration Files | All present and accurate |
| Directory Structure | Partially accurate |

---

## 1. Verified Items (Correct)

### Module Structure (Correct)
- `app.py`, `config.py`, `extensions.py`, `constants.py`, `celery_app.py` all exist at root
- `models/`, `schemas/`, `utils/`, `prompts/`, `tests/` directories exist as documented

### Key Configuration Files (Correct)
- `pipeline.yaml` - 307 lines, contains all documented sections (selector, researcher, writer, editor, newsletter, subagent, memory, stages, experiments, schedule)
- `providers.yaml` - 146 lines, contains LLM and search provider definitions
- `sources.yaml` - 70 lines, contains hackernews, techcrunch, arstechnica, theverge sources
- `topics.yaml` - 28 lines, contains ai, privacy, security, programming, hardware topics
- `config.py` - 326 lines, contains Development, Production, Testing configurations

### LLM Providers (Mostly Correct)
Document claims: ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter

Actual implementation includes: ollama-local, openai, anthropic, gemini, deepseek, groq, openrouter, xai, togetherai, fireworks, cerebras, zai, minimax, opencode

**Note:** Implementation has MORE providers than documented (undocumented functionality).

### Search Providers (Correct)
- duckduckgo (enabled, default)
- google (disabled)
- searxng (disabled)

### Security Architecture (All Implemented)

| Feature | Implementation | Status |
|---------|---------------|--------|
| Fail-Closed | `config.py:254-278` ProductionConfig.validate() checks all required secrets | Verified |
| TOTP 2FA | `services/totp.py` with verify_token, generate_backup_codes, verify_backup_code, consume_backup_code | Verified |
| Session Binding | `routes/admin/__init__.py:73-84` checks IP and User-Agent on each request | Verified |
| HMAC Webhooks | `services/webhooks.py:102-120` generate_signature, `services/task_security.py:31-96` task signing | Verified |
| SSRF Protection | `utils/url.py:243-262` validate_url_safe with DNS resolution check | Verified |
| Login Lockout | `routes/admin/__init__.py:151-161` Redis Lua script + in-memory fallback | Verified |

### Infrastructure (Correct)
- Web Server: Granian (mentioned in docs, not in overview.md but confirmed elsewhere)
- Task Queue: Celery + Redis
- Database: SQLite (WAL mode)
- Cache: Redis
- Email: SMTP with connection pooling

---

## 2. Discrepancies

### Directory Structure Issue: `subagent/` Location

**Document says:**
```
ainews/
├── subagent/              # Tool-enabled LLM agents
```

**Actual:**
```
services/subagent/         # Tool-enabled LLM agents (NOT at top level)
├── chain.py
├── conditions.py
├── config.py
├── middleware.py
├── prompt_templates.py
├── registry.py
├── runner.py
├── tools.py
└── utils.py
```

**Impact:** High - The subagent module is a major component but is not at the top level as documented.

### LLM Providers: Documentation Missing Providers

**Document says:** ollama, openai, anthropic, gemini, deepseek, groq, openrouter

**Actual (from providers.yaml):**
- ollama-local (enabled, default)
- openai, anthropic, gemini, deepseek, groq, openrouter (disabled)
- Additional: xai, togetherai, fireworks, cerebras, zai, minimax, opencode (all disabled)

**Impact:** Medium - Document underrepresents the system's capabilities.

---

## 3. Issues Found

### Issue 1: Layering Violation - Adapters Import from Services

**Location:** Multiple files in `adapters/` import from `services.url`

| File | Line | Import |
|------|------|--------|
| `adapters/api.py` | 11 | `from services.url import validate_url_safe` |
| `adapters/rss.py` | 12 | `from services.url import validate_url_safe` |
| `adapters/session.py` | 8 | `from services.url import UnsafeURLError, validate_url_safe` |
| `adapters/web.py` | 14 | `from services.url import UnsafeURLError, validate_url_safe` |

**Architecture Principle Violated:** "Adapters should NOT contain business logic or import from services"

**AGENTS.md states:** SSRF protection is now in `utils/url.py` for clean layering. Adapters import from `utils/url.py`, services re-export from utils.

**Current State:** Adapters import from `services.url` (which re-exports from `utils/url.py`). This is a backward-compatibility shim but technically violates the clean layering principle since adapters are reaching into the services layer.

**Recommendation:** Update adapters to import directly from `utils/url.py` and remove the `services/url.py` backward-compat shim.

### Issue 2: Duplicate Code in URL Validation

**Location:** Both `utils/url.py` and `services/url.py` implement nearly identical SSRF protection logic.

`utils/url.py:100-115` and `services/url.py:32-47` both define `_BLOCKED_NETWORKS` with the same values.

This violates DRY (Don't Repeat Yourself) and could lead to divergence.

**Recommendation:** Have `services/url.py` import directly from `utils/url.py` rather than duplicating the logic.

### Issue 3: services/ Layer Has TYPE_CHECKING Import from adapters

**Location:** `services/crawling.py:13`
```python
from adapters.base import RawItem
```

This is inside a `TYPE_CHECKING` block which is acceptable for type hints only, but the comment doesn't indicate this is a TYPE_CHECKING import. Need to verify if it's properly guarded.

### Issue 4: `subagent/` Not at Top Level

The subagent module documented at `ainews/subagent/` is actually located at `services/subagent/`. This is a significant structural discrepancy that could cause confusion during development.

**Impact:** High - Developers following the documentation would look for `subagent/` at the top level and not find it.

---

## 4. Security Considerations (All Addressed)

### Verified Security Implementations

1. **Fail-Closed Production Startup** (`config.py:253-278`)
   - Checks SECRET_KEY, ADMIN_PASSWORD, CELERY_TASK_SECRET
   - Validates SECRET_KEY is 64-character hex string
   - Validates CELERY_TASK_SECRET is at least 32 characters
   - Calls `_validate_llm_providers()` to check provider configuration

2. **TOTP 2FA with Backup Codes** (`services/totp.py`)
   - `generate_secret()` creates TOTP secrets
   - `verify_token()` validates TOTP tokens
   - `generate_backup_codes()` creates 8 codes
   - `verify_backup_code()` validates without consuming
   - `consume_backup_code()` marks code as used

3. **Session Hijacking Protection** (`routes/admin/__init__.py:73-84`)
   - Stores IP and User-Agent in session on login
   - Validates both on each authenticated request
   - Clears admin session if mismatch detected

4. **HMAC Webhooks** (`services/webhooks.py:102-120`)
   - `generate_signature()` creates HMAC-SHA256 signatures
   - Timestamp replay protection in webhook handling

5. **HMAC Task Signing** (`services/task_security.py`)
   - `verify_task()` returns False when CELERY_TASK_SECRET is unset (fail-closed)
   - All beat-scheduled tasks use HMAC signing

6. **SSRF Protection** (`utils/url.py:243-262`)
   - Blocks private/reserved IP ranges
   - Performs DNS resolution to catch DNS rebinding attacks
   - 5-second DNS cache with 1024 max entries

7. **Login Lockout** (`routes/admin/__init__.py:151-161`)
   - Redis Lua script for atomic check-and-record (prevents TOCTOU)
   - 5 failed attempts in 15 minutes triggers 15-minute lockout
   - In-memory fallback when Redis unavailable

---

## 5. Missing/Undocumented Functionality

### Not Documented in overview.md

1. **Additional LLM Providers:** xai, togetherai, fireworks, cerebras, zai, minimax, opencode
2. **Newsletter Pipeline:** Reader, writer, editor stages for executive summary generation
3. **Subagent Chains:** research_deep and edit_review chain configurations
4. **Experiments:** A/B testing framework with prompt variants
5. **Memory System:** Trend memory with consolidation and TTL management
6. **Metrics & Tracing:** OpenTelemetry integration, cost tracking

---

## 6. Recommendations

### High Priority

1. **Update Directory Structure in overview.md**
   - Document `services/subagent/` instead of `subagent/`
   - Or move subagent to top level if cleaner architecture desired

2. **Update LLM Providers List**
   - Document all 14 providers in providers.yaml
   - Or consolidate to the 8 documented providers

### Medium Priority

3. **Fix Layering Violations**
   - Update adapters to import from `utils/url.py` directly
   - Remove duplicate SSRF code from `services/url.py`

4. **Add Missing Documentation**
   - Newsletter pipeline stages
   - Subagent chain configurations
   - Experiment framework
   - Memory system

### Low Priority

5. **Consider Adding __init__.py exports** for subagent module at services level

---

## 7. Conclusion

The architecture document is largely accurate but has several discrepancies:

1. **Critical:** `subagent/` directory location is wrong
2. **High:** Layering violations in URL validation imports
3. **Medium:** LLM providers list is incomplete
4. **Low:** Missing documentation for some features

The security architecture is well-implemented and matches the documentation. The core structure is sound.

**Overall Assessment:** The document requires updates to accurately reflect the implementation, particularly around directory structure and provider list.

---

*End of Review*
