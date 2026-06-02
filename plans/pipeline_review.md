# Pipeline Architecture Review

## Summary
The pipeline documentation is largely accurate but has one **Major discrepancy** in degradation behavior: the document claims all disabled stages route through `_finalize()`, but the actual code only routes through `_finalize()` when `skip_next="finalize"`. For select and research stages, the code dispatches directly to the next stage, bypassing `_finalize()` and its `_should_route_to_review()` check.

## Verified Claims

### 1. Pipeline Stages and Status Values
- All status values in `constants.py:30-43` match the documented table (pending, selecting, selected, researching, writing, written, editing, review, done, skipped, failed) ✓
- `VALID_TRANSITIONS` in `constants.py:52-64` matches documented transitions exactly ✓

### 2. Selector Thresholds (Line 74-78)
- `selected=True` AND `score >= min_score` → proceed to research ✓
- `selected=False` → mark as `skipped` ✓
- `selected=True` but `score < min_score` → mark as `skipped` ✓
- Low confidence → mark as `review` ✓
- Code: `tasks/select.py:126-171`

### 3. Write Quality Gate (Line 101)
- Marks for review if body < 500 chars OR empty key_points OR empty citations ✓
- Code: `tasks/write.py:12-27` `_is_degenerate_write()`

### 4. Research Quality Gate
- Degenerate research brief (no key claims OR impact_score < 10) → review ✓
- Code: `tasks/research.py:13-28` `_is_degenerate_research()`

### 5. Selector retry_max=20 Override (Line 291)
- Selector stage uses `retry_max=20` with `retry_countdown=15` ✓
- Code: `tasks/select.py:201-202`

### 6. 3-Stage Newsletter LLM (Line 148-159)
- Executive summary uses reader → writer → editor pipeline ✓
- Code: `services/newsletter_pipeline.py:166` `generate_executive_summary()`

### 7. A/B Experiment Distribution (Line 262-264)
- 70% control, 15% variant_a, 15% variant_b via MD5 hashing ✓
- Code: `tasks/select.py:32-43`

### 8. Shadow Quality Assessments (Line 258-260)
- Each stage (research, write, edit) performs non-blocking quality assessment ✓
- Code: `tasks/research.py:181-201`, `tasks/write.py:106-125`, `tasks/edit.py:280-304`

### 9. Newsletter Lock (Line 171-176)
- Idempotency key TTL: 2 days (86400×2) ✓
- Lock TTL: 10 minutes (600 seconds) ✓
- Code: `tasks/newsletter.py:381-401, 433`

### 10. Two-Tier Retry System (Line 324-337)
- Celery task retry: max_retries=3, exponential backoff capped at 300s ✓
- Stage failure retry: MAX_STAGE_RETRIES=3, MAX_TOTAL_RETRIES=10, MAX_STAGE_FAILURES=3 ✓
- Code: `constants.py:6-11`, `services/pipeline_failure.py`

### 11. Circuit Breaker (Line 339-344)
- Opens after 5 failures in 2 minutes (window_seconds=120) ✓
- Recovery timeout 60 seconds ✓
- Half-open allows 1 probe request ✓
- Code: `services/circuit_breaker.py:40-52`, `services/llm/__init__.py:20-21`

### 12. Dynamic Fallback Chain (Line 242, 346-350)
- Falls through to next enabled provider in `providers.yaml` order ✓
- Filters out providers with open circuits ✓
- Code: `services/llm/__init__.py:57-97`

### 13. AuthError Handling (Line 352)
- Authentication failures cause immediate failure without retry or fallback ✓
- Code: `tasks/pipeline.py:192-199`

### 14. Scheduled Tasks Table (Line 182-197)
- All scheduled tasks and intervals match `config.py:148-205` ✓
- Note: `retry-stuck-articles` task name matches `tasks.retry.retry_stuck` ✓

### 15. MAX_CONSECUTIVE_FAILURES (Line 254-256)
- Default: 10, configurable via environment variable ✓
- Code: `config.py:69`

### 16. Edit Stage Degradation (Line 279-287)
- When edit fails with `degradation_count >= 2` → route to review ✓
- When edit fails and `_should_route_to_review()` → route to review ✓
- When edit fails but neither condition → finalize to DONE ✓
- Code: `services/pipeline_degradation.py:133-184` `_degrade_edit_stage()`

### 17. Post-Finalize Behavior (Line 120-124)
- Updates `published_at` timestamp ✓
- Triggers webhooks for `article.published` ✓
- Updates trend memory ✓
- Generates embedding ✓
- Code: `services/pipeline_degradation.py:212-278` `post_finalize_article()`

