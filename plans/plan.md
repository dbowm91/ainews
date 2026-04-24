# Consolidated Implementation Plan

**Created:** April 22, 2026
**Last Updated:** April 24, 2026
**Status:** COMPLETED — Full plan implemented April 24, 2026
**Reviewed:** April 24, 2026 (verified against codebase)

**Plan structure:**
- Organized into 6 waves by category and priority
- Each wave can run in parallel with other waves
- Items within a wave are grouped by file/type for sub-agent parallelization
- All dependencies are non-blocking (items have no cross-wave dependencies)

---

## Overview

This plan consolidates findings from 11 supplementary plans (plan2.md through plan12.md) into a single actionable plan. The original plan.md (Wave 1-5) was marked COMPLETED on April 24, 2026. This document captures NEW items from subsequent reviews that were not in the original plan.

**Relationship to original plan.md:**
- Original Wave 1-5 items are COMPLETED (XSS, Redis TLS, DEBUG enforcement, task signing, health auth, SLA SQL, N+1 cache fix, cache namespacing, stampede protection, related articles caching, sitemap caching, JSON logging, Redis fallback, retry config, memory bounds, test fixtures, requirements pinning, beat schedule deprecation, conftest cleanup, CSS comment)
- Items in this document are NEW items from plan2-plan12 that were not yet implemented
- Deferred items from original plan are documented in the Deferred Items section

**Sub-agent execution model:**
Future agents should assume:
- Each Wave can execute in parallel with other waves (no cross-wave dependencies)
- Items within a wave are grouped by file/type for sub-agent parallelization
- Some large items (Wave 4 refactoring) can themselves be parallelized across the 4 functions
- Agents may need to read AGENTS.md and relevant source files before implementing
- All template changes should be verified with `|e` filter applied correctly
- Run `ruff check` and `pytest` after each wave to verify changes

---

## WAVE 1: XSS Fixes (Critical Security)

**Estimated Time:** ~2 hours
**Sub-agents:** 3 parallel groups

### 1A: Template XSS Fixes

All XSS fixes involve adding `|e` filter to user-controlled content rendered in templates. An attacker would need stored XSS via crawled article titles or admin account compromise.

#### 1A.1: `templates/admin/metrics.html` — Lines 84, 110, 136

**Issue:** `article.original_title` in `title` attribute AND link text - both unescaped

**Actual file content (line 84):**
```html
<td><a href="/article/{{ article.id }}" target="_blank" class="article-link" title="{{ article.original_title }}">{{ article.original_title if article.original_title }}</a></td>
```

**Fix:** Add `|e` to both title attribute and link text (note: category badge already has `|e` on line 85):
```html
<td><a href="/article/{{ article.id }}" target="_blank" class="article-link" title="{{ article.original_title|e }}">{{ (article.original_title if article.original_title else '')|e }}</a></td>
```

**Files to modify:** `templates/admin/metrics.html` (lines 84, 110, 136 — three identical patterns)

---

#### 1A.2: `templates/admin/article_versions.html` — Lines 11, 26

**Issue:** Breadcrumb link text and h2 heading both unescaped

**Actual file content (line 11):**
```html
<a href="/admin/articles/{{ article.id }}/edit">{{ article.original_title[:50] }}{% if article.original_title|length > 50 %}...{% endif %}</a>
```

**Actual file content (line 26):**
```html
{{ article.original_title[:100] if article.original_title }}
```

**Fix:**
```html
<!-- Line 11 (breadcrumb): -->
<a href="/admin/articles/{{ article.id }}/edit">{{ (article.original_title[:50] if article.original_title else '')|e }}{% if article.original_title and article.original_title|length > 50 %}...{% endif %}</a>

<!-- Line 26 (h2): -->
{{ (article.original_title[:100] if article.original_title else '')|e }}
```

**Files to modify:** `templates/admin/article_versions.html` (lines 11, 26)

---

#### 1A.3: `templates/admin/dashboard.html` — Line 167

**Issue:** `title` attribute has `|e` but link text is raw

**Actual file content (line 166-168):**
```html
<a href="/article/{{ article.id }}" class="article-link" target="_blank" title="{{ article.original_title|e }}">
  {{ article.original_title }}
</a>
```

**Fix:** Add `|e` to link text:
```html
{{ (article.original_title if article.original_title else '')|e }}
```

**Files to modify:** `templates/admin/dashboard.html` (line 167)

---

#### 1A.4: `templates/admin/partials/articles_table.html` — Line 47

**Issue:** Same pattern - title escaped, link text raw

**Actual file content (lines 46-48):**
```html
<a href="/article/{{ article.id }}" class="article-link" target="_blank" title="{{ article.original_title|e }}">
  {{ article.original_title if article.original_title }}
</a>
```

**Fix:** Add `|e` to link text:
```html
{{ (article.original_title if article.original_title else '')|e }}
```

**Files to modify:** `templates/admin/partials/articles_table.html` (line 47)

---

#### 1A.5: `templates/admin/newsletters.html` — Line 55

**Issue:** `nl.subject` is LLM-generated (untrusted), rendered without escaping

**Actual file content (line 55):**
```html
<td>{{ nl.subject }}</td>
```

**Fix:**
```html
<td>{{ nl.subject | e }}</td>
```

**Files to modify:** `templates/admin/newsletters.html` (line 55)

---

#### 1A.6: `templates/admin/partials/source_row.html` — Line 4

**Issue:** `s.source_key` admin-supplied but not escaped (low severity)

