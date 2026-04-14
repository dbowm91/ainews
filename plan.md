# Consolidated Implementation Plan

This document consolidates all improvement items from the planning phase into a unified, prioritized implementation plan with wave-based parallelization.

## Overview

The implementation is organized into **4 waves** of parallelizable work:

| Wave | Focus | Items | Parallelizable |
|------|-------|-------|----------------|
| **Wave 1** | Critical Security | XSS, Prompt Injection, eval() replacement | Yes |
| **Wave 2** | High-Priority Security | Session fixation, webhook masking, Redis URL | Yes |
| **Wave 3** | Code Quality & Reliability | Config access, datetime, logging, transaction safety | Yes |
| **Wave 4** | Performance Optimization | Regex pre-compile, eager loading, cache fixes | Yes |
| **Wave 5** | Infrastructure | Newsletter batching, source health, cleanup tasks | Yes |

---

## Wave 1: Critical Security (Parallelizable)

### W1.1: Fix XSS in Templates - Add HTML Escaping
**Priority**: Critical | **Impact**: Security | **Effort**: Medium

**Files**: `templates/partials/condensed_article.html`, `templates/partials/article_body.html`, `templates/partials/article_card.html`, `templates/partials/related_articles.html`, `templates/partials/top_impact.html`, `templates/admin/partials/review_table.html`, `templates/share_redirect.html`

**Issue**: LLM-generated content (`final_article` JSON fields) and crawled content rendered without HTML escaping. Malicious LLM output could inject XSS.

**Solution**: Add `|e` filter to all LLM-generated and external content:

```html
{{ fa.headline|e }}
{{ fa.tldr|e }}
{{ fa.why_it_matters|e }}
```

**Affected Templates and Fields**:
| File | Fields |
|------|--------|
| `templates/partials/condensed_article.html` | headline, tldr, why_it_matters, point, body, what_to_watch, source, original_url, cite.title, cite.url |
| `templates/partials/article_body.html` | sd.headline, original_title, sd.tldr, summary, sd.why_it_matters, p |
| `templates/partials/article_card.html` | _fa.headline (2x), _fa.tldr, _summary.tldr |
| `templates/partials/related_articles.html` | original_title, _fa.tldr |
| `templates/partials/top_impact.html` | _fa.headline, _fa.tldr |
| `templates/admin/partials/review_table.html` | _fa.tldr[:120] |
| `templates/share_redirect.html` | _fa.headline |

---

### W1.2: Fix Subagent Prompt Injection
**Priority**: Critical | **Impact**: Security | **Effort**: Medium

**Files**: `services/subagent.py` (lines 346, 524), `tasks/research.py`, `tasks/edit.py`

**Issue**: `template.format()` is called with unescaped user content. Malicious content could inject `</source_article>` closing tags to break XML structure.

**Solution**: Apply `esc_xml_text()` before formatting:

```python
from services.prompts import esc_xml_text

prompt_data_escaped = {
    "title": esc_xml_text(article.original_title or ""),
    "body": esc_xml_text(article.extracted_text or ""),
    "web_results": _format_web_results_escaped(web_results),
}
prompt = template.format(**prompt_data_escaped)
```

**Affected Functions**:
| Line | Function | Unescaped Fields |
|------|----------|------------------|
| 346 | `_call_subagent()` | title, body, web_results |
| 524 | `_call_edit_contextualization()` | draft, brief, topic_notes, related_articles, trend_memory |

Also fix `tasks/research.py:_format_web_results()` which does NOT escape XML characters.

---

### W1.3: Replace eval() in Subagent Condition Evaluation
**Priority**: Critical | **Impact**: Security | **Effort**: Medium

**Files**: `services/subagent.py` (lines 777-785)

**Issue**: `eval()` in condition evaluation is a security risk even with empty `__builtins__`.

**Solution**: Replace with safe expression parser using Python's `ast` module:

