# Review: config.md

**Reviewed:** 2026-05-31
**Source:** `architecture/config.md`
**Reviewer:** Subagent 5 (Infrastructure & Config Layer)
**Status:** COMPLETE

---

## Verified Claims

### Configuration Files
| Claim | Status | Evidence |
|-------|--------|----------|
| 5 config files exist | VERIFIED | `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`, `config.py` all exist |
| `pipeline.yaml` → `PipelineRootConfig` | VERIFIED | `schemas/pipeline.py:159-169` |
| `sources.yaml` → `SourceConfig` | VERIFIED | `schemas/source.py` |
| `topics.yaml` → `TopicsConfig` | VERIFIED | `schemas/topic.py` |
| `config.py` → Flask Config classes | VERIFIED | `config.py:37-326` |

### PipelineRootConfig Structure
| Claim | Status | Evidence |
|-------|--------|----------|
| `pipeline` key with `selector`, `researcher`, `writer`, `editor` | VERIFIED | `schemas/pipeline.py:44-49` |
| `newsletter` key | VERIFIED | `schemas/pipeline.py:52-57` |
| `newsletter_pipeline` key | VERIFIED | `schemas/pipeline.py:60-90` |
| `subagent` key | VERIFIED | `schemas/pipeline.py:121-134` |
| `memory` key | VERIFIED | `schemas/pipeline.py:137-147` |
| `experiments` key | VERIFIED | `schemas/pipeline.py:167` |
| `stages` key | VERIFIED | `schemas/pipeline.py:168` |
| `schedule` key | VERIFIED | `schemas/pipeline.py:169` |

### RoleConfig
| Claim | Status | Evidence |
|-------|--------|----------|
| `enabled: bool = True` | VERIFIED | `schemas/pipeline.py:17` |
| `provider: str = Field(...)` (required) | VERIFIED | `schemas/pipeline.py:18` |
| `model: str = Field(...)` (required) | VERIFIED | `schemas/pipeline.py:19` |
| `max_tokens: int = 4096` | VERIFIED | `schemas/pipeline.py:20` (via `MAX_TOKENS_FIELD`) |
| `temperature: float = Field(default=0.0)` | VERIFIED | `schemas/pipeline.py:21` |
| `concurrency: int = Field(default=2)` | VERIFIED | `schemas/pipeline.py:22` |
| `timeout_seconds: int = Field(default=120)` | VERIFIED | `schemas/pipeline.py:23` |
| `min_score: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:25` |
| `web_search: Optional[bool] = None` | VERIFIED | `schemas/pipeline.py:26` |
| `web_search_max_results: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:27` |
| `web_search_provider: Optional[str] = None` | VERIFIED | `schemas/pipeline.py:28` |
| `db_related_max: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:29` |
| `max_article_text_length: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:30` |
| `max_key_points: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:31` |
| `max_tags: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:32` |

### SubagentStageConfig
| Claim | Status | Evidence |
|-------|--------|----------|
| `enabled: bool = False` | VERIFIED | `schemas/pipeline.py:94` |
| `provider: Optional[str] = None` | VERIFIED | `schemas/pipeline.py:95` |
| `model: Optional[str] = None` | VERIFIED | `schemas/pipeline.py:96` |
| `max_tokens: int = 4096` | VERIFIED | `schemas/pipeline.py:97` |
| `temperature: float = 0.0` | VERIFIED | `schemas/pipeline.py:98` |
| `timeout_seconds: int = 120` | VERIFIED | `schemas/pipeline.py:99` |
| `max_retries: int = 1` | VERIFIED | `schemas/pipeline.py:101` |
| `retry_delay: float = 5.0` | VERIFIED | `schemas/pipeline.py:102` |
| `task_template: Optional[str] = None` | VERIFIED | `schemas/pipeline.py:103` |
| `tools: list[str] = []` | VERIFIED | `schemas/pipeline.py:104` |
| `max_iterations: int = 5` | VERIFIED | `schemas/pipeline.py:105` |