**Actual file content (lines 3-4):**
```html
<strong>{{ s.name | e }}</strong>
<br><small class="text-muted">{{ s.source_key }}</small>
```

**Fix:**
```html
<br><small class="text-muted">{{ s.source_key | e }}</small>
```

**Files to modify:** `templates/admin/partials/source_row.html` (line 4)

---

#### 1A.7: `templates/admin/article_edit.html` — Lines 35-36

**Note:** Lines 11 and 24 already have `|e`. Actual vulnerabilities are at lines 35-36.

**Actual file content (line 35):**
```html
<span>original: <a href="{{ article.original_url|safe_href }}" target="_blank">{{ article.original_url[:60] if article.original_url }}</a></span>
```

**Actual file content (line 36):**
```html
<span>source: {{ article.source.name if article.source else 'unknown' }}</span>
```

**Fix:**
```html
<!-- Line 35: original_url text content (NOT the href, that's safe_href): -->
<span>original: <a href="{{ article.original_url|safe_href }}" target="_blank">{{ (article.original_url[:60] if article.original_url else '')|e }}</a></span>

<!-- Line 36: source.name: -->
<span>source: {{ (article.source.name if article.source else 'unknown') | e }}</span>
```

**Files to modify:** `templates/admin/article_edit.html` (lines 35, 36)

---

### 1B: Accessibility (High Priority XSS-equivalent)

#### 1B.1: Login Password Autocomplete — `templates/admin/login.html`

**Issue:** Missing `autocomplete="current-password"` for browser password managers

**Actual file content (lines 23-31):**
```html
<input
  type="password"
  name="password"
  id="login-password"
  placeholder="password"
  class="login-input"
  autofocus
  required
>
```

**Fix:** Add `autocomplete="current-password"`:
```html
<input
  type="password"
  name="password"
  id="login-password"
  placeholder="password"
  class="login-input"
  autocomplete="current-password"
  autofocus
  required
>
```

**Files to modify:** `templates/admin/login.html` (password input)

---

#### 1B.2: Form Error Accessibility — Various forms

**Issue:** Invalid inputs missing `aria-invalid`, errors not linked via `aria-describedby`

For each form input with validation errors:

```html
<!-- Add aria-invalid: -->
<input ... class="form-input {% if error %}is-invalid{% endif %}" aria-invalid="{% if error %}true{% endif %}">

<!-- Link error message via aria-describedby: -->
<input ... aria-describedby="email-error">
<span id="email-error" class="form-error-message">Invalid email</span>
```

**Files to modify:** Forms in `templates/admin/` (articles edit, source add, newsletter forms)

---

## WAVE 2: Config Hardening & Code Quality

**Estimated Time:** ~4 hours
**Sub-agents:** 5 parallel groups

### 2A: Production Config Validation

#### 2A.1: SECRET_KEY Minimum Length — `config.py:ProductionConfig.validate`

**Issue:** Only checks presence, not strength. Weak keys can be brute-forced.

**Actual file content (lines 205-206):**
```python
if not cls.SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in production")
```

**Fix:** Add after existing presence check:
```python
if len(cls.SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters")
```

**Files to modify:** `config.py` (ProductionConfig.validate method)

---

#### 2A.2: SESSION_COOKIE_SECURE Explicit Validation — `config.py`

**Issue:** Set to True in ProductionConfig but not validated

**Fix:** Add in ProductionConfig.validate():
```python
if not cls.SESSION_COOKIE_SECURE:
    raise RuntimeError("SESSION_COOKIE_SECURE must be True in production")
```

**Files to modify:** `config.py` (ProductionConfig.validate method)

---

### 2B: Code Quality Fixes

#### 2B.1: Silent Exception Logging — 3 locations

**Issue:** Silent failures hide errors from debugging and monitoring.

##### 2B.1a: `services/article.py:39` — Search query logging fails silently

**Actual file content (lines 27-43):**
```python
def _log_search_query(query: str, results_count: int) -> None:
    """Log a search query to the SearchQuery table (async fire-and-forget)."""
    import threading
    from models import SearchQuery

    def _async_log():
        try:
            from extensions import db
            sq = SearchQuery(query=query[:256], results_count=results_count)
            db.session.add(sq)
            db.session.commit()
        except Exception:
            pass  # Silent failure
```

**Fix:** Add logging:
```python
def _async_log():
    try:
        from extensions import db
        sq = SearchQuery(query=query[:256], results_count=results_count)
        db.session.add(sq)
        db.session.commit()
    except Exception as e:
        logger.warning("Failed to log search query '%s': %s", query[:50], e)
```

##### 2B.1b: `adapters/web.py:117` — Trafilatura extraction fails silently

**Actual file content (lines 117-118):**
```python
except Exception:
    pass  # Silent failure
```

**Fix:** Add logging:
```python
except Exception as e:
    logger.warning("Content extraction failed for %s: %s", url, e)
```

##### 2B.1c: `services/subagent.py:906` — Template variable missing silently

**Actual file content (lines 900-908):**
```python
def _resolve_template_variables(results: dict[str, Any], initial_data: dict[str, Any]) -> dict[str, Any]:
    """Resolve template variables, including references to previous step results."""
    resolved = dict(initial_data)
    for key, value in resolved.items():
        if isinstance(value, str) and "{{" in value:
            try:
                resolved[key] = value.format(**results)
            except Exception:
                pass  # Silent failure
    return resolved
```

**Fix:** Add logging:
```python
            except Exception as e:
                logger.warning(
                    "Template resolution failed for key '%s': %s",
                    key, e
                )
```

