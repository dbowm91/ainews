# Comprehensive Codebase Improvement Plan - Plan 6

**Date:** 2026-04-28
**Scope:** Critical bugs, security issues, architecture improvements from codebase deep-dive
**Priority Order:** Critical → High → Medium → Low

---

## Executive Summary

Comprehensive deep-dive of the ainews codebase identified **24 distinct issues** across all system layers:

- **3 Critical** (will cause runtime crashes/failures)
- **6 High** (security, data integrity, observability)
- **12 Medium** (architecture, performance, testing)
- **3 Low** (polish, documentation)

**Estimated Impact:**
- **Correctness:** Fix 3 critical bugs (state machine violations, version creation order, env var resolution)
- **Security:** Strengthen 2 security patterns (silent exceptions, service framework imports)
- **Observability:** Fix Prometheus metrics, add missing experiment tracking
- **Architecture:** Improve separation of concerns, persistence, modern patterns
- **User Experience:** Fix PWA functionality (broken service worker)

---

## 🔴 CRITICAL PRIORITY

### 1. Fix Pipeline State Machine Violations

**Problem:** Multiple tasks attempt invalid state transitions that will raise `InvalidStateTransitionError` at runtime.

**Invalid Transitions Found:**
| File | Line | Invalid Transition | Status |
|------|------|---------------------|--------|
| `tasks/select.py` | 170 | `PENDING → SKIPPED` | **INVALID** |
| `tasks/research.py` | 207 | `RESEARCHING → REVIEW` | **INVALID** |
| `tasks/write.py` | 116 | `WRITING → REVIEW` | **INVALID** |
| `tasks/pipeline.py` | 280 | `PENDING → FAILED` | **INVALID** |
| `tasks/retry.py` | 195 | Direct assignment bypasses validation | **BUG** |

**Current `VALID_TRANSITIONS` (constants.py:40-49):**
```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.EDITING: frozenset([PipelineStatus.REVIEW, PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.REVIEW: frozenset([PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.DONE: frozenset(),
    PipelineStatus.SKIPPED: frozenset(),
    PipelineStatus.FAILED: frozenset([PipelineStatus.PENDING]),
}
```

**Fix Options:**

**Option A (Recommended):** Update `VALID_TRANSITIONS` to allow these flows if intentional:
```python
# constants.py - UPDATE:
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.REVIEW, PipelineStatus.SKIPPED]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.REVIEW, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.REVIEW, PipelineStatus.FAILED]),
    # ... rest unchanged
}
```

**Option B:** Change code to route through valid states:
- `select.py:170`: PENDING → REVIEW → SKIPPED
- `research.py:207`: RESEARCHING → FAILED (not REVIEW)
- `write.py:116`: WRITING → FAILED (not REVIEW)

**Also Fix Direct Assignments:**
```python
# tasks/research.py:225 - CHANGE FROM:
article.pipeline_status = PipelineStatus.WRITING
# CHANGE TO:
_transition_article_status(article, PipelineStatus.WRITING)

# tasks/write.py:134 - CHANGE FROM:
article.pipeline_status = PipelineStatus.EDITING
# CHANGE TO:
_transition_article_status(article, PipelineStatus.EDITING)

# tasks/retry.py:195 - CHANGE FROM:
article.pipeline_status = PipelineStatus.FAILED
# CHANGE TO:
_transition_article_status(article, PipelineStatus.FAILED)
```

**Files to modify:** `constants.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/pipeline.py`, `tasks/retry.py`

---

### 2. Fix Version Creation Order in Edit Pipeline

**Problem:** In `tasks/edit.py:326-335`, article is MODIFIED before version is created, capturing new state instead of pre-edit state.

**Current Code (BUG):**
```python
# tasks/edit.py lines 326-335:
article.final_article = result_json  # MODIFIED FIRST!
article.original_ai_article = result_json

# Version created AFTER modification (captures NEW state!)
create_article_version(article, change_reason="pipeline_edit", changed_by="pipeline:editor")
```

