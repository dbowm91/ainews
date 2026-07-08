# Milestone B.2: Provider and Default-Provider Validation

## Objective

Make LLM provider configuration validation strict, predictable, and operator-friendly in production. A production service should not boot with an enabled but unusable provider, an invalid provider type, missing required credentials, or a `default_provider` that points to a disabled or nonexistent provider.

## Current risk

The provider configuration system is flexible, but earlier inspection found production validation can log warnings and continue after provider validation errors. That creates a mismatch between startup success and actual runtime capability. It also makes deployment failures harder to diagnose because the app may boot and fail later inside the pipeline.

## Affected files

Likely files:

- `config.py`
- `schemas/llm.py`
- `schemas/common.py`
- `providers.yaml`
- `tests/`
- `docs/configuration.md`
- `docs/deployment.md`
- `.env.example`

## Validation requirements

Production provider validation should enforce:

- Provider config file loads successfully.
- Provider sections have expected shape.
- Enabled providers must have known provider types.
- Enabled providers must pass their Pydantic config model validation.
- Enabled providers with `${ENV_VAR}` placeholders must resolve required env vars.
- Empty-string resolved required env vars fail.
- `default_provider` must be set.
- `default_provider` must exist in provider definitions.
- `default_provider` must be enabled.
- `default_provider` must pass validation.
- At least one enabled provider must pass validation.
- Search provider defaults should be validated separately from LLM provider defaults.

## Implementation plan

### Step 1: Make env-var resolution recursive or explicitly scoped

Inspect `schemas/common.py` and `schemas/llm.py` to determine whether nested provider configs are recursively resolving `${VAR}` placeholders. Provider config often nests values under `config:` dictionaries; shallow resolution is insufficient if required placeholders are nested.

Preferred behavior:

```python
def resolve_env_vars(value, required=False):
    if isinstance(value, dict):
        return {k: resolve_env_vars(v, required=required) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v, required=required) for v in value]
    if isinstance(value, str):
        return resolve_env_var(value, required=required)
    return value
```

Be careful: not all env placeholders are required globally. Requiredness should be enforced by provider-specific config models or explicit production validation.

### Step 2: Normalize provider validation results

Create a helper that returns structured provider validation results rather than logging and continuing.

Suggested result fields:

- `provider_id`
- `enabled`
- `provider_type`
- `valid`
- `errors`
- `warnings`

Production validation can then fail if any enabled provider has errors.

### Step 3: Validate provider type and config model

For each enabled provider:

1. Check provider type is known.
2. Load its config model.
3. Validate nested config.
4. Resolve required env vars.
5. Fail on missing credentials or malformed URLs/models.

If a provider is disabled, it can have missing credentials without failing production. However, disabled providers with malformed YAML should still fail if the malformed structure prevents config loading entirely.

### Step 4: Validate `default_provider`

Implement explicit validation:

```python
if not default_provider:
    errors.append("default_provider is required in production")
elif default_provider not in providers:
    errors.append(...)
elif not providers[default_provider].enabled:
    errors.append(...)
elif not provider_results[default_provider].valid:
    errors.append(...)
```

Do not accept a fallback provider silently in production unless explicitly documented and tested.

### Step 5: Validate no-provider and multi-provider cases

Cases to support:

- One enabled valid local provider.
- One enabled valid cloud provider with env API key.
- Multiple enabled providers where one is invalid: production should fail, because enabled means intended usable.
- Disabled provider with missing key: production should pass.
- Default provider disabled: production should fail.
- No enabled provider: production should fail.

### Step 6: Improve error messages

Errors should include provider ID and field name, not only Pydantic traces.

Examples:

- `Provider 'openai' is enabled but OPENAI_API_KEY is not set`
- `Provider 'ollama-local' is enabled but config.host is empty`
- `default_provider 'anthropic' is disabled`
- `default_provider 'missing' does not exist in providers.yaml`

Avoid including actual secret values in exceptions or logs.

## Test plan

Add provider validation tests using temporary YAML/config data and monkeypatched env vars.

Required tests:

- Valid enabled Ollama/local provider passes shape validation.
- Valid enabled OpenAI-style provider passes when env API key is present.
- Enabled OpenAI-style provider with missing env API key fails.
- Disabled OpenAI-style provider with missing env API key does not fail.
- Unknown enabled provider type fails.
- Invalid provider config shape fails.
- `default_provider` missing fails.
- `default_provider` nonexistent fails.
- `default_provider` disabled fails.
- `default_provider` invalid fails.
- Multiple enabled providers with one invalid fails.
- No enabled providers fails.

Targeted command:

```bash
uv run pytest tests/ -k "provider or default_provider or llm_config" -q
```

## Documentation updates

Update `docs/configuration.md` and `.env.example` to explain:

- How provider enablement works.
- Difference between disabled provider placeholders and enabled provider required keys.
- `default_provider` requirements.
- Docker-specific local provider host considerations.
- Example valid provider configs for Ollama and one cloud provider.

## Acceptance criteria

- Production provider validation fails closed on invalid enabled providers.
- `default_provider` is validated as present, enabled, and valid.
- Disabled provider missing credentials do not block production.
- Error messages are actionable and non-secret.
- Tests cover valid and invalid cases.

## Handoff cautions

- Do not perform live LLM API calls during config validation.
- Do not require API keys for disabled providers.
- Avoid implicit default-provider fallback in production.
- Keep provider validation compatible with future provider additions by centralizing provider type metadata.

## Status: COMPLETE

All 6 steps implemented and verified:

1. **Recursive env-var resolution** — `schemas/common.py:resolve_env_vars()` already handles nested dicts/lists (B.2 Step 1 done in B.1)
2. **Structured provider validation** — `_validate_llm_providers()` tracks `valid_provider_ids` set, `_validate_provider_type()`, `_validate_provider_config()`, `_validate_cloud_api_key()` return structured results
3. **Provider type and config validation** — Each enabled provider validated against `ADAPTER_CONFIGS` Pydantic schema
4. **`default_provider` validation** — `_validate_default_provider()` now checks existence, enabled status, AND config validity via `valid_provider_ids` set
5. **Multi-provider and edge cases** — Tests cover: no providers, one invalid, disabled provider, missing default, disabled default, invalid config default
6. **Actionable error messages** — Provider ID and field name in all errors, no secrets leaked

### Test Results
- `tests/test_production_config.py`: 56/56 pass (including new `test_default_provider_invalid_config_fails`)
- All smoke tests: 73/73 pass
- `ruff check`: 0 new issues
