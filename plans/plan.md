# Implementation Plan — Consolidated

**Created:** April 22, 2026
**Last Updated:** April 24, 2026
**Status:** COMPLETED — All 5 waves implemented
**Total Items:** ~65 across 5 waves

---

## Implementation Complete

All waves have been implemented as of April 24, 2026. Verification:
- Wave 1 (XSS): Templates updated with |e escaping, validate_bulk_ids, env documentation
- Wave 2 (Security): Redis TLS, DEBUG enforcement, task signing, health endpoint auth
- Wave 3 (Performance): SLA SQL aggregation, N+1 fix, cache namespacing
- Wave 4 (Error handling): JSON logging, Redis fallback, retry config, memory bounds
- Wave 5 (Test/CQ): Test fixtures, requirements pinning, beat schedule deprecation

**Wave dependency model:**
- Wave 1 and Wave 2 touch completely different files and can run in parallel
- Wave 3 can start as soon as its file-level dependencies are clear
- Waves 4 and 5 are lower priority and can be picked up independently

---

## Deferred Items

These items were evaluated and intentionally excluded:

| Item | Source | Reason |
|------|--------|--------|
| E.2: Celery Task Event Streaming | plan.md | Requires celery.events.RealityMonitor, Redis streaming, MetricsCollector updates |
| E.3: Structured Tool Result Format | plan4.md | Already implemented via `esc_xml_text` in `services/prompts.py` — 65+ uses |
| E.4: Celery Worker Network Isolation | plan4.md | Requires hosting platform + CI/CD that don't exist |
| 2.6: Dashboard Event-Based Invalidation | plan5.md | 60-second TTL covers the need — event-based adds 150+ LOC for marginal benefit |
| 1.1: CI/CD Pipeline | plan5.md | Requires hosting platform with GitHub Actions |
| Rate limiting on subscribe endpoints | plan5.md | AGENTS.md explicitly says: "Do not add `@limiter.limit()` decorators to routes" — WAF handles this |
| Font variable renaming | plan10.md | Cosmetic, high effort (25+ files), low value — `--text-lg` documented in AGENTS.md |
| Theme transition `!important` removal | plan10.md | Cosmetic, high risk for low reward |
| Unique constraints on SQLite | plan8.md | SQLite can't ALTER TABLE to add constraints per AGENTS.md |
| Circuit breaker Redis persistence | plan8.md | Too large scope; in-memory is acceptable for current scale |
| Duplicate detection query batching | plan7.md | Minor improvement; the `.limit(1000)` fix in Wave 3 addresses the main concern |
| Admin articles count removal | plan7.md | Minor UX improvement, not worth template changes |
| Search analytics SQL cleanup | plan4.md | Confusing but functional — low priority |
| ENV_VAR resolution warning | plan8.md | `resolve_env_var()` already returns empty string with deduplicated warnings |
| Beat schedule reload fix | plan8.md | Verification item only, not actionable |
| LRU Cache O(1) eviction | plan4.md | 1000-item max makes this negligible; already in Wave 5 as optional |

---

## WAVE 1: Critical Security — XSS & Input Validation

**Estimated Time:** ~30 minutes
**Sub-agents:** 2 (can run in parallel)

**Sub-agent context:** Jinja2 autoescape is enabled but `|e` filter is still needed in certain contexts (attribute values, textarea content). Adding `|e` is always safe and never breaks functionality.

### A1: Template XSS Fixes

**Files:** `templates/admin/article_edit.html`, `templates/admin/dead_letters.html`, `templates/article.html`, `templates/partials/condensed_article.html`

#### A1a: `templates/admin/article_edit.html` — CRITICAL stored XSS

LLM-generated `final_article` JSON is rendered in form fields without escaping. An admin viewing the edit page could execute malicious scripts.

| Line | Field | Current | Fix |
|------|-------|---------|-----|
| 11 | breadcrumb title | `{{ article.original_title[:50] }}` | Add `\|e` |
| 24 | page title | `{{ article.original_title[:100] if article.original_title }}` | Add `\|e` |
| 48 | headline input value | `{{ fa.get('headline', '')... }}` | Add `\|e` |
| 53 | tldr textarea | `{{ fa.get('tldr', '')... }}` | Add `\|e` |
| 58 | why_it_matters textarea | `{{ fa.get('why_it_matters', '')... }}` | Add `\|e` |
| 63 | body textarea | `{{ fa.get('body', '')... }}` | Add `\|e` |
| 68 | what_to_watch textarea | `{{ fa.get('what_to_watch', '')... }}` | Add `\|e` |
| 73 | key_points textarea | `{{ '\n'.join(...) }}` | Add `\|e` |
| 79 | tags input value | `{{ ', '.join(...) }}` | Add `\|e` |
| 30 | error message | `{{ error }}` | Add `\|e` |

**Example fix:**
```html
<!-- Line 48 -->
value="{{ (fa.get('headline', '') if fa else article.original_title or '') | e }}"

<!-- Line 53 -->
{{ (fa.get('tldr', '') if fa else '') | e }}

<!-- Line 30 -->
{{ error | e }}
```

