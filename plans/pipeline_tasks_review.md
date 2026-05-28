# Pipeline, Tasks, and Prompts Architecture Documentation Review

Review of `architecture/pipeline.md`, `architecture/tasks.md`, and `architecture/prompts.md` against the actual codebase.

## Verified Claims

### Pipeline Status Values (pipeline.md)
- All 11 status values match `constants.py:30-43`: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed`
- Valid transitions match `constants.py:52-63` exactly

### Retry Limits (pipeline.md)
- `MAX_STAGE_RETRIES = 3` confirmed at `constants.py:9`
- `MAX_STAGE_FAILURES = 3` confirmed at `constants.py:10`
- `MAX_TOTAL_RETRIES = 10` confirmed at `constants.py:11`
- Selector `retry_max=20` with `retry_countdown=15` confirmed at `tasks/select.py:201-202`

### Circuit Breaker (pipeline.md)
- 5 failures in 2 minutes → open: confirmed at `services/circuit_breaker.py:46-47` (`failure_threshold=5`, `window_seconds=120.0`)
- 60 seconds recovery → half-open with 1 request: confirmed at `services/circuit_breaker.py:44-45` (`recovery_timeout=60.0`, `half_open_max_calls=1`)

### Scheduled Tasks (pipeline.md)
All 14 scheduled tasks verified in `config.py:get_beat_schedule()`:
1. `run-all-sources` — every 30 min ✓
2. `generate-newsletters` — daily 8 AM ET ✓
3. `backfill-embeddings` — daily 2 AM ✓
4. `publish-scheduled-articles` — every 5 min ✓
5. `cleanup-old-logs` — daily 3 AM ✓
6. `consolidate-trend-memory` — daily 3:30 AM ✓
7. `purge-trend-memory` — daily 3:45 AM ✓
8. `cleanup-old-versions` — daily 3:45 AM ✓
9. `cleanup-expired-verifications` — every 15 min ✓
10. `cleanup-stale-limiter-slots` — every 5 min ✓
11. `retry-failed-newsletter-deliveries` — every 2 hours ✓
12. `recalculate-impact-scores` — daily 4 AM ✓
13. `cleanup-inactive-subscribers` — daily 1 AM ✓
14. `retry-stuck-articles` — every 60 min ✓

### Newsletter 3-Stage LLM (pipeline.md)
- `generate_executive_summary()` confirmed in `services/newsletter_pipeline.py:166`
- Reader → Writer → Editor pipeline confirmed at `services/newsletter_pipeline.py:192-301`
- Batch size 500 confirmed at `tasks/newsletter.py:85`

### Task Functions Exist (tasks.md)
All task functions confirmed to exist:
- `run_all_sources` in `tasks/crawl.py:269` ✓
- `aggregate_crawl_results` in `tasks/crawl.py:215` ✓
- `process_item` in `tasks/extract.py:278` ✓
- `select_article` in `tasks/select.py:59` ✓
- `research_article` in `tasks/research.py:267` ✓
- `write_article` in `tasks/write.py:48` ✓
- `edit_article` in `tasks/edit.py:396` ✓
- `generate_daily_newsletters` in `tasks/newsletter.py:476` ✓
- `publish_scheduled_articles` in `tasks/scheduler.py:11` ✓
- `retry_stuck` in `tasks/retry.py:78` ✓
- `cleanup_old_pipeline_logs` in `tasks/cleanup.py:19` ✓
- `cleanup_expired_verifications` in `tasks/cleanup.py:69` ✓
- `cleanup_stale_limiter_slots` in `tasks/cleanup.py:110` ✓
- `consolidate_trend_memory` in `tasks/cleanup.py:134` ✓
- `recalculate_impact_scores` in `tasks/cleanup.py:171` ✓
- `purge_trend_memory` in `tasks/cleanup.py:237` ✓
- `cleanup_old_article_versions` in `tasks/cleanup.py:268` ✓
- `backfill_embeddings` in `tasks/embeddings.py:21` ✓
- `cleanup_inactive_subscribers` in `tasks/subscribers.py:15` ✓
- `dispatch_webhook_task` in `tasks/webhook.py:13` ✓

### run_stage() Signature (tasks.md)
Matches `tasks/pipeline.py:353-362` exactly:
```python
def run_stage(stage, article_id, work_fn, task_self, run_id=None, skip_next="finalize", retry_countdown=30, retry_max=15)
```

### Quality Gates (tasks.md)
- select: `confidence="low"` → `review`: confirmed at `tasks/select.py:127`
- research: `_is_degenerate_research(brief)` → `review`: confirmed at `tasks/research.py:13-28`, `tasks/research.py:206`
- write: `_is_degenerate_write(draft)` → `review`: confirmed at `tasks/write.py:12-27`, `tasks/write.py:128`
- edit: validation fails → `review`: confirmed at `tasks/edit.py:148-186`

### Degradation Behavior (pipeline.md)
- select → auto-select score 6 → research: confirmed at `services/pipeline_degradation.py:34-42`
- research → source text only impact_score=30 → write: confirmed at `services/pipeline_degradation.py:15-30,43-47`
- write → minimal draft → edit: confirmed at `services/pipeline_degradation.py:48-56`
- edit → degradation_count >= 2 or `_should_route_to_review()` → review, else finalize to DONE: confirmed at `services/pipeline_degradation.py:130-180`

### PipelineLog Model (pipeline.md)
- `run_id`, `stage`, `article_id`, `started_at`, `completed_at`, `status`, `error`, `meta`: all exist in `models/pipeline.py:36-57`
- Field names match (including `meta` not `metadata`)

### Prompt Files Exist (prompts.md)
All 7 documented files exist:
1. `prompts/selector.txt` ✓
2. `prompts/researcher.txt` ✓
3. `prompts/writer.txt` ✓
4. `prompts/editor.txt` ✓
5. `prompts/newsletter_reader.txt` ✓
6. `prompts/newsletter_writer.txt` ✓
7. `prompts/newsletter_editor.txt` ✓

### Prompt Escaping (prompts.md)
- `esc_xml_text()` in `utils/text.py:19-21` ✓
- `esc_xml_attr()` in `utils/text.py:24-33` ✓
- `escape_prompt_data()` in `utils/text.py:36-50` ✓
- `_escape_prompt_data` re-export at `services/subagent/__init__.py:54` ✓

### Context Truncation Functions (prompts.md)
- `count_tokens()` at `services/prompts.py:33-54` ✓
- `sliding_window_truncate()` at `services/prompts.py:115-154` ✓
- `importance_weighted_truncate()` at `services/prompts.py:157-226` ✓
- `smart_truncate_context()` at `services/prompts.py:316-395` ✓
- `summarize_context()` at `services/prompts.py:257-313` ✓

### Subagent Prompt Templates (prompts.md)
- `services/subagent/prompt_templates.py` exists ✓
- `_SUBAGENT_TASK_TEMPLATES` dict with `research_synthesis` and `edit_contextualization` keys confirmed ✓

### Experiment System (prompts.md)
- `_assign_experiment_group()` in `tasks/select.py:19-43` ✓
- MD5 hash-based deterministic assignment ✓
- 70% control, 15% variant_a, 15% variant_b distribution ✓

---

## Incorrect Claims

### 1. `get_system_prompt()` Signature — MEDIUM
**prompts.md:22-25** documents:
```python
def get_system_prompt(stage: str) -> str:
```
**Actual signature** at `services/prompts.py:95-112`:
```python
def get_system_prompt(role: str, yaml_prompt: str | None) -> str:
```
The `yaml_prompt` parameter is required (not optional). The function checks `yaml_prompt` first, then falls back to file loading.

### 2. `load_prompt_file()` Signature — MEDIUM
**prompts.md:27-28** documents:
```python
def load_prompt_file(filename: str) -> str:
```
**Actual signature** at `services/prompts.py:85-92`:
```python
def load_prompt_file(name: str) -> str | None:
```
Return type is `str | None`, not `str` (returns `None` when file not found). Parameter name is `name`, not `filename`.

### 3. `count_tokens()` Signature — LOW
**prompts.md:52-53** documents:
```python
def count_tokens(text: str, model: str = "gpt-4") -> int:
```
**Actual signature** at `services/prompts.py:34`:
```python
def count_tokens(text: str, model: str | None = None) -> int:
```
Default is `None`, not `"gpt-4"`.

### 4. Truncation Function Parameter Names — LOW
**prompts.md:55-58** documents `max_tokens` parameter:
```python
def sliding_window_truncate(text: str, max_tokens: int) -> str:
def importance_weighted_truncate(text: str, max_tokens: int) -> str:
```
**Actual** at `services/prompts.py:115,157`:
```python
def sliding_window_truncate(text: str, max_chars: int = 8000, model: str | None = None, ...) -> str:
def importance_weighted_truncate(text: str, max_chars: int = 8000, key_topics: list[str] = None) -> str:
```
Parameter is `max_chars`, not `max_tokens`. Additional parameters (`model`, `key_topics`) also exist.

### 5. `smart_truncate_context()` Signature — LOW
**prompts.md:61-62** documents:
```python
def smart_truncate_context(context: str, max_tokens: int) -> str:
```
**Actual** at `services/prompts.py:316-325`:
```python
def smart_truncate_context(text: str, max_chars: int = 8000, model: str | None = None, llm_provider=None, ...) -> tuple[str, bool]:
```
Multiple additional parameters exist, and return type is `tuple[str, bool]`, not `str`.

### 6. `summarize_context()` Signature — LOW
**prompts.md:64-65** documents:
```python
def summarize_context(context: str, max_tokens: int) -> str:
```
**Actual** at `services/prompts.py:257`:
```python
def summarize_context(text: str, llm_provider=None, max_tokens: int = 512, temperature: float = 0.0) -> str:
```
Parameter name is `text`, and `llm_provider` and `temperature` parameters also exist.

### 7. `escape_prompt_data()` Location Reference — LOW
**prompts.md:85** states:
```
Used by `services/subagent.py:_escape_prompt_data()` before template resolution.
```
`services/subagent.py` does not exist. The actual module is `services/subagent/__init__.py:54` which aliases `_escape_prompt_data = escape_prompt_data`. The functions are actually called directly from `services/subagent/runner.py:67`, `services/subagent/chain.py:104`, and `services/subagent/utils.py:32` as `escape_prompt_data()`, not via the `_escape_prompt_data` alias.

### 8. PipelineLog Missing Fields in Documentation — LOW
**pipeline.md:279-288** documents:
```python
class PipelineLog(Base):
    run_id, stage, article_id, started_at, completed_at, status, error, meta
