# Pipeline Review Plan

Review the newsletter pipeline and [pipeline.md](../architecture/pipeline.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual pipeline implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Degradation Behavior**: Verify graceful degradation when stages are disabled

## Key Files

- `services/newsletter_pipeline.py` - Newsletter orchestration
- `tasks/select.py` - Selection stage
- `tasks/research.py` - Research stage
- `tasks/write.py` - Writing stage
- `tasks/edit.py` - Editing stage
- `services/pipeline_monitor.py` - Pipeline health monitoring
- `services/pipeline_degradation.py` - Graceful degradation logic
- `services/pipeline_failure.py` - Failure handling
- `services/pipeline_utils.py` - Pipeline utilities including run_stage()

## Known Issues to Verify

- VALID_TRANSITIONS includes selecting and selected (not just documented statuses)
- PipelineStatus has SELECTING, SELECTED, WRITTEN added
- Fallback chain is dynamic from providers.yaml, not hardcoded

## Pipeline Stages

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

## Review Checklist

- [ ] Verify stage transitions match documented valid transitions
- [ ] Verify selector: LLM scores 1-10, threshold >= 6 with medium/high confidence
- [ ] Verify researcher: builds research brief with web search + context
- [ ] Verify writer: Smart Brevity format, 200-400 words, 2-5 key points
- [ ] Verify editor: contextualization via subagent, tag assignment, validation
- [ ] Verify degradation behavior when stages disabled via pipeline.yaml
- [ ] Verify degradation path: select→research→write→edit→review→done when disabled
- [ ] Verify two-tier retry: Celery task retry (3 max) + stage failure retry (3 per stage)
- [ ] Verify circuit breaker: Closed→Open (5 failures/2min)→Half-Open (60s)
- [ ] Verify dynamic fallback chain from providers.yaml enabled providers
- [ ] Verify executive summary 3-stage: reader→writer→editor
- [ ] Verify newsletter generation: fetch DONE articles, build HTML, batch send (500)
- [ ] Verify pipeline monitor: stage durations, failure rates, queue depth

## Output

Save findings to `plans/pipeline_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found