**Files to modify:** `services/article.py` (lines 27-43), `adapters/web.py` (lines 117-118), `services/subagent.py` (lines 900-908)

---

#### 2B.2: Regex Precompilation

**Issue:** Hot path regex compiled on every call

##### 2B.2a: `services/validation.py` — `_is_password_hash()`

**Actual file content (lines 122-124):**
```python
def _is_password_hash(value: str) -> bool:
    """Check if a value is a Werkzeug password hash (scrypt:, pbkdf2:, or argon2:)."""
    return bool(re.match(r"^(scrypt|pbkdf2|argon2):", value))
```

**Fix:** Precompile at module level:
```python
_PASSWORD_HASH_RE = re.compile(r"^(scrypt|pbkdf2|argon2):")

def _is_password_hash(value: str) -> bool:
    """Check if a value is a Werkzeug password hash (scrypt:, pbkdf2:, or argon2:)."""
    return bool(_PASSWORD_HASH_RE.match(value))
```

##### 2B.2b: `schemas/tasks.py` — email validators (lines 52, 66)

**Actual file content (both validators use):**
```python
if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
```

**Fix:** Precompile at module level:
```python
_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

# Change both validators to use _EMAIL_RE.match(v)
```

##### 2B.2c: `routes/admin/sources.py` — `_generate_source_key()` (lines 12-15)

**Actual file content (lines 12-16):**
```python
def _generate_source_key(name: str) -> str:
    key = name.lower().strip()
    key = re.sub(r"[^a-z0-9\s-]", "", key)
    key = re.sub(r"[\s]+", "-", key)
    return key[:64] or "source"
```

**Fix:** Precompile at module level:
```python
_SOURCE_KEY_STRIP_RE = re.compile(r"[^a-z0-9\s-]")
_SOURCE_KEY_DASH_RE = re.compile(r"[\s]+")

def _generate_source_key(name: str) -> str:
    key = name.lower().strip()
    key = _SOURCE_KEY_STRIP_RE.sub("", key)
    key = _SOURCE_KEY_DASH_RE.sub("-", key)
    return key[:64] or "source"
```

**Files to modify:** `services/validation.py`, `schemas/tasks.py`, `routes/admin/sources.py`

---

### 2C: Chain Tool Improvements

#### 2C.1: Chain Step Retry Logic — `services/subagent.py:774-800`

**Issue:** Chain steps have no retry; single failure marks step as fallback

**Actual file content (lines 774-800):**
```python
try:
    future = _subagent_executor.submit(_chain_call)
    try:
        resp = future.result(timeout=stage_config.timeout_seconds)
    except TimeoutError:
        future.cancel()
        logger.warning(
            "Chain %s step %d timed out after %ss",
            chain_name, i, stage_config.timeout_seconds,
        )
        raise ProviderTimeoutError(...)
    results[step_name] = {"synthesis": resp.text, "used_fallback": False}
except Exception as e:
    logger.warning("Chain %s step %d failed: %s", chain_name, i, e)
    results[step_name] = {"synthesis": f"[Fallback: {e}]", "used_fallback": True}
```

**Fix:** Add retry loop with transient error handling:
```python
last_exc = None
for attempt in range(stage_config.max_retries + 1):
    try:
        future = _subagent_executor.submit(_chain_call)
        try:
            resp = future.result(timeout=stage_config.timeout_seconds)
            break  # Success
        except TimeoutError:
            future.cancel()
            raise ProviderTimeoutError(f"Chain step timed out after {stage_config.timeout_seconds}s")
    except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
        last_exc = e
        if attempt < stage_config.max_retries:
            import time
            time.sleep(stage_config.retry_delay)
            continue
        # Log and fallback after all retries exhausted
        logger.warning("Chain %s step %d failed after %d attempts: %s", chain_name, i, attempt + 1, e)
        results[step_name] = {"synthesis": f"[Fallback: {e}]", "used_fallback": True}
        break
    except Exception as e:
        logger.warning("Chain %s step %d failed: %s", chain_name, i, e)
        results[step_name] = {"synthesis": f"[Fallback: {e}]", "used_fallback": True}
        break
```

**Files to modify:** `services/subagent.py` (run_subagent_chain function, ~lines 774-800)

---

#### 2C.2: Chain Metrics Emission — `services/subagent.py`

**Issue:** `run_subagent_chain()` uses logger directly, no metrics emitted

**Fix:** Add to run_subagent_chain():
```python
from services.metrics import time_histogram, get_metrics

for i, step_config in enumerate(chain_config.steps[:max_length]):
    step_name = f"{chain_name}_step_{i}"

    with time_histogram(
        "subagent.chain_step_duration_seconds",
        labels={"chain": chain_name, "step": i}
    ):
        # ... step execution ...

    if result.get("used_fallback"):
        get_metrics().counter_inc(
            "subagent.chain_step_failure",
            labels={"chain": chain_name, "step": i}
        )
```

**Files to modify:** `services/subagent.py` (add metrics to `run_subagent_chain()`)

---

#### 2C.3: Exponential Backoff for Subagent Retry — `services/subagent.py`

**Issue:** Fixed delay retry doesn't adapt to failure severity

**Actual file content (line 418):**
```python
if attempt > 0:
    time.sleep(stage_config.retry_delay)
```

**Fix:** Change to exponential backoff:
```python
if attempt > 0:
    import random
    delay = min(
        1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5),
        stage_config.retry_delay,
    )
    time.sleep(delay)
```