**Fix:** Move `create_article_version()` call to BEFORE modification:
```python
# tasks/edit.py - FIX:
# Create version BEFORE modification (capture OLD state)
create_article_version(article, change_reason="pipeline_edit", changed_by="pipeline:editor")

# Then modify article
article.final_article = result_json
article.original_ai_article = result_json
```

**Compare:** `routes/admin/articles.py:241-246` correctly creates version BEFORE modification.

**File to modify:** `tasks/edit.py`

---

### 3. Fix providers.yaml Environment Variable Resolution

**Problem:** `providers.yaml` uses `${ENV_VAR}` syntax (e.g., `${OPENAI_API_KEY}`), but `resolve_env_vars()` is only called in `schemas/pipeline.py`, NOT in `schemas/llm.py`.

**Impact:** API keys in `providers.yaml` are NOT being resolved to actual values at runtime.

**Current Code (WRONG):**
```python
# schemas/llm.py - _load_providers_config_from_file():
def _load_providers_config_from_file(path):
    p = Path(path)
    if not p.exists():
        return LLMProvidersConfig()
    raw = load_yaml_file(p)
    return LLMProvidersConfig(**raw)  # MISSING: resolve_env_vars(raw)!
```

**Fix:**
```python
# schemas/llm.py - FIX:
def _load_providers_config_from_file(path):
    p = Path(path)
    if not p.exists():
        return LLMProvidersConfig()
    raw = load_yaml_file(p)
    from schemas.common import resolve_env_vars
    raw = resolve_env_vars(raw)  # ADD THIS LINE
    return LLMProvidersConfig(**raw)
```

**File to modify:** `schemas/llm.py`

---

## 🟡 HIGH PRIORITY

### 4. Fix Prometheus Histogram Metrics

**Problem:** `services/metrics.py:117-128` `get_prometheus()` outputs `_count` and `_sum` but **missing `_bucket` entries** required by Prometheus for proper histogram queries.

**Current Code (BROKEN):**
```python
# services/metrics.py lines 117-128:
def _get_prometheus(self):
    # ...
    for key, values in self._histograms.items():
        lines.append(f"{key}_count {len(values)}")
        lines.append(f"{key}_sum {sum(values)}")
        # MISSING: _bucket entries!
    return "\n".join(lines)
```

**Fix:** Implement proper histogram bucket output:
```python
# services/metrics.py - FIX:
def _get_prometheus(self):
    # ...
    for key, values in self._histograms.items():
        # Define standard Prometheus buckets
        buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]
        for bucket in buckets:
            count = sum(1 for v in values if v <= bucket)
            lines.append(f'{key}_bucket{{le="{bucket}"}} {count}')
        lines.append(f"{key}_count {len(values)}")
        lines.append(f"{key}_sum {sum(values)}")
    return "\n".join(lines)
```

**File to modify:** `services/metrics.py`

---

### 5. Fix Silent Exception Handling Violations

**Problem:** AGENTS.md states "Exceptions should not be silently swallowed unless the catch is for a deliberate fallback. Use %-formatting in log calls." Two violations found:

**Violation 1:** `services/health.py:184`
```python
# WRONG:
except Exception:
    pass  # SILENT - no logging!
```

**Fix:**
```python
# FIX:
except Exception as e:
    logger.debug("Failed to get version info: %s", e)
```

**Violation 2:** `services/subagent.py:1088`
```python
# WRONG:
except Exception:
    return False  # SILENT - no logging!
```

**Fix:**
```python
# FIX:
except Exception as e:
    logger.debug("Expression evaluation failed: %s", e)
    return False
```

**Files to modify:** `services/health.py`, `services/subagent.py`

---

### 6. Add Missing A/B Experiment Tests

