# Tasks Review Plan

Review the `tasks/` package and [tasks.md](../architecture/tasks.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual task implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Stage Transitions**: Verify status flow matches documented transitions

## Key Files

- `tasks/crawl.py` - run_all_sources task
- `tasks/extract.py` - process_item task
- `tasks/select.py` - select_article task
- `tasks/research.py` - research_article task
- `tasks/write.py` - write_article task
- `tasks/edit.py` - edit_article task
- `tasks/newsletter.py` - generate_daily_newsletters task
- `tasks/scheduler.py` - publish_scheduled_articles task
- `tasks/embeddings.py` - backfill_embeddings task
- `tasks/cleanup.py` - Cleanup tasks

## Known Issues to Verify

- `run_stage()` helper resolves provider/model before acquiring limiter resources
- Use `provider_id` (actual provider used) not `rc.provider` (configured provider) when releasing
- MagicMock in tests causes JSON serialization failures (test infrastructure issue)

## Review Checklist

- [ ] Verify stage transitions: pending→select→research→write→edit→done
- [ ] Verify run_stage helper: lock acquisition, status update, task execution, transition, lock release
- [ ] Verify rate limiter slots: always release in finally block
- [ ] Verify provider_id usage when releasing limiter slots
- [ ] Verify Celery Beat schedule matches documented tasks
- [ ] Verify degradation behavior when stages are disabled
- [ ] Verify retry logic: exponential backoff, max_retries

## Output

Save findings to `plans/tasks_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found