#### A1b: `templates/admin/dead_letters.html` — CRITICAL

| Line | Current | Fix |
|------|---------|-----|
| 66 | `{{ article.original_title if article.original_title else '(no title)' }}` | Wrap in parens, add `\|e` |
| 106 | Same as line 66 | Same fix |

Note: Lines 65 and 105 correctly use `|e` in `title=` attributes.

#### A1c: Public templates — HIGH

| File | Line | Current | Fix |
|------|------|---------|-----|
| `templates/article.html` | 3 | `{{ article.original_title }}` in `<title>` | `{{ article.original_title\|e }}` |
| `templates/partials/condensed_article.html` | 88 | `{{ article.writer_model or 'ai agent' }}` | `{{ (article.writer_model or 'ai agent')\|e }}` |

---

### A2: Validation & Documentation

#### A2a: Bulk Article IDs Validation — HIGH

**File:** `routes/admin/api/articles.py`

`bulk_article_operations()` at line 174 validates list type and length but does NOT validate that individual IDs are positive integers. `validate_bulk_ids()` exists in `services/validation.py:90` but is not called here.

```python
# Add after line 189 (after the len check):
from services.validation import validate_bulk_ids

try:
    article_ids = validate_bulk_ids(article_ids)
except ValueError as e:
    return jsonify({"error": str(e)}), 400
```

#### A2b: WEBHOOK_SECRET_KEY Documentation — HIGH

**Files:** `.env.example`, `docs/configuration.md`

`.env.example` (94 lines) does not mention `WEBHOOK_SECRET_KEY`. `docs/configuration.md` (334 lines) also does not mention it.

Add to `.env.example`:
```bash
# Webhook secret encryption key (44 base64 characters)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
WEBHOOK_SECRET_KEY=
```

Add to `docs/configuration.md` in Optional variables section:
```markdown
| WEBHOOK_SECRET_KEY | Yes | Fernet key for webhook secret encryption |
```

#### A2c: Token Logging Verbosity — LOW

**File:** `routes/public/subscribe.py`

Lines 171 and 212 log full subscriber tokens. Truncate to first 8 characters for debugging without exposing full token.

```python
# Line 171: Change from
logger.exception("Failed to unsubscribe token %s", token)
# To
logger.exception("Failed to unsubscribe token %s...", token[:8])

# Line 212: Same pattern
logger.exception("Failed to verify subscriber token %s...", token[:8])
```

---

## WAVE 2: Security Infrastructure & Configuration

**Estimated Time:** ~5 hours
**Sub-agents:** 4 (can run in parallel)

### A1: Redis TLS/SSL Connection Security — CRITICAL

**Files:** `extensions.py`, `services/config_cache.py`, `docs/security.md`, `.env.example`

All Redis connections use plaintext. No `ssl=` parameter on any `ConnectionPool.from_url()` call.

**`extensions.py` (lines 106-112):**
```python
redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
ssl_enabled = redis_url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"

pool = redis.ConnectionPool.from_url(
    redis_url,
    max_connections=100,
    socket_timeout=5,
    socket_connect_timeout=3,
    socket_keepalive=True,
    ssl=ssl_enabled,
)
```

**`services/config_cache.py` (line 248):**
```python
ssl_enabled = url.startswith("rediss://") or os.environ.get("REDIS_SSL") == "true"
pool = redis.ConnectionPool.from_url(url, max_connections=20, socket_timeout=5, ssl=ssl_enabled)
```

**Documentation updates:**
- `docs/security.md`: Add Redis TLS requirement, document `REDIS_SSL=true` env var and `rediss://` protocol
- `.env.example`: Add `REDIS_SSL=false` and `CELERY_BROKER_URL` examples with `rediss://`

---

### A2: DEBUG Mode Enforcement — HIGH

**File:** `config.py`

`ProductionConfig.validate()` (lines 240-258) validates SECRET_KEY, ADMIN_PASSWORD, and CELERY_TASK_SECRET but does NOT check that `DEBUG` is `False`.

```python
# Add to ProductionConfig.validate() after existing checks:
if cls.DEBUG:
    raise RuntimeError("DEBUG must be False in production")
```

---

### A3: Task Signing & Health Endpoint — MEDIUM

#### A3a: Celery Task Signature for `cleanup_old_article_versions`

**Files:** `tasks/cleanup.py`, `config.py`

`cleanup_old_article_versions` (line 152 in `tasks/cleanup.py`) accepts `days_to_keep` and `dry_run` from Celery Beat but has no HMAC verification. Uses Pydantic validation but not `verify_task()`.

```python
# Add at start of cleanup_old_article_versions task body:
from services.task_security import verify_task

if not verify_task("cleanup_old_article_versions", (), {"days_to_keep": days_to_keep, "dry_run": dry_run}):
    raise ValueError("Invalid task signature")
```

Also update beat schedule in `config.py` `get_beat_schedule()` to sign kwargs:
```python
from services.task_security import sign_task

# In the beat schedule entry for cleanup_old_article_versions:
"kwargs": sign_task(
    "cleanup_old_article_versions",
    (),
    {"days_to_keep": versions_days, "dry_run": False}
),
```