**Problem:** The A/B experiment system has minimal test coverage. `tests/test_task_select.py` has 2 out of 4 tests **skipped** with reason "Mock integration issue - needs refactoring".

**Missing Test Coverage:**
- No dedicated `tests/test_experiments.py` file
- No tests for `_assign_experiment_group()` deterministic hashing
- No tests for variant prompt selection in `writer.py`/`editor.py`
- No tests for edge cases (invalid experiment groups, disabled experiments)

**Recommended Test Structure:**
```python
# tests/test_experiments.py:
def test_experiment_group_assignment_deterministic():
    """Same article_id + salt = same group."""
    from tasks.select import _assign_experiment_group
    group1 = _assign_experiment_group(123, "salt123")
    group2 = _assign_experiment_group(123, "salt123")
    assert group1 == group2

def test_experiment_group_distribution():
    """Verify 70/15/15 split approximately."""
    from tasks.select import _assign_experiment_group
    results = {"control": 0, "variant_a": 0, "variant_b": 0}
    for i in range(1000):
        group = _assign_experiment_group(i, "salt123")
        results[group] += 1
    assert 650 <= results["control"] <= 750  # ~70%
    assert 125 <= results["variant_a"] <= 175  # ~15%
    assert 125 <= results["variant_b"] <= 175  # ~15%

def test_variant_prompt_selection():
    """Test writer uses variant prompt when experiment_group set."""
    from services.writer import get_writer_system_prompt
    from models import Article
    
    article = Article()
    article.experiment_group = "variant_a"
    # Mock pipeline config with variants
    # Assert variant prompt returned
```

**File to create:** `tests/test_experiments.py`

---

### 7. Fix PWA Service Worker

**Problem:** PWA functionality is broken - service worker can't control root paths, and offline fallback doesn't exist.

**Issues:**
1. **Wrong scope:** Service worker at `/static/js/service-worker.js` - scope limited to `/static/js/`
2. **Missing offline route:** `/offline/` referenced in SW but doesn't exist in Flask routes
3. **Missing PNG icons:** Only SVG provided (production PWAs need 192x192, 512x512)

**Fix 1 - Move SW to root or add scope parameter:**
```javascript
// static/js/app.js - FIX registration:
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/js/service-worker.js', {
      scope: '/'
    }).then(function(registration) {
      console.log('SW registered with scope:', registration.scope);
    }).catch(function(error) {
      console.log('SW registration failed:', error);
    });
  });
}
```

**Fix 2 - Create offline route and template:**
```python
# routes/public/__init__.py - ADD:
@public_bp.route("/offline/")
def offline():
    return render_template("offline.html"), 200
```

**Fix 3 - Fix manifest icon purpose field:**
```json
// static/manifest.json - FIX:
"icons": [
  {
    "src": "/static/svg/ai.svg",
    "sizes": "any 192x192 512x512",
    "type": "image/svg+xml",
    "purpose": "any maskable"
  }
]
```

**Files to modify:** `static/js/app.js`, `routes/public/__init__.py`, `static/manifest.json`, create `templates/offline.html`

---

### 8. Persist Circuit Breaker State

**Problem:** Circuit breakers in `services/circuit_breaker.py` are in-memory only - state is lost on Celery worker restart.

**Current State:** Circuit state stored in `_breakers: dict[str, CircuitBreaker]` module variable.

**Recommended Fix:** Store state in Redis:
```python
# services/circuit_breaker.py - ADD Redis persistence:
def _get_breaker_state(name: str) -> dict | None:
    """Load circuit state from Redis."""
    try:
        redis_client = get_redis()
        key = f"ainews:circuit:{name}"
        data = redis_client.get(key)
        if data:
            import json
            return json.loads(data)
    except Exception:
        pass
    return None

def _save_breaker_state(name: str, state: dict):
    """Save circuit state to Redis with TTL."""
    try:
        redis_client = get_redis()
        key = f"ainews:circuit:{name}"
        import json
        redis_client.setex(key, 3600, json.dumps(state))  # 1 hour TTL
    except Exception:
        pass

# In CircuitBreaker methods, call _save_breaker_state() after state changes
```