### ReviewConfig
| Claim | Status | Evidence |
|-------|--------|----------|
| `enabled: bool = False` | VERIFIED | `schemas/pipeline.py:37` |
| `auto_publish_threshold: Optional[int] = None` | VERIFIED | `schemas/pipeline.py:38-41` |

### MemoryConfig
| Claim | Status | Evidence |
|-------|--------|----------|
| `ttl_days_low: int = 7` | VERIFIED | `schemas/pipeline.py:138` |
| `ttl_days_medium: int = 30` | VERIFIED | `schemas/pipeline.py:139` |
| `ttl_days_high: int = 0` | VERIFIED | `schemas/pipeline.py:140` |
| `consolidation_cooldown_hours: int = 24` | VERIFIED | `schemas/pipeline.py:141` |
| `max_entries_per_propose: int = 3` | VERIFIED | `schemas/pipeline.py:142` |
| `consolidation_merge_window_hours: int = 72` | VERIFIED | `schemas/pipeline.py:143` |
| `truncation_llm_enabled: bool = True` | VERIFIED | `schemas/pipeline.py:144` |
| `truncation_llm_threshold: int = 2000` | VERIFIED | `schemas/pipeline.py:145` |
| `truncation_llm_max_tokens: int = 512` | VERIFIED | `schemas/pipeline.py:146` |
| `truncation_llm_temperature: float = 0.0` | VERIFIED | `schemas/pipeline.py:147` |

### providers.yaml Structure
| Claim | Status | Evidence |
|-------|--------|----------|
| `providers:` key (list) | VERIFIED | `providers.yaml:1-124` |
| `search_providers:` section (plural) | VERIFIED | `providers.yaml:127-150` |
| `default_provider: ollama-local` | VERIFIED | `providers.yaml:125` |
| `default_search_provider: duckduckgo` | VERIFIED | `providers.yaml:151` |
| ollama-local provider | VERIFIED | `providers.yaml:2-8` |
| openai provider | VERIFIED | `providers.yaml:10-17` |
| anthropic provider | VERIFIED | `providers.yaml:19-25` |
| gemini provider | VERIFIED | `providers.yaml:27-33` |
| deepseek provider | VERIFIED | `providers.yaml:35-42` |
| groq provider | VERIFIED | `providers.yaml:44-51` |
| openrouter provider | VERIFIED | `providers.yaml:53-60` |
| xai provider | VERIFIED | `providers.yaml:62-69` |
| togetherai provider | VERIFIED | `providers.yaml:71-78` |
| fireworks provider | VERIFIED | `providers.yaml:80-87` |
| cerebras provider | VERIFIED | `providers.yaml:89-96` |
| zai provider | VERIFIED | `providers.yaml:98-105` |
| minimax provider | VERIFIED | `providers.yaml:107-114` |
| opencode provider | VERIFIED | `providers.yaml:116-123` |

### Config Loading Functions
| Claim | Status | Evidence |
|-------|--------|----------|
| `load_pipeline_config()` | VERIFIED | `schemas/pipeline.py:183-190` |
| `load_sources()` | VERIFIED | `schemas/source.py` |
| `load_providers_config()` | VERIFIED | `schemas/llm.py` |
| `cached_config_with_mtime()` | VERIFIED | `schemas/common.py:82-97` |
| `get_config_with_default()` | VERIFIED | `services/config_utils.py:13-71` |
| `validate_config()` | VERIFIED | `services/config_unified.py:220-231` |

### Beat Schedule
| Claim | Status | Evidence |
|-------|--------|----------|
| `get_beat_schedule()` in `config.py` | VERIFIED | `config.py:117-203` |
| All 14 tasks listed | VERIFIED | `config.py:146-203` |
| Configurable via `pipeline.yaml` `schedule:` section | VERIFIED | `config.py:133-144` |

