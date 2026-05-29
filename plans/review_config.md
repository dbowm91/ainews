# Config.md Review

**Reviewed:** 2026-05-29
**Source:** `architecture/config.md`

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| `pipeline.yaml` purpose | ✅ Verified | Contains pipeline stages, newsletter, subagent, memory, experiments, schedules |
| `providers.yaml` purpose | ✅ Verified | Contains LLM + search provider definitions |
| `sources.yaml` purpose | ✅ Verified | Contains news source definitions |
| `topics.yaml` purpose | ✅ Verified | Contains topic definitions |
| `PipelineRootConfig` structure | ✅ Verified | `schemas/pipeline.py:150-159` |
| `RoleConfig` fields | ✅ Verified | `schemas/pipeline.py:16-32` |
| `SubagentStageConfig` fields | ✅ Verified | `schemas/pipeline.py:93-105` |
| `MemoryConfig` fields | ✅ Verified | `schemas/pipeline.py:128-138` |
| `SourceConfig` schema | ✅ Verified | `schemas/source.py:17-52` |
| Environment variable `GOOGLE_API_KEY` | ✅ Verified | `providers.yaml:137` |
| Environment variable `GOOGLE_CSE_ID` | ✅ Verified | `providers.yaml:138` |
| Config loading via `cached_config_with_mtime` | ✅ Verified | `schemas/common.py` |
| `get_beat_schedule()` loading from `pipeline.yaml` | ✅ Verified | `config.py:118-203` |
| `validate_config()` function | ✅ Verified | `services/config_unified.py:220` |
| `get_config_with_default()` for Celery | ✅ Verified | `services/config_utils.py:26-42` |

---

## Incorrect Claims

### HIGH: `providers.yaml` YAML structure doesn't match doc (lines 283-321)

**Doc shows:**
```yaml
providers:
  ollama-local:
    type: openai
    enabled: true
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
    default_model: "qwen3:8b"
```

**Actual (`providers.yaml:1-7`):**
```yaml
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: "http://localhost:11434"
      model: "qwen3:8b"
      max_tokens: 4096
```

The actual structure uses a **list** of provider objects with `id`, `type`, `enabled`, `config` fields, NOT a dict keyed by provider name. Also `type` is `ollama` not `openai`, and config fields differ (`host`/`model`/`max_tokens` vs `base_url`/`api_key`/`default_model`).

### HIGH: Search provider config key is `search_providers:` not `search:` (line 310)

**Doc says:**
```yaml
search:
  default: duckduckgo
  providers:
```

**Actual (`providers.yaml:127`):**
```yaml
search_providers:
  - id: duckduckgo
    type: duckduckgo
    enabled: true
    config: {}
```

Uses `search_providers:` with list structure, not `search:` with nested dict.

### MEDIUM: `RoleConfig` docstring says `provider`/`model` are required (line 236-237)

**Doc says:**
```python
class RoleConfig(BaseModel):
    provider: str = Field(...)  # Required
    model: str = Field(...)  # Required
```

**Actual (`schemas/pipeline.py:17-19`):**
```python
class RoleConfig(BaseModel):
    enabled: bool = True
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
```

The doc omits `enabled: bool = True`. While `provider`/`model` ARE required, the doc is incomplete.

### MEDIUM: `SubagentStageConfig` docstring wrong `provider`/`model` optionality (line 255-256)

**Doc says:**
```python
class SubagentStageConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
```

**Actual (`schemas/pipeline.py:93-96`):**
```python
class SubagentStageConfig(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = MAX_TOKENS_FIELD
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    ...
```

Actually correct - `provider`/`model` ARE Optional[str] = None in the schema. But the actual runtime behavior is that `resolve_subagent_config()` falls back to the default role config when these are None.

---

## Bugs Found

### MEDIUM: Google env var names corrected but old names may still appear

Per `plans/plan.md:36`, the Google env var names were corrected from `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX` to `GOOGLE_API_KEY`/`GOOGLE_CSE_ID`. This was fixed in config.md but the **old names** (`GOOGLE_SEARCH_API_KEY`, `GOOGLE_SEARCH_CX`) were never the actual env vars used in code - they were always `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`. The doc incorrectly documented what the CORRECT names should be.

---

## Improvement Opportunities

### `SourceConfig` schema documentation incomplete (lines 362-375)

The doc shows:
```python
class SourceConfig(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=128)
    type: str  # "rss", "api", or "web" (validated by field_validator)
    enabled: bool = True
    schedule_minutes: int = Field(default=30, ge=5, le=1440)
    config: dict[str, Any]  # Adapter-specific (RSSConfig, APIConfig, or WebConfig)
    topics: TopicMatchConfig = Field(default_factory=TopicMatchConfig)
```

Missing `topics` field definition and `schedule_minutes` is correct but the actual field is `schedule_minutes: int = Field(default=30, ge=5, le=1440)` with `topics: TopicMatchConfig` field.

### Celery Beat Schedule mentions 14 tasks but shows only partial mapping

The doc at line 129 says "14 scheduled tasks" but the table shows all 14 correctly. The actual `config.py:get_beat_schedule()` returns exactly 14 tasks (lines 146-203).

### Missing `CONFIG_CACHE_REDIS_URL` env var documentation

The environment variables table (lines 451-473) doesn't include `CONFIG_CACHE_REDIS_URL`. While `config_cache.py` has a fallback chain (uses `CONFIG_CACHE_REDIS_URL` if set, else derives from `CELERY_BROKER_URL`), this env var should be documented.

### Missing `CONFIG_CACHE_REDIS_PASSWORD` env var

The config cache supports `CONFIG_CACHE_REDIS_PASSWORD` for dedicated config cache Redis auth (`config_cache.py:303`).

---

## Stale Content

### `RoleConfig` example in doc shows `provider: str = Field(...)` without showing default values for other fields

The doc example at lines 234-245 shows a partial schema. The full `RoleConfig` includes many more optional fields like `web_search`, `web_search_max_results`, `db_related_max`, `max_article_text_length`, `max_key_points`, `max_tags` that are role-specific.

### Newsletter pipeline subagent config example shows wrong structure

Lines 114-158 show subagent config with `provider: null, model: null` but the actual `SubagentStageConfig` uses `Optional[str] = None` and `resolve_subagent_config()` handles the null → default role fallback.

---

## Priority Findings

| Priority | Finding | Location |
|----------|---------|----------|
| HIGH | `providers.yaml` structure is completely wrong | `config.md:283-321` |
| HIGH | `search_providers:` vs `search:` | `config.md:310` |
| MEDIUM | `RoleConfig` doc omits `enabled` field | `config.md:234-245` |
| MEDIUM | Missing `CONFIG_CACHE_REDIS_URL` env var | `config.md` env var table |
| LOW | Incomplete `SourceConfig` schema documentation | `config.md:362-375` |
