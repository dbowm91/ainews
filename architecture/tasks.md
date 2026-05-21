# Tasks Module

The `tasks/` package contains Celery tasks implementing the newsletter pipeline. Shared helpers in `tasks/pipeline.py` (like `run_stage()`) are used across multiple pipeline stages.

## File Inventory

| File | Task | Stage | Description |
|------|------|-------|-------------|
| `crawl.py` | `run_all_sources` | `crawl` | Orchestrates parallel crawling via Celery group/chord |
| `extract.py` | `process_item` | `extract` | Extracts content, deduplicates, creates Article |
| `select.py` | `select_article` | `select` | LLM scores article 1-10 for newsworthiness |
| `research.py` | `research_article` | `research` | LLM builds research brief with web search + context |
| `write.py` | `write_article` | `write` | LLM writes condensed article (Smart Brevity) |
| `edit.py` | `edit_article` | `edit` | LLM edits with contextualization, assigns tags |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter` | Builds + sends newsletters with executive summary (batches of 500) |
| `scheduler.py` | `publish_scheduled_articles` | `publish` | Publishes articles at scheduled time |
| `cleanup.py` | Various | - | See cleanup tasks below |
| `retry.py` | `retry_stuck` | - | Retry/dead-letter stuck articles |
| `subscribers.py` | `cleanup_inactive_subscribers` | - | Flag inactive subscribers |
| `webhook.py` | `dispatch_webhook_task` | - | Async webhook dispatch |
| `embeddings.py` | `backfill_embeddings` | `embeddings` | Generates embeddings for articles and trend memory |

### Cleanup Tasks (`cleanup.py`)

| Task | Schedule | Description |
|------|----------|-------------|
| `cleanup_old_pipeline_logs` | Daily 3 AM | Clean old pipeline logs |
| `cleanup_expired_verifications` | Every 15 min | Clean expired email verifications |
| `cleanup_stale_limiter_slots` | Every 5 min | Clean stale rate limiter slots |
| `consolidate_trend_memory` | Daily 3:30 AM | Consolidate trend memory entries |
| `recalculate_impact_scores` | Daily 4:00 AM | Recalculate article impact scores |
| `purge_trend_memory` | Daily 3:45 AM | Purge expired trend memory |
| `cleanup_old_article_versions` | Daily 3:45 AM | Clean old article versions |

## Pipeline Stages

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ pending │───→│ select  │───→│research │───→│  write  │───→│  edit   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                                                       │
                                                       ▼
                                                ┌──────────┐
                                                │   done   │
                                                └──────────┘
                                                       ▲
                                                       │
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  fail   │←───│  fail   │←───│  fail   │←───│  fail   │←───│ review  │
│         │    │         │    │         │    │         │    │(manual) │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
```

### Stage Transitions

| Current | Next (success) | Next (review) | Next (fail) |
|---------|----------------|--------------|-------------|
| `pending` | `select` | - | `failed` |
| `select` | `research` | `review` | `failed` |
| `research` | `write` | `review` | `failed` |
| `write` | `edit` | `review` | `failed` |
| `edit` | `done` | `review` | `failed` |

### Quality Gates

Beyond simple success/failure, each stage has quality gates that can route articles to `review` for manual inspection:

| Stage | Quality Gate Condition | Action |
|-------|----------------------|--------|
| select | confidence="low" | Route to `review` |
| research | `_is_degenerate_research(brief)` returns True | Route to `review` |
| write | `_is_degenerate_write(draft)` returns True | Route to `review` |
| edit | Validation fails | Route to `review` |

## Core Tasks

### Crawl Task (`crawl.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def run_all_sources(self):
    """Orchestrate parallel crawling of all sources"""
    # Uses Celery group for parallel source fetching
    # Uses chord for barrier + callback
    # Dispatches to process_item for each discovered item
```

### Process Item (`extract.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def process_item(self, source_id: int, item_data: dict):
    """Extract content and create article"""
    # 1. extract_content_if_needed() - trafilatura/readability
    # 2. find_duplicate_article() - URL + title dedup
    # 3. create_article_record()
    # 4. dispatch to select_article
