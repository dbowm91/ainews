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

## Adapter Config Validation (FIXED - CRIT-3)
`SourceConfig.config` in `schemas/source.py` now has a `field_validator` that validates `config` against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on `type`. The `ADAPTER_CONFIGS` dict at line 98-102 maps type to config class.

## SearchConfig Caching Bug (FIXED)
`load_search_config()` in `schemas/search.py:31` now correctly uses `config_path = Path(path)` for proper mtime-based cache invalidation. The cache now tracks the correct file when a custom path is passed.

## Known Bugs (OPEN)
- **ProcessItemTask topics validation:** `ProcessItemTask.topics` at `schemas/tasks.py:99` is a `list[str]` with no `max_length` constraint. Other schemas like `SelectArticleTask` have `validate_topics` validators. Add a similar validator or `max_length` constraint.

## Architecture Documentation Review Findings

When reviewing or updating `architecture/schemas.md`:
- **`RoleConfig` is missing entirely** - not documented at all despite having `enabled: bool = True` field and role-specific optional fields
- **`ReviewConfig` is missing** - exists at `schemas/pipeline.py:35-41` but not documented
- **`SubagentStageConfig` fields not enumerated** - 13 fields at `schemas/pipeline.py:93-105` with `max_iterations: int = Field(default=5, ge=1, le=20)`
- **Role-specific optional fields** at `schemas/pipeline.py:24-32` include: `system_prompt`, `min_score` (selector), `web_search`, `web_search_max_results`, `web_search_provider`, `db_related_max`, `max_article_text_length` (researcher), `max_key_points` (writer), `max_tags` (editor)

## Wave 9 Review Findings

### WebConfig Field Descriptions Missing
`schemas/source.py:94-96` has `max_items`, `request_delay_min`, `request_delay_max` fields without field descriptions. Add descriptions for developer experience.

### SearchConfig YAML Key Mapping
`schemas/search.py:12,23` - Schema field is `default_provider` but YAML key is `default_search_provider`. Add clarifying comment.

### ResearchBrief Schema Fields Verified
Actual fields at `schemas/llm_responses.py:53-79`:
- `source_summary`, `key_claims`, `direct_quotes`, `external_sources`, `related_articles`, `context_notes`, `newsworthiness`, `impact_score`

The architecture docs at `architecture/pipeline.md:88` incorrectly show `{key_findings, context, citations, related_trends}`. `architecture/prompts.md:109` has the correct schema.