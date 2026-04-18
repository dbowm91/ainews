# Implementation Plan — FUTURE WORK

## Summary

This consolidated plan aggregates all pending improvement items from plans 2-7. All items from the original Wave 1-6 (plan.md) are marked as COMPLETED and serve as historical reference.

---

## Consolidated Plan Structure

Items are organized into **8 waves** based on dependencies and parallelization potential:

| Wave | Focus | Items | Dependencies |
|------|-------|-------|--------------|
| **Wave 1** | Security & HTML Escaping | W1.1-W1.4 | None — foundational |
| **Wave 2** | Code Quality Fixes | W2.1-W2.6 | None — independent |
| **Wave 3** | LLM Provider Improvements | W3.1-W3.9 | None — independent |
| **Wave 4** | Performance Optimizations | W4.1-W4.9 | None — independent |
| **Wave 5** | Newsletter & Operational | W5.1-W5.7 | None — independent |
| **Wave 6** | Admin & Security Hardening | W6.1-W6.7 | Wave 1 partial |
| **Wave 7** | Architecture & Future Work | W7.1-W7.9 | Design decisions needed |
| **Wave 8** | UI/UX Improvements | W8.1-W8.14 | None — independent |

**Parallelization Strategy:** Waves 1-5 and Wave 8 contain items that can be executed in parallel by separate sub-agents since they operate on different files/subsystems. Wave 6 depends on Wave 1's HTML escaping baseline. Wave 7 requires architectural design decisions before implementation.

---

## Wave 1: Security & HTML Escaping (Critical)

### W1.1: XSS in Admin Topic Notes Templates

**Files:** `templates/admin/partials/topic_note_row.html`, `templates/admin/topic_notes.html`

**Issue:** Database content (`note.topic`, `note.source`, `note.note`) is rendered without the `|e` filter. An admin who enters `<script>alert(1)</script>` as a topic name causes script execution.

**Fix in `topic_note_row.html`:**
```html
<span class="mono">{{ note.topic|e }}</span>
<span class="mono text-muted">{{ (note.source or "—")|e }}</span>
<span class="text-muted">{{ note.note[:100]|e }}...</span>

hx-get="{{ url_for('admin.topic_notes_row', topic=note.topic|urlencode, source=(note.source or '')|urlencode) }}"
<input type="hidden" name="topic" value="{{ note.topic|e }}">
<input type="hidden" name="source" value="{{ (note.source or '')|e }}">
```

**Fix in `topic_notes.html`:**
```html
value="{{ topic|e }}"
value="{{ source|e }}"
```

**Effort:** Low | **Testing:** Create topic note with `<script>` content — verify no execution

---

### W1.2: Missing HTML Escape for selector_result.reason

**File:** `templates/partials/article_body.html:48`

**Issue:** LLM-generated `selector_result.reason` rendered without `|e` filter.

**Current:**
```html
<p class="article-body">Not selected. Score: {{ article.selector_result.score }}/10. {{ article.selector_result.reason }}</p>
```

**Fix:**
```html
<p class="article-body">Not selected. Score: {{ article.selector_result.score }}/10. {{ article.selector_result.reason|e }}</p>
```

**Effort:** Low | **Testing:** View skipped article page — verify reason renders safely

---

### W1.3: Unescaped URL in Newsletter HTML

**File:** `services/newsletter.py:74-75`

**Issue:** Unsubscribe URL inserted without escaping. Defense-in-depth requires consistent escaping.

**Current:**
```python
unsub_link = f'<a href="{unsub}" style="color:#888;text-decoration:none;">unsubscribe</a>'
```

**Fix:**
```python
safe_unsub = html.escape(unsub, quote=True)
unsub_link = f'<a href="{safe_unsub}" style="color:#888;text-decoration:none;">unsubscribe</a>'
```

Note: `services/email.py:151` already correctly uses `html.escape(unsubscribe_url, quote=True)`.

**Effort:** Low | **Testing:** Verify newsletter HTML source contains properly escaped unsubscribe URL

---

### W1.4: Email Subject Lines Not Escaped

**Files:** `services/newsletter.py:158`, `services/email.py:56,109`

**Issue:** Email subjects containing user-controlled content not HTML-escaped.

**Fix:**
```python
# services/newsletter.py:158
subject = f"ainews// — {html.escape(title)} — {date_str}"

# services/email.py:56
subject = f"Confirm your subscription to {html.escape(site_name)} — {html.escape(newsletter_label)}"

# services/email.py:109
subject = f"Subscribed to {html.escape(site_name)} — {html.escape(newsletter_label)}"
```

**Effort:** Low | **Testing:** Verify newsletter emails render with escaped characters in subject

---

## Wave 2: Code Quality Fixes

### W2.1: Missing `nullable=False` on Citation.position

**File:** `models.py:164`

**Issue:** `Citation.position` has `default=1` but lacks `nullable=False`. Code path creating Citation without position inserts NULL.