```python
import ast
import operator

_ALLOWED_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.And: operator.and_,
    ast.Or: operator.or_,
    ast.Not: operator.not_,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_ALLOWED_NAMES = {"True", "False", "None", "results"}

def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Safely evaluate a condition expression against the context."""
    try:
        tree = ast.parse(condition, mode="eval")
    except (SyntaxError, ValueError):
        return False
    allowed_names = {"results": context, **context}
    
    def _eval_node(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        elif isinstance(node, ast.BoolOp):
            op = _ALLOWED_OPS[type(node.op)]
            values = [_eval_node(v) for v in node.values]
            return op(values[0], values[1]) if len(values) == 2 else op(*values)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _eval_node(node.operand)
        elif isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                op = _ALLOWED_OPS[type(op_node)]
                right = _eval_node(comparator)
                if not op(left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ValueError(f"Unknown identifier: {node.id}")
            return allowed_names[node.id]
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Attribute):
            obj = _eval_node(node.value)
            return getattr(obj, node.attr)
        elif isinstance(node, ast.Subscript):
            obj = _eval_node(node.value)
            if isinstance(node.slice, ast.Constant):
                idx = node.slice.value
                if isinstance(obj, (list, tuple)):
                    return obj[idx]
                elif isinstance(obj, dict):
                    return obj[idx]
            raise ValueError("Only constant indices supported")
        else:
            raise ValueError(f"Unsupported node type: {type(node).__name__}")
    
    return bool(_eval_node(tree))
```

---

### W1.4: Add Security Tests for eval() Replacement
**Priority**: High | **Impact**: Verification | **Effort**: Low

**File**: `tests/test_security_conditions.py` (new)

**Required Tests**:
1. **Positive cases**: Numeric comparisons, string comparisons, boolean operations, attribute access, dictionary key access
2. **Negative cases** (should return False, not raise): Import attempts, function calls, dunder access, subscript assignment, lambda definitions
3. **Edge cases**: Empty condition, whitespace-only, non-existent context keys

---

## Wave 2: High-Priority Security (Parallelizable)

### W2.1: Fix Session Fixation on Login
**Priority**: High | **Impact**: Security | **Effort**: Low

**File**: `routes/admin/auth.py` (lines 52-53)

**Issue**: `session.pop("admin", None)` followed by `session["admin"] = True` does NOT regenerate session ID.

**Solution**:
```python
session.clear()  # or session.regenerate_id()
session["admin"] = True
```

---

### W2.2: Mask Webhook Secrets in API Responses
**Priority**: High | **Impact**: Security | **Effort**: Low

**File**: `routes/admin/api/webhooks.py` (line 92)

**Issue**: Full webhook secret returned in create response.

**Solution**:
```python
def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"
```

---

### W2.3: Fix Redis Credential URL Parsing
**Priority**: High | **Impact**: Security | **Effort**: Low

**File**: `extensions.py` (lines 24-28)

**Issue**: URL reconstruction strips credentials when switching databases.

**Solution**:
```python
from urllib.parse import urlparse, urlunparse

def _get_limiter_storage_uri() -> str:
    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    if "://" in broker_url:
        parsed = urlparse(broker_url)
        new_parsed = parsed._replace(path="/15")
        return urlunparse(new_parsed)
    return "memory://"
```

---

### W2.4: Fix RSS XML Injection
**Priority**: Medium | **Impact**: Security | **Effort**: Low

**File**: `services/rss.py` (lines 28-35)

**Issue**: LLM-generated headlines inserted into XML without escaping.

**Solution**:
```python
import html
title_text = html.escape(headline or article.original_title or "")
SubElement(item, "title").text = title_text
description_text = html.escape(tldr or "")
SubElement(item, "description").text = description_text
```

---

### W2.5: Fix Trend Memory Prompt Injection
**Priority**: Medium | **Impact**: Security | **Effort**: Low

**File**: `services/trend_memory.py` (line 178)

**Solution**:
```python
from services.prompts import esc_xml_text
prompt = TREND_MEMORY_PROMPT.format(
    draft=esc_xml_text(draft),
    topics=", ".join(topics),
    summary=esc_xml_text(summary),
)
```

---

### W2.6: Fix Select/Newsletter Prompt Injection
**Priority**: Medium | **Impact**: Security | **Effort**: Medium

**Files**: `tasks/select.py`, `services/newsletter_pipeline.py`