#### A3b: Health Endpoint Auth for Detailed Mode

**File:** `routes/public/__init__.py` (lines 108-115)

`/health?detailed=true` exposes git commit hash and DB pool stats without authentication.

```python
@public_bp.route("/health")
def health() -> tuple[Response, int]:
    from services.health import run_health_checks
    detailed = request.args.get("detailed", "false").lower() == "true"
    if detailed and not session.get("admin"):
        detailed = False
    result = run_health_checks(include_celery=True, detailed=detailed)
    code = 200 if result.is_healthy else 503
    return jsonify(result.to_dict()), code
```

#### A3c: verify_task() Docstring Fix

**File:** `services/task_security.py` (lines 47-77)

The docstring at line 57 says "True if ... no secret is configured" but the actual code returns `False` (fail-closed) when no secret is configured. Fix the docstring:

```python
Returns:
    True if signature is valid or no signature is present (internal .s() call)
    False if signature is invalid or CELERY_TASK_SECRET is not configured
```

---

### A4: Missing Environment Variables Documentation — HIGH

**File:** `.env.example`

15+ environment variables used in code are not documented. Add the following sections:

```bash
# === REQUIRED FOR PRODUCTION ===

# HMAC signing secret for Celery tasks (min 32 characters)
CELERY_TASK_SECRET=

# Public site URL for newsletter links (no trailing slash)
SITE_URL=https://ainews.example.com

# === REDIS ===

# Redis TLS (set to "true" for rediss:// or TLS connections)
REDIS_SSL=false

# Redis password (if authentication enabled)
REDIS_PASSWORD=

# === SEARCH PROVIDERS ===

# Google Custom Search API
GOOGLE_API_KEY=
GOOGLE_CSE_ID=

# === LLM PROVIDERS (Optional) ===

GEMINI_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
XAI_API_KEY=
TOGETHERAI_API_KEY=
FIREWORKS_API_KEY=
CEREBRAS_API_KEY=
ZAI_API_KEY=
MINIMAX_API_KEY=
OPENCODE_API_KEY=

# === OPERATIONAL (Optional) ===

# Dead letter alert threshold (default: 10)
DEAD_LETTER_ALERT_THRESHOLD=10

# Content extraction timeout in seconds (default: 30)
CONTENT_EXTRACTOR_TIMEOUT=30

# Logging format: json or text (default: json)
LOG_FORMAT=json

# Duplicate detection window in days (default: 7)
DUPLICATE_DETECTION_DAYS=7

# Ollama configuration
OLLAMA_MODEL=llama3.1
OLLAMA_HOST=http://localhost:11434
```

---

## WAVE 3: Performance

**Estimated Time:** ~5 hours
**Sub-agents:** 3 (can run in parallel, no file conflicts)

### A1: SLA Metrics SQL Aggregation — CRITICAL

**File:** `routes/admin/api/pipeline.py` (lines 139-234)

Current code loads ALL articles with `.all()` (line 155) and computes avg/p50/p95 in Python. For 30-day ranges, this can consume ~750MB+.

**Implementation:** Add `_compute_duration_stats()` helper using SQLite `ROW_NUMBER() OVER()` for percentile computation:

```python
def _compute_duration_stats(session, Article, cutoff, start_col, end_col, base_filters=None):
    if base_filters is None:
        base_filters = []

    duration_expr = (func.julianday(end_col) - func.julianday(start_col)) * 86400
    base_filters = base_filters + [start_col.isnot(None), end_col.isnot(None)]

    total = session.query(func.count()).filter(*base_filters).scalar()
    if total == 0:
        return {"avg": None, "p50": None, "p95": None}

    avg = session.query(func.avg(duration_expr)).filter(*base_filters).scalar()

    p50_subq = session.query(
        duration_expr.label('duration'),
        func.row_number().over(order_by=duration_expr).label('rn'),
    ).filter(*base_filters).subquery()

    p50_offset = (total // 2) + 1
    p95_offset = max(1, int(total * 0.95))

    p50 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p50_offset).scalar()
    p95 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p95_offset).scalar()

    return {
        "avg": round(avg, 1) if avg else None,
        "p50": round(p50, 1) if p50 else None,
        "p95": round(p95, 1) if p95 else None,
    }
```

Replace lines 149-213 with:
```python
base_filters = [Article.published_at.isnot(None), Article.published_at >= cutoff]

c2s = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.selected_at, base_filters)
s2p = _compute_duration_stats(db.session, Article, cutoff, Article.selected_at, Article.published_at, base_filters)
c2p = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.published_at, base_filters)
```

**Sub-agent note:** The response JSON format MUST remain identical. Verify with: `curl -s "http://localhost:5000/admin/api/pipeline/sla?days=7" | python -m json.tool`

---

### A2: N+1 Query Fix + Cache Scoping — CRITICAL

#### A2a: N+1 Fix in Public Feeds

**File:** `routes/public/feeds.py` (line 37)

