# Newsletter Pipeline

The pipeline is the core workflow that transforms raw articles into polished newsletter content.

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Article Processing                                 │
│                                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐      │
│  │  RSS/   │──→│ select  │──→│research │──→│  write  │──→│  edit   │      │
│  │  API    │   │ (LLM)   │   │ (LLM)   │   │ (LLM)   │   │ (LLM)   │      │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘      │
│       │              │             │            │             │             │
│       ▼              ▼             ▼            ▼             ▼             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐  ┌─────────┐   ┌─────────┐         │
│  │process_ │   │ score   │   │research │  │ Smart   │   │finalize │         │
│  │ item    │   │   1-10  │   │  brief  │  │ Brevity │   │+tags    │         │
│  └─────────┘   └─────────┘   └─────────┘  └─────────┘   └─────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         Newsletter Generation                              │
│                                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │
│  │  Fetch DONE  │──→│ Exec Summary │──→│Build HTML    │──→│Send (batched)│  │
│  │  articles    │   │ (3-stage LLM)│   │newsletter    │   │ 500/batch    │  │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Article Pipeline Stages

Pipeline stages use these statuses (defined in `constants.py`):

| Status | Description |
|--------|-------------|
| `pending` | Article awaiting processing |
| `selecting` | Selector stage in progress |
| `selected` | Article selected for processing |
| `researching` | Research stage in progress |
| `writing` | Writing stage in progress |
| `written` | Draft article written |
| `editing` | Editing stage in progress |
| `review` | Awaiting manual review |
| `done` | Processing complete |
| `skipped` | Stage skipped |
| `failed` | Stage failed (can be retried) |

Valid transitions:
- `pending` → `researching`, `review`
- `researching` → `writing`, `failed`
- `writing` → `editing`, `failed`
- `editing` → `review`, `done`, `failed`
- `review` → `done`, `failed`
- `done`/`skipped` → (terminal)
- `failed` → `pending` (reprocess)

### 1. Select

**Purpose**: Score article newsworthiness 1-10

**Process**:
- LLM evaluates article against newsworthiness criteria
- Returns `{score, confidence, reasoning, key_topics}`

**Thresholds**:
- Score >= 6 with medium/high confidence → proceed to research
- Score < 6 or low confidence → mark as `review` or `discard`

### 2. Research

**Purpose**: Build comprehensive research brief

**Process**:
- LLM analyzes article content
- Subagent performs web search for context
- Fetches related trend memory entries
- Produces `{key_findings, context, citations, related_trends}`

**Degradation**: If disabled, skips to `review`

### 3. Write

**Purpose**: Create condensed article in Smart Brevity format

**Process**:
- LLM writes 200-400 word article
- Format: hook → context → key points → implications
- Target: 3-5 key points, actionable insights

**Validation**: If body < 500 chars, marks for `review`

### 4. Edit

**Purpose**: Polish and contextualize article

**Process**:
- Subagent contextualizes with related articles, trends
- LLM edits for clarity, flow, accuracy
- Tags assigned via topic classifier
- Validation: schema validation + quality checks
- Post-finalize: trend memory update, webhook dispatch

**Degradation**: If disabled, marks for `review`

### 5. Finalize

**Purpose**: Mark article complete, trigger downstream actions

**Process**:
- Update `finalized_at` timestamp
- Update `pipeline_status` to `done`
- Trigger webhooks for `article.published`
- Update trend memory with new observations

## Newsletter Generation

### Daily Newsletter Flow

```
8:00 AM ET: generate_daily_newsletters
    │
    ├── _fetch_articles_for_newsletter()
    │   # Status=DONE, published within 24h, impact_score > 0
    │
    ├── generate_executive_summary()
    │   # 3-stage LLM: reader → writer → editor
    │   # Theme identification + overview + highlights
    │
    ├── generate_main_newsletter()
    │   # HTML email with preamble + articles
    │
    └── _send_emails_parallel()
        # Batch size: 500
        # Retry: 3 attempts
```