**Issue**: Raw article content embedded without escaping.

**Solution**:
```python
from services.prompts import esc_xml_text
prompt = (
    f"<article>\n"
    f"<title>{esc_xml_text(article.original_title or '')}</title>\n"
    f"<topics>{esc_xml_text(', '.join(article.topics or []))}</topics>\n"
    f"<preview>{esc_xml_text(text_preview)}</preview>\n"
    f"</article>\n"
)
```

---

### W2.7: Remove CSRF Exemption on Tracking Endpoint
**Priority**: Medium | **Impact**: Security | **Effort**: Low

**File**: `routes/public/links.py` (line 90)

**Solution**: Remove `@csrf.exempt` from `track_share_click` endpoint.

---

### W2.8: Fix Default SECRET_KEY in Warning Logs
**Priority**: Low | **Impact**: Security | **Effort**: Low

**File**: `app.py` (lines 72-75)

**Issue**: Warning contains literal default SECRET_KEY value.

**Solution**:
```python
if dev_cfg.SECRET_KEY == "dev-secret-key-change-me":
    logger.warning(
        "SECRET_KEY is using a default value — "
        "sessions are insecure. Set SECRET_KEY env var for production."
    )
```

---

## Wave 3: Code Quality & Reliability (Parallelizable)

### W3.1: Fix current_app.config.get() in Celery Tasks
**Priority**: High | **Impact**: Reliability | **Effort**: Low

**Files**: `tasks/pipeline.py`, `services/url.py`

**Issue**: Using `current_app.config.get()` in Celery tasks is inconsistent with project conventions.

**Solution** (tasks/pipeline.py):
```python
from services.config_utils import get_config_with_default

def _get_pipeline_timeout_seconds() -> int:
    return get_config_with_default("PIPELINE_TIMEOUT_SECONDS", PIPELINE_TIMEOUT_SECONDS)
```

**Solution** (services/url.py):
```python
def _get_dns_cache_config() -> tuple[int, int]:
    ttl = get_config_with_default("DNS_CACHE_TTL", _DNS_CACHE_TTL)
    max_size = get_config_with_default("DNS_CACHE_MAX", _DNS_CACHE_MAX)
    return ttl, max_size
```

---

### W3.2: Fix Datetime Naive/Aware Mixing
**Priority**: High | **Impact**: Reliability | **Effort**: Low

**Files**: `routes/public/feeds.py`, `tasks/extract.py`

**Issue**: `datetime.now(timezone.utc)` returns aware datetimes, but `Article.original_published_at` is naive. Comparisons raise `TypeError`.

**Solution** (feeds.py):
```python
# Before: cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
# After - normalize to naive datetime
cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
```

**Solution** (extract.py):
```python
if published_at:
    pub_date = datetime.fromisoformat(published_at)
    if pub_date.tzinfo is not None:
        pub_date = pub_date.replace(tzinfo=None)
else:
    pub_date = datetime.utcnow()
```

---

### W3.3: Add Error Handling to _fetch_item
**Priority**: Medium | **Impact**: Robustness | **Effort**: Low

**File**: `adapters/api.py` (lines ~128-129)

**Issue**: Silently swallows all exceptions.

**Solution**:
```python
except Exception as e:
    logger.warning("Failed to fetch item from API: %s", str(e))
    return None
```

---

### W3.4: Fix ValidationError Inheritance
**Priority**: Medium | **Impact**: Consistency | **Effort**: Low

**File**: `services/article_validation.py` (line 9)

**Solution**:
```python
class ValidationError(ValueError):
    pass
```

---

### W3.5: Add Explicit Timeouts to LLM Clients
**Priority**: High | **Impact**: Reliability | **Effort**: Low

**Files**: `services/llm/openai.py`, `services/llm/anthropic.py`

**Solution** (openai.py):
```python
self._client_kwargs = {
    "api_key": cfg.api_key,
    "base_url": cfg.base_url,
    "timeout": 120.0,
}
```

**Solution** (anthropic.py):
```python
self._timeout = 120.0
# In client property:
self._client = Anthropic(api_key=self._api_key, timeout=self._timeout)
```

