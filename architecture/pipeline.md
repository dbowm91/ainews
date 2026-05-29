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
- `pending` → `selecting`, `researching`, `review`
- `selecting` → `selected`, `failed`
- `selected` → `researching`, `failed`
- `researching` → `writing`, `failed`
- `writing` → `editing`, `failed`
- `written` → `editing`, `failed`
- `editing` → `review`, `done`, `failed`
- `review` → `done`, `failed`
- `done` → (terminal)
- `skipped` → (terminal, reached from `failed` during reprocess)
- `failed` → `pending` (reprocess)

### 1. Select

**Purpose**: Score article newsworthiness 1-10

**Process**:
- LLM evaluates article against newsworthiness criteria
- Returns `{score, confidence, reasoning, key_topics}`

**Thresholds**:
- `selected=True` AND `score >= min_score` (default 6) → proceed to research
- `selected=False` → mark as `skipped` (regardless of score)
- `selected=True` but `score < min_score` → mark as `skipped`
- Low confidence → mark as `review` (regardless of selected/score)

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

**Validation**: Marks for `review` if body < 500 chars OR empty key_points OR empty citations

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
- Update `published_at` timestamp
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

### Newsletter Lock

Newsletter generation uses a Redis‑based lock to prevent concurrent runs. The `_check_newsletter_lock` function:

1. Checks an idempotency key (`idempotency:newsletter:{YYYY-MM-DD}`) to skip if already completed today.
2. Acquires a distributed lock (`ainews:newsletter_lock`) with a 10‑minute TTL using a Lua script.
3. If the lock is held by another task, the current task skips (returns `skipped`).
4. If acquisition fails due to Redis error, the task raises (cannot proceed safely).

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
| `cleanup-old-versions` | Daily 3:45 AM | Clean up old article versions (note: minute hardcoded to :45, only hour is configurable via `cleanup_old_versions_hour`) |
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

## Pipeline Details

### Pipeline Timeout

The pipeline enforces a hard timeout per article. If an article exceeds `PIPELINE_TIMEOUT_SECONDS` (default: 3600 seconds, configurable via environment variable), it is automatically dead‑lettered (status set to `failed`) and removed from further processing. This prevents articles from being stuck indefinitely in the pipeline.

### Valid Pipeline Statuses

`VALID_PIPELINE_STATUSES` is a frozen set used for validating article statuses. It includes: `pending`, `researching`, `writing`, `editing`, `review`, `done`, `skipped`, and `failed`. Notably, it excludes the transient statuses `selecting`, `selected`, and `written`, which are only used internally during stage transitions and are never persisted as final article statuses.

### MAX_CONSECUTIVE_FAILURES

The `MAX_CONSECUTIVE_FAILURES` configuration (default: 10) controls the maximum number of consecutive failures across all stages before an article is marked as failed. This is separate from per-stage retry limits and total retry budget. Configurable via environment variable.

### Shadow Quality Assessments

Each stage (research, write, edit) performs a non‑blocking “shadow” quality assessment using `lightweight_quality_signals()`. This evaluates the output for groundedness, coherence, completeness, and safety. Results are logged for monitoring but do not affect the pipeline flow (the assessment is purely observational).

### A/B Experiment Distribution

When experiments are enabled in `pipeline.yaml`, articles are assigned to experiment groups (`control`, `variant_a`, `variant_b`) via deterministic MD5 hashing of `article_id:salt:experiment`. The distribution is 70% control, 15% variant_a, 15% variant_b. The writer and editor stages select prompt variants based on the assigned group.

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
| edit | Apply fallback →
  - If degradation_count >= 2 OR _should_route_to_review() → route to review
  - Else → finalize to DONE (auto-publish if impact_score >= threshold) |

**Retry Limits:**
- Per-stage retries: 3 (configurable via `MAX_STAGE_RETRIES`)
  - **Exception**: Selector stage uses `retry_max=20` with `retry_countdown=15` for more aggressive selection attempts
- Per-stage failure limit: 3 consecutive failures at same stage → article marked failed
- Total retries: 10 (configurable via `MAX_TOTAL_RETRIES`)

Articles in `review` status require manual intervention. Articles with `impact_score >= auto_publish_threshold` (from `pipeline.yaml` `review.auto_publish_threshold`, default: disabled) bypass review and auto-publish.

## Monitoring

### Pipeline Monitor (`services/pipeline_monitor.py`)

Tracks pipeline health:
- Stage success/failure counts per stage
- Throughput tracking (items per minute)
- Failure reason breakdown (rate_limit, timeout, server_error, circuit_open)
- Does NOT track: p95/p99 percentiles, queue depth per stage, source health correlation

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
- Backoff: exponential (30s, 60s, 120s, 240s, ... up to 300s max)
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

**AuthError handling**: Authentication failures (`AuthError`) cause immediate failure without retry or fallback. This prevents infinite auth loops and is not retried.