**File to modify:** `services/circuit_breaker.py`

---

### 9. Configure OpenTelemetry Exporter

**Problem:** `services/logging_utils.py:49-54` creates `BatchSpanProcessor` with `NoopExporter` - traces never leave the process.

**Current Code:**
```python
# services/logging_utils.py:
def get_tracer(name: str = "ainews"):
    if not _tracers:
        provider = TracerProvider()
        processor = BatchSpanProcessor(NoopExporter())  # NO EXPORT!
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    # ...
```

**Fix:** Add OTLP exporter configuration:
```python
# services/logging_utils.py - FIX:
def get_tracer(name: str = "ainews"):
    if not _tracers:
        provider = TracerProvider()
        
        # Check for OTLP endpoint configuration
        otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otel_endpoint:
            from opentelemetry.exporter.otlp import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otel_endpoint)
            processor = BatchSpanProcessor(exporter)
        else:
            # Noop for development
            processor = BatchSpanProcessor(NoopExporter())
        
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    # ...
```

**File to modify:** `services/logging_utils.py`

---

### 10. Fix `publish_scheduled_articles` Error Handling

**Problem:** `tasks/scheduler.py` `publish_scheduled_articles` task is missing critical error handling that all other tasks have.

**Missing:**
- `autoretry_for` decorator parameter
- `SoftTimeLimitExceeded` exception handling
- `retry_backoff`, `retry_jitter` parameters

**Fix:**
```python
# tasks/scheduler.py - FIX:
@shared_task(
    bind=True,
    soft_time_limit=120,
    time_limit=180,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def publish_scheduled_articles(self):
    try:
        # ... existing code ...
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("publish_scheduled_articles exceeded soft time limit")
        raise
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.remove()
```

**File to modify:** `tasks/scheduler.py`

---

### 11. Align DNS Cache TTL

**Problem:** Inconsistency between `services/url.py:37` (`_DNS_CACHE_TTL = 60`) and `config.py:57` (`DNS_CACHE_TTL = safe_int("DNS_CACHE_TTL", 300)`).

**Current State:** Actual default used is 60 seconds (from `url.py`), but documentation says 300.

**Fix Options:**

**Option A:** Align `url.py` to use config:
```python
# services/url.py - FIX:
from services.config_utils import get_config_with_default
_DNS_CACHE_TTL = get_config_with_default("DNS_CACHE_TTL", 60)
```

**Option B:** Update `config.py` default to 60:
```python
# config.py - FIX:
DNS_CACHE_TTL = safe_int("DNS_CACHE_TTL", 60)
```

**Files to modify:** `services/url.py` and/or `config.py`

---

### 12. Make Services Framework-Agnostic

**Problem:** Several services import Flask/Celery directly, creating framework coupling.

**Violations:**
| File | Framework Import | Issue |
|------|-------------------|-------|
| `services/config_unified.py` | `from flask import current_app` | Should accept config as param |
| `services/config_utils.py` | `from flask import current_app` | Should accept config as param |
| `services/email.py` | `from flask import current_app` | Should accept config as param |
| `services/audit.py` | `from flask import request` | Should accept request info as param |
| `services/pipeline_degradation.py` | `from celery.utils.log import get_task_logger` | Use standard logging |
| `services/pipeline_failure.py` | `from celery.utils.log import get_task_logger` | Use standard logging |

**Fix Pattern (for config_unified.py):**
```python
# BEFORE:
def get_config():
    from flask import current_app
    return current_app.config["..."]

# AFTER:
def get_config(app_config=None):
    if app_config is None:
        from flask import current_app
        app_config = current_app.config
    return app_config["..."]
```

**Files to modify:** 7 service files

