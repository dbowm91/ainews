---
name: pipeline_stage_transitions
description: "Pipeline stage transitions, quality gates, and degradation behavior — covering VALID_TRANSITIONS, quality gate routing, stage failure handling, and degradation paths. Triggers: pipeline, stage, transition, quality gate, degradation, failure."
---

## Pipeline State Machine

The pipeline uses a state machine defined in `constants.py:52-64`:

```python
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.SELECTING, PipelineStatus.RESEARCHING, PipelineStatus.REVIEW]),
    PipelineStatus.SELECTING: frozenset([PipelineStatus.SELECTED, PipelineStatus.FAILED]),
    PipelineStatus.SELECTED: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.FAILED]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITTEN: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.EDITING: frozenset([PipelineStatus.REVIEW, PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.REVIEW: frozenset([PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.DONE: frozenset(),  # Terminal state
    PipelineStatus.SKIPPED: frozenset(),  # Terminal state
    PipelineStatus.FAILED: frozenset([PipelineStatus.PENDING]),  # Can be reprocessed
}
```

## Stage Transitions Table

| Current | Next (success) | Next (quality gate) | Next (fail) |
|---------|----------------|---------------------|-------------|
| `pending` | `selecting`, `researching` | `review` | `failed` |
| `selecting` | `selected` | - | `failed` |
| `selected` | `researching` | - | `failed` |
| `researching` | `writing` | - | `failed` |
| `writing` | `editing` | - | `failed` |
| `written` | `editing` | - | `failed` |
| `editing` | `done` | `review` | `failed` |
| `review` | `done` | - | `failed` |
| `done` | *(terminal)* | - | - |
| `skipped` | *(terminal)* | - | - |
| `failed` | `pending` | - | - |

Use `is_valid_transition(from_status, to_status)` in `constants.py` to validate transitions.

## Quality Gates

Each stage has quality gates that route articles to `review` for manual inspection:

| Stage | Quality Gate Condition | Action |
|-------|----------------------|--------|
| select | confidence="low" | Route to `review` |
| research | `_is_degenerate_research(brief)` returns True | Route to `review` |
| write | `_is_degenerate_write(draft)` returns True | Route to `review` |
| edit | Validation fails OR `_should_route_to_review(article)` returns True OR quality report `passed=False` | Route to `review` |

### Quality Gate Implementation

Quality gates are checked in each stage task:
- **Select:** `tasks/select.py` — checks `confidence` field from selector LLM response
- **Research:** `tasks/research.py` — calls `_is_degenerate_research()` on the research brief
- **Write:** `tasks/write.py` — calls `_is_degenerate_write()` on the draft
- **Edit:** `tasks/edit.py:161-349` — three separate checks

### Edit Stage Quality Gate (3 conditions)

The edit stage has three distinct quality gate conditions:

1. **Validation failure** (`tasks/edit.py:161-185`): Article fails schema validation
2. **`_should_route_to_review(article)` returns True** (`tasks/edit.py:189-206`): Editorial check
3. **Quality report `passed=False`** (`tasks/edit.py:328-349`): LLM-judged quality issues

## Degradation Behavior

When a stage fails after exhausting retries, the article enters degradation mode:

### Degradation Entry Points

- **Select failure:** `_degrade_and_advance()` in `services/pipeline_degradation.py:183` auto-selects article
- **Research failure:** Article goes to `writing` with placeholder research brief
- **Write failure:** Article goes to `editing` with placeholder draft
- **Edit failure:** Article routes to `review` for manual inspection

### Degradation Flow

1. Stage fails after `MAX_STAGE_FAILURES` (3) at same stage
2. `_handle_stage_failure()` in `services/pipeline_failure.py` determines if degradation applies
3. If degradation applies, `degrade_stage()` in `services/pipeline_degradation.py` generates fallback content
4. Article advances to next stage with degraded content

### Disabled Stage Routing

When a stage is disabled via `skip_next="finalize"`:
- Article routes through `_finalize()` in `services/pipeline_degradation.py:278-309`
- `_finalize()` calls `_should_route_to_review()`:
  - If True → routes to `PipelineStatus.REVIEW`
  - Otherwise → routes to `PipelineStatus.DONE` (DEFAULT path)
- Articles do NOT go directly to the next stage when a stage is disabled

## Per-Stage Failure Tracking

`services/pipeline_failure.py:_track_stage_failure()` tracks failures per stage per article in Redis:

```python
stage_failure_key = f"article:{article.id}:stage_failures:{stage}"
stage_failures = redis_client.hincrby(stage_failure_key, "count", 1)
if stage_failures >= 3:
    article.pipeline_status = PipelineStatus.FAILED
```

Early termination after 3 failures at same stage prevents infinite retry loops.

## Total Retry Budget

Articles have a total retry budget of `MAX_TOTAL_RETRIES` (10). When exhausted:
- Article is marked as `failed`
- Dead letter queue UI shows the article at `/admin/dead-letters`
- Can be manually reprocessed via admin UI

## Stage Task Signatures

### run_stage()

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
```

**Note:** Selector stage uses `retry_max=20` (hardcoded in `tasks/select.py:202`), not the default 15.

## Key Files

| File | Purpose |
|------|---------|
| `constants.py` | `PipelineStatus`, `VALID_TRANSITIONS`, `is_valid_transition()` |
| `tasks/pipeline.py` | `run_stage()`, `_dispatch_next()`, `_transition_article_status()` |
| `services/pipeline_failure.py` | `_handle_stage_failure()`, `_track_stage_failure()` |
| `services/pipeline_degradation.py` | `degrade_stage()`, `_finalize()`, `_degrade_and_advance()` |
| `tasks/select.py` | Select stage task with low-confidence quality gate |
| `tasks/research.py` | Research stage task with degenerate-brief quality gate |
| `tasks/write.py` | Write stage task with degenerate-draft quality gate |
| `tasks/edit.py` | Edit stage task with 3-condition quality gate |