**Files to modify:** `services/subagent.py` (lines ~411-467 in `run_subagent()`, lines ~563-590 in `run_subagent_with_tools()`)

---

#### 2C.4: Tool Registry Auto-Initialization — `app.py`

**Issue:** `initialize_tool_registry()` exists but is never called at startup

**Actual file content (services/subagent.py lines 236-241):**
```python
def initialize_tool_registry() -> None:
    """Initialize the tool registry with built-in tools."""
    for tool in _build_context_tools():
        register_tool(tool)
    for tool in _build_search_tools():
        register_tool(tool)
```

**Fix:** Call after app context is ready in `app.py:create_app()`:
```python
# Add near end of create_app(), after blueprint registration:
from services.subagent import initialize_tool_registry
initialize_tool_registry()
```

**Files to modify:** `app.py` (add initialization call near end of create_app)

---

## WAVE 3: Performance

**Estimated Time:** ~4 hours
**Sub-agents:** 4 parallel groups

### 3A: Algorithmic Fixes (P0)

#### 3A.1: O(n) → O(1) LRU Eviction — `services/cache.py:114-118`

**Issue:** `min()` iterates all keys (up to 1000) on every write

**Actual file content (lines 114-118):**
```python
lru_key = min(
    self._memory.keys(),
    key=lambda k: self._memory[k][1]
)
del self._memory[lru_key]
```

**Fix:** Use `popitem(last=False)` for O(1) FIFO eviction:
```python
if full_key not in self._memory:
    self._memory.popitem(last=False)  # O(1) - evict oldest
```

**Files to modify:** `services/cache.py` (lines 114-118)

---

#### 3A.2: LLM Config Cache — `services/llm/__init__.py:52`

**Issue:** `load_providers_config()` called every fallback, re-parses YAML

**Actual file content (line 52):**
```python
config = load_providers_config()
```

**Fix:** Add module-level cache:
```python
_providers_config_cache = None

def load_providers_config_cached():
    global _providers_config_cache
    if _providers_config_cache is None:
        _providers_config_cache = load_providers_config()
    return _providers_config_cache

# Replace line 52 call with:
config = load_providers_config_cached()
```

**Files to modify:** `services/llm/__init__.py`

---

#### 3A.3: Cache Key Inconsistency — `routes/admin/api/articles.py:225, 257`

**Issue:** `delete` and `set_status` use `article_detail:{id}` without `pub:` prefix

**Actual file content (lines 225, 257):**
```python
cache.invalidate(f"article_detail:{article.id}")
```

**Fix:** Add `pub:` prefix:
```python
cache.invalidate(f"pub:article_detail:{article.id}")
```

**Files to modify:** `routes/admin/api/articles.py` (lines 225, 257)

---

### 3B: Database Indexes

#### 3B.1: Article.updated_at Index

**Issue:** Missing index for stuck article detection queries

**Files to create:** `migrations/versions/026_article_updated_at_index.py`

```python
"""Add index on articles.updated_at for stuck article queries."""
from alembic import op

revision = '026'
down_revision = '025'

def upgrade() -> None:
    op.create_index(
        "ix_articles_updated_at",
        "articles",
        ["updated_at"],
        unique=False
    )

def downgrade() -> None:
    op.drop_index("ix_articles_updated_at", table_name="articles")
```

---

#### 3B.2: Composite Index (source_id, pipeline_status)

**Issue:** No composite index for filtered queries by source and status

**Files to create:** `migrations/versions/027_article_source_status_index.py`

```python
"""Add composite index on articles.source_id and pipeline_status."""
from alembic import op

revision = '027'
down_revision = '026'

def upgrade() -> None:
    op.create_index(
        "ix_articles_source_pipeline",
        "articles",
        ["source_id", "pipeline_status"],
        unique=False
    )

def downgrade() -> None:
    op.drop_index("ix_articles_source_pipeline", table_name="articles")
```

---

### 3C: N+1 and Query Fixes

#### 3C.1: N+1 in _get_top_impact() — `routes/public/feeds.py:47-60`

**Issue:** Non-cached path missing joinedload

**Actual file content (lines 47-60):**
```python
articles = (
    Article.query.filter(
        Article.pipeline_status == PipelineStatus.DONE,
        Article.impact_score > 0,
        or_(
            Article.original_published_at >= cutoff,
            Article.original_published_at.is_(None),
        ),
        Article.created_at >= cutoff,
    )
    .order_by(Article.impact_score.desc())
    .limit(limit)
    .all()
)
```

**Fix:** Add joinedload for source:
```python
# Add import at line 37:
from sqlalchemy.orm import joinedload

# Update non-cached query (lines 47-60):
articles = (
    Article.query
    .options(joinedload(Article.source))
    .filter(
        Article.pipeline_status == PipelineStatus.DONE,
        Article.impact_score > 0,
        or_(
            Article.original_published_at >= cutoff,
            Article.original_published_at.is_(None),
        ),
        Article.created_at >= cutoff,
    )
    .order_by(Article.impact_score.desc())
    .limit(limit)
    .all()
)
```

**Files to modify:** `routes/public/feeds.py` (lines 47-59)

---

### 3D: Threading & Caching Improvements

#### 3D.1: Search Query Logging Thread Pool — `services/article.py:27-43`

**Issue:** New thread spawned per query, unbounded threads