---

### W3.6: Fix Token Tracking in Pipeline
**Priority**: Medium | **Impact**: Accuracy | **Effort**: Low

**File**: `tasks/pipeline.py` (line 341)

**Issue**: `record_provider_success` called with `tokens_used=max_tokens` instead of actual usage.

**Solution**:
```python
result = work_fn(article, provider, model, max_tokens)
record_provider_success(provider_id, model, tokens_used=result.tokens_used)
```

---

### W3.7: Convert f-string Logs to %-formatting
**Priority**: Low | **Impact**: Performance | **Effort**: Low

**File**: `services/limiter.py` (lines 47-52, 60-66)

**Solution**:
```python
logger.error("Failed to acquire slot for %s: %s", provider_id, e)
logger.error("Failed to release slot for %s: %s", provider_id, e)
```

---

### W3.8: Verify Database Transaction Rollback Patterns
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: All modules performing database operations

**Checklist**:
- [ ] `routes/admin/__init__.py` - Login attempts
- [ ] `routes/admin/articles.py` - Bulk operations
- [ ] `routes/admin/sources.py` - Source CRUD
- [ ] `routes/admin/topic_notes.py` - Note CRUD
- [ ] `tasks/pipeline.py` - Stage updates
- [ ] `services/article.py` - Article operations
- [ ] `services/context_service.py` - Topic notes

---

### W3.9: Add Type Hints to Utility Modules
**Priority**: Low | **Impact**: DX | **Effort**: Medium

**File**: `services/redis_utils.py`

**Solution**: Add type hints to all function signatures following existing codebase patterns.

---

### W3.10: Extract Magic Numbers to Config
**Priority**: Low | **Impact**: Maintainability | **Effort**: Low

**Files**: `routes/admin/__init__.py:40`, `tasks/retry.py:113`

**Solution**: Define `_LOGIN_LOCKOUT_SECONDS = 900` in config.py with proper defaults.

---

## Wave 4: Performance Optimization (Parallelizable)

### W4.1: Pre-compile Regex Patterns
**Priority**: High | **Impact**: High | **Effort**: Low

**Files**: `services/article.py`, `services/url.py`, `services/email.py`, `services/validation.py`, `models.py`

**Issue**: Regex patterns compiled on every function call instead of once at module load.

**Solution**:
```python
# At module level
_TITLE_WORDS_RE = re.compile(r"[a-z0-9]+")

# In function
other_words = set(_TITLE_WORDS_RE.findall(other_title.lower()))
```

**Affected Patterns**:
| File | Pattern | Current Line |
|------|---------|--------------|
| `services/article.py` | `r"[a-z0-9]+"` | 216 |
| `services/url.py` | `r"\s+"` | 278 |
| `services/email.py` | Multiple | 158, 166 |
| `services/validation.py` | `r"[\x00-\x1f\x7f]"` | 76 |
| `models.py` | Multiple | 14-15 |

---

### W4.2: Add Eager Loading to Routes
**Priority**: High | **Impact**: Medium | **Effort**: Low

**Files**: `routes/admin/articles.py`, `routes/public/feeds.py`, `routes/admin/review.py`

**Solution**:
```python
from sqlalchemy.orm import joinedload, selectinload

q = Article.query.options(
    joinedload(Article.source),
    joinedload(Article.tags),
).order_by(Article.created_at.desc())
```

**Affected Queries**:
| File | Line | Missing Eager Load |
|------|------|---------------------|
| `routes/admin/articles.py` | 72 | source, tags |
| `routes/public/feeds.py` | 145, 184, 229, 260 | source, tags |
| `routes/admin/review.py` | 19 | source, tags, metrics |
| `services/related.py` | 75 | tags |

---

### W4.3: Fix ResponseCache.get_or_set() Stampede Vulnerability
**Priority**: Critical | **Impact**: Performance | **Effort**: Medium

**File**: `services/cache.py` (lines 115-122)

**Issue**: Classic cache stampede - all concurrent requests hit `loader_fn()` on cache miss.