```python
# Current:
articles = Article.query.filter(Article.id.in_(cached_ids)).all()

# Fix:
from sqlalchemy.orm import joinedload

articles = (
    Article.query
    .options(joinedload(Article.source), joinedload(Article.tags))
    .filter(Article.id.in_(cached_ids))
    .all()
)
```

#### A2b: Cache Key Namespacing

**Problem:** Admin operations invalidate public cache keys using bare prefixes like `invalidate_prefix("index")` which has no namespace separation.

**Files to change:**

`routes/public/feeds.py` — prefix all cache keys with `pub:`:
```python
# Line 31: cache_key = f"pub:top_impact:{limit}"
# Line 69: cache_key = f"pub:index:page:{page}:cat:{category}:q:{query}"
# Line 113: cache_key = f"pub:topic:{category}:page:{page}"
# Line 199: cache_key = f"pub:rss_feed:all:{site_url}"
# Line 242: cache_key = f"pub:rss_feed:{category}:{site_url}"
```

`routes/public/links.py` (line 30):
```python
cache_key = f"pub:article_detail:{article_id}"
```

`routes/admin/articles.py` (lines 283-289):
```python
# Change:
cache.invalidate_prefix("index")    →  cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("topic")    →  cache.invalidate_prefix("pub:topic")
cache.invalidate_prefix("rss")      →  cache.invalidate_prefix("pub:rss")
cache.invalidate(f"article_detail:{article_id}")  →  cache.invalidate(f"pub:article_detail:{article_id}")
```

`routes/admin/review.py` (lines 87-97):
```python
cache.invalidate_prefix("pub:index")
cache.invalidate_prefix("pub:topic")
cache.invalidate_prefix("pub:rss")
if article.category:
    cache.invalidate_prefix(f"pub:topic:{article.category}")
```

**Sub-agent note:** After this change, there will be a brief cold-cache period. Verify with `redis-cli keys "pub:*"` to confirm new key format.

---

### A3: Caching Improvements — HIGH/MEDIUM

#### A3a: Provider Info Caching — HIGH

**File:** `services/llm/__init__.py` (lines 107-109)

`get_provider_info()` makes a live API call to the LLM provider on every dashboard load. Wrap in ResponseCache.

```python
def get_provider_info() -> dict:
    from services.cache import get_response_cache
    cache = get_response_cache()

    def _fetch():
        provider = get_provider()
        return provider.health_check()

    try:
        return cache.get_or_set("llm:provider:info", _fetch, ttl=300)
    except Exception:
        return _fetch()
```

#### A3b: Dashboard Stampede Protection — MEDIUM

**File:** `routes/admin/dashboard.py` (lines 77-86)

Dashboard uses raw `redis_client.setex()` without stampede protection. Replace with `ResponseCache.get_or_set()`:

1. Extract all stat computation into a `_compute_dashboard_stats()` function
2. Replace manual get/set with `get_or_set("dashboard:stats:v2", _compute_dashboard_stats, ttl=300)`
3. Add Redis error fallback

#### A3c: Related Articles Caching — MEDIUM

**File:** `services/related.py` or call site in `routes/public/links.py`

`find_related_articles()` runs an expensive 50-article SQL query + Python scoring on every article view. Cache result with TTL 600s.

```python
def find_related_articles_cached(article_id: int, limit: int = 5):
    from services.cache import get_response_cache
    cache = get_response_cache()
    cache_key = f"pub:related:{article_id}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = find_related_articles(article_id, limit)
    cache.set(cache_key, result, ttl=600)
    return result
```

#### A3d: Sitemap Caching — MEDIUM

**File:** `routes/public/feeds.py` (sitemap route ~line 277)

Cache sitemap XML with 5-minute TTL using key `pub:sitemap:xml`.

#### A3e: Dashboard Source Count — LOW

**File:** `routes/admin/dashboard.py` (line 127)

```python
# Current:
sources = Source.query.all()
source_count = len(sources)

# Fix:
source_count = Source.query.count()
```

---

## WAVE 4: Error Handling, Reliability & Database

**Estimated Time:** ~3 hours
**Sub-agents:** 3 (can run in parallel, minimal file conflicts)

### A1: Error Handling — MEDIUM/HIGH

#### A1a: Webhook json.loads — LOW (downgraded from CRITICAL)

**File:** `tasks/edit.py` (line 271)

**Verified:** The `json.loads(article.final_article)` at line 271 is inside a `try/except Exception` block (lines 263-283) for webhook triggering. The main article processing uses Pydantic model validation (`CondensedArticle`) and `validate_and_raise()` which handles `JSONDecodeError`. The risk is that a JSON parse failure in the webhook trigger is logged as a generic "Webhook trigger failed" warning rather than specifically identifying the JSON issue.

Fix: Add more specific logging inside the webhook try block:
```python
try:
    headline = (
        json.loads(article.final_article).get("headline", "")
        if article.final_article
        else ""
    )
except json.JSONDecodeError as e:
    logger.warning("Malformed final_article JSON in webhook for article %d: %s", article.id, e)
    headline = article.original_title or ""
```

#### A1b: Silent Duplicate Check Failure — MEDIUM

