# Review: config.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- **Configuration files table** (pipeline.yaml, providers.yaml, sources.yaml, topics.yaml, config.py): All verified to exist
- **PipelineRootConfig structure**: Verified at `schemas/pipeline.py:150-159` — has `pipeline`, `newsletter`, `newsletter_pipeline`, `subagent`, `memory`, `stages`, `schedule` fields
- **RoleConfig schema**: Verified at `schemas/pipeline.py:16-32` — has `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `concurrency`, `timeout_seconds`, `system_prompt`, `min_score`, plus role-specific optional fields
- **SubagentStageConfig schema**: Verified at `schemas/pipeline.py:93-105` — has `enabled`, `provider`, `model`, `max_tokens`, `temperature`, `timeout_seconds`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`
- **MemoryConfig schema**: Verified at `schemas/pipeline.py:128-138` — has `ttl_days_low`, `ttl_days_medium`, `ttl_days_high`, `consolidation_cooldown_hours`, `max_entries_per_propose`, `consolidation_merge_window_hours`, `truncation_llm_enabled`, `truncation_llm_threshold`, `truncation_llm_max_tokens`, `truncation_llm_temperature`
- **SourceConfig schema**: Verified at `schemas/source.py:106-131` — has `id`, `name`, `type`, `enabled`, `schedule_minutes`, `config`, `topics` fields with correct validators
- **SourceConfig `validate_adapter_config`**: Confirmed at `schemas/source.py:124-131` — validates config against RSSConfig/APIConfig/WebConfig based on type
- **TopicsConfig**: Referenced in `schemas/topic.py` — validated via `validate_config()` at `services/config_unified.py:228`
- **load_pipeline_config**: Verified at `schemas/pipeline.py:173-180` — uses `cached_config_with_mtime`
- **load_sources**: Verified at `schemas/source.py:145-150` — uses `cached_config_with_mtime`
- **cached_config_with_mtime signature**: Verified at `schemas/common.py:82-97` — `(key, loader_fn, config_path, ttl)`
- **get_config_with_default**: Verified at `services/config_utils.py:13-71` — `(key, default, converter, log_missing)`
- **validate_config**: Verified at `services/config_unified.py:220-231` — returns `(is_valid, errors)` tuple
- **Celery beat schedule loading**: `Config.get_beat_schedule()` at `config.py:117-203` confirmed
- **Environment variables table**: All variables verified in `config.py` (FLASK_CONFIG, SECRET_KEY, DATABASE_URL, REDIS_URL, REDIS_SSL, REDIS_MAX_CONNECTIONS, SMTP_*, CELERY_BROKER_URL, etc.)
- **Config reload**: `Config.reload_beat_schedule()` at `config.py:205-220` confirmed
- **RoleConfig `web_search` field**: Documented in config.md line 42, verified at `schemas/pipeline.py:26`
- **SubagentStageConfig `tools` field**: Documented, verified at `schemas/pipeline.py:104`
- **Pydantic serialization in config_cache**: `_serialize`/`_deserialize` with `_type` metadata at `services/config_cache.py:19-55`

## Incorrect Claims

1. **`config_utils.py` code sample shows non-existent `celery_support.get_current_app`**
   - config.md line 438-443 shows:
     ```python
     from celery_support import get_current_app
     app = get_current_app()
     return app.config.get(key, default)
     ```
   - Actual code at `services/config_utils.py:43-46` uses:
     ```python
     from flask import current_app
     value = current_app.config.get(key)
     ```
   - `celery_support.py` only has `_app_cache` and `clear_app_cache()` — no `get_current_app` function exists
   - Priority: **MEDIUM** — incorrect code sample

2. **`cached_config_with_mtime` signature has swapped parameters**
   - config.md line 428-431 shows: `cached_config_with_mtime(key, loader_fn, config_path, ttl)`
   - Actual signature at `schemas/common.py:82-83`: `cached_config_with_mtime(key, loader_fn, config_path, ttl)`
   - The parameter ORDER is actually correct in the doc. However, the doc's description says "uses ConfigCache (Redis-backed) with mtime-based staleness detection" which is accurate
   - Priority: **N/A** — no issue found on closer inspection

