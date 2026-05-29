# Review: pipeline.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- Pipeline status values match `constants.py:30-43` (PipelineStatus class)
- Valid transitions match `constants.py:52-64` (VALID_TRANSITIONS dict)
- Selector returns `{score, confidence, reasoning, key_topics}` — `tasks/select.py:74-112` builds prompt requesting these fields; `schemas/llm_responses.py` has `SelectionResult` model
- Low confidence → `review` — `tasks/select.py:127-146`
- `selected=False` → `skipped` — `tasks/select.py:172-191`
- Research uses web search + subagent — `tasks/research.py:48-110`
- Write body < 500 chars triggers quality gate — `tasks/write.py:21` (`len(body.strip()) < 500`)
- Edit uses contextualization subagent — `tasks/edit.py:70-145`
- Newsletter 3-stage LLM (reader→writer→editor) — `tasks/newsletter.py:132-163` calls `generate_executive_summary()`
- Email batch size 500 — `tasks/newsletter.py:85` (`BATCH_SIZE = 500`)
- Scheduled tasks table: 14 tasks — `config.py:146-203` has exactly 14 entries
- Pipeline timeout default 3600 seconds — `constants.py:14`
- `VALID_PIPELINE_STATUSES` excludes transient statuses — `constants.py:97-108`
- `MAX_CONSECUTIVE_FAILURES` default 10 — `config.py:67`
- Shadow quality assessments via `lightweight_quality_signals()` — `tasks/research.py:181-201`, `tasks/write.py:106-125`, `tasks/edit.py:346-370`
- A/B experiment 70/15/15 distribution — `tasks/select.py:36-43`
- `PipelineLog` model has `meta` field (not `metadata`) — `models/pipeline.py:57`
- Circuit breaker: 5 failures in 2 minutes, 60s recovery, half-open with 1 probe — `services/circuit_breaker.py:40-46`
- `get_provider_chain()` dynamic fallback — `services/llm/__init__.py:57-97`
- AuthError causes immediate failure without retry — `tasks/pipeline.py:192-199`
- Degradation for select: auto-select score 6 — `services/pipeline_degradation.py:33-41`
- Degradation for research: impact_score=30 — `services/pipeline_degradation.py:15-30`
- Degradation for edit: finalize or route to review — `services/pipeline_degradation.py:130-180`
- Selector retry_max=20 with retry_countdown=15 — `tasks/select.py:201-202`
- Per-stage retries: 3 (`MAX_STAGE_RETRIES`) — `constants.py:9`
- Total retries: 10 (`MAX_TOTAL_RETRIES`) — `constants.py:11`

## Incorrect Claims

1. **`selected=True but score < min_score → mark as review or discard`** — `tasks/select.py:126-191`
   - Priority: **HIGH**
   - The code at `tasks/select.py:172-179` routes ALL cases where `not (selected and score >= min_score)` to `SKIPPED`, regardless of whether `selected` is True or False. There is no `review` path for this condition. The only `review` path is low confidence when the article IS selected and scores above min_score (`tasks/select.py:127-146`). The documentation implies a `review` option that does not exist in the code.

2. **Researcher temperature 0.4 in pipeline.yaml example** — `pipeline.yaml:23`
   - Priority: **MEDIUM**
   - The document's YAML example at line 219 shows `temperature: 0.4` for the researcher, but `pipeline.yaml:23` shows `temperature: 0.0`. The actual config differs from the documentation example.

3. **Write validation: "If body < 500 chars, marks for review"** — `pipeline.md:101`
   - Priority: **MEDIUM**
   - The documentation implies only body length is checked. The actual `_is_degenerate_write()` at `tasks/write.py:12-27` also checks `not article_obj.key_points` (empty key points) and `not article_obj.citations` (empty citations). The doc omits these additional conditions.