**File:** `tasks/extract.py` (lines 154-158)

Dedup check failure is caught broadly and logged, but no metric is emitted for monitoring.

```python
except Exception as exc:
    logger.warning("Dedup check failed for %s: %s", truncate_for_log(validated.title), exc)
    duplicate = None
    try:
        from services.metrics import get_metrics
        get_metrics().increment("pipeline.dedup_check_failed", tags={"source": source_key})
    except Exception:
        pass
```

#### A1c: Cache get_or_set Redis Error Handling — MEDIUM

**File:** `services/cache.py` (lines 136, 150, 155)

Three Redis calls in `get_or_set()` lack `redis.exceptions.RedisError` handling. If Redis is down, these propagate as unhandled errors instead of falling through gracefully.

Wrap lines 136, 150, 155 in try/except for `redis.exceptions.RedisError`:
```python
try:
    if self._redis.set(lock_key, "1", nx=True, ex=10):
        # ... existing logic ...
except redis.exceptions.RedisError as e:
    logger.warning("Failed to acquire cache lock for %s: %s", lock_key, e)
    value = loader_fn()
    self.set(key, value, ttl)
    return value
```

#### A1d: Newsletter Retry Configuration — MEDIUM

**File:** `tasks/newsletter.py` (lines 351-357)

`generate_daily_newsletters` is missing `autoretry_for`, `retry_backoff`, `retry_jitter`. All other orchestrator tasks have these.

```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
```

---

### A2: Database Indexes — MEDIUM

**File:** `migrations/versions/` (new files)

Latest migration is `024_missing_query_indexes.py`. Create 5 new migrations:

**025_article_pipeline_status_partial_indexes.py:**
```python
def upgrade() -> None:
    op.create_index("ix_articles_pipeline_status_failed", "articles", ["updated_at"],
        unique=False, where="pipeline_status = 'failed'")
    op.create_index("ix_articles_pipeline_status_review", "articles", ["impact_score"],
        unique=False, where="pipeline_status = 'review'")
    op.create_index("ix_articles_pipeline_status_active", "articles", ["updated_at"],
        unique=False, where="pipeline_status IN ('pending', 'researching', 'writing', 'editing')")
```

**026_subscriber_active_index.py:**
```python
op.create_index("ix_subscribers_active_deleted", "subscribers", ["active", "deleted_at"], unique=False)
```

**027_webhook_event_index.py:**
```python
op.create_index("ix_webhook_events_webhook_delivered", "webhook_events", ["webhook_id", "delivered_at"], unique=False)
```

**028_pipeline_run_type_status_index.py:**
```python
op.create_index("ix_pipeline_runs_type_status", "pipeline_runs", ["run_type", "status"], unique=False)
```

**029_audit_log_action_index.py:**
```python
op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"], unique=False)
```

**Sub-agent note:** SQLite doesn't support `op.create_unique_constraint` via ALTER TABLE. Use partial indexes only. Run `flask db upgrade` after creating all migrations.

---

### A3: Transaction & Memory Fixes — HIGH/MEDIUM

#### A3a: Bulk Operations Transaction Ordering — MEDIUM

**File:** `routes/admin/api/articles.py`

In `_bulk_set_category` (line 14), `_bulk_reprocess` (line 52), and `_bulk_add_tags` (line 129), cache invalidation happens BEFORE `db.session.commit()`. If commit fails, cache is already invalidated (stale).

Fix pattern for all three:
```python
# 1. Make DB changes
# 2. Commit FIRST (try/except SQLAlchemyError with rollback)
# 3. Invalidate cache AFTER successful commit (try/except redis.exceptions.RedisError)
```

#### A3b: Unbounded Memory in Duplicate Detection — HIGH

**File:** `services/article.py` (lines 290-304)

`find_duplicate_titles()` has no `.limit()` or `.order_by()`. Add:
```python
.order_by(Article.created_at.desc())
.with_entities(Article.id, Article.original_title)
.limit(1000)
```

---

## WAVE 5: Test Infrastructure, Code Quality & Frontend

**Estimated Time:** ~8 hours
**Sub-agents:** 3 (can run in parallel)

### A1: Test Infrastructure — MEDIUM

#### A1a: Shared MockRedis Fixture

**File:** `tests/conftest.py`

Add a `mock_redis_client` fixture using `tests.mock_redis.MockRedis` for stateful Redis testing. Current `mock_redis` fixture (line 50) is a plain `MagicMock`.

```python
@pytest.fixture
def mock_redis_client():
    from tests.mock_redis import MockRedis
    return MockRedis()
```

#### A1b: Autouse DNS Cache Clear Fixture

**File:** `tests/conftest.py`

Currently `_clear_dns_cache` is defined locally in `tests/test_url_ssrf.py` and `tests/test_url_validate.py`. Move to conftest.py as autouse:

```python
from services.url import _dns_cache

@pytest.fixture(autouse=True)
def _clear_dns_cache():
    _dns_cache.clear()
    yield
    _dns_cache.clear()
```

Remove the local fixtures from individual test files.