### Environment Variables
| Claim | Status | Evidence |
|-------|--------|----------|
| `FLASK_CONFIG` | VERIFIED | `app.py:295` |
| `SECRET_KEY` | VERIFIED | `config.py:38` |
| `DATABASE_URL` | VERIFIED | `config.py:244` |
| `REDIS_URL` | VERIFIED | `services/circuit_breaker.py:216` |
| `REDIS_SSL` | VERIFIED | `extensions.py:108` |
| `REDIS_MAX_CONNECTIONS` | VERIFIED | `extensions.py:107` |
| `CONFIG_CACHE_REDIS_URL` | VERIFIED | `services/config_cache.py:297-301` |
| `CONFIG_CACHE_REDIS_PASSWORD` | VERIFIED | `services/config_cache.py:303` |
| `OPENAI_API_KEY` | VERIFIED | `providers.yaml:14` |
| `ANTHROPIC_API_KEY` | VERIFIED | `providers.yaml:21` |
| `GEMINI_API_KEY` | VERIFIED | `providers.yaml:29` |
| `GOOGLE_API_KEY` | VERIFIED | `providers.yaml:137` |
| `GOOGLE_CSE_ID` | VERIFIED | `providers.yaml:138` |
| `SEARXNG_BASE_URL` | VERIFIED | (used in `services/search/searxng.py`) |
| `WEBHOOK_SECRET_KEY` | VERIFIED | `services/webhooks.py:36` |
| `CELERY_TASK_SECRET` | VERIFIED | `config.py:56` |
| `EXPERIMENT_SALT` | VERIFIED | `pipeline.yaml:197` (referenced as `${EXPERIMENT_SALT}`) |
| `CONTENT_EXTRACTOR_WORKERS` | VERIFIED | `services/content_extractor.py` |
| `RELATED_CANDIDATE_LIMIT` | VERIFIED | `services/related.py` |

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| — | None found | — | — |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | `config.md` line 638 says "call `Config.reload_beat_schedule()` then `POST /api/v1/config/reload` to apply" — the `reload_beat_schedule()` method requires a `celery_app` parameter (`config.py:206`), but the documentation doesn't mention this | `config.py:206` | MEDIUM | `reload_beat_schedule(cls, celery_app)` requires the Celery app instance; the doc implies it can be called without arguments |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Document that `RoleConfig.provider` and `RoleConfig.model` are required fields (use `Field(...)`) — callers must always provide them | documentation | P2 |
| 2 | Add note that `MemoryConfig` has 4 additional fields (`truncation_llm_enabled`, `truncation_llm_threshold`, `truncation_llm_max_tokens`, `truncation_llm_temperature`) beyond what's shown in the `pipeline.yaml` example | documentation | P2 |
| 3 | Document the `SubagentConfig` structure more clearly — it has `default`, `research`, `edit`, and `chains` fields | documentation | P2 |
| 4 | Add `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` to the environment variables table | documentation | P2 |
| 5 | Document that `StageConfig` is a stub with only a `tools` field — actual config is in `RoleConfig` and `SubagentStageConfig` | documentation | P3 |
| 6 | Add `REDIS_PASSWORD` and `SMTP_*` env vars to the environment variables table | documentation | P3 |
| 7 | Document that `config.py:get_beat_schedule()` uses `pipeline_cfg.schedule` dict (not the Pydantic model) — the schedule section is `dict` typed | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 638 | "call `Config.reload_beat_schedule()` then `POST /api/v1/config/reload` to apply" | `reload_beat_schedule()` requires `celery_app` parameter — the doc implies a no-arg call | Update to mention `celery_app` parameter |

---

## Summary

- Verified: 92 claims
- Incorrect: 0 claims
- Bugs: 1 (HIGH: 0, MEDIUM: 1, LOW: 0)
- Improvements: 7
- Stale items: 1

The config.md document is highly accurate and comprehensive. The main issue is a minor documentation gap around the `reload_beat_schedule()` method signature. All schema definitions, environment variables, and configuration file structures match the actual code. The only medium-severity issue is the missing `celery_app` parameter in the `reload_beat_schedule()` documentation.