4. **`_check_newsletter_lock`: "If acquisition fails due to Redis error, the task raises (cannot proceed safely)"** — `pipeline.md:176`
   - Priority: **LOW**
   - The documentation says the function "raises" on Redis error, but the function signature at `tasks/newsletter.py:379` is `_check_newsletter_lock(redis_client, task_id)` and it returns tuples. When `lock_status == 0` (held by another), it returns `(None, None, {"skipped": True, ...})`. When `lock_status` is 1 or 2 (success), it returns `(lock_status, None, None)`. The function itself does raise on Redis errors (`tasks/newsletter.py:402-404`), but the description of the return value for the "skipped" case is slightly misleading — it returns a tuple with a dict, not a simple "skipped" value.

## Bugs Found

1. **Selector stage routes `selected=True, score < min_score` to SKIPPED instead of review** — `tasks/select.py:126-191`
   - Priority: **HIGH**
   - When `result.selected` is True but `result.score < (rc.min_score or 6)`, the code falls through to the `else` block at line 172 which sets status to `SKIPPED`. The documentation claims this should go to `review` or `discard`. This is either a documentation bug or a code bug — the behavior differs from documented intent. Articles that were explicitly selected by the LLM but scored below threshold are silently discarded rather than flagged for human review.

2. **Potential race condition in newsletter idempotency key and lock** — `tasks/newsletter.py:419-433`
   - Priority: **MEDIUM**
   - The idempotency key check (`redis_client.exists(idempotency_key)` at line 382) and the lock acquisition are not atomic. Between checking `exists` and acquiring the lock, another worker could complete. However, the idempotency key is set AFTER successful generation (line 433), so this is a TOCTOU window that could allow duplicate generation in theory, though the lock mitigates it.

3. **Newsletter lock return tuple inconsistency** — `tasks/newsletter.py:406-409`
   - Priority: **LOW**
   - When `lock_status == 0` (locked by another), the function returns a 3-tuple: `(None, None, {"skipped": True, ...})`. When `lock_status` is 1 or 2, it returns `(lock_status, None, None)`. The caller at `_generate_daily_newsletters_core` unpacks as `lock_status, lock_key, skip_result` (line 419), but when `lock_status` is 1 or 2, `lock_key` and `skip_result` are both `None`. This works but the variable naming is confusing — `lock_key` is not actually the Redis lock key in this context.

## Improvement Opportunities

1. **Document the `selected=True, score < min_score` behavior accurately** — `pipeline.md:77`
   - Priority: **HIGH**
   - Either update the documentation to reflect the actual behavior (routes to `skipped`), or update the code to route to `review` as documented. The current mismatch is confusing.

2. **Document the `level` field on PipelineLog** — `pipeline.md:310-318`
   - Priority: **LOW**
   - The PipelineLog schema shown in the documentation omits the `level` field (`db.Column(db.String(8), default="info")` at `models/pipeline.py:50`). Adding it would make the documentation complete.

3. **Document quality report routing in edit stage** — `pipeline.md:103-114`
   - Priority: **MEDIUM**
   - The edit stage description doesn't mention the `build_quality_report()` + `persist_quality_report()` logic at `tasks/edit.py:379-419` which can route articles to `review` when `quality_result.passed` is False. This is an additional quality gate beyond schema validation.

4. **Add `published_at` timestamp documentation in Finalize stage** — `pipeline.md:117-124`
   - Priority: **LOW**
   - The finalize description mentions `published_at` but doesn't document that it's set in `_post_finalize_article()` at `tasks/edit.py:221`. Also missing: the SLA metric tracking (`tasks/edit.py:223-225`) and embedding generation trigger (`tasks/edit.py:280-283`).

## Stale Content

1. **`pipeline.yaml` example values differ from actual config** — `pipeline.md:200-240`
   - Priority: **MEDIUM**
   - The pipeline.yaml example shows `researcher.temperature: 0.4` but actual `pipeline.yaml:23` is `0.0`. The example also doesn't reflect the `newsletter_pipeline` section or `subagent` configuration that exists in the real config.

2. **Newsletter lock description mentions `ainews:newsletter_lock` with "10-minute TTL"** — `pipeline.md:174`
   - Priority: **LOW**
   - The actual TTL is 600 seconds (10 minutes) at `tasks/newsletter.py:401` (`args=[task_id, 600]`), which matches. However, the idempotency key TTL is 86400 * 2 (2 days) at `tasks/newsletter.py:433`, which is not documented.