#### A1c: ResponseCache Test Fixture

**File:** `tests/conftest.py`

```python
@pytest.fixture
def response_cache_setup(mock_redis_client):
    from services.cache import ResponseCache
    cache = ResponseCache()
    cache._redis = mock_redis_client
    return cache
```

#### A1d: Missing Test Coverage

Create new test files:

**`tests/test_task_security.py`** (5 tests):
- `test_sign_task_creates_valid_signature`
- `test_verify_task_accepts_valid_signature`
- `test_verify_task_rejects_tampered_signature`
- `test_verify_task_fails_closed_on_missing_secret`
- `test_verify_task_allows_internal_call`

**`tests/test_webhooks.py`** (4 tests):
- `test_dispatch_creates_event_record`
- `test_trigger_event_only_calls_subscribed_webhooks`
- `test_webhook_idempotency_prevents_duplicate_events`
- `test_webhook_retry_on_failure`

**`tests/test_trend_memory.py`** (4 tests):
- Test propose_trend_memory creates entries
- Test get_memory_for_topics returns matching entries
- Test memory expiry filtering
- Test consolidation promotes low→medium

Add to `tests/test_admin_api.py`:
- `test_export_subscribers_streams_csv`
- `test_export_subscribers_correct_format`

**Sub-agent note:** All test files need `CELERY_TASK_SECRET` set via `@patch.dict("os.environ", {"CELERY_TASK_SECRET": "test-secret-key-at-least-32-characters"})`. Use the `app` fixture for tests that need database access.

---

### A2: Code Quality — LOW/MEDIUM

#### A2a: Exception Handling Improvements

| File | Line | Current | Fix |
|------|------|---------|-----|
| `models.py` | 29 | `except Exception:` in `decode_short_url` | `except (ValueError, TypeError):` |
| `adapters/web.py` | 117 | `except Exception: pass` in trafilatura fallback | Add `logger.debug("Trafilatura extraction failed: %s", e)` before `pass` |
| `routes/admin/api/articles.py` | ~148 | `except Exception` near db commit | `except SQLAlchemyError` |

#### A2b: Redis Version Alignment

**File:** `requirements.txt` (line 10)

```diff
- redis>=7.0.0,<8.0.0
+ redis==6.4.0
```

`pyproject.toml` correctly pins `redis==6.4.0`. No Redis 7.x features are used.

#### A2c: Beat Schedule Deprecation Comment

**File:** `config.py`

The `CELERY_BEAT_SCHEDULE` class attribute on `Config` (lines 85-123) is dead code — `get_beat_schedule()` (line 126) reads from `pipeline.yaml`. Add deprecation comment:

```python
CELERY_BEAT_SCHEDULE = {}  # DEPRECATED: Use get_beat_schedule() instead. Actual schedule is loaded from pipeline.yaml.
```

#### A2d: Dead Fixture Removal

**File:** `tests/conftest.py` (lines 39-46)

`_reset_factory_counter` fixture is dead code — the counter generates unique strings that remain unique across tests without reset.

#### A2e: Citation Lazy Loading

**File:** `models.py` (~line 139)

```python
# Current:
citations = db.relationship("Citation", backref="article", lazy="select", cascade="all, delete-orphan")
# Change to:
citations = db.relationship("Citation", backref="article", lazy="selectin", cascade="all, delete-orphan")
```

#### A2f: SoftTimeLimitExceeded Work Loss

**File:** `tasks/pipeline.py` (lines 275-286)

When soft timeout occurs, `last_error` update is never persisted (session rolled back before commit), and `retry_count` is not incremented. Fix: persist failure state before re-raising.

```python
except SoftTimeLimitExceeded:
    db.session.rollback()

    exc_article = db.session.get(Article, article_id)
    if exc_article:
        exc_article.last_error = f"{stage}: soft time limit exceeded"
        exc_article.retry_count = (exc_article.retry_count or 0) + 1
        exc_article.total_retries = (exc_article.total_retries or 0) + 1
        exc_article.pipeline_status = _get_stuck_status_for_stage(stage)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    record_stage_result(stage, success=False, run_id=run_id)
    raise
```

#### A2g: Additional Code Quality Items (Optional)

These are low-priority polish items that can be deferred:
- Tag.articles backref (`models.py`)
- Trend memory deduplication (`services/trend_memory.py`)
- Subagent chain re-escaping (`services/subagent.py`)
- ModelLimiter initial poll interval adjustment (`services/limiter.py`)
- ResponseCache second SET NX fix (`services/cache.py`)
- Stage failure TTL refresh (`services/pipeline_failure.py`)
- Trend memory batch consolidation (`services/trend_memory.py`)
- Trend memory batch commit (`services/trend_memory.py`)
- L1 cache cleanup task (`services/cache.py`)

---

### A3: Frontend (CSS/Build) — MEDIUM/LOW

#### A3a: CSS Duplication Cleanup — HIGH

**Files:** `static/css/layout.css`, `static/css/critical.css`

12 classes duplicated across both files (`.nav`, `.logo`, `.logo-slash`, `.nav-links`, `.nav-meta`, `.nav-tag`, `.container`, `.site-header`, `.site-footer`, `.htmx-indicator`, `.htmx-request #content`, `.nav-toggle-label`). Also `.nav-tag` is duplicated WITHIN `layout.css` (lines 59-66 AND 108-115).

Refactor `layout.css` to only add responsive overrides, not re-declare base rules from `critical.css`. Keep `critical.css` as the source of truth for base definitions.

**Sub-agent note:** This is intentional duplication per AGENTS.md — `critical.css` is inlined and must work standalone. Do NOT remove the duplication entirely — only remove rules in `layout.css` that are exact copies without any additions. Keep responsive `@media` overrides in `layout.css`. The `.htmx-indicator` duplication MUST stay in both files.

#### A3b: Theme Toggle Dedup — HIGH

**File:** `static/css/components.css` (lines 238-273)

`.theme-toggle` and `.theme-icon-light` are byte-for-byte identical to `critical.css` (lines 256-291). Remove from `components.css` — `critical.css` (inlined) provides these rules.

#### A3c: CSS Token Duplication Comment — LOW

**File:** `static/css/critical.css`

Add comment at top of custom properties section:
```css
/*
 * IMPORTANT: Tokens are duplicated in this file AND variables.css.
 * Any changes must be made to BOTH files to prevent color flash on first paint.
 * See: AGENTS.md - "CSS consolidation note"
 */
```

#### A3d: Build Pipeline — MEDIUM

**Files:** `Makefile`, `templates/base.html`, `templates/base_admin.html`, `.gitignore`

Add CSS/JS minification using esbuild:

```makefile
build-assets: ## Minify and bundle CSS/JS for production
	esbuild static/css/style.css --bundle --minify --outfile=static/css/style.min.css
	esbuild static/js/app.js static/js/theme.js static/js/share-a11y.js --bundle --minify --outfile=static/js/app.min.js

.PHONY: build-assets
```

Update templates to reference `.min` versions. Add `*.min.css` and `*.min.js` to `.gitignore`. Keep `htmx.min.js` as a separate vendor file.

---

## Implementation Parallelization

```
WAVE 1 ─┬── A1: Template XSS (templates/)
         └── A2: Validation & Docs (routes, .env.example)
              (~30 min, 2 parallel agents)

WAVE 2 ─┬── A1: Redis TLS (extensions.py, config_cache.py)
         ├── A2: DEBUG enforcement (config.py)
         ├── A3: Task signing + Health + Docstring (tasks/, routes/, services/)
         └── A4: Env vars docs (.env.example)
              (~5 hrs, 4 parallel agents)

WAVE 3 ─┬── A1: SLA SQL aggregation (routes/admin/api/pipeline.py)
         ├── A2: N+1 fix + Cache scoping (feeds.py, links.py, admin/)
         └── A3: Caching improvements (llm/, dashboard.py, related.py)
              (~5 hrs, 3 parallel agents)

WAVE 4 ─┬── A1: Error handling (edit.py, extract.py, cache.py, newsletter.py)
         ├── A2: Database indexes (migrations/)
         └── A3: Transaction + memory fixes (articles.py, article.py)
              (~3 hrs, 3 parallel agents)

WAVE 5 ─┬── A1: Test infrastructure (conftest.py, test files)
         ├── A2: Code quality (models.py, requirements.txt, config.py, etc.)
         └── A3: Frontend CSS (layout.css, critical.css, components.css)
              (~8 hrs, 3 parallel agents)
```

**File conflict analysis (no two agents touch same file in same wave):**
- Wave 1: A1 touches templates, A2 touches routes + .env
- Wave 2: A1 touches extensions.py + config_cache.py, A2 touches config.py, A3 touches tasks/cleanup.py + routes/public/__init__.py + services/task_security.py, A4 touches .env.example
- Wave 3: A1 touches pipeline.py, A2 touches feeds.py + links.py + admin files, A3 touches llm/ + dashboard.py
- Wave 4: A1 touches edit.py + extract.py + cache.py + newsletter.py, A2 creates new migration files, A3 touches articles.py (admin api) + article.py (services)
- Wave 5: A1 touches test files, A2 touches production code, A3 touches CSS files

**Total estimated:** ~21 hours across all waves

---

## Rollback Plan

| Change | Rollback Method |
|--------|----------------|
| XSS fixes (`\|e` filters) | Remove `\|e` filters |
| Redis TLS | Remove `ssl=` parameter |
| DEBUG enforcement | Remove check from `ProductionConfig.validate()` |
| SLA SQL aggregation | Revert to `.all()` + Python loops |
| N+1 feeds fix | Remove `joinedload()` calls |
| Cache scoping | Remove `pub:` prefix from keys |
| Database indexes | `flask db downgrade <migration>` |
| Test fixtures | Revert conftest.py changes |
| CSS dedup | Revert changes in layout.css |

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

**Wave 1 (XSS):** Navigate to `/admin/articles/<id>/edit` with crafted `final_article` containing `<script>alert('xss')</script>`. Verify it does NOT execute.

