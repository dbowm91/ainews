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

## Adapter Config Validation (BUG - CRIT-3)
`SourceConfig.config` in `schemas/source.py` is typed as `dict[str, Any]` with no adapter-specific validation. An RSS source with API-config fields will pass validation silently and fail at runtime. A `field_validator` should be added to validate `config` against the appropriate adapter schema based on `type`. The `ADAPTER_CONFIGS` dict already exists at line 98-102 mapping type to config class (RSSConfig, APIConfig, WebConfig).