```
**Actual model** at `models/pipeline.py:36-57` also has: `id`, `level`, `message`, `created_at`. The `level` field (default "info") and `message` field are not documented. The `created_at` field (auto-set) is not documented.

### 9. `generate_daily_newsletters` Missing `@shared_task` Decorator — HIGH
**tasks.md:154** documents:
```python
@celery_app.task(bind=True, max_retries=3)
def generate_daily_newsletters(self):
```
**Actual** at `tasks/newsletter.py:476`: The function is defined as a plain function without any `@shared_task` or `@celery_app.task` decorator. It takes `self` as first parameter but is not decorated. The beat schedule references it as `tasks.newsletter.generate_daily_newsletters`. This may work via Celery's lazy task registration, but is inconsistent with other tasks in the codebase that all use `@shared_task`.

### 10. `select_article` Signature — LOW
**tasks.md:110** documents:
```python
def select_article(self, article_id: int):
```
**Actual** at `tasks/select.py:59`:
```python
def select_article(self, article_id: int, run_id=None):
```
The `run_id` parameter is missing from the documentation.

### 11. `research_article` Signature — LOW
**tasks.md:121** documents:
```python
def research_article(self, article_id: int):
```
**Actual** at `tasks/research.py:267`:
```python
def research_article(self, article_id: int, run_id=None):
```
The `run_id` parameter is missing from the documentation.

### 12. `write_article` Signature — LOW
**tasks.md:131** documents:
```python
def write_article(self, article_id: int):
```
**Actual** at `tasks/write.py:48`:
```python
def write_article(self, article_id: int, run_id=None):
```
The `run_id` parameter is missing from the documentation.

### 13. `edit_article` Signature — LOW
**tasks.md:143** documents:
```python
def edit_article(self, article_id: int):
```
**Actual** at `tasks/edit.py:396`:
```python
def edit_article(self, article_id: int, run_id=None):
```
The `run_id` parameter is missing from the documentation.

---

## Bugs Found

### 1. `generate_daily_newsletters` May Not Be Registered as a Celery Task — HIGH
At `tasks/newsletter.py:476`, the function is defined without a `@shared_task` decorator but takes `self` as a first parameter (Celery bound task convention). The beat schedule in `config.py:156-158` references `tasks.newsletter.generate_daily_newsletters` as a Celery task. All other pipeline tasks use `@shared_task(bind=True, ...)`. This function may not be properly registered as a Celery task, potentially causing the scheduled newsletter generation to fail silently.

### 2. `_check_newsletter_lock` Has `@shared_task` But Should Be Private — LOW
At `tasks/newsletter.py:366-409`, `_check_newsletter_lock` is decorated with `@shared_task` (a public Celery task) despite being a private helper function. While not a functional bug, it unnecessarily exposes an internal function as a publicly callable Celery task.

---

## Improvement Opportunities

### 1. Document `VALID_PIPELINE_STATUSES` Incompleteness — MEDIUM
`constants.py:97-108` defines `VALID_PIPELINE_STATUSES` as a frozenset that excludes `SELECTING`, `SELECTED`, `WRITTEN`, and `FAILED` despite these being defined in `PipelineStatus`. This is used for validation purposes but the documentation does not explain why certain statuses are excluded. Consider documenting the intent.

### 2. Document Pipeline Timeout — MEDIUM
`pipeline.md` does not mention the pipeline hard timeout (`PIPELINE_TIMEOUT_SECONDS = 3600` in `constants.py:14`). Articles that exceed this timeout are automatically dead-lettered in `tasks/pipeline.py:316-331`. This is an important operational detail.

### 3. Document `MAX_CONSECUTIVE_FAILURES` Config — LOW
`config.py:67` defines `MAX_CONSECUTIVE_FAILURES` (default 10) as a configurable constant, separate from `MAX_TOTAL_RETRIES`. The documentation mentions `MAX_TOTAL_RETRIES` but not this additional configurable.

### 4. Document Newsletter Lock Mechanism — LOW
`tasks/newsletter.py:379-409` implements a Redis-based idempotency lock for newsletter generation to prevent duplicate daily newsletters. This is not documented in `pipeline.md`.

### 5. Document Shadow Quality Assessment — LOW
`tasks/research.py:181-201`, `tasks/write.py:106-125`, and `tasks/edit.py:340-364` all run shadow (non-blocking) quality assessments via `lightweight_quality_signals()`. These are non-critical but produce metrics. Not documented.

### 6. Document A/B Experiment Distribution — LOW
`tasks/select.py:36-43` documents the 70/15/15 split in code comments, but `prompts.md:151` only mentions "deterministic MD5 hash" without the distribution. Consider documenting the actual percentages.

---

## Stale Content

### 1. `services/researcher.py` Reference — LOW
**prompts.md:179** references `services/researcher.py` for "Research prompt assembly with XML tags". While the file exists, the actual prompt building is done via `build_research_prompt()` which builds XML-escaped content directly. The description is slightly misleading — it's not just "prompt assembly" but includes web search results, related articles, topic notes, and trend memory integration.

### 2. `services/writer.py` Reference — LOW
**prompts.md:180** references `services/writer.py` for "Writer prompt assembly with experiment support". The file exists and the claim is correct, but the experiment support is in `get_writer_system_prompt()` (variant selection), not in the prompt assembly itself.

### 3. `services/editor.py` Reference — LOW
**prompts.md:181** references `services/editor.py` for "Editor prompt assembly with contextualization". The file exists and the claim is correct. The contextualization is gathered in `tasks/edit.py:_gather_editor_context()` and passed to `build_editor_prompt_with_context()` in `services/editor.py`.

### 4. Write Stage Word Count Claim — LOW
**pipeline.md:97** states "LLM writes 200-400 word article". The actual `_is_degenerate_write()` check in `tasks/write.py:12-27` only validates `< 500 chars` (not words), and there is no explicit 200-400 word validation. The prompt may target this range but it's not enforced in code.

### 5. `validate_and_raise()` Reference — LOW
**tasks.md:147** states edit calls `validate_and_raise()`. The actual call is `validate_and_raise(article.final_article)` in `tasks/edit.py:162`, but the documentation doesn't mention that this validates the `final_article` field specifically.

---

## Priority Summary

| Priority | Count | Key Items |
|----------|-------|-----------|
| HIGH | 2 | `generate_daily_newsletters` missing decorator; task signatures missing `run_id` |
| MEDIUM | 4 | `get_system_prompt` wrong signature; `load_prompt_file` wrong signature; `VALID_PIPELINE_STATUSES` incomplete; pipeline timeout undocumented |
| LOW | 17 | Various parameter name mismatches; stale references; missing field documentation |
