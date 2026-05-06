# Tasks Module

The `tasks/` package contains Celery tasks implementing the newsletter pipeline. Tasks use the `run_stage()` helper for standard lifecycle management.

## File Inventory

| File | Task | Stage | Description |
|------|------|-------|-------------|
| `crawl.py` | `run_all_sources` | `crawl` | Orchestrates parallel crawling via Celery group/chord |
| `extract.py` | `process_item` | `extract` | Extracts content, deduplicates, creates Article |
| `select.py` | `select_article` | `select` | LLM scores article 1-10 for newsworthiness |
| `research.py` | `research_article` | `research` | LLM builds research brief with web search + context |
| `write.py` | `write_article` | `write` | LLM writes condensed article (Smart Brevity) |
| `edit.py` | `edit_article` | `edit` | LLM edits with contextualization, assigns tags |
| `newsletter.py` | `generate_daily_newsletters` | `newsletter` | Builds + sends newsletters with executive summary |
| `scheduler.py` | `publish_scheduled_articles` | `publish` | Publishes articles at scheduled time |
| `cleanup.py` | Various | - | Cleanup old logs, versions, expired data |
| `embeddings.py` | `backfill_embeddings` | `embeddings` | Generates embeddings for articles and trend memory |

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

Standard task lifecycle via `pipeline_utils.run_stage()`:

```python
def run_stage(task, article_id: int, stage: str, next_stage: str, task_func):
    """Standard stage runner with locking and error handling"""
    # 1. Acquire stage lock (prevents duplicate processing)
    # 2. Update article status to stage
    # 3. Execute task_func
    # 4. On success: transition to next_stage
    # 5. On failure: handle_retry() or mark_failed()
    # 6. Release stage lock in finally block
```

## Degradation Path

When full pipeline is disabled, articles follow:

```
select → research → write → edit → review → done
```

Articles skip select/research and go directly to `review` for manual processing.

## Scheduler

Celery Beat schedule (from `pipeline.yaml`):

| Task | Schedule | Description |
|------|----------|-------------|
| `run_all_sources` | Every 30 min | Crawl all sources |
| `generate_daily_newsletters` | 8:00 AM ET | Generate newsletters |
| `publish_scheduled_articles` | Every 5 min | Check scheduled publishes |
| `cleanup_old_logs` | Daily 3 AM | Clean old pipeline logs |
| `backfill_embeddings` | Weekly | Update embeddings |

## Rate Limiting

Tasks respect rate limits via `services.limiter`:

- **LLM slots**: Configured per provider (default: 10 concurrent)
- **Source slots**: Per-source rate limiting
- **Release in finally**: Always release acquired slots