**Current:**
```python
position = db.Column(db.Integer, default=1)
```

**Fix:**
```python
position = db.Column(db.Integer, nullable=False, default=1)
```

**Effort:** Low | **Testing:** Run tests; consider migration for existing databases

---

### W2.2: Redundant Exception Re-Raise in base.py

**File:** `services/llm/base.py:233-234`

**Issue:** `except Exception as e: raise e` adds no value — dead code.

**Current:**
```python
except Exception as e:
    raise e
```

**Fix:** Remove the try/except block entirely.

**Effort:** Trivial | **Testing:** Run LLM-related tests

---

### W2.3: Confusing Timeout Exception Import Alias

**File:** `services/subagent.py:6, 437`

**Issue:** `concurrent.futures.TimeoutError` imported as `ConcurrentTimeoutError` but bare `TimeoutError` caught at line 437.

**Current (line 6):**
```python
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as ConcurrentTimeoutError,
)
```

**Fix:** Remove unused alias:
```python
from concurrent.futures import ThreadPoolExecutor
```

**Effort:** Trivial | **Testing:** Run subagent tests

---

### W2.4: Incomplete Mock in setup_pipeline_mocks

**File:** `tests/helpers/pipeline_mocks.py:50-53`

**Issue:** `redis_mock` missing `register_script()` mock configuration.

**Current:**
```python
redis_mock = MagicMock()
redis_mock.set.return_value = True
redis_mock.get.return_value = b"task-test"
```

**Fix:** Add:
```python
redis_mock.register_script.return_value = MagicMock()
```

**Effort:** Low | **Testing:** Run pipeline stage tests with ModelLimiter

---

### W2.5: Redundant Exception Re-Raise in chat_with_tools

**File:** `services/llm/base.py:233-234`

**Issue:** Duplicate of W2.2 (same issue, referenced in plan6).

**Status:** See W2.2

---

### W2.6: Misleading CSRF Exemption Comment

**File:** `routes/public/links.py:90-93`

**Issue:** Comment claims endpoint is CSRF exempt but no decorator is applied.

**Current:**
```python
# CSRF exemption: this endpoint is called from client-side JS...
```

**Fix:**
```python
# Note: This endpoint is CSRF-protected via Flask-WTF but the read-only nature
# (metrics recording only) limits impact...
```

**Effort:** None | **Testing:** None

---

## Wave 3: LLM Provider Improvements

### W3.1: Dated Anthropic Structured Outputs Beta Flag

**File:** `services/llm/anthropic.py:100`

**Issue:** Uses deprecated `betas=["structured-outputs-2025-11-13"]` instead of stable API.

**Current:**
```python
"betas": ["structured-outputs-2025-11-13"],
"output_format": {"type": "json_schema", "schema": schema},
```

**Fix:** Remove `betas` parameter:
```python
"output_format": {"type": "json_schema", "schema": schema},
```

Verify SDK version supports stable structured outputs (`>=0.25.0`).

**Effort:** Low | **Testing:** Run structured output tests

---

### W3.2: Provider Cache Invalidation Incomplete

**File:** `services/llm/__init__.py:21-23`

**Issue:** `clear_provider_cache()` only clears `ProviderManager._cache`, not underlying `ConfigCache`.

**Current:**
```python
def clear_provider_cache() -> None:
    _manager.clear_cache()
```

**Fix:**
```python
def clear_provider_cache() -> None:
    _manager.clear_cache()
    from services.config_cache import get_config_cache
    cache = get_config_cache()
    cache.invalidate("providers")
```

**Effort:** Low | **Testing:** Modify providers.yaml, call clear_provider_cache(), verify new provider returned

---

### W3.3: No Retry/Success Metrics in chat_structured

**File:** `services/llm/base.py:89-131`

**Issue:** Validation failures and retries not tracked in metrics.

**Fix:** Add metrics instrumentation:
```python
metrics.counter_inc(
    "llm.validation_failures",
    labels={"model": model or self.default_model, "provider": self.provider_id},
)
# ... retry logic ...
metrics.counter_inc(
    "llm.validation_retries",
    labels={"model": model or self.default_model, "provider": self.provider_id},
)
```

**Effort:** Low | **Testing:** Create test returning invalid JSON — verify metrics increment

---

### W3.4: Fallback Provider Model Not Validated

**File:** `services/llm/__init__.py:46-67`

**Issue:** Fallback provider with empty `model` causes runtime errors.

**Fix:** Validate fallback has non-empty model:
```python
fallback_model = pdef.config.get("model", "")
if not fallback_model:
    logger.warning("Fallback provider %s has no model configured, skipping", pdef.id)
    continue
```

**Effort:** Low | **Testing:** Create fallback with no model — verify skipped and logged

---

### W3.5: Ollama Tool Call ID Synthesis Not Used

**File:** `services/llm/ollama.py:148`

**Issue:** Ollama synthesizes `id=f"call_{i}"` but Ollama uses message ordering, not IDs.

