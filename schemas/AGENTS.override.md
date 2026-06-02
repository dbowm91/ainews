# Schemas Conventions

Contextual conventions for agents working in the `schemas/` directory.

## Environment Variables

Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders in configuration schemas.
- For required config (api keys, secrets), use `resolve_env_var(val, required=True)` to fail fast on missing vars.
- For optional config with defaults, use `resolve_env_var(val, required=False)` which returns empty string on missing.

## Schema Notes

- **StageConfig vs SubagentStageConfig:** `StageConfig` in `schemas/pipeline.py` is an empty stub (only `tools` field). The actual stage configuration is in `SubagentStageConfig` which has `enabled`, `max_retries`, `retry_delay`, `timeout` fields.
- **RawItem Location:** `RawItem` dataclass was moved from `adapters/base.py` to `schemas/item.py`. Use `schemas/item.py` for the type.
- **LLM Response Schemas:** Documented fields in `architecture/schemas.md` often don't match actual implementation. For example:
  - `ResearchBrief` uses `key_claims`, `context_notes`, `external_sources` (not `key_findings`, `context`, `citations`)
  - `CondensedArticle` uses `headline`, `tldr`, `body` (not `title`, `summary`, `word_count`)
  - `NewsletterBrief` uses `themes`, `highlights`, `connections` (not `newsletter_id`, `subject`)
- **PipelineLog meta field:** Uses `meta` (not `metadata`) due to SQLAlchemy reserved name restriction.
- **Admin Schemas:** `schemas/admin.py` contains: `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams`.
- **LLM Config Schemas:** `schemas/llm.py` contains: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig`, `load_providers_config()`.
- **SendEmailTask validator:** `SendEmailTask` in `schemas/tasks.py:59-70` HAS an email validator (`@field_validator("email")` using `_EMAIL_RE`). Do NOT document it as lacking validation.

## Adapter Config Validation
`SourceConfig.config` in `schemas/source.py` has a `field_validator` that validates `config` against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on `type`. The `ADAPTER_CONFIGS` dict at line 98-102 maps type to config class.

## SearchConfig Caching
`load_search_config()` in `schemas/search.py:31` uses `config_path = Path(path)` for proper mtime-based cache invalidation when custom paths are passed.

## Architecture Documentation Review Findings

When reviewing or updating `architecture/schemas.md`:
- **`RoleConfig` is missing entirely** - not documented at all despite having `enabled: bool = True` field and role-specific optional fields
- **`ReviewConfig` is missing** - exists at `schemas/pipeline.py:35-41` but not documented
- **`SubagentStageConfig` fields not enumerated** - 13 fields at `schemas/pipeline.py:93-105` with `max_iterations: int = Field(default=5, ge=1, le=20)`
- **Role-specific optional fields** at `schemas/pipeline.py:24-32` include: `system_prompt`, `min_score` (selector), `web_search`, `web_search_max_results`, `web_search_provider`, `db_related_max`, `max_article_text_length` (researcher), `max_key_points` (writer), `max_tags` (editor)