### 18. Newsletter Batch Size (Line 144)
- Batch size: 500 ✓
- Code: `tasks/newsletter.py:85` `BATCH_SIZE = 500`

## Discrepancies Found

### 1. **Major: Disabled Stage Routing - Select and Research bypass `_finalize()`**
- **Claim** (Line 268-275): "When stages are disabled via `pipeline.yaml`, articles bypass that stage by routing through `_finalize()`"
- **Reality**: The code in `tasks/pipeline.py:260-267` only calls `_finalize()` when `skip_next == "finalize"`:
  ```python
  def _handle_disabled(rc, skip_next, run_id, stage, article_id):
      if not rc.enabled:
          if skip_next == "finalize":
              _finalize(article_id)
          else:
              _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
          return True
      return False
  ```
  - **Select** (`tasks/select.py:200`): `skip_next=PipelineStatus.RESEARCHING` → dispatches directly to `researching`, does NOT call `_finalize()`
  - **Research** (`tasks/research.py:322`): `skip_next=PipelineStatus.WRITING` → dispatches directly to `writing`, does NOT call `_finalize()`
  - **Write** (`tasks/write.py:182`): `skip_next=PipelineStatus.EDITING` → dispatches directly to `editing`, does NOT call `_finalize()`
  - **Edit** (`tasks/edit.py:382`): `skip_next="finalize"` → calls `_finalize()` ✓

- **Severity**: Major
- **Location**: `tasks/pipeline.py:260-267`
- **Suggested fix**: Change the `_handle_disabled` condition from `if skip_next == "finalize"` to always call `_finalize()`:
  ```python
  if not rc.enabled:
      _finalize(article_id)
      return True
  ```
  This ensures all disabled stages check `_should_route_to_review()` before finalization.

### 2. **Minor: VALID_PIPELINE_STATUSES Documentation**
- **Claim** (Line 252): "`VALID_PIPELINE_STATUSES` excludes the transient statuses `selecting`, `selected`, and `written`"
- **Reality**: `constants.py:97-108` shows `VALID_PIPELINE_STATUSES` is a frozen set that does NOT include `pending`, `selecting`, `selected`, or `written`:
  ```python
  VALID_PIPELINE_STATUSES = frozenset(
      {
          PipelineStatus.PENDING,  # <-- INCLUDED!
          PipelineStatus.RESEARCHING,
          PipelineStatus.WRITING,
          PipelineStatus.EDITING,
          PipelineStatus.REVIEW,
          PipelineStatus.DONE,
          PipelineStatus.SKIPPED,
          PipelineStatus.FAILED,
      }
  )
  ```
  The document incorrectly says `pending` is excluded. `selecting`, `selected`, and `written` ARE correctly excluded.
- **Severity**: Minor
- **Location**: `architecture/pipeline.md:252`, `constants.py:97-108`
- **Suggested fix**: Update the documentation to say "`VALID_PIPELINE_STATUSES` excludes the transient statuses `selecting`, `selected`, and `written` (but includes `pending` for articles awaiting processing)."

## Bugs Identified

No actual bugs found - the code is internally consistent. The discrepancy is purely documentation vs. code behavior.

## Improvement Opportunities

### 1. **Consistency in Disabled Stage Handling**
- **Location**: `tasks/pipeline.py:260-267`
- **Benefit**: If the documented behavior (all stages route through `_finalize()`) is desired, changing `_handle_disabled` to always call `_finalize()` would ensure consistent behavior across all stages. This would also ensure `_should_route_to_review()` is always checked for disabled stages.

### 2. **Document the `_handle_disabled` Logic**
- **Location**: `architecture/pipeline.md:266-276`
- **Benefit**: The current degradation behavior table doesn't capture the actual conditional behavior. If the conditional behavior is intentional, document it clearly:
  - Select, Research, Write: When disabled, dispatch directly to next stage
  - Edit: When disabled, route through `_finalize()`

## Stale Items Found

None - all documented features exist in the codebase.

## Recommendations

1. **High Priority**: Resolve the disabled stage routing discrepancy. Decide whether:
   - The documented behavior (all stages route through `_finalize()`) is correct, and fix `_handle_disabled()` to match
   - Or update the documentation to reflect the actual conditional behavior

2. **Low Priority**: Fix the `VALID_PIPELINE_STATUSES` documentation to correctly state that `pending` IS included (just `selecting`, `selected`, and `written` are excluded).

3. **Low Priority**: Consider adding inline comments to `_handle_disabled()` explaining why different stages use different `skip_next` values and the implications for disabled stage behavior.