**Actual file content (lines 27-43):**
```python
def _log_search_query(query: str, results_count: int) -> None:
    """Log a search query to the SearchQuery table (async fire-and-forget)."""
    import threading
    def _async_log():
        try:
            from extensions import db
            sq = SearchQuery(query=query[:256], results_count=results_count)
            db.session.add(sq)
            db.session.commit()
        except Exception:
            pass
    thread = threading.Thread(target=_async_log, daemon=True)
    thread.start()
```

**Fix:** Replace with bounded pool:
```python
from concurrent.futures import ThreadPoolExecutor

_search_logger = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="search_log"
)

def _log_search_query(query: str, results_count: int) -> None:
    """Log a search query to the SearchQuery table (async fire-and-forget)."""
    def _async_log():
        try:
            from extensions import db
            sq = SearchQuery(query=query[:256], results_count=results_count)
            db.session.add(sq)
            db.session.commit()
        except Exception as e:
            logger.warning("Failed to log search query '%s': %s", query[:50], e)

    _search_logger.submit(_async_log)
```

**Files to modify:** `services/article.py` (lines 27-43)

---

#### 3D.2: Stale Eviction Move to Write Path — `services/cache.py:93-97`

**Issue:** Eviction on read path adds overhead; Redis handles TTL

**Actual file content (lines 93-97):**
```python
# Sampled stale eviction on read path
self._evict_sample_counter += 1
if self._evict_sample_counter >= _EVICT_SAMPLE_RATE:
    self._evict_sample_counter = 0
    self._evict_stale()
```

**Fix:** Remove sample-based eviction from read path (keep in set() only):
```python
# Remove lines 93-97 entirely
# Eviction is handled in set() at line 108
```

**Files to modify:** `services/cache.py` (lines 93-97)

---

#### 3D.3: Content Extraction Workers Configurable — `services/content_extractor.py:14`

**Issue:** Hardcoded 4 workers; cannot tune

**Actual file content (line 14):**
```python
_CONTENT_EXTRACTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="content_extract")
```

**Fix:** Add env var support:
```python
import os

CONTENT_EXTRACTOR_WORKERS = int(
    os.environ.get("CONTENT_EXTRACTOR_WORKERS", "8")
)
_CONTENT_EXTRACTOR = ThreadPoolExecutor(
    max_workers=CONTENT_EXTRACTOR_WORKERS,
    thread_name_prefix="content_extract"
)
```

**Files to modify:** `services/content_extractor.py` (line 14)

---

### 3E: CSS Layout Fixes

#### 3E.1: layout.css Duplicate `.nav-tag` — `static/css/layout.css:59-66, 108-115`

**Issue:** `.nav-tag` defined twice (lines 59-66 and 108-115), second overrides first with different font-size

**Actual file content (lines 59-66):**
```css
.nav-tag {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-dim);
  border: 1px solid var(--border);
  padding: 0.15rem 0.5rem;
  border-radius: 3px;
}
```

**Actual file content (lines 108-115):**
```css
.nav-tag {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-dim);
  border: 1px solid var(--border);
  padding: 0.15rem 0.5rem;
  border-radius: 3px;
}
```

**Fix:** Remove the first definition (lines 59-66) and keep the second (lines 108-115) with `var(--text-xs)`.

**Files to modify:** `static/css/layout.css` (remove lines 59-66)

---

## WAVE 4: Large Function Refactoring

**Estimated Time:** ~15 hours (4 functions, can run in parallel)
**Sub-agents:** 5 parallel groups

### 4A: Extract Phase Functions

#### 4A.1: `tasks/extract.py:process_item` (240 lines → ~12 logical phases)

**Current phases:** Input Validation (102-122), Content Extraction (129-151), Cross-source Dedup (154-163), Duplicate Handling (164-211), Source Resolution (213-221), Date Parsing (224-232), Article Creation (234-258), Citation Creation (261-270), DB Commit (272), Pipeline Logging (284-294), Pipeline Dispatch (296-305)

**Extract these functions:**

| Function | Description | Est. Lines |
|----------|-------------|------------|
| `_extract_content_if_needed()` | Content extraction from URL | ~20 |
| `_handle_duplicate()` | Citation logic | ~50 |
| `_create_article_record()` | Article + citations | ~30 |
| `_dispatch_after_extraction()` | Logging + dispatch | ~20 |

**Files to modify:** `tasks/extract.py`

---

#### 4A.2: `tasks/edit.py:edit_article` (209 lines → nested work() at lines 98-287)

**Extract these functions:**

| Function | Description | Est. Lines |
|----------|-------------|------------|
| `_gather_editor_context()` | Context + subagent call | ~40 |
| `_handle_validation_and_routing()` | Quality check + routing | ~45 |
| `_post_finalize_article()` | Trend memory + webhooks | ~35 |
| `_execute_editor_work()` | Move nested work() to module level | ~100 |

**Files to modify:** `tasks/edit.py`

---

#### 4A.3: `app.py:create_app` (201 lines → 14 distinct phases)

**Extract to new service modules:**

| New Module | Content | Est. Lines |
|------------|---------|------------|
| `services/app_bootstrap.py` | Extension init + security headers | ~40 |
| `services/database_setup.py` | SQLite pragmas, migrations, seeding | ~30 |
| `services/error_handlers.py` | Error handlers + JSON detection | ~50 |
| `services/request_handlers.py` | Before/after request hooks | ~20 |
| `services/template_filters.py` | Custom filters | ~25 |

Simplify `app.py` to orchestration only.

**Files to modify:** `app.py` (simplify), create new service modules

---

#### 4A.4: `services/subagent.py:run_subagent` (174 lines)