**Wave 3 (Performance):**
```bash
curl -s "http://localhost:5000/admin/api/pipeline/sla?days=7" | python -m json.tool
redis-cli keys "pub:*"
```

**Wave 4 (Migrations):**
```bash
flask db upgrade
./scripts/query_analysis.sh
```

---

## Issue Summary

| ID | Wave | Priority | Category | File(s) | Description |
|----|------|----------|----------|---------|-------------|
| XSS-001 | 1 | CRITICAL | XSS | templates/admin/article_edit.html | Form values without escaping (10 locations) |
| XSS-002 | 1 | CRITICAL | XSS | templates/admin/dead_letters.html | Title text without escaping (2 locations) |
| XSS-003 | 1 | HIGH | XSS | templates/article.html | Missing `\|e` on original_title in `<title>` |
| XSS-004 | 1 | HIGH | XSS | templates/partials/condensed_article.html | Missing `\|e` on writer_model |
| VAL-001 | 1 | HIGH | Validation | routes/admin/api/articles.py | Missing integer validation on bulk IDs |
| DOC-001 | 1 | HIGH | Documentation | .env.example, docs/configuration.md | Missing WEBHOOK_SECRET_KEY |
| LOG-001 | 1 | LOW | Logging | routes/public/subscribe.py | Full tokens logged (lines 171, 212) |
| SEC-001 | 2 | CRITICAL | TLS | extensions.py, config_cache.py | No TLS for Redis connections |
| SEC-002 | 2 | HIGH | Config | config.py | DEBUG not checked in ProductionConfig.validate() |
| SEC-003 | 2 | MEDIUM | Task | tasks/cleanup.py | cleanup_old_article_versions lacks HMAC signing |
| SEC-004 | 2 | MEDIUM | Info | routes/public/__init__.py | Detailed health leaks system info |
| SEC-005 | 2 | LOW | Docs | services/task_security.py | Inaccurate docstring |
| SEC-006 | 2 | HIGH | Documentation | .env.example | Missing 15+ env vars |
| PERF-001 | 3 | CRITICAL | Memory | routes/admin/api/pipeline.py | SLA loads all articles |
| PERF-002 | 3 | CRITICAL | N+1 | routes/public/feeds.py | Missing joinedload on source |
| PERF-003 | 3 | CRITICAL | Cache | routes/admin/articles.py | Overbroad invalidation |
| PERF-004 | 3 | HIGH | API | services/llm/__init__.py | Uncached provider info |
| PERF-005 | 3 | MEDIUM | Stampede | routes/admin/dashboard.py | No lock on setex |
| PERF-006 | 3 | MEDIUM | Cache | services/related.py | Uncached find_related_articles |
| PERF-007 | 3 | MEDIUM | Cache | routes/public/feeds.py | Sitemap not cached |
| PERF-008 | 3 | LOW | Query | routes/admin/dashboard.py | Loads all sources for count |
| ERR-001 | 4 | LOW | Error | tasks/edit.py:271 | json.loads in webhook trigger without specific error |
| ERR-002 | 4 | MEDIUM | Error | tasks/extract.py:154 | Silent dedup check failure |
| ERR-003 | 4 | MEDIUM | Error | services/cache.py:136,150,155 | Missing Redis error handling |
| ERR-004 | 4 | MEDIUM | Celery | tasks/newsletter.py:351 | Missing retry_jitter |
| DB-001 | 4 | MEDIUM | Index | migrations/versions/* | Missing partial indexes |
| DB-002 | 4 | MEDIUM | Transaction | routes/admin/api/articles.py | Bulk ops cache-before-commit |
| DB-003 | 4 | HIGH | Memory | services/article.py:290 | Unbounded duplicate detection |
| TEST-001 | 5 | MEDIUM | Test | conftest.py | No shared MockRedis fixture |
| TEST-002 | 5 | MEDIUM | Test | conftest.py | No autouse DNS cache clear |
| TEST-003 | 5 | MEDIUM | Test | conftest.py | No ResponseCache fixture |
| TEST-004 | 5 | MEDIUM | Test | tests/ | Missing critical tests |
| CQ-001 | 5 | HIGH | Dependency | requirements.txt | Redis version conflict |
| CQ-002 | 5 | MEDIUM | Error | models.py:29 | Broad exception in decode_short_url |
| CQ-003 | 5 | MEDIUM | Config | config.py | Dead beat schedule attribute |
| CQ-004 | 5 | LOW | Code | models.py:139 | Citation lazy loading |
| CQ-005 | 5 | LOW | Code | tests/conftest.py:39 | Dead fixture |
| CQ-006 | 5 | LOW | Reliability | tasks/pipeline.py:275 | SoftTimeLimitExceeded work loss |
| FE-001 | 5 | HIGH | CSS | critical.css, layout.css | 12 classes duplicated |
| FE-002 | 5 | HIGH | CSS | components.css | .theme-toggle duplicated |
| FE-003 | 5 | MEDIUM | Build | Makefile, templates | No minification/bundling |
| FE-004 | 5 | LOW | CSS | critical.css | Add token duplication comment |

---

*End of consolidated plan*