3. **ConfigCache `get` method signature in infrastructure.md vs config.md**
   - infrastructure.md line 243 shows: `def get(self, key: str, loader_fn: Callable, ttl: int = 300) -> Any:`
   - config.md line 429 shows: `cached_config_with_mtime(key, loader_fn, config_path, ttl)` (a different function)
   - Both are accurate for their respective functions
   - Priority: **N/A** — no issue

4. **Missing `pipeline.yaml` field `experiments` in PipelineRootConfig**
   - config.md shows `experiments:` as a top-level section in the YAML structure
   - `PipelineRootConfig` at `schemas/pipeline.py:150-159` does NOT have an `experiments` field
   - The experiments config is likely loaded separately or through the `schedule` dict
   - Priority: **MEDIUM** — documented YAML structure doesn't match schema

5. **Missing `pipeline.yaml` field `stages` in config.md YAML structure**
   - config.md shows `stages:` as a top-level section (line 187-193)
   - `PipelineRootConfig` does have `stages: dict[str, StageConfig]` at line 158 — this IS correct
   - Priority: **N/A** — verified as correct

## Bugs Found

1. **`get_config_with_default` logs warning for every missing config key on every call**
   - `services/config_utils.py:48-51`: When `log_missing=True` (default), logs a warning every time a missing key is accessed
   - In Celery tasks that call this frequently, this can generate excessive log noise
   - The `log_missing` parameter exists but isn't commonly used by callers
   - Priority: **LOW** — performance/logging issue

2. **`validate_config` catches `yaml.YAMLError` but the import happens inside the function**
   - `services/config_unified.py:214`: `import yaml` is done inside `_validate_config_section` which means the import error could mask YAML parsing errors
   - Priority: **LOW** — unlikely in practice since yaml is a core dependency

## Improvement Opportunities

1. **PipelineRootConfig missing `experiments` field documentation**
   - The YAML structure shows `experiments:` but PipelineRootConfig doesn't have this field
   - If experiments config is loaded separately, this should be documented
   - If it's part of `schedule` dict, the documentation should clarify
   - Priority: **MEDIUM**

2. **ConfigCache `invalidate_if_stale` doesn't update cached mtime after invalidation**
   - `services/config_cache.py:241-261`: When `current_mtime > cached_mtime`, it invalidates but doesn't update the mtime cache
   - This means the next call will re-check the mtime (which is fine, but slightly wasteful)
   - Priority: **LOW**

3. **Environment variables table missing `CELERY_RESULT_BACKEND`**
   - `config.py:95-96` defines `CELERY_RESULT_BACKEND` but it's not in the env vars table
   - Priority: **LOW**

4. **ConfigCache docstring mentions `CONFIG_CACHE_REDIS_DB` but code uses `CONFIG_CACHE_REDIS_URL`**
   - `services/config_cache.py:280-281` docstring says `CONFIG_CACHE_REDIS_DB`
   - Actual code at line 298 uses `CONFIG_CACHE_REDIS_URL`
   - Priority: **LOW** — source code docstring issue, not in architecture doc

## Stale Content

1. **`config_utils.py` code sample references non-existent function**
   - `celery_support.get_current_app` does not exist
   - Priority: **MEDIUM**

2. **`cached_config_with_mtime` function signature in code sample is missing `config_path` param**
   - The doc at line 429 shows the correct signature, but the description says "automatic invalidation when the source file changes" — the actual function at `schemas/common.py:82-97` does this correctly
   - Priority: **N/A** — actually correct

3. **Missing `celery_support.py` from Key Files table**
   - `celery_support.py` is imported by `celery_app.py` but not documented
   - Priority: **LOW**