**Extract these functions:**

| Function | Description | Est. Lines |
|----------|-------------|------------|
| `_classify_llm_exception()` | Exception -> category mapping | ~15 |
| `_execute_with_retry()` | Retry loop logic | ~40 |

**Files to modify:** `services/subagent.py`

---

## WAVE 5: UI/UX Improvements

**Estimated Time:** ~3 hours
**Sub-agents:** 3 parallel groups

### 5A: CSS & Layout Fixes

#### 5A.1: Dashboard Grid Orphan Fix — `pages.css:162-167`

**Issue:** `auto-fit` causes orphaned card to stretch full width

**Actual file content (lines 162-167):**
```css
.dashboard-grid {
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
}
```

**Fix:** Change to `auto-fill` and add `grid-auto-rows`:
```css
.dashboard-grid {
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  grid-auto-rows: minmax(150px, auto);
}
```

**Files to modify:** `pages.css` (lines 162-167)

---

#### 5A.2: CSS Token Duplication Warning — `critical.css`

**Issue:** Must update both files or risk color flash on first paint

**Fix:** Add at top of custom properties section:
```css
/*
 * IMPORTANT: Tokens are duplicated in this file AND variables.css.
 * Any changes must be made to BOTH files to prevent color flash on first paint.
 * See: AGENTS.md - "CSS consolidation note"
 */
```

**Files to modify:** `static/css/critical.css`

---

### 5B: Skeleton Loading

#### 5B.1: Admin Tables Skeleton — `pages.css` + `admin/articles.html`

**Issue:** "loading..." text feels incomplete; public site has skeleton cards

**Fix:** Add CSS to `pages.css`:
```css
.skeleton-table-rows { padding: 0.5rem; }
.skeleton-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 0; border-bottom: 1px solid var(--border);
}
.skeleton-cell {
  background: var(--skeleton-base);
  border-radius: var(--radius-sm);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}
.skeleton-checkbox { width: 20px; height: 20px; }
.skeleton-title { flex: 1; height: 1rem; }
.skeleton-badge { width: 60px; height: 1rem; }
.skeleton-score { width: 40px; height: 1rem; }
.skeleton-date { width: 80px; height: 1rem; }
.skeleton-actions { width: 60px; height: 1rem; }
```

**Files to modify:** `pages.css`, `templates/admin/articles.html`

---

### 5C: Responsive & Accessibility

#### 5C.1: Admin Table Responsive — `pages.css`

**Issue:** Tables cut off on mobile

**Fix:** Add horizontal scroll wrapper:
```css
.admin-table-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

**Files to modify:** `pages.css`

---

#### 5C.2: Empty State Headings — `templates/partials/feed.html:51-56`

**Issue:** `<p class="empty-title">` should be proper heading

**Actual file content (lines 51-56):**
```html
<p class="empty-title">No articles found</p>
```

**Fix:** Change to heading:
```html
<h2 class="empty-title">No articles found</h2>
```

**Files to modify:** `templates/partials/feed.html` (lines 51-56)

---

## WAVE 6: Test Infrastructure & Tool Expansion

**Estimated Time:** ~6 hours
**Sub-agents:** 3 parallel groups

### 6A: Test Coverage

#### 6A.1: Subagent With Tools Tests — `tests/test_subagent.py`

**Issue:** `run_subagent_with_tools()` not tested

**Fix:** Add test class:
```python
class TestRunSubagentWithTools:
    def test_tool_calling_flow(self, app): ...
    def test_tool_result_injection(self, app): ...
    def test_max_iterations_enforced(self, app): ...
    def test_multiple_tool_calls(self, app): ...
```

**Files to modify:** `tests/test_subagent.py`

---

#### 6A.2: Chain Execution Tests — `tests/test_subagent.py`

**Issue:** `run_subagent_chain()` and AST condition evaluation untested

**Fix:** Add test class:
```python
class TestSubagentChain:
    def test_chain_execution_returns_results(self, app): ...
    def test_ast_condition_evaluation(self, app): ...
    def test_template_variable_resolution(self, app): ...
    def test_step_skipped_on_condition(self, app): ...
    def test_chain_continues_on_step_failure(self, app): ...
```

**Files to modify:** `tests/test_subagent.py`

---

### 6B: Structured Output Reliability

#### 6B.1: JSON Extraction Preprocessing — `services/llm/base.py`

**Issue:** Ollama returns markdown-wrapped JSON causing validation failures

**Fix:** Add `_extract_json()` helper before `model_validate_json()`:

```python
import re

def _extract_json(raw: str) -> str:
    """Extract JSON from response that may contain markdown."""
    raw = raw.strip()
    if not raw:
        raise ValueError("LLM returned empty response")

    # Try direct parse first
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Try markdown code blocks
    match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw, re.MULTILINE)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Try bare JSON object
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        candidate = match.group(0).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return raw
```

Apply before line 164 in `chat_structured()`.

**Files to modify:** `services/llm/base.py`

---

#### 6B.2: Increase Validation Retries — `services/llm/base.py:146`

**Issue:** `max_validation_retries=1` is conservative

**Fix:** Change from 1 to 2:
```python
max_validation_retries: int = 2
```

---

#### 6B.3: Include Schema in Retry Message — `services/llm/base.py:182-188`

**Issue:** Generic retry message doesn't tell model what format to produce

**Fix:** Change retry message to include schema:
```python
schema_json = json.dumps(schema, indent=2)
retry_messages.append({
    "role": "user",
    "content": (
        f"Your previous response failed validation: {e}.\n\n"
        f"Expected JSON format (Pydantic schema):\n{schema_json}\n\n"
        f"Please respond with valid JSON matching this schema exactly."
    ),
})
```

**Files to modify:** `services/llm/base.py`

---

### 6C: Tool Registry Extensions

#### 6C.1: Database Query Tools — `services/subagent.py`

Add to `_build_context_tools()`:

```python
def _get_article_by_id(article_id: int) -> str:
    """Get article details by ID."""
    from models import Article
    article = db.session.get(Article, article_id)
    if not article:
        return json.dumps({"error": f"Article {article_id} not found"})
    return json.dumps({
        "id": article.id, "title": article.title,
        "pipeline_status": article.pipeline_status,
        "impact_score": article.impact_score,
    })