```

### Select (`select.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def select_article(self, article_id: int):
    """LLM scores article 1-10 for newsworthiness"""
    # Uses selector prompt template
    # Returns: {score, confidence, reasoning}
    # Threshold: score >= 6 with medium/high confidence
```

### Research (`research.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def research_article(self, article_id: int):
    """LLM builds research brief with web search + context"""
    # Uses researcher prompt template
    # Calls subagent for web search
    # Returns: ResearchBrief with key_points, context, citations
```

### Write (`write.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def write_article(self, article_id: int):
    """LLM writes condensed article (Smart Brevity format)"""
    # Uses writer prompt template
    # Target: 200-400 words, 2-5 key points
    # Format: hook, context, key points, implications
```

### Edit (`edit.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def edit_article(self, article_id: int):
    """LLM edits with contextualization, assigns tags"""
    # Calls subagent with context tools
    # Assigns tags via _assign_tags()
    # Validates via validate_and_raise()
    # Calls _post_finalize_article() on success
```

### Newsletter (`newsletter.py`)

```python
@celery_app.task(bind=True, max_retries=3)
def generate_daily_newsletters(self):
    """Build and send newsletters with executive summary"""
    # 1. _fetch_articles_for_newsletter()
    # 2. generate_executive_summary() - 3-stage LLM
    # 3. generate_main_newsletter()
    # 4. generate_topic_newsletters()
    # 5. _send_emails_parallel() - batches of 500
```

## run_stage Helper

Standard task lifecycle via `tasks/pipeline.run_stage()`:

```python
def run_stage(
    stage: str,
    article_id: int,
    work_fn,
    task_self,
    run_id=None,
    skip_next: str = "finalize",
    retry_countdown: int = 30,
    retry_max: int = 15,
):
    """Execute a pipeline stage with standard lifecycle management."""
    # 1. Check if stage is disabled (skip if so)
    # 2. Acquire stage lock (prevents duplicate processing)
    # 3. Get provider for stage (with circuit breaker fallback)
    # 4. Acquire rate limiter slot
    # 5. Execute work_fn
    # 6. On success: transition to next_stage
    # 7. On failure: handle_retry() or mark_failed()
    # 8. Release stage lock and rate limiter slot in finally block
```

**Note:** `tasks/pipeline.py` contains shared helper functions (`run_stage()`, `_run_stage_core()`, `_handle_stage_exception()`, `_handle_disabled()`, etc.) used across all stage tasks.

## Degradation Path

When full pipeline is disabled via `pipeline.yaml`, articles bypass normal stage flow and go directly to `review`:

```
pending → review → done
```

Articles skip select, research, write, and edit stages for manual processing.

## Scheduler

Celery Beat schedule (from `config.py:get_beat_schedule()`):

| Task | Schedule | Description |
|------|----------|-------------|
| `run-all-sources` | Every 30 min | Crawl all sources |
| `retry-stuck-articles` | Every 60 min | Retry/dead-letter stuck articles |
| `generate-newsletters` | 8:00 AM ET | Generate newsletters |
| `cleanup-old-logs` | Daily 3 AM | Clean old pipeline logs |
| `consolidate-trend-memory` | Daily 3:30 AM | Consolidate trend memory entries |
| `purge-trend-memory` | Daily 3:45 AM | Purge expired trend memory |
| `cleanup-old-versions` | Daily 3:45 AM | Clean old article versions |
| `cleanup-expired-verifications` | Every 15 min | Clean expired email verifications |
| `publish-scheduled-articles` | Every 5 min | Check scheduled publishes |
| `cleanup-stale-limiter-slots` | Every 5 min | Clean stale rate limiter slots |
| `retry-failed-newsletter-deliveries` | Every 2 hours | Retry failed email deliveries |
| `recalculate-impact-scores` | Daily 4:00 AM | Recalculate article impact scores |
| `cleanup-inactive-subscribers` | Daily 1:00 AM | Flag inactive subscribers |
| `backfill-embeddings` | Daily 2:00 AM | Generate missing embeddings |

## Rate Limiting

Tasks respect rate limits via `services.limiter`:

- **LLM slots**: Configured per provider (default: 10 concurrent)
- **Source slots**: Per-source rate limiting
- **Release in finally**: Always release acquired slots