**Solution**: Add per-key mutex:
```python
def get_or_set(self, key: str, loader_fn: Callable[[], Any], ttl: int = 120) -> Any:
    cached = self.get(key)
    if cached is not None:
        return cached
    
    lock_key = f"lock:{key}"
    if self._redis_client.set(lock_key, "1", nx=True, ex=10):
        try:
            cached = self.get(key)
            if cached is not None:
                return cached
            value = loader_fn()
            self.set(key, value, ttl)
            return value
        finally:
            self._redis_client.delete(lock_key)
    else:
        import time
        for _ in range(50):
            time.sleep(0.1)
            cached = self.get(key)
            if cached is not None:
                return cached
        return loader_fn()
```

---

### W4.4: Fix Subagent ThreadPoolExecutor Reuse
**Priority**: High | **Impact**: Medium | **Effort**: Medium

**File**: `services/subagent.py` (lines 393-416, 562-588)

**Issue**: New ThreadPoolExecutor created for each retry attempt.

**Solution**:
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    for attempt in range(stage_config.max_retries + 1):
        try:
            if attempt > 0:
                time.sleep(stage_config.retry_delay)
            future = executor.submit(_call_with_timeout)
            result = future.result(timeout=stage_config.timeout_seconds)
```

---

### W4.5: Add Limiter Acquire Timeout
**Priority**: High | **Impact**: High | **Effort**: Medium

**File**: `services/limiter.py` (lines 39-53)

**Issue**: `acquire()` blocks indefinitely with no timeout.

**Solution**: Add proper timeout mechanism using Redis blocking commands or polling loop.

---

### W4.6: Fix Circuit Breaker Fallback State
**Priority**: High | **Impact**: High | **Effort**: Medium

**File**: `services/llm/__init__.py` (lines 54-58)

**Issue**: Each fallback provider creates new circuit breaker, not sharing state.

**Solution**: Track fallback attempts per request context, sharing failure state across providers.

---

### W4.7: Fix Race Condition in Lock Acquisition
**Priority**: Medium | **Impact**: Medium | **Effort**: Medium

**Files**: `tasks/crawl.py`, `tasks/newsletter.py`

**Issue**: Check-then-act pattern with separate GET/SET calls.

**Solution**: Use atomic Lua script (see `services/redis_utils.py:release_lock`).

---

### W4.8: Replace String Concatenation with List/Join
**Priority**: Medium | **Impact**: Medium | **Effort**: Low

**File**: `services/newsletter.py` (lines 26-29, 53-67)

**Solution**:
```python
para_parts = []
for para in paragraphs:
    para_parts.append(f"<p>{html.escape(para)}</p>")
para_html = "".join(para_parts)
```

---

### W4.9: Optimize find_duplicate_titles() O(N²) Behavior
**Priority**: High | **Impact**: Algorithm | **Effort**: Medium

**File**: `services/article.py` (lines 235-281)

**Solution**: Pre-fetch recent articles in batch to avoid per-item queries.

---

### W4.10: Add LRU Eviction to Config Cache
**Priority**: Medium | **Impact**: Medium | **Effort**: Medium

**File**: `services/config_cache.py` (lines 76, 91-94)

**Issue**: Uses FIFO eviction instead of LRU.

**Solution**: Use `collections.OrderedDict` for O(1) LRU operations.

---

### W4.11: Add Response Cache to article_detail()
**Priority**: High | **Impact**: Performance | **Effort**: Low

**File**: `routes/public/links.py`

**Solution**:
```python
cache = get_response_cache()
cache_key = f"article_detail:{article_id}"
cached_html = cache.get(cache_key)
if cached_html:
    return make_response(cached_html)
# ... existing logic ...
cache.set(cache_key, resp.get_data(), ttl=300)
```

---

## Wave 5: Infrastructure & Optimization (Parallelizable)

### W5.1: Parallelize Newsletter Generation with Celery group
**Priority**: Medium | **Impact**: Latency | **Effort**: Medium

**File**: `tasks/newsletter.py` (lines 251-276)

**Solution**:
```python
from celery import group

# Fetch articles for all newsletters first
all_articles = {
    topic_key: _fetch_articles_for_newsletter(topic_key, cutoff, nl.max_articles)
    for topic_key in ["main"] + list(topics.keys())
}

# Build all newsletter generation tasks
task_signatures = [
    _generate_topic_newsletter_impl.s(
        topic_key,
        all_articles[topic_key],
        site_url,
        nl.max_articles,
        None,  # dry_run_email only for main
        nl,
    )
    for topic_key in ["main"] + list(topics.keys())
]

job = group(task_signatures)
results = job.apply_async()
all_results = results.get(timeout=600, propagate=False)
```

---

### W5.2: Batch Email Sending (500/recipient)
**Priority**: Medium | **Impact**: Task overhead | **Effort**: Medium

**File**: `tasks/newsletter.py`

**Solution**:
```python
def _send_batches(subscribers, subject, html, headers):
    BATCH_SIZE = 500
    for i in range(0, len(subscribers), BATCH_SIZE):
        batch = subscribers[i:i + BATCH_SIZE]
        send_email_batch.s(
            recipients=[s.email for s in batch],
            subject=subject,
            html=html,
            headers=headers,
        ).apply_async()
```

---

### W5.3: Batch retry_stuck Commits (50/article)
**Priority**: Medium | **Impact**: Database | **Effort**: Low

**File**: `tasks/retry.py` (lines 73-99)

**Solution**:
```python
BATCH_SIZE = 50
# ... classify articles into batches ...
for i in range(0, len(articles_to_retry), BATCH_SIZE):
    batch = articles_to_retry[i:i + BATCH_SIZE]
    for article in batch:
        article.retry_count = (article.retry_count or 0) + 1
    db.session.commit()
    
    dispatch_group = group([
        _dispatch_stage.si(article.id, article.pipeline_status)
        for article in batch
    ])
    dispatch_group.apply_async()
```

---

### W5.4: Fix SoftTimeLimitExceeded Handling Consistency
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: `tasks/pipeline.py:run_stage()`, `tasks/crawl.py`, `tasks/extract.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`

**Issue**: Only `tasks/newsletter.py` explicitly catches `billiard.exceptions.SoftTimeLimitExceeded`.

**Solution**: Add explicit handling before generic exception handling in all pipeline stage tasks:
```python
from billiard.exceptions import SoftTimeLimitExceeded

try:
    # ... stage work ...
except SoftTimeLimitExceeded:
    db.session.rollback()
    logger.error("SoftTimeLimitExceeded in %s for article %s", stage, article_id)
    raise
except Exception as e:
    # ... existing handling ...
```

---

### W5.5: Add Pipeline Stage Timeout Metrics
**Priority**: Medium | **Impact**: Observability | **Effort**: Low

**File**: `tasks/pipeline.py:run_stage()`

**Solution**:
```python
except SoftTimeLimitExceeded:
    metrics.increment("pipeline.stage.timeout", labels={"stage": stage})
    raise
