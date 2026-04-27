# Pipeline Failure Tracking

## Overview

The pipeline failure tracking system tracks per-stage failure counts to enable early termination and intelligent degradation when pipeline stages fail repeatedly. It combines database counters (for retry budgets) with Redis counters (for per-stage failure tracking).

## Redis Key Structure

Failure counts are stored in Redis using a hash with a 7-day TTL:

```
ainews:article:stage_failures:{article_id}:{stage}
```

Key components:
- **Prefix**: `ainews:article:stage_failures:`
- **Article ID**: Database ID of the article
- **Stage**: One of `select`, `research`, `write`, `edit`
- **TTL**: 7 days (604800 seconds)

The hash contains a single field `count` storing the number of failures at that stage.

### Key Pattern for Bulk Operations

```python
pattern = f"ainews:article:stage_failures:{article_id}:*"
for key in redis_client.scan_iter(match=pattern):
    redis_client.delete(key)
```

This pattern is used in:
- `_bulk_reprocess()` in `routes/admin/api/articles.py:172`
- Single article reprocess in `routes/admin/articles.py:440`

## Failure Tracking Flow

### Decision Tree

When a stage fails, `_handle_stage_failure()` in `services/pipeline_failure.py:41` evaluates the following decisions in order:

```
1. Has total_retries >= MAX_TOTAL_RETRIES (default: 10)?
   YES → Mark article FAILED, return True (do not retry)
   NO  → Continue

2. Has this stage failed >= 3 times?
   YES → Mark article FAILED (early termination), return True
   NO  → Continue

3. Has retry_count >= MAX_STAGE_RETRIES (default: 3)?
   YES → Degrade stage, return True (advance to next stage)
   NO  → Commit retry_count, return False (caller should retry)
```

### Key Counters

| Counter | Source | Purpose |
|---------|--------|---------|
| `article.retry_count` | DB | Stage-specific retry attempts |
| `article.total_retries` | DB | Global retry budget |
| `stage_failures` | Redis | Per-stage failure count for early termination |

## Stage Degradation Map

When a stage exhausts its retry budget, `degrade_stage()` in `services/pipeline_degradation.py:235` advances the article to the next stage with degraded content:

| Failed Stage | Next Status | Action |
|-------------|------------|--------|
| `select` | RESEARCHING | Set `selector_result` to fallback |
| `research` | WRITING | Generate minimal `research_brief` from source text |
| `write` | EDITING | Use fallback article JSON |
| `edit` | REVIEW | Use draft as final (route to review) |

### Degradation Fields

```python
_STAGE_DEGRADE_MAP = {
    "select": {
        "next_status": PipelineStatus.RESEARCHING,
        "set_fields": lambda article: setattr(
            article,
            "selector_result",
            {"selected": True, "score": 6, "reason": "auto-selected after failure"},
        ),
    },
    "research": {
        "next_status": PipelineStatus.WRITING,
        "set_fields": _degrade_research,
    },
    "write": {
        "next_status": PipelineStatus.EDITING,
        "set_fields": lambda article: setattr(
            article, "draft_article", _build_fallback_article(article)
        ),
    },
}
```

For the edit stage, `_degrade_edit_stage()` in `services/pipeline_degradation.py:125` applies fallback content and checks routing criteria:
- If `degradation_count >= 2`, route to review
- Otherwise, use draft as final and mark DONE

### Multi-Stage Degradation

If an article degrades through 2+ stages, it's routed directly to review (`services/pipeline_degradation.py:95-107`). This prevents articles with severely degraded quality from continuing through multiple stages.

## Reprocessing Behavior

When an article is reprocessed (via admin UI or bulk operations), the following reset occurs:

### Database Reset

```python
article.pipeline_status = PipelineStatus.PENDING
article.pipeline_started_at = datetime.now(timezone.utc)
article.retry_count = 0
article.total_retries = 0
article.last_error = None
article.selector_result = None
article.research_brief = None
article.draft_article = None
article.final_article = None
```

### Redis Key Clearing

After DB commit, stage failure keys are cleared:

```python
try:
    redis_client = get_redis()
    pattern = f"ainews:article:stage_failures:{article.id}:*"
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)
except redis.exceptions.RedisError:
    logger.warning("Failed to clear stage failure keys during reprocess")
```

This ensures reprocessed articles don't immediately fail with early termination due to stale failure counts.

## Constants

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_STAGE_RETRIES` | 3 | Per-stage retry budget before degradation |
| `MAX_TOTAL_RETRIES` | 10 | Global retry budget before permanent failure |
| `_MAX_STAGE_FAILURES` | 3 | Per-stage failures triggering early termination |

These are configurable via environment variables or Flask config.

## Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `pipeline.degradation` | `stage`, `reason` | Counter for degradation events |
| `pipeline.multi_stage_degradation` | - | Counter for 2+ stage degradations |

## Known Issues

### Historical: Stage Failure Keys Not Cleared on Reprocess

**Status**: Fixed during wave5_3 (verification in plan.md line 827)

Prior to the fix, reprocessing an article would reset database counters but leave Redis keys intact. This caused reprocessed articles to immediately fail with early termination after 3 attempts at any stage, regardless of fresh retries.

The fix (merged in wave5_3) adds Redis key clearing in both:
- Single article reprocess: `routes/admin/articles.py:437-444`
- Bulk article reprocess: `routes/admin/api/articles.py:167-176`

### PENDING→REVIEW Transition Missing

**Status**: Documented in AGENTS.md:694

The `VALID_TRANSITIONS` constant does not include PENDING→REVIEW. This means articles cannot transition directly from PENDING to REVIEW without going through SELECT first. This is a known limitation - see plan item wave7_5 for details.

## Integration with Pipeline

The failure handling integrates with `run_stage()` in `tasks/pipeline.py:341`:

```python
if exc_article and _handle_stage_failure(exc_article, stage, ce, run_id=run_id):
    logger.info("Article %s will not be retried", exc_article.id)
    return {"status": "skipped", "reason": "degraded_or_failed"}
```

When `_handle_stage_failure()` returns `True`, the stage returns a degraded dict and does not re-raise, allowing the pipeline to continue gracefully.