### Executive Summary (3-Stage)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   reader   │───→│   writer    │───→│   editor    │
│ (extract)  │    │  (generate) │    │  (polish)   │
└─────────────┘    └─────────────┘    └─────────────┘
```

**Reader**: Extracts key themes and developments from articles
**Writer**: Generates first-draft summary from reader output
**Editor**: Polishes for clarity, consistency, impact

### Topic Newsletters

Per-topic newsletters generated similarly:
1. Fetch articles for topic (DONE status, matching topic tag)
2. Generate executive summary (smaller scope)
3. Build topic newsletter HTML
4. Send to topic subscribers

### Scheduled Tasks

The pipeline uses Celery Beat for scheduled task orchestration:

| Task | Schedule | Description |
|------|----------|-------------|
| `run-all-sources` | Every 30 min | Crawl all RSS/API sources |
| `generate-newsletters` | Daily 8 AM ET | Generate and send newsletters |
| `backfill-embeddings` | Daily 2 AM | Generate missing article embeddings |
| `publish-scheduled-articles` | Every 5 min | Publish articles at scheduled time |
| `cleanup-old-logs` | Daily 3 AM | Clean old pipeline logs |
| `consolidate-trend-memory` | Daily 3:30 AM | Consolidate trend memory |
| `purge-trend-memory` | Daily 3:45 AM | Purge expired trend memory |
| `cleanup-old-versions` | Daily 3:45 AM | Clean up old article versions |
| `cleanup-expired-verifications` | Every 15 min | Clean expired email verification tokens |
| `cleanup-stale-limiter-slots` | Every 5 min | Clean stale rate limiter slots |
| `retry-failed-newsletter-deliveries` | Every 2 hours | Retry failed newsletter email deliveries |
| `recalculate-impact-scores` | Daily 4 AM | Recalculate article impact scores |
| `cleanup-inactive-subscribers` | Daily 1 AM | Clean up inactive newsletter subscribers |
| `retry-stuck-articles` | Every 60 min | Retry articles stuck in pipeline |

## Pipeline Configuration

From `pipeline.yaml`:

```yaml
stages:
  selector:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 1024
    temperature: 0.2
    concurrency: 4
    timeout_seconds: 60
    min_score: 6

  researcher:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    temperature: 0.4
    max_tokens: 8192

  writer:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    temperature: 0.5
    max_tokens: 4096

  editor:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    temperature: 0.3
    max_tokens: 4096

newsletter:
  daily_send_time: "08:00"
  enable_topic_newsletters: true
  batch_size: 500
```

**Note:** The fallback chain is dynamically determined from enabled providers in `providers.yaml` configuration order, not a hardcoded order.

## Degradation Behavior

When stages are disabled via `pipeline.yaml`, articles bypass that stage and advance directly to the next status:

| Stage Disabled | Behavior |
|----------------|----------|
| select | Article goes directly to `researching` (selection skipped) |
| research | Article goes directly to `writing` |
| write | Article goes directly to `editing` |
| edit | Article finalizes immediately (no editing) |

When stages fail persistently (after max retries), articles degrade to the next stage:

| Stage Fails | Degraded To |
|-------------|-------------|
| select | Auto-select with score 6, advance to research |
| research | Uses source text only (impact_score=30), advance to write |
| write | Minimal draft from extracted text, advance to edit |
| edit | Finalize immediately with fallback |

**Retry Limits:**
- Per-stage retries: 3 (configurable via `MAX_STAGE_RETRIES`)
- Per-stage failure limit: 3 consecutive failures at same stage → article marked failed
- Total retries: 10 (configurable via `MAX_TOTAL_RETRIES`)

Articles in `review` status require manual intervention.

## Monitoring

### Pipeline Monitor (`services/pipeline_monitor.py`)

Tracks pipeline health:
- Stage durations (avg, p95, p99)
- Failure rates per stage
- Queue depth per stage
- Source health correlation

### Pipeline Logs

Each stage writes to `PipelineLog`:
```python
class PipelineLog(Base):
    run_id: int
    stage: str
    article_id: int
    started_at: DateTime
    completed_at: DateTime
    status: str  # started, completed, failed
    error: str | None
    meta: JSON
```

## Failure Handling

### Two-Tier Retry System

The pipeline has two independent retry mechanisms:

**1. Celery Task Retry** (for transient errors)
- Max retries: 3 per task
- Backoff: exponential (30s, 60s, 120s)
- Triggered by: network timeouts, rate limits, temporary provider failures

**2. Stage Failure Retry** (for persistent failures)
- Per-stage retry limit: 3 (`MAX_STAGE_RETRIES`)
- After 3 per-stage retries: article degrades to next stage
- Per-stage failure limit: 3 consecutive failures at same stage → article marked failed
- Total retry budget: 10 across all stages (`MAX_TOTAL_RETRIES`)

### Circuit Breaker

LLM providers have circuit breakers:
- Closed: Normal operation
- Open: After 5 failures in 2 minutes
- Half-open: After 60 seconds, test with 1 request

### Fallback Chain

The fallback chain is **dynamic** - determined by enabled providers in `providers.yaml` configuration order. The `get_provider_chain()` function iterates through enabled providers and filters out those with open circuits.

If primary fails, falls through to next provider until one succeeds.