```

---

### W5.6: Add Article Version Cleanup Task
**Priority**: Medium | **Impact**: Maintainability | **Effort**: Low

**File**: `tasks/cleanup.py`

**Solution**:
```python
@celery_app.task
def cleanup_old_article_versions(days_to_keep: int = 90) -> int:
    """Remove article versions older than specified days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    deleted = ArticleVersion.query.filter(
        ArticleVersion.created_at < cutoff
    ).delete()
    db.session.commit()
    return deleted
```

Add to Celery beat schedule:
```python
'cleanup-old-versions': {
    'task': 'tasks.cleanup.cleanup_old_article_versions',
    'schedule': crontab(hour=3, minute=45),
    'kwargs': {'days_to_keep': 90},
}
```

---

### W5.7: Source Health Hysteresis
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: `services/crawling.py`, `models.py:Source`

**Issue**: Sources auto-disable after 10 failures but re-enable on single success.

**Solution**: Require N consecutive successes before marking as healthy:
```python
HEALTHY_THRESHOLD = 3  # consecutive successes to be "healthy"
```

---

### W5.8: Webhook Retry with Backoff
**Priority**: Medium | **Impact**: Reliability | **Effort**: Medium

**Files**: `services/webhooks.py`, `models.py:Webhook`

**Solution**: Implement exponential backoff retry:
```python
import backoff

@backoff.on_exception(
    backoff.expo,
    (ConnectionError, TimeoutError),
    max_tries=3,
    base_delay=60,
    max_delay=3600,
)
def _deliver_webhook_with_retry(webhook: Webhook, payload: dict) -> bool:
    # ... existing delivery logic ...
```

---

### W5.9: Trend Memory Consolidation Optimization
**Priority**: Low | **Impact**: Performance | **Effort**: Medium

**File**: `services/trend_memory.py` (line 120+)

**Issue**: N+1 queries when promoting low-importance entries.

**Solution**: Batch the lookups:
```python
topics_with_high = db.session.query(TrendMemory.topic).filter(
    TrendMemory.topic.in_([e.topic for e in low_entries]),
    TrendMemory.importance == 3
).distinct().all()
topics_with_high = {t[0] for t in topics_with_high}
```

---

### W5.10: Newsletter Batch Transaction Safety
**Priority**: Low | **Impact**: Reliability | **Effort**: Medium

**File**: `tasks/newsletter.py:generate_daily_newsletters()`

**Issue**: Process fails mid-way, partial newsletters may be sent.

**Solution**: Use draft state and proper transaction boundaries.

---

### W5.11: Add Request ID Tracing Across Pipeline
**Priority**: Medium | **Impact**: Observability | **Effort**: Medium

**Files**: `tasks/pipeline.py`, `tasks/*`, `services/logging_utils.py`

**Solution**: Implement request ID propagation from Celery task ID through all pipeline stages.

---

### W5.12: Add Composite Indexes
**Priority**: High | **Impact**: Database | **Effort**: Low

**Files**: New migrations

**Solution**:
```python
# Migration: 017_add_subscriber_indexes.py
op.create_index('ix_subscribers_newsletter_active_deleted', 'subscribers',
    ['newsletter_type', 'active', 'deleted_at'], unique=False)

# Migration: 018_add_pipeline_log_indexes.py
op.create_index('ix_pipeline_logs_run_created', 'pipeline_logs',
    ['run_id', 'created_at'], unique=False)
```

---

### W5.13: Increase Tag Cloud Cache TTL (60s → 600s)
**Priority**: Low | **Impact**: Performance | **Effort**: Low

**File**: `services/config_cache.py`

**Solution**: Change `cache.set(key, tag_cloud, ttl=60)` to `ttl=600`.

---

## Implementation Order

### Phase 1: Wave 1 - Critical Security (Do First)
- W1.1: Fix XSS in templates
- W1.2: Fix subagent prompt injection
- W1.3: Replace eval() in condition evaluation
- W1.4: Add security tests

### Phase 2: Wave 2 - High-Priority Security
- W2.1-W2.8: Session fixation, webhook secrets, Redis URL, RSS XML, trend memory, select/newsletter, CSRF exemption, SECRET_KEY logs

### Phase 3: Wave 3 - Code Quality & Reliability
- W3.1-W3.10: Config access, datetime, error handling, timeouts, logging, transaction safety

### Phase 4: Wave 4 - Performance Optimization
- W4.1-W4.11: Regex pre-compile, eager loading, cache stampede, concurrency fixes

### Phase 5: Wave 5 - Infrastructure
- W5.1-W5.13: Newsletter batching, source health, cleanup tasks, indexes

---

## Testing

All changes should pass:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

**Security-specific tests**:
```bash
.venv/bin/python -m pytest tests/test_url_ssrf.py -v
.venv/bin/python -m pytest tests/test_security_conditions.py -v
```

**Database migrations**:
```bash
# Before applying migrations
scripts/verify_backup.sh

# Run migration tests
.venv/bin/python -m pytest tests/test_migration.py -v
```

---

## Notes

- Database schema unchanged except for new indexes (migrations 017, 018)
- No new external dependencies required (uses stdlib `ast`, `OrderedDict`)
- All security improvements use existing `html` and `services.prompts` utilities
- Template changes require thorough browser testing for UX
- CSP nonce implementation deferred to future hardening work
- Backward compatible — all changes are internal refactoring with no API contract changes