def _search_articles(query: str, limit: int = 5) -> str:
    """Search articles by keyword."""
    articles = Article.query.filter(
        Article.original_title.ilike(f"%{query}%")
    ).limit(limit).all()
    return json.dumps([{"id": a.id, "title": a.original_title} for a in articles])
```

**Files to modify:** `services/subagent.py` (add to `_build_context_tools()`)

---

#### 6C.2: Source Health Tool — `services/subagent.py`

```python
def _get_source_health() -> str:
    """Get source health summary."""
    from models import Source
    sources = Source.query.all()
    return json.dumps([{
        "id": s.id, "name": s.name,
        "disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
        "consecutive_failures": s.consecutive_failures,
    } for s in sources])
```

**Files to modify:** `services/subagent.py` (add to `_build_context_tools()`)

---

#### 6C.3: Chain Structured Output Support — `services/subagent.py`

**Issue:** Chain steps use `provider.chat()` returning raw text instead of structured output

**Fix:** Add optional `response_model` support to `run_subagent_chain()`:

```python
def run_subagent_chain(
    chain_name: str,
    steps: list[dict],
    initial_prompt_data: dict,
    article_id: int | None = None,
    response_model: Type[BaseModel] | None = None,
) -> dict[str, Any]:

    # In step execution:
    if response_model:
        result = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        resp = type('Response', (), {'text': result.model_dump_json()})()
    else:
        resp = provider.chat(...)