---

## 🟢 MEDIUM PRIORITY

### 13. Add SQLite WAL Checkpoint Management

**Problem:** No automatic WAL checkpoint configuration. WAL file can grow unbounded if checkpoints can't complete.

**Fix 1 - Add PRAGMAs to app.py:**
```python
# app.py - ADD to set_sqlite_pragma():
cursor.execute("PRAGMA wal_autocheckpoint=4000")  # Checkpoint every 4MB
cursor.execute("PRAGMA journal_size_limit=52428800")  # 50MB WAL limit
```

**Fix 2 - Add periodic checkpoint task:**
```python
# tasks/cleanup.py - ADD:
@shared_task
def wal_checkpoint():
    """Run RESTART checkpoint during low-traffic periods."""
    from flask import current_app
    with current_app.app_context():
        db.session.execute("PRAGMA wal_checkpoint(RESTART)")
        current_app.logger.info("WAL checkpoint completed")
```

**Fix 3 - Add to Celery beat schedule in config.py:**
```python
# config.py - ADD to get_beat_schedule():
"wal-checkpoint": {
    "task": "tasks.cleanup.wal_checkpoint",
    "schedule": crontab(hour="*", minute="*/30"),
},
```

**Files to modify:** `app.py`, `tasks/cleanup.py`, `config.py`

---

### 14. Move Metrics to Redis (Scalability)

**Problem:** `services/metrics.py` and `services/cost_tracker.py` store metrics in-memory. Each Celery worker has its own metrics instance.

**Current State:** `MetricsCollector` uses Python data structures (dict, deque) - not shared across workers.

**Fix:** Follow `services/pipeline_monitor.py` pattern - use Redis for metrics storage.

**Implementation:** (Large change - consider for future release)

---

### 15. Add Experiment Result Tracking

**Problem:** A/B experiment system assigns groups and uses variant prompts, but doesn't track outcomes (completion rates, impact scores by variant).

**Missing:**
- No metrics emitted for experiment variants
- No admin endpoint to view experiment results
- No mechanism to conclude experiments

**Recommended Addition:**
```python
# services/metrics.py - ADD:
def track_experiment_variant(variant: str, stage: str):
    """Track which experiment variant was used."""
    from services.metrics import get_metrics
    metrics = get_metrics()
    metrics.counter_inc("experiment.variant_used", labels={"variant": variant, "stage": stage})

# In tasks/select.py after group assignment, emit metric
from services.metrics import track_experiment_variant
track_experiment_variant(group, "select")
```

**File to modify:** `services/metrics.py`, `tasks/select.py`, `tasks/write.py`, `tasks/edit.py`

---

### 16. Fix Tests Task `publish_scheduled_articles`

**Problem:** Identified in deep-dive that `tasks/scheduler.py` has missing error handling.

**Already covered in High Priority #10.**

---

### 17. Add `stop_grace_period` to Docker Services

**Problem:** Default stop timeout is 10s, but Granian needs 30s to finish in-flight requests.

**Fix:**
```yaml
# docker-compose.yml - ADD to web service:
services:
  web:
    # ... existing config ...
    stop_grace_period: 30s  # Override default 10s for Granian
```

**File to modify:** `docker-compose.yml`

---

### 18. Fix `_COMPILED_PATTERNS` Dead Code in `trend_detector.py`

**Problem:** Module-level `_COMPILED_PATTERNS` appears unused in favor of `_COMPILED_CACHE` with lazy loading.

**Fix:** Remove unused `_COMPILED_PATTERNS` variable if `_COMPILED_CACHE` is preferred.

**File to modify:** `services/trend_detector.py`

---

### 19. Standardize `PipelineLogger` to Use %-formatting

**Problem:** `services/logging_utils.py:155-159` `PipelineLogger._format()` uses f-strings instead of %-formatting.

