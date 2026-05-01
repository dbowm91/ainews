# Pipeline Architecture

## State Machine

Articles flow through defined pipeline stages. Each stage transitions the article to a new status or degrades gracefully on failure.

```
pending → researching → writing → editing → (review) → done
     ↓           ↓         ↓          ↓
   skipped    failed   failed    failed
```

Note: `PipelineStatus.SELECTING` is deprecated and removed. Articles transition from `pending` to `researching` (selection logic is integrated into the research phase).

### Valid Transitions

| From | To | Notes |
|------|----|-------|
| pending | researching | After selection |
| pending | skipped | Below min_score |
| researching | writing | Research complete |
| researching | review | Quality gate |
| researching | failed | After retries |
| writing | editing | Draft complete |
| writing | review | Quality gate |
| writing | failed | After retries |
| editing | review | Validation |
| editing | done | Finalized |
| editing | failed | After retries |
| review | done | Manual publish |
| review | failed | Marked failed |
| review | researching | Reprocess |

### Pipeline Statuses

| Status | Meaning |
|--------|---------|
| pending | Awaiting processing (selection integrated into research) |
| researching | LLM evaluating newsworthiness and selecting articles |
| writing | LLM drafting article |
| editing | LLM reviewing/polishing |
| review | Needs manual review |
| done | Published |
| failed | Permanently failed |
| skipped | Not selected |

## Degradation System

When a pipeline stage fails, the article may degrade gracefully instead of failing entirely.

### Stage Degradation

Each stage has a degradation handler that attempts partial completion:

- **Research**: Uses source text only, sets impact_score to 30
- **Write**: Generates minimal draft from extracted text
- **Edit**: Routes to review status

### Degradation Tracking

Articles track degradation count via `degradation_count`. Articles with 2+ degradations are routed to manual review.

## Retry Budget

Articles have a total retry budget (`total_retries`) that increments on every stage failure.

| Total Retries | Behavior |
|-------------|---------|
| < MAX_TOTAL_RETRIES | Retry current stage |
| >= MAX_TOTAL_RETRIES | Mark failed, skip pipeline |

Default `MAX_TOTAL_RETRIES` is 10 (configurable via env var).

## Per-Stage Failure Tracking

Each stage tracks failures independently in Redis for early termination decisions.

- **Threshold**: 3 failures at same stage
- **Action**: After 3 failures, article is routed to review instead of retrying

The failure tracking is per-stage, per-article — a research failure doesn't prevent write retries.

## Duplicate Detection

Articles from different sources with similar titles are filtered out.

- **Algorithm**: Jaccard similarity on title word sets
- **Threshold**: 0.5 (configurable via `TITLE_SIMILARITY_THRESHOLD`)
- **Window**: Last 7 days, different sources only
- **Limit**: Max 1000 comparisons per check

## SLA Monitoring

Article processing has SLA timestamps tracked at each stage:

| Field | Meaning |
|-------|---------|
| crawled_at | RSS/API item fetched |
| selected_at | LLM selected for coverage |
| published_at | Article finalized |

SLA metrics are computed at publication time.

## Pipeline Run Tracking

`PipelineRun` model tracks each crawl/newsletter execution:

- Task ID, status, triggered_by (scheduled/manual)
- Articles fetched, processed, selected counts
- Error message on failure

`PipelineLog` provides per-article, per-stage logging with levels: info, warning, error.