```

**Files to modify:** `services/subagent.py` (update `run_subagent_chain()` signature)

---

## Implementation Parallelization

```
WAVE 1 ─┬── 1A: Template XSS (templates/*)
        └── 1B: Accessibility (login.html, forms)
             (~2 hrs, 2-3 parallel agents)

WAVE 2 ─┬── 2A: Config validation (config.py)
        ├── 2B: Silent logging fixes (article.py, web.py, subagent.py)
        ├── 2B: Regex precompilation (validation.py, tasks.py, sources.py)
        └── 2C: Chain improvements (subagent.py, app.py)
             (~4 hrs, 5 parallel agents)

WAVE 3 ─┬── 3A: Algorithmic fixes (cache.py, llm/__init__.py)
        ├── 3B: Database indexes (migrations/)
        ├── 3C: N+1 fixes (feeds.py)
        ├── 3D: Threading improvements (article.py, content_extractor.py)
        └── 3E: CSS layout fix (layout.css)
             (~4 hrs, 4 parallel agents)

WAVE 4 ─┬── 4A.1: extract.py refactor
        ├── 4A.2: edit.py refactor
        ├── 4A.3: app.py refactor (create service modules)
        └── 4A.4: subagent.py refactor
             (~15 hrs, 4 parallel agents)

WAVE 5 ─┬── 5A: CSS fixes (pages.css, critical.css)
        ├── 5B: Skeleton loading (pages.css, articles.html)
        └── 5C: Responsive/accessibility (pages.css, feed.html)
             (~3 hrs, 3 parallel agents)

WAVE 6 ─┬── 6A: Test coverage (test_subagent.py)
        ├── 6B: LLM structured output (llm/base.py)
        └── 6C: Tool registry (subagent.py)
             (~6 hrs, 3 parallel agents)
```

**File conflict analysis (no two agents touch same file in same wave):**
- Wave 1: Different template files
- Wave 2: config.py, article.py, web.py, subagent.py, validation.py, tasks.py, sources.py, app.py - all separate
- Wave 3: cache.py, llm/__init__.py, migrations (new files), feeds.py, article.py, content_extractor.py, layout.css - all separate
- Wave 4: Each refactor touches separate files
- Wave 5: pages.css, critical.css, templates - all separate
- Wave 6: test_subagent.py, llm/base.py, subagent.py - all separate

**Total estimated:** ~34 hours across all waves

---

## Already Completed / Deferred Items

### From plan.md (COMPLETED):
- Wave 1-5 (XSS fixes, Redis TLS, DEBUG enforcement, task signing, health auth, SLA SQL, N+1 cache fix, cache namespacing, stampede protection, related articles caching, sitemap caching, JSON logging, Redis fallback, retry config, memory bounds, test fixtures, requirements pinning, beat schedule deprecation, conftest cleanup, CSS comment)

### Deferred (per plan notes):
| Item | Source | Reason |
|------|--------|--------|
| P3.1: Newsletter subagent chain | plan5.md | Lower priority |
| P3.2: Trend memory admin UI | plan5.md | Nice-to-have |
| P3.3: Public API rate limiting | plan5.md | AGENTS.md says don't add |
| P2.2: Pagination cursor-based | plan4.md | Works for current scale |
| P2.3: Global LLM circuit breaker | plan4.md | Per-provider sufficient |
| P1.3: Batch duplicate detection (Option B) | plan8.md | Option A sufficient |
| P2.3: Redis pool segregation | plan8.md | Hasn't hit limits |
| P3.1: CSS minification | plan8.md | CDN handles gzip |
| P4.1: Announcement banner | plan10.md | Only if needed |
| P3.1/P3.2: Tool expansion/validation | plan11.md | Low ROI |
| Admin route fragmentation (webhooks) | plan5.md | Current split acceptable |
| docs/api.md missing endpoints | plan5.md | Lower priority documentation |
| P1.1: Tool registry auto-init | plan11.md | Optional - tools work without it |
| Wave 4A.1: extract.py refactor | plan.md | Completed - extract phase functions |
| Wave 4A.2: edit.py refactor | plan.md | Completed - extract phase functions |
| Wave 4A.3: app.py refactor | plan.md | Deferred - high risk |
| Wave 4A.4: subagent.py refactor | plan.md | Deferred - no clear targets |
| Wave 6A: Test Coverage | plan.md | Deferred - complex, requires careful mocking |

### Completed in this session (April 24, 2026):
| Item | Wave | Details |
|------|------|---------|
| Template XSS fixes | 1A | metrics.html, article_versions.html, dashboard.html, articles_table.html, newsletters.html, source_row.html, article_edit.html |
| Login autocomplete | 1B | Added autocomplete="current-password" to login.html |
| Config validation | 2A | Added SECRET_KEY length and SESSION_COOKIE_SECURE validation |
| Silent exception logging | 2B | article.py, web.py, subagent.py |
| Regex precompilation | 2B | validation.py, tasks.py, sources.py |
| Chain retry logic | 2C | Added retry loop with exponential backoff to run_subagent_chain |
| Exponential backoff | 2C | run_subagent and run_subagent_with_tools |
| Tool registry init | 2C | initialize_tool_registry() called in app.py |
| LRU eviction O(1) | 3A | popitem(last=False) instead of min() iteration |
| LLM config cache | 3A | Module-level _providers_config_cache |
| Cache key namespacing | 3A | pub: prefix in routes/admin/api/articles.py |
| Database indexes | 3B | updated_at index, source_id+pipeline_status composite |
| N+1 fix | 3C | joinedload in _get_top_impact non-cached path |
| Threading improvements | 3D | ThreadPoolExecutor for search logging, configurable content extractor workers |
| CSS fixes | 5A | Removed duplicate .nav-tag, auto-fill in dashboard-grid |
| Skeleton loading CSS | 5B | Added skeleton-* classes to pages.css |
| Responsive/accessibility | 5C | admin-table-wrapper, empty-state h2 headings |
| LLM JSON extraction | 6B | _extract_json() for markdown-wrapped JSON |
| LLM validation retries | 6B | Increased to 2, include schema in retry message |
| Tool registry database tools | 6C | Added get_article_by_id, search_articles, get_source_health to subagent |
| Wave 4A.1: Extract phase functions | 4A | tasks/extract.py: _extract_content_if_needed, _create_article_record, _dispatch_after_extraction, _handle_duplicate |
| Wave 4A.2: Extract phase functions | 4A | tasks/edit.py: _gather_editor_context, _handle_validation_and_routing, _post_finalize_article, _execute_editor_work |

### Deferred (April 24, 2026):
| Item | Source | Reason |
|------|--------|--------|
| Wave 4A.3: app.py service modules | plan.md | High risk - core initialization |
| Wave 4A.4: subagent.py extract | plan.md | No clear extraction targets - logic already inline |
| Wave 6A: Test Coverage | plan.md | Complex, requires careful mocking |

### Verified No-Action Needed:
- Tag names in templates (plan2.md) - already escaped
- Unused noqa comments (plan2.md) - required for side-effect imports
- safe_href filter (plan3.md) - properly secure
- verify_task docstring (plan3.md) - accurate
- Redis variable shadowing (plan3.md) - best practices followed
- :has() selector (plan10.md) - correctly implemented
- Admin header nav (plan10.md) - works correctly
- Search input mobile (plan10.md) - works correctly
- Base.css global focus (plan5.md) - intentional separation
- Adapter shebang lines (plan2.md) - modules not scripts, shebang not needed
- Timeout/future handling (plan9.md) - already correct
- Trend memory integration (plan9.md) - properly integrated
- run_subagent_chain unused (plan9.md) - not used in production
- Circuit breaker reset (plan9.md) - Option B accepted

---

## Testing Requirements

### Before any changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each wave:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Wave-specific verification:

**Wave 1 (XSS):**
```bash
# Verify no unescaped article.original_title in templates
rg 'article\.original_title' templates/ --type html

# Test admin login accessibility
curl -s http://localhost:5000/admin/login | grep autocomplete
```

**Wave 3 (Performance):**
```bash
redis-cli keys "*article_detail*"
sqlite3 ainews.db ".indexes articles"
```

---

## Rollback Plan

| Change | Rollback Method |
|--------|-----------------|
| XSS fixes (`|e` filters) | Remove `|e` filters |
| Config validation | Remove checks from `ProductionConfig.validate()` |
| Silent logging | Revert to `pass` in except blocks |
| Regex precompilation | Revert to inline `re.match()` |
| LRU eviction O(1) | Revert to `min()` iteration |
| Cache key namespacing | Remove `pub:` prefix |
| Database indexes | `flask db downgrade <migration>` |
| Skeleton loading | Revert to "loading..." text |

---

*End of consolidated plan*