**Current:**
```python
id=f"call_{i}",  # Ollama doesn't provide ids
```

**Fix:**
```python
id="",  # Ollama doesn't use IDs — relies on message ordering
```

**Effort:** Trivial | **Testing:** Existing Ollama tests pass

---

### W3.6: Anthropic Health Check Uses Very Low max_tokens

**File:** `services/llm/anthropic.py:195`

**Issue:** `max_tokens=1` may cause rejection on some models.

**Fix:**
```python
max_tokens=10,
```

**Effort:** Trivial | **Testing:** Manual health check test

---

### W3.7: Bare Re-Raise in chat_with_tools

**File:** `services/llm/base.py:233-234`

**Issue:** Duplicate of W2.2.

**Status:** See W2.2

---

### W3.8: System Prompt Insertion Inconsistency

**File:** `services/llm/base.py:212-213 vs 310-318`

**Issue:** `chat()` uses `_build_messages()` but `chat_with_tools()` inserts directly.

**Fix:** Refactor `chat_with_tools()` to use `_build_messages()`:
```python
all_messages = self._build_messages(messages, system)
```

**Effort:** Trivial | **Testing:** Existing tool-calling tests pass

---

### W3.9: Ollama Thinking Block Fallback is Model-Specific

**File:** `services/llm/ollama.py:49-51`

**Issue:** Returns thinking content for qwen3 models but this is model-specific behavior.

**Fix:** Add config option:
```python
def _extract_text(self, resp, return_thinking: bool = False) -> str:
    # ...
    if not content and return_thinking:
        thinking = message.get("thinking")
        # ...
```

**Effort:** Low | **Testing:** Verify non-thinking models work correctly

---

### W3.10: ProviderManager Instantiation Failure Not Logged Gracefully

**File:** `services/provider_base.py:52-67`

**Issue:** Provider init failures not logged before propagating.

**Fix:** Add warning log:
```python
try:
    provider = cls(pdef.id, pdef.config)
except Exception as e:
    logger.warning("Failed to instantiate %s provider %s: %s", self.category, provider_id, e)
    raise
```

**Effort:** Low | **Testing:** Configure provider with invalid credentials — verify warning logged

---

## Wave 4: Performance Optimizations

### W4.1: Missing Database Indexes on Foreign Keys

**Files:** `models.py:96, 158, 297, 382, 44`

**Issue:** FK columns lack explicit indexes for frequent JOINs/filter operations.

**Fix:** Add `index=True` to:
- `Article.source_id` (line 96)
- `Citation.article_id` (line 158)
- `PipelineLog.article_id` (line 297)
- `TrendMemory.source_article_id` (line 382)
- `article_tags.tag_id` via explicit index

**Migration required:**
```bash
flask db migrate -m "Add missing FK indexes"
```

**Effort:** Low | **Testing:** EXPLAIN QUERY PLAN on articles by source query

---

### W4.2: Missing Eager Loading in Newsletter Article Query

**Files:** `services/newsletter.py:151`, `routes/admin/newsletters.py:162-171`

**Issue:** Articles fetched without joinedload for source/tags — N+1 on template access.

**Fix:**
```python
from sqlalchemy.orm import joinedload

articles = (
    query.options(joinedload(Article.source), joinedload(Article.tags))
    .order_by(Article.impact_score.desc())
    .limit(max_articles)
    .all()
)
```

**Effort:** Low | **Testing:** Enable SQL logging, generate newsletter — verify no N+1

---

### W4.3: N+1 Query in Article Detail Route

**File:** `routes/public/links.py:34`

**Issue:** Article fetched without joinedload for tags.

**Fix:**
```python
from sqlalchemy.orm import joinedload
article = (
    Article.query.options(joinedload(Article.tags))
    .filter(Article.short_id == article_id)
    .first_or_404()
)
```

**Effort:** Low | **Testing:** Request article detail — verify no additional tag query

---

### W4.4: Unbounded PipelineRun Query

**File:** `routes/admin/pipelines.py:23`

**Issue:** `all()` returns unlimited rows if many stuck in "running" state.

**Fix:**
```python
running = PipelineRun.query.filter_by(status="running").order_by(
    PipelineRun.started_at.desc()
).limit(100).all()
```

**Effort:** Low | **Testing:** Verify old stuck pipelines excluded

---

### W4.5: find_duplicate_titles() Optimization

**File:** `services/article.py:260-280`

**Issue:** Loads ALL recent titles, computes Jaccard on all.

**Fix:** Add word count pre-filtering and early exit:
```python
# Pre-filter by approximate word count range (±30%)
min_words = max(1, int(word_count * 0.7))
max_words = int(word_count * 1.3)
# ... then compute Jaccard only on similar-length titles
```

**Effort:** Medium | **Testing:** Time function with 1000+ articles — should complete < 1s

---

### W4.6: Non-Atomic Lock Reacquisition in Crawl Task

**File:** `tasks/crawl.py:47-63`

**Issue:** Separate GET then SET instead of atomic check-and-modify.

**Fix:** Use Lua script:
```python
_REACQUIRE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
else
    return 0
end
"""
```

**Effort:** Low | **Testing:** Simulate concurrent crawl tasks — only one proceeds

---

### W4.7: Newsletter Lock Multiple Redis Round-Trips

**File:** `tasks/newsletter.py:330-365`

**Issue:** Lock acquire/refresh uses 2-4 round-trips where one Lua script suffices.

**Fix:** Consolidate to single atomic operation via Lua script.

**Effort:** Low | **Testing:** Concurrent newsletter generation — second skips gracefully

---

### W4.8: Naive vs Aware Datetime Comparison

**File:** `tasks/pipeline.py:189-202`

**Issue:** `datetime.now(timezone.utc)` (aware) compared against naive `pipeline_started_at`.

**Fix:**
```python
started_at = article.pipeline_started_at
if started_at.tzinfo is not None:
    started_at = started_at.replace(tzinfo=None)
elapsed = (datetime.utcnow() - started_at).total_seconds()
```

**Effort:** Low | **Testing:** Start long-running pipeline — verify timeout works correctly

---

### W4.9: scan_iter in Limiter Cleanup Batching

**File:** `services/limiter.py:127`

**Issue:** `scan_iter` without count hint could be slow with many keys.

**Fix:** Add batch processing:
```python
cursor = 0
while True:
    cursor, keys = self._redis.scan(cursor, match=pattern, count=1000)
    for key in keys:
        ttl = self._redis.ttl(key)
        if ttl < 0:
            pipeline.delete(key)
    if cursor == 0:
        break
    if time.time() - start_time > 30:
        break
```

**Effort:** Low | **Testing:** Create many stale slots — verify cleanup completes within soft time limit

---

## Wave 5: Newsletter & Operational Improvements

### W5.1: Newsletter Generation Not Idempotent

**File:** `tasks/newsletter.py:generate_daily_newsletters`

**Issue:** Double-trigger creates duplicate newsletters.

**Fix:** Use idempotency key:
```python
IDEMPOTENCY_KEY = "idempotency:newsletter:{date}"

if redis_client.exists(IDEMPOTENCY_KEY.format(date=today)):
    return  # Already generated today
# ... generate ...
redis_client.setex(IDEMPOTENCY_KEY.format(date=today), 86400 * 2, "1")
```

**Effort:** Low | **Testing:** Trigger twice simultaneously — only one runs

---

### W5.2: Article Version Cleanup Dry-Run Mode

**File:** `tasks/cleanup.py:cleanup_old_article_versions`

**Issue:** Permanent deletion without preview.

**Fix:** Add dry-run parameter:
```python
def cleanup_old_article_versions(days_to_keep: int = 90, dry_run: bool = False):
    if dry_run:
        return {"would_delete": count, "oldest_version": ..., "articles_affected": ...}
    # ... delete ...
```

Add admin endpoint: `GET /admin/api/cleanup/article-versions/preview`

**Effort:** Low | **Testing:** Run with dry_run=True — verify nothing deleted

---

### W5.3: Per-Stage Failure Tracking

**File:** `services/pipeline_failure.py`, `tasks/pipeline.py`

**Issue:** Once degraded, article follows single path. No tracking of "fails at every stage" patterns.

**Fix:** Add Redis-based per-stage failure tracking:
```python
stage_failure_key = f"article:{article.id}:stage_failures:{stage}"
stage_failures = redis_client.hincrby(stage_failure_key, "count", 1)
if stage_failures >= 3:
    article.pipeline_status = PipelineStatus.FAILED
```

**Effort:** Low | **Testing:** Fail same article 3x at research — verify stops retrying

---

### W5.4: Database Query Logging Not Wired

**File:** `logging_config.py`

**Issue:** `DB_QUERY_LOG_LEVEL` config exists but SQLAlchemy logging not configured.

**Fix:**
```python
if config_name == "production":
    db_log_level = os.environ.get("DB_QUERY_LOG_LEVEL", "WARNING").upper()
    logging.getLogger("sqlalchemy.engine").setLevel(getattr(logging, db_log_level))
```

**Effort:** Low | **Testing:** Verify development shows queries; production with default does not

---

### W5.5: Pipeline Metrics in Admin UI

**File:** `routes/admin/dashboard.py`, `templates/admin/dashboard.html`

**Issue:** Pipeline health metrics in Redis but not displayed in admin.

**Fix:** Add stats to dashboard context:
```python
stats = get_pipeline_stats()
# ... pass to template
pipeline_health=stats,
```

Add template section showing success/failure rates, average stage duration, dead letter count.

**Effort:** Low | **Testing:** Verify stats display correctly

---

### W5.6: Request ID Propagation

**Files:** `services/logging_utils.py`, `app.py`, `tasks/pipeline.py`

**Issue:** HTTP request IDs not propagated to Celery tasks.

**Fix:**
```python
# app.py:before_request
request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
g.request_id = request_id

# When dispatching Celery task:
celery_task.delay(article_id, _request_id=getattr(g, "request_id", None))
```

**Effort:** Low | **Testing:** Trigger bulk reprocess with request ID header — verify task logs include it

---

### W5.7: Blocking Celery get() in Newsletter Tasks

**File:** `tasks/newsletter.py:82, 297`

**Issue:** `get(timeout=300/600)` blocks worker thread.

**Fix:** Use callback-based chord:
```python
from celery import chord

job = chord(
    (send_single_email.s(email, subject, html, topic, date_str) for email in recipients),
    aggregate_newsletter_results.s()
)
job.apply_async()  # Don't block
```

**Effort:** Medium | **Testing:** Send newsletter — verify worker processes other tasks during send

---

## Wave 6: Admin & Security Hardening

### W6.1: JSON API Endpoints Lack CSRF Validation

**Files:** `routes/admin/api/articles.py:103-105`, `routes/admin/api/webhooks.py`

**Issue:** JSON endpoints bypass Flask-WTF CSRF (only validates form/multipart).

**Fix:** Add global JS to send CSRF header:
```html
<script>
document.body.addEventListener('htmx:configRequest', function(event) {
    event.detail.headers['X-CSRFToken'] = "{{ csrf_token() }}";
});
</script>
```

Or create decorator for JSON endpoints checking `X-CSRFToken` header.

**Effort:** Medium | **Testing:** Send POST without CSRF token — should return 400

---

### W6.2: Plaintext Admin Password in .env

**File:** `.env:2`

**Issue:** `ADMIN_PASSWORD=changeme` in plaintext.

**Fix:**
```
ADMIN_PASSWORD=
# Generate with: python scripts/hash_password.py
```

Add startup check warning if password is empty or equals default.

**Effort:** Low | **Testing:** Start with empty password — should warn

---

### W6.3: Default Secret Key Only Warns

**File:** `config.py:125`, `app.py:74-77`

**Issue:** Development mode proceeds with insecure `"dev-secret-key-change-me"`.

**Fix in DevelopmentConfig:**
```python
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in development...")
```

**Effort:** Low | **Testing:** Unset SECRET_KEY — should raise RuntimeError

---

### W6.4: HTMX Subscribe Form CSRF Bypass

**File:** `templates/partials/subscribe_box.html:23`, `routes/public/subscribe.py:22`

**Issue:** CSRF token via `hx-vals` as JSON may bypass validation.

**Fix:** Use `hx-headers`:
```html
<div hx-headers='{"X-CSRFToken": "{{ csrf_token() }}"}'>
```

Update route to check both form and JSON:
```python
if request.is_json:
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
```

**Effort:** Low | **Testing:** Submit via HTMX — verify CSRF passes

---

### W6.5: TestingConfig Disables CSRF

**File:** `config.py:133`

**Issue:** `WTF_CSRF_ENABLED = False` allows CSRF vulnerabilities undetected.

**Fix:** Add CSRF test fixture and tests:
```python
@pytest.fixture
def csrf_enabled_app(app):
    original = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    yield app
    app.config["WTF_CSRF_ENABLED"] = original
```

**Effort:** Medium | **Testing:** Run CSRF-specific tests

---

### W6.6: safe_href Validation Failure Logging

**File:** `app.py:228-242`

**Issue:** Silently returns "#" on URL validation failure.

**Fix:** Add logging:
```python
current_app.logger.warning(
    "safe_href blocked URL due to validation failure: %s (%s)",
    value[:100], str(e)[:100]
)
```

**Effort:** Low | **Testing:** Verify blocked URLs logged appropriately

---

### W6.7: Misleading CSRF Exemption Comment

**File:** `routes/public/links.py:90-93`

**Issue:** Same as W2.6.

**Status:** See W2.6

---

## Wave 7: Architecture & Future Work

### W7.1: Celery Batch Processing

**Files:** `tasks/pipeline.py`, `tasks/select.py`, etc.

**Issue:** Single-threaded pipeline execution — no intra-task parallelism.

**Fix:** Refactor stage tasks to use `ThreadPoolExecutor` for parallel LLM calls within batch:
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(_select_single, article_id): article_id for article_id in article_ids}
```

**Effort:** High | **Testing:** Benchmark throughput before/after

---

### W7.2: Atomic Pipeline Stage Transitions

**Files:** `models.py:106`, `tasks/pipeline.py`

**Issue:** Partial article state on failure — corrupted content.

**Fix:** Implement state machine with valid transitions:
```python
VALID_TRANSITIONS = {
    PENDING: [EXTRACTING],
    EXTRACTING: [SELECTING, FAILED],
    # ...
}

