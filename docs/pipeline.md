# Pipeline Architecture

## Stage vs Status Naming

The pipeline uses two distinct concepts that are important to distinguish:

| Concept | Values | Purpose |
|---------|--------|---------|
| **Stages** | `select`, `research`, `write`, `edit` | Logical phases of article processing |
| **Statuses** | `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `failed`, `skipped` | State machine values for tracking article state |

**Stage names** are task/action identifiers used in task functions like `select_article`, `research_article`, etc.

**Status values** are stored in `Article.pipeline_status` and drive the state machine transitions in `VALID_TRANSITIONS`.

The mapping between stages and statuses:
- `select` stage → `selecting`/`selected` status (or directly to `researching` if selection is integrated)
- `research` stage → `researching` status
- `write` stage → `writing` status
- `edit` stage → `editing` status

## State Machine

Articles flow through defined pipeline stages. Each stage transitions the article to a new status or degrades gracefully on failure.

```
pending → researching → writing → editing → (review) → done
     ↓           ↓         ↓          ↓
   skipped    failed   failed    failed
```

Note: `selecting` and `selected` statuses exist in the code but selection logic is integrated into the research phase.

### Valid Transitions

| From | To | Notes |
|------|----|-------|
| pending | researching | After selection (selection integrated into research) |
| pending | review | Quality gate |
| pending | skipped | Below min_score |
| pending | failed | Can be reprocessed |
| researching | writing | Research complete |
| researching | failed | After retries |
| writing | editing | Draft complete |
| writing | failed | After retries |
| editing | review | Validation |
| editing | done | Finalized |
| editing | failed | After retries |
| review | done | Manual publish |
| review | failed | Marked failed |
| review | researching | Reprocess |

Note: `selecting` and `selected` statuses exist but are handled within the research stage. Articles transition from `pending` directly to `researching`.

### Pipeline Statuses

| Status | Meaning |
|--------|---------|
| pending | Awaiting processing (selection integrated into research) |
| researching | LLM evaluating newsworthiness and selecting articles |
| writing | LLM drafting article |
| editing | LLM reviewing/polishing |
| review | Needs manual review |
| done | Published |
| failed | Permanently failed (can be reprocessed) |
| skipped | Not selected |

## Degradation System

When a pipeline stage fails persistently, the article degrades gracefully instead of failing entirely.

### Stage Degradation

Each stage has a degradation handler that attempts partial completion:

- **Select failure**: Auto-select with score 6, advance to research
- **Research failure**: Uses source text only, sets impact_score to 30, advance to write
- **Write failure**: Generates minimal draft from extracted text, advance to edit
- **Edit failure**: Routes to review status for manual intervention

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