**Current Code:**
```python
# services/logging_utils.py:
def _format(self, msg: str, **context) -> str:
    if context:
        ctx = json.dumps(context, default=str)
        return f"[{self.stage}] {msg} | {ctx}"  # f-string!
    return f"[{self.stage}] {msg}"              # f-string!
```

**Fix:** Since this is a helper method (not a direct log call), it's acceptable. But for consistency, consider:
```python
# Option: Accept f-strings here since it's a formatter, not a logger call
# OR refactor to use %-formatting if strictly following AGENTS.md
```

**File to modify:** `services/logging_utils.py` (low priority - can defer)

---

### 20. Add `/offline/` Route for PWA

**Already covered in High Priority #7.**

---

### 21. Create `tests/test_csrf.py` for CSRF Protection Tests

**Problem:** No tests for `@validate_csrf_json` decorator.

**Recommended Tests:**
```python
# tests/test_csrf.py:
def test_csrf_reject_missing_token(client):
    """Test CSRF protection rejects missing token."""
    response = client.post(
        "/admin/api/articles/bulk",
        json={"article_ids": [1], "action": "delete"}
    )
    assert response.status_code == 403

def test_csrf_accept_valid_token(client):
    """Test CSRF protection accepts valid token."""
    # Get token from cookie, submit with X-CSRFToken header
    pass  # Implementation depends on test setup
```

**File to create:** `tests/test_csrf.py`

---

### 22. Refactor `models.py` into Package

**Problem:** `models.py` is 486 lines with 14 models. Consider splitting into package.

**Recommended Structure:**
```
models/
├── __init__.py          # Exports all models
├── base.py              # Base classes, helper functions
├── article.py           # Article, Citation, ArticleVersion, ArticleMetric
├── source.py            # Source, SourceHealth
├── newsletter.py        # Newsletter, Subscriber
├── pipeline.py          # PipelineRun, PipelineLog
├── webhook.py           # Webhook, WebhookEvent
├── search.py            # SearchQuery
├── audit.py             # AuditLog
├── trend.py             # TrendMemory, TopicNote
└── share.py             # ShareConfig
```

**Note:** This is a large refactor - consider for future release.

---

## 🟢 LOW PRIORITY

### 23. Add L1 Cache Monitoring

**Problem:** `services/cache.py` `ResponseCache` L1 (in-memory) cache has no hit/miss tracking.

**Fix:** Add counters to `MetricsCollector`:
```python
# services/cache.py - ADD to get():
def get(self, key):
    # ... L1 hit:
    if cached:
        get_metrics().counter_inc("cache.l1_hits")
    # ... L2 hit:
    else if redis_cached:
        get_metrics().counter_inc("cache.l2_hits")
    # ... miss:
    else:
        get_metrics().counter_inc("cache.misses")
```

**File to modify:** `services/cache.py`

---

### 24. Populate `docs/` Directory

**Problem:** `/home/sugarwookie/projects/ainews/docs/` directory exists but is empty.

**Recommended Files:**
- `docs/architecture.md` - System overview, component interactions
- `docs/deployment.md` - Production deployment guide
- `docs/troubleshooting.md` - Common issues and solutions
- `docs/monitoring.md` - Metrics, alerts, dashboards

**Files to create:** 4 markdown files in `docs/`

---

## Implementation Order

### Phase 1: Critical (Do First - 1-2 Hours)
1. Fix pipeline state machine violations (#1)
2. Fix version creation order in edit pipeline (#2)
3. Fix providers.yaml env var resolution (#3)

### Phase 2: High Priority (Do Next - 3-4 Hours)
4. Fix Prometheus histogram metrics (#4)
5. Fix silent exception handling (#5)
6. Add missing A/B experiment tests (#6)
7. Fix PWA service worker (#7)
8. Persist circuit breaker state (#8)
9. Configure OpenTelemetry exporter (#9)
10. Fix `publish_scheduled_articles` (#10)
11. Align DNS cache TTL (#11)
12. Make services framework-agnostic (#12)

### Phase 3: Medium Priority (Do After - 4-6 Hours)
13. Add SQLite WAL checkpoint management (#13)
14. Move metrics to Redis (#14) [Consider for future release]
15. Add experiment result tracking (#15)
16. Add `stop_grace_period` to Docker (#17)
17. Fix dead code in trend_detector.py (#18)
18. Standardize PipelineLogger (#19) [Low priority]
19. Add `/offline/` route (#20) [Already in #7]
20. Create CSRF tests (#21)
21. Refactor models.py (#22) [Consider for future release]

### Phase 4: Low Priority (Polish - 1-2 Hours)
22. Add L1 cache monitoring (#23)
23. Populate docs/ directory (#24)

---

## Testing Strategy

### Pre-Implementation
```bash
# Run existing tests
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Post-Phase 1 (Critical Fixes)
```bash
# Test state machine fixes
.venv/bin/python -m pytest tests/test_pipeline.py -x -v
.venv/bin/python -m pytest tests/test_pipeline_e2e.py -x -v

# Test version creation fix
.venv/bin/python -m pytest tests/test_task_edit.py -x -v

# Test providers.yaml fix
.venv/bin/python -m pytest tests/test_config.py -x -v
```

### Post-Phase 2 (High Priority)
```bash
# Test Prometheus fix
curl http://localhost:5000/admin/api/metrics | grep "_bucket"

# Test PWA fix
curl -I http://localhost:5000/  # Check service-worker.js loads
# Check browser DevTools > Application > Service Workers

# Test experiment tests
.venv/bin/python -m pytest tests/test_experiments.py -x -v
```

### Post-Phase 3 (Medium Priority)
```bash
# Test WAL checkpoint
sqlite3 instance/ainews.db "PRAGMA wal_checkpoint(RESTART);"

# Test OpenTelemetry (if OTLP endpoint configured)
# Check Jaeger/Zipkin for traces
```

---

## Rollback Plan

### For Script/Config Changes
1. **Keep backups** of original files:
   ```bash
   cp tasks/edit.py tasks/edit.py.bak
   cp constants.py constants.py.bak
   # etc.
   ```

2. **Git-based rollback:**
   ```bash
   git diff  # Review changes
   git checkout -- tasks/edit.py  # Revert single file
   git reset --hard HEAD~1  # Revert last commit
   ```

### For Database Migration (if adding migration 030)
```bash
# Test migration
.venv/bin/flask db upgrade
.venv/bin/flask db downgrade 029  # Rollback
```

### For Docker Changes
```bash
# Previous image still available via:
docker images
docker tag <previous-image-id> ainews-web:previous
# If new build fails, retag:
docker tag ainews-web:previous ainews-web:latest
```

---

## Summary

| Priority | Items | Est. Time | Impact |
|----------|-------|-----------|--------|
| 🔴 Critical | 3 | 1-2 hours | **HIGH** - Prevents runtime crashes |
| 🟡 High | 9 | 3-4 hours | **HIGH** - Security, observability |
| 🟢 Medium | 9 | 4-6 hours | **MEDIUM** - Architecture, performance |
| 🟢 Low | 2 | 1-2 hours | **LOW** - Polish |
| **Total** | **23** | **8-12 hours** | |

**Recommended First Session:** Complete Phase 1 (Critical) - these are blocking issues that can cause runtime failures.

**Files Modified (Estimated):** 20+ files + 1 new migration + 1 new test file

**Success Metrics:**
- [ ] No `InvalidStateTransitionError` in logs
- [ ] Version history captures pre-edit state
- [ ] `providers.yaml` env vars resolve correctly
- [ ] Prometheus histograms have `_bucket` entries
- [ ] No silent exception handling violations
- [ ] PWA service worker controls root scope
- [ ] Circuit breaker state persists across restarts