def run_stage_atomic(article, stage_name, new_status):
    if new_status not in VALID_TRANSITIONS.get(article.pipeline_status, []):
        raise InvalidStateTransition(...)
    try:
        result = execute_stage(article, stage_name)
        article.pipeline_status = new_status
        db.session.commit()
    except Exception:
        db.session.rollback()
        article.pipeline_status = "failed"
        raise
```

**Effort:** High | **Testing:** Kill worker mid-pipeline — verify article ends in FAILED

---

### W7.3: ResponseCache Stampede Uses Polling

**File:** `services/cache.py:156-164`

**Issue:** `BLPOP`/`BRPOP` would be more efficient than polling.

**Fix:** Use Redis blocking pop:
```python
result = redis_client.blpop(lock_key, timeout=lock_timeout)
if result:
    return redis_client.get(cache_key)
```

**Effort:** Medium | **Testing:** Simulate cache stampede — verify single computation

---

### W7.4: Dead Letter Queue UI

**Files:** `routes/admin/dashboard.py`, `templates/admin/dead_letters.html`

**Issue:** Dead letter articles no dedicated admin UI.

**Fix:** Add "Dead Letter" tab:
```python
@admin_bp.route("/admin/dead-letters")
@require_auth
def dead_letters():
    stats = get_dead_letter_stats()
    recent_failures = Article.query.filter(
        Article.pipeline_status == "failed"
    ).order_by(Article.updated_at.desc()).limit(20).all()
```

Create template showing total dead letters, exceeded retry budget articles, bulk reprocess/delete.

**Effort:** Medium | **Testing:** Create dead letter — verify appears in UI

---

### W7.5: Dynamic Celery Beat Schedule

**Files:** `config.py:82-120`, `pipeline.yaml`

**Issue:** Beat schedule static — requires restart to change interval.

**Fix:** Extract to `pipeline.yaml`:
```python
def get_beat_schedule():
    pipeline_cfg = get_config().get("pipeline", {})
    schedule["run-all-sources"] = {
        "task": "tasks.crawl.run_all_sources",
        "schedule": timedelta(minutes=pipeline_cfg.get("crawl_interval_minutes", 30)),
    }
```

Reload on config change via `reload_beat_schedule()`.

**Effort:** Medium | **Testing:** Change interval in pipeline.yaml, call reload — verify new interval

---

### W7.6: Newsletter HTML Validation in CI

**File:** `tests/test_newsletter.py`

**Issue:** HTML validity not tested.

**Fix:** Add HTML well-formedness test using HTMLParser.

**Effort:** Low | **Testing:** Run new test; intentionally break HTML — verify catches error

---

### W7.7: OpenTelemetry Tracing

**Files:** `services/llm/base.py`, `services/crawling.py`, `tasks/pipeline.py`

**Issue:** No distributed tracing for correlation across workers.

**Fix:** Add OpenTelemetry instrumentation:
```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

@contextlib.contextmanager
def traced_llm_call(provider: str, model: str, stage: str):
    with tracer.start_as_current_span(f"llm.{stage}") as span:
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model", model)
        yield
```

**Effort:** Medium | **Testing:** Verify traces appear in tracing backend

---

### W7.8: Source Health Auto-Recovery Documentation

**Files:** `docs/...`, `services/crawling.py`

**Issue:** No documented mechanism for source auto-recovery after 10 failures.

**Fix:** Add documentation explaining:
1. Auto-disable after 10 consecutive failures
2. Manual re-enable via `POST /admin/api/sources/<id>/enable`
3. Optional: Auto-recovery after N successes

**Effort:** None | **Testing:** N/A

---

### W7.9: Rate Limiting Documentation

**File:** `docs/deployment.md`

**Issue:** Public endpoints have no rate limiting (relies on WAF/reverse proxy).

**Fix:** Document that infrastructure handles rate limiting. If no proxy, revisit decision.

**Effort:** None | **Testing:** N/A

---

## Wave 8: UI/UX Improvements

### W8.1: CSS Critical Path Consolidation

**Files:** `static/css/base.css`, `static/css/layout.css`, `templates/partials/critical_css.html`

**Issue:** CSS reset/base styles defined in 3 places — maintenance risk.

**Fix:** Remove duplication from `base.css` and `layout.css`, keep only in `critical_css.html`:
- Remove from `base.css`: reset, html, body, skip-link, sr-only, a, scrollbar, ::selection
- Remove from `layout.css`: `.site-header` (lines 7-13), `#content` transition (lines 84-86)
- Keep in `base.css`: `.theme-transitioning`, `:focus-visible`, scroll-behavior media query
- Keep in `layout.css`: Navigation layout, container, footer, responsive breakpoints, keyframes

**Effort:** Medium | **Testing:** Dark/light themes work; scrollbar, focus states, hamburger menu function

---

### W8.2: prefers-reduced-motion on Progress Bar

**Files:** `static/css/layout.css:106-109`, `templates/partials/critical_css.html:24-26`

**Issue:** HTMX progress bar animation runs without reduced motion check.

**Fix in `critical.css`:**
```css
@media (prefers-reduced-motion: reduce) {
  @keyframes progress-bar { ... }
  .htmx-request::before { animation: none; background: var(--accent); height: 2px; }
}
```

Remove duplicate from `layout.css`.

**Effort:** Low | **Testing:** Enable OS reduced motion — verify no moving progress bar

---

### W8.3: Empty Media Query Block

**File:** `static/css/layout.css:273-287`

**Issue:** Empty media query `(min-width: 641px) and (max-width: 768px)`.

**Fix:** Remove or add meaningful tablet-portrait responsive adjustments.

**Effort:** None | **Testing:** Verify layout at 641-768px acceptable

---

### W8.4: Stale Comment References

**File:** `static/css/pages.css:733`

**Issue:** Comment references non-existent section scheme.

**Current:**
```css
/* Search keyboard hint (8.17) - moved to articles.css */
```

**Fix:** Update to:
```css
/* Keyboard shortcut hint for search focus */
```

**Effort:** None | **Testing:** N/A

---

### W8.5: Duplicate .rss-* Rule Sets

**File:** `static/css/articles.css:828-841, 843-857`

**Issue:** `.rss-badge` and `.rss-link` defined twice each.

**Fix:** Audit and consolidate to single definition per class.

**Effort:** Low | **Testing:** Verify RSS link in feed and badge in topic pages render correctly

---

### W8.6: Search Input Missing Visible Label

**File:** `templates/partials/feed.html:9-23`

**Issue:** `aria-label` present but no visible `<label>`.

**Fix:**
```html
<label for="search-input" class="sr-only">Search articles</label>
<input id="search-input" type="search" ... autocomplete="off">
```

**Effort:** Low | **Testing:** Verify screen reader announces label; autofill doesn't interfere

---

### W8.7: Pagination Missing aria-disabled

**File:** `templates/partials/pagination.html`

**Issue:** Disabled prev/next spans lack `aria-disabled="true"`.

**Fix:**
```html
<span class="pag-link pag-disabled" aria-disabled="true">&larr; prev</span>
<nav class="pagination" aria-label="Article page navigation">
```

**Effort:** Low | **Testing:** Verify screen reader announces disabled state

---

### W8.8: Hamburger Touch Target Size

**File:** `static/css/layout.css:161-163`

**Issue:** Touch target 44px adequate but could be larger.

**Fix:** Increase to 48px in mobile breakpoint:
```css
@media (max-width: 640px) {
  .nav-toggle-label { width: 48px; height: 48px; }
  .nav-toggle-label span { width: 28px; }
}
```

**Effort:** Low | **Testing:** Verify hamburger visible and easy to tap on mobile

---

### W8.9: Article Title Truncation in Admin Table

**File:** `static/css/pages.css`

**Issue:** Titles truncate without visible ellipsis.

**Fix:**
```css
.article-link {
  display: block;
  max-width: 400px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

**Effort:** Low | **Testing:** View dashboard with long titles — verify ellipsis appears

---

### W8.10: Admin Nav Overflow Skip Mechanism

**File:** `static/css/pages.css:435-460`

**Issue:** Keyboard users cannot easily reach overflow nav items.

**Fix:** Verify current `pointer-events: none` on fade is decorative only. Current implementation may be acceptable — verify tab order works correctly.

**Effort:** Low | **Testing:** Tab through admin nav — verify all links reachable

---

### W8.11: base.html Inline Styles

**File:** `templates/base.html:14-24`

**Issue:** Header/footer styles inline instead of in CSS files.

**Fix:** Move `.nav-tag`, `.site-footer`, and `.site-header` border-bottom to `layout.css`.

**Effort:** Low | **Testing:** Verify header, footer, nav-tag render correctly

---

### W8.12: Duplicate #content Transition

**File:** `static/css/layout.css:84-86`

**Issue:** `#content` transition defined in both `critical_css.html` and `layout.css`.

**Fix:** Remove duplicate from `layout.css` since `critical_css.html` inlined first.

**Effort:** None | **Testing:** Verify transition still works

---

### W8.13: Empty State Suggestions

**File:** `templates/partials/feed.html:49-60`

**Issue:** Empty state could link directly to clear filters.

**Current:**
```html
<p class="empty-description">try adjusting your search terms or clearing filters</p>
```

**Fix:**
```html
{% if query or category %}
  <p class="empty-description">
    try adjusting your search terms or
    <a href="/">clearing all filters</a>
  </p>
{% endif %}
```

**Effort:** Low | **Testing:** Verify empty state renders and link works

---

### W8.14: Share Button A11y

**File:** `templates/partials/share_macro.html`

**Issue:** `<details>/<summary>` open/close state not properly announced.

**Fix:** Add `aria-expanded` and keyboard support via JS:
```html
<details class="share-details">
  <summary class="share-btn" aria-label="Share" aria-expanded="false" role="button">
```

```javascript
document.querySelectorAll('.share-details').forEach(details => {
  details.addEventListener('toggle', () => {
    details.querySelector('summary').setAttribute('aria-expanded', details.open.toString());
  });
});
```

**Effort:** Medium | **Testing:** Verify screen reader announces share button and state

---

## Items Already Correct (No Action Needed)

### Code Quality
| Item | Evidence |
|------|----------|
| `email.py:151` URL escaping | Already uses `html.escape(unsubscribe_url, quote=True)` |
| `ArticleVersion.version_number` nullable | Already has `nullable=False` |

### Security
| Item | Evidence |
|------|----------|
| SSRF Protection | `services/url.py:172-202` blocks private IPs with DNS cache |
| SQL Injection | SQLAlchemy ORM with LIKE pattern escaping |
| Session Fixation | `session.clear()` before admin session set (`auth.py:52`) |
| Password Hashing | werkzeug scrypt/pbkdf2/argon2 |
| Login Lockout | Atomic Redis Lua script + in-memory fallback |
| HTML Escaping | `|e` filter on article content, `html.escape()` in services |
| Security Headers | Flask-Talisman with CSP, HSTS configured |
| Cookie Security | httpOnly, sameSite=Lax, secure in production |

### Performance
| Item | Evidence |
|------|----------|
| SQLite WAL mode | `app.py` sets `PRAGMA journal_mode=WAL` |
| Redis connection pool | `extensions.py:86-93` with `max_connections=100` |
| FTS5 full-text search | `services/pagination.py:90-116` with proper indexing |
| `yield_per(500)` streaming | `routes/admin/subscribers.py` uses generator |
| SoftTimeLimitExceeded handling | Explicit catch in `tasks/pipeline.py:235` |
| Worker recycling | `CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000` |
| ResponseCache LRU | `services/cache.py` with OrderedDict and 1000 entry limit |
| Stampede protection | `services/cache.py:get_or_set()` uses `SET NX` locking |
| Config mtime invalidation | `services/config_cache.py` tracks file mtime |
| Tag cache | `tasks/edit.py` with 300s TTL |

### Architecture
| Item | Evidence |
|------|----------|
| Redis error handling | `services/limiter.py` catches `redis.exceptions.RedisError` |
| Celery task locking | `tasks/newsletter.py` uses `self.request.id` as lock value |
| Config cache reload | `routes/admin/api.py` calls `clear_app_cache()` |
| Article detail caching | `routes/public/links.py` uses `ResponseCache` |
| Newsletter empty content guard | `tasks/newsletter.py` checks before sending |
| Subscriber validation | `routes/public/subscribe.py` validates against known keys |

### LLM
| Item | Evidence |
|------|----------|
| Thread-safe lazy client init | `services/llm/base.py:63-69` double-checked locking |
| Circuit breaker with fallback | `services/llm/__init__.py:30-71` |
| Structured output Pydantic validation | `services/llm/base.py:89-131` with 1 retry |
| Tool calling loop | `services/llm/base.py:194-308` with max 5 iterations |
| Centralized error handling | `services/llm/errors.py` maps SDK exceptions |

### UI/UX
| Item | Evidence |
|------|----------|
| Theme system | GitHub-inspired dark/light with CSS custom properties |
| Accessibility | Skip links, ARIA labels, `focus-visible` states |
| Touch targets | 44px minimum enforced |
| Print styles | Comprehensive in `utilities.css` |
| HTMX UX | Progress bar, skeleton loading, keyboard shortcuts |
| Responsive breakpoints | Mobile-first 640px, 768px, 900px |
| Toast notifications | Proper ARIA live regions |
| CSS module organization | Well-structured imports in `style.css` |

---

## Testing Commands

After making changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

For database migrations:
```bash
scripts/verify_backup.sh
.venv/bin/python -m pytest tests/test_migration.py -v
```

---

## Rollback Plan

If any change causes issues:
1. Revert the specific file change
2. Run tests to confirm restoration
3. Re-analyze before re-applying
4. For model changes, generate downgrade migration
5. Clear relevant Redis keys (config cache, locks)

---

## Parallelization Notes

**Waves 1, 2, 3, 4, 5, 8** contain items that operate on different files/subsystems and can be executed in parallel by separate sub-agents.

**Wave 6** depends on Wave 1's HTML escaping baseline (W6.1-W6.5 build on security foundations).

**Wave 7** requires architectural design decisions before implementation — coordinate with team.

**Recommended sub-agent allocation:**
- **Agent A**: Wave 1 (Security) + Wave 6 (Admin Hardening)
- **Agent B**: Wave 2 (Code Quality) + Wave 3 (LLM Provider)
- **Agent C**: Wave 4 (Performance) + Wave 5 (Operational)
- **Agent D**: Wave 8 (UI/UX)
- **Agent E**: Wave 7 (Architecture) — requires design review first
