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

## Adapter Config Validation (FIXED - CRIT-3)
`SourceConfig.config` in `schemas/source.py` now has a `field_validator` that validates `config` against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on `type`. The `ADAPTER_CONFIGS` dict at line 98-102 maps type to config class.

## SearchConfig Caching Bug (IDENTIFIED - FIX PLANNED)
`load_search_config()` in `schemas/search.py` has a bug at line 31: `config_path` is hardcoded to `BASE_DIR / "providers.yaml"` instead of using `Path(path)`. This means the cache tracks the wrong file for invalidation when a custom path is passed. The fix is: change `config_path = BASE_DIR / "providers.yaml"` to `config_path = Path(path)`. This is documented in `plans/plan.md` Phase 1 item 1.1.