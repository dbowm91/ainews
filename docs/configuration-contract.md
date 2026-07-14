# Configuration Contract

Machine-oriented inventory of every configuration surface in the ainews project. Each row represents a single configurable value, its physical destination, serialization, type constraints, and runtime consumers.

---

## Legend

| Column | Meaning |
|--------|---------|
| **Key** | Canonical dotted-notation identifier |
| **Destination** | Physical file or env-var surface (`config.py` → Flask config, `providers.yaml`, `pipeline.yaml`, `sources.yaml`, `topics.yaml`) |
| **Env / Path** | Environment variable name (for env-based keys) or YAML path (for YAML-based keys) |
| **Type** | Python type and constraints |
| **Profiles** | Required in which profiles: `all`, `production`, `development`, `testing` |
| **Default Source** | Where the default originates: `env var`, `YAML default`, `code default`, `derived` |
| **Secret** | Classification: `secret`, `sensitive`, `public`, `generated`, `derived`, `deprecated` |
| **Restart** | Which process needs restart: `web`, `worker`, `scheduler`, `all`, `none` |
| **Validator** | Code that validates the field at startup or runtime |
| **Consumers** | Modules or subsystems that read the value |
| **Deprecated** | Whether superseded by another key |

---

## 1 — Environment Variables (config.py)

### 1.1 Secrets & Authentication

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validator | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|-----------|-----------|------------|
| `secret_key` | Flask config | `SECRET_KEY` | `str` | production | env var | secret | all | `ProductionConfig._validate_secrets` | Flask sessions, CSRF, JWT signing | — |
| `secret_key_fallbacks` | Flask config | `SECRET_KEY_PREVIOUS_1`, `SECRET_KEY_PREVIOUS_2` | `list[str]` | all | env var (empty) | secret | all | — | Flask session verification | — |
| `admin_password` | Flask config | `ADMIN_PASSWORD` | `str` | production | env var | secret | all | `ProductionConfig._validate_secrets` | `routes/admin/__init__.py` login | — |
| `celery_task_secret` | Flask config | `CELERY_TASK_SECRET` | `str` | production | env var | secret | all | `ProductionConfig._validate_secrets` | `tasks/` HMAC signing | — |

### 1.2 Database

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validator | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|-----------|-----------|------------|
| `sqlalchemy_database_uri` | Flask config | `DATABASE_URL` | `str` (SQLAlchemy URI) | production | env var (fallback: `instance/prod.db`) | derived | all | — | `extensions.db`, all models | — |

### 1.3 Safe Fetch (HTTP client)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validator | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|-----------|-----------|------------|
| `safe_fetch_max_redirects` | Flask config | `SAFE_FETCH_MAX_REDIRECTS` | `int` (≥1) | all | code default: `5` | public | none | `_validate_safe_fetch` | `services/safe_fetch.py` | — |
| `safe_fetch_max_bytes` | Flask config | `SAFE_FETCH_MAX_BYTES` | `int` (1–10 000 000) | all | code default: `2 000 000` | public | none | `_validate_safe_fetch` | `services/safe_fetch.py` | — |
| `safe_fetch_connect_timeout` | Flask config | `SAFE_FETCH_CONNECT_TIMEOUT` | `float` (0.1–30) | all | code default: `5.0` | public | none | `_validate_safe_fetch` | `services/safe_fetch.py` | — |
| `safe_fetch_read_timeout` | Flask config | `SAFE_FETCH_READ_TIMEOUT` | `float` (0.1–60) | all | code default: `10.0` | public | none | `_validate_safe_fetch` | `services/safe_fetch.py` | — |
| `safe_fetch_total_timeout` | Flask config | `SAFE_FETCH_TOTAL_TIMEOUT` | `float` (≥0.1) | all | code default: `20.0` | public | none | `_validate_safe_fetch` | `services/safe_fetch.py` | — |

### 1.4 DNS & Cache

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `dns_cache_ttl` | Flask config | `DNS_CACHE_TTL` | `int` | all | code default: `300` | public | none | — | `services/url.py` | — |
| `dns_cache_max` | Flask config | `DNS_CACHE_MAX` | `int` | all | code default: `1024` | public | none | — | `services/url.py` | — |
| `l1_cache_maxsize` | Flask config | `L1_CACHE_MAXSIZE` | `int` | all | code default: `1000` | public | none | — | `services/cache.py` | — |

### 1.5 Login Security

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `login_max_attempts` | Flask config | `LOGIN_MAX_ATTEMPTS` | `int` | all | code default: `5` | public | none | — | `routes/admin/__init__.py` | — |
| `login_lockout_seconds` | Flask config | `LOGIN_LOCKOUT_SECONDS` | `int` | all | code default: `900` | public | none | — | `routes/admin/__init__.py` | — |

### 1.6 Content & Verification

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `min_content_length` | Flask config | `MIN_CONTENT_LENGTH` | `int` | all | code default: `200` | public | none | — | `services/config_unified.py`, `tasks/crawl.py` | — |
| `verification_expiry_seconds` | Flask config | `VERIFICATION_EXPIRY_SECONDS` | `int` | all | code default: `3600` | public | none | — | `routes/admin/__init__.py` | — |

### 1.7 Theme Subsystem

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `themes_enabled` | Flask config | `THEMES_ENABLED` | `bool` | all | code default: `true` | public | web | `_validate_themes` | `services/themes/loader.py`, `routes/themes.py` | — |
| `themes_custom_dir` | Flask config | `THEMES_CUSTOM_DIR` | `str` (path) | all | code default: `""` | public | web | `_validate_themes` | `services/themes/loader.py` | — |
| `themes_allow_custom` | Flask config | `THEMES_ALLOW_CUSTOM` | `bool` | all | code default: `true` | public | web | `_validate_themes` | `services/themes/loader.py` | — |
| `themes_default` | Flask config | `THEMES_DEFAULT` | `str` | all | code default: `""` | public | web | `_validate_themes` | `services/themes/loader.py` | — |
| `themes_default_dark` | Flask config | `THEMES_DEFAULT_DARK` | `str` | all | code default: `"catppuccin-mocha"` | public | web | `_validate_themes` | `services/themes/loader.py`, `theme.js` | — |
| `themes_default_light` | Flask config | `THEMES_DEFAULT_LIGHT` | `str` | all | code default: `"catppuccin-latte"` | public | web | `_validate_themes` | `services/themes/loader.py`, `theme.js` | — |
| `themes_max_file_bytes` | Flask config | `THEMES_MAX_FILE_BYTES` | `int` (1024–1 048 576) | all | code default: `262144` | public | web | `_validate_themes` | `services/themes/parser.py` | — |
| `themes_strict_contrast` | Flask config | `THEMES_STRICT_CONTRAST` | `bool` | all | code default: `false` | public | web | `_validate_themes` | `services/themes/contrast.py` | — |

### 1.8 Database & Observability

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `db_query_log_level` | Flask config | `DB_QUERY_LOG_LEVEL` | `str` (log level) | all | code default: `"WARNING"` | public | none | — | `app.py` SQLAlchemy event | — |
| `otel_exporter_otlp_endpoint` | Flask config | `OTEL_EXPORTER_OTLP_ENDPOINT` | `str` (URL) | all | code default: `""` | public | web | — | `services/metrics.py` | — |

### 1.9 SMTP

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `smtp_host` | Flask config | `SMTP_HOST` | `str` | all | code default: `"localhost"` | public | web | — | `services/newsletter_email.py` | — |
| `smtp_port` | Flask config | `SMTP_PORT` | `int` | all | code default: `587` | public | web | — | `services/newsletter_email.py` | — |
| `smtp_user` | Flask config | `SMTP_USER` | `str` | all | code default: `""` | sensitive | web | — | `services/newsletter_email.py` | — |
| `smtp_password` | Flask config | `SMTP_PASSWORD` | `str` | all | code default: `""` | secret | web | — | `services/newsletter_email.py` | — |
| `smtp_from` | Flask config | `SMTP_FROM` | `str` (email) | all | code default: `"noreply@ainews.dev"` | public | web | — | `services/newsletter_email.py` | — |
| `smtp_use_tls` | Flask config | `SMTP_USE_TLS` | `bool` | all | code default: `true` | public | web | — | `services/newsletter_email.py` | — |
| `smtp_pool_size` | Flask config | `SMTP_POOL_SIZE` | `int` | all | code default: `5` | public | web | — | `services/newsletter_email.py` | — |

### 1.10 Celery

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `celery_broker_url` | Flask config | `CELERY_BROKER_URL` | `str` (Redis URI) | all | code default: `"redis://localhost:6379/0"` | sensitive | all | — | `extensions.py`, Celery app | — |
| `celery_result_backend` | Flask config | `CELERY_RESULT_BACKEND` | `str` (Redis URI) | all | code default: `"redis://localhost:6379/1"` | sensitive | all | — | Celery app | — |

### 1.11 Pipeline Retry & Limits

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `max_stage_retries` | Flask config | `MAX_STAGE_RETRIES` | `int` | all | code default: `3` (from `constants.py`) | public | worker | — | `tasks/pipeline.py:run_stage` | — |
| `max_total_retries` | Flask config | `MAX_TOTAL_RETRIES` | `int` | all | code default: `10` (from `constants.py`) | public | worker | — | `tasks/pipeline.py`, `services/config_unified.py` | — |
| `pipeline_timeout_seconds` | Flask config | `PIPELINE_TIMEOUT_SECONDS` | `int` | all | code default: `3600` (from `constants.py`) | public | worker | — | `tasks/pipeline.py` | — |
| `max_consecutive_failures` | Flask config | `MAX_CONSECUTIVE_FAILURES` | `int` | all | code default: `10` | public | worker | — | `services/config_unified.py`, source health | — |
| `stuck_threshold_minutes` | Flask config | `STUCK_THRESHOLD_MINUTES` | `int` | all | code default: `60` | public | worker | — | `tasks/retry.py`, `services/config_unified.py` | — |
| `retry_soft_cutoff_minutes` | Flask config | `RETRY_SOFT_CUTOFF_MINUTES` | `int` | all | code default: `15` | public | worker | — | `tasks/pipeline.py`, `services/config_unified.py` | — |

### 1.12 Detection & Misc

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `flask_config` | Flask config | `FLASK_CONFIG` | `str` | all | code default: `"development"` | public | all | — | `app.py:create_app` | — |
| `ainews_running_in_docker` | env only | `AINEWS_RUNNING_IN_DOCKER` | `str` (`"1"` = true) | all | env var | public | none | `_detect_docker_environment` | `config.py:_validate_docker_ollama_host` | — |

### 1.13 Flask Hardcoded Settings (not env-configurable)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `sqlalchemy_track_modifications` | Flask config | — | `bool` (`False`) | all | code default | public | — | — | `extensions.db` | — |
| `send_file_max_age_default` | Flask config | — | `int` (`31536000`) | all | code default | public | — | — | Flask static files | — |
| `session_cookie_httponly` | Flask config | — | `bool` (`True`) | all | code default | public | — | `_validate_session_security` | Flask sessions | — |
| `session_cookie_samesite` | Flask config | — | `str` (`"Lax"`) | all | code default | public | — | `_validate_session_security` | Flask sessions | — |
| `session_cookie_secure` | Flask config | — | `bool` (`True` in prod) | production | code default | public | — | `_validate_session_security` | Flask sessions | — |
| `session_use_signer` | Flask config | — | `bool` (`True`) | all | code default | public | — | — | Flask sessions | — |
| `session_cookie_path` | Flask config | — | `str` (`"/"`) | all | code default | public | — | — | Flask sessions | — |
| `permanent_session_lifetime` | Flask config | — | `timedelta` (`2h`) | all | code default | public | — | — | Flask sessions | — |
| `max_content_length` | Flask config | — | `int` (`65536`) | all | code default | public | — | — | Flask request parsing | — |
| `wtf_csrf_enabled` | Flask config | — | `bool` (`True` in prod) | production | code default | public | — | — | Flask-WTF CSRF | — |

---

## 2 — providers.yaml

### 2.1 Top-Level Keys

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `providers` | `providers.yaml` | YAML: `providers` | `list[ProviderDef]` | all | YAML default | — | worker | `ProductionConfig._validate_llm_providers` | `services/llm/__init__.py`, `tasks/pipeline.py` | — |
| `default_provider` | `providers.yaml` | YAML: `default_provider` | `str` | all | YAML default: `"ollama-local"` | public | worker | `_validate_default_provider` | `services/llm/__init__.py:get_provider_chain` | — |
| `search_providers` | `providers.yaml` | YAML: `search_providers` | `list[ProviderDef]` | all | YAML default | — | worker | — | `services/search/*.py` | — |
| `default_search_provider` | `providers.yaml` | YAML: `default_search_provider` | `str` | all | YAML default: `"duckduckgo"` | public | worker | — | `services/search/__init__.py` | — |

### 2.2 Provider Definition (`providers[]`)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `providers[].id` | `providers.yaml` | YAML: `providers[].id` | `str` (pattern: `^[a-z0-9_\-]+$`) | all | YAML required | public | — | Pydantic | All pipeline roles | — |
| `providers[].type` | `providers.yaml` | YAML: `providers[].type` | `str` (`ollama`/`openai`/`anthropic`/`gemini`) | all | YAML required | public | — | `_validate_provider_type` | `services/llm/` adapters | — |
| `providers[].enabled` | `providers.yaml` | YAML: `providers[].enabled` | `bool` | all | YAML default: `true` | public | — | — | `get_provider_chain` | — |
| `providers[].config` | `providers.yaml` | YAML: `providers[].config` | `dict` | all | YAML default: `{}` | varies | — | `_validate_provider_config` | LLM adapter classes | — |

### 2.3 Provider Config Fields (per type)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `providers[].config.host` | `providers.yaml` | YAML (ollama only) | `str` (URL) | all | YAML default: `"http://localhost:11434"` | public | — | `_validate_docker_ollama_host` | `OllamaAdapter` | — |
| `providers[].config.model` | `providers.yaml` | YAML | `str` | all | YAML required | public | — | Pydantic | LLM adapters | — |
| `providers[].config.max_tokens` | `providers.yaml` | YAML | `int` (256–128000) | all | YAML default: `4096` | public | — | Pydantic | LLM adapters | — |
| `providers[].config.api_key` | `providers.yaml` | YAML (cloud only) | `str` (`${ENV_VAR}`) | all | env var via `${}` | secret | — | `_validate_cloud_api_key` | `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter` | — |
| `providers[].config.base_url` | `providers.yaml` | YAML (openai-type only) | `str` (URL) | all | YAML varies by provider | public | — | — | `OpenAIAdapter` | — |

### 2.4 Search Provider Config Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `search_providers[].id` | `providers.yaml` | YAML: `search_providers[].id` | `str` | all | YAML required | public | — | Pydantic | `services/search/__init__.py` | — |
| `search_providers[].type` | `providers.yaml` | YAML: `search_providers[].type` | `str` (`duckduckgo`/`google`/`searxng`/`hybrid`) | all | YAML required | public | — | Pydantic | `services/search/` | — |
| `search_providers[].enabled` | `providers.yaml` | YAML: `search_providers[].enabled` | `bool` | all | YAML default: `true` | public | — | — | `services/search/__init__.py` | — |
| `search_providers[].config` | `providers.yaml` | YAML: `search_providers[].config` | `dict` | all | YAML default: `{}` | varies | — | — | Search adapter classes | — |
| `search_providers[].config.api_key` | `providers.yaml` | YAML (google only) | `str` (`${GOOGLE_API_KEY}`) | all | env var | secret | — | — | `services/search/google.py` | — |
| `search_providers[].config.cse_id` | `providers.yaml` | YAML (google only) | `str` (`${GOOGLE_CSE_ID}`) | all | env var | sensitive | — | — | `services/search/google.py` | — |
| `search_providers[].config.host` | `providers.yaml` | YAML (searxng only) | `str` (URL) | all | YAML default: `"http://localhost:8888"` | public | — | — | `services/search/searxng.py` | — |

---

## 3 — pipeline.yaml

### 3.1 Pipeline Role Config (`pipeline.selector`, `.researcher`, `.writer`, `.editor`)

Each role (`selector`, `researcher`, `writer`, `editor`) has the same schema via `RoleConfig`:

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `pipeline.{role}.enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: `true` | public | worker | — | `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py` | — |
| `pipeline.{role}.provider` | `pipeline.yaml` | YAML | `str` | all | YAML required | public | worker | — | `tasks/pipeline.py:run_stage`, `services/llm/__init__.py` | — |
| `pipeline.{role}.model` | `pipeline.yaml` | YAML | `str` | all | YAML required | public | worker | — | `tasks/pipeline.py:run_stage`, `services/llm/__init__.py` | — |
| `pipeline.{role}.max_tokens` | `pipeline.yaml` | YAML | `int` (256–128000) | all | YAML default: `4096` | public | worker | Pydantic | LLM adapters | — |
| `pipeline.{role}.temperature` | `pipeline.yaml` | YAML | `float` (0.0–2.0) | all | YAML default: `0.0` | public | worker | Pydantic | LLM adapters | — |
| `pipeline.{role}.concurrency` | `pipeline.yaml` | YAML | `int` (1–32) | all | YAML default: `2` | public | worker | Pydantic | `services/limiter.py` | — |
| `pipeline.{role}.timeout_seconds` | `pipeline.yaml` | YAML | `int` (10–600) | all | YAML default: `120` | public | worker | Pydantic | `services/llm/` | — |
| `pipeline.{role}.system_prompt` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | LLM adapters (system message) | — |

#### Role-Specific Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `pipeline.selector.min_score` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/select.py` | — |
| `pipeline.researcher.web_search` | `pipeline.yaml` | YAML | `bool \| null` | all | YAML default: `null` | public | worker | — | `tasks/research.py` | — |
| `pipeline.researcher.web_search_max_results` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/research.py` | — |
| `pipeline.researcher.web_search_provider` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | `tasks/research.py` → `services/search/` | — |
| `pipeline.researcher.db_related_max` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/research.py` | — |
| `pipeline.researcher.max_article_text_length` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/research.py` | — |
| `pipeline.writer.max_key_points` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/write.py` | — |
| `pipeline.editor.max_tags` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/edit.py` | — |

### 3.2 Review Config

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `pipeline.review.enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: `false` | public | worker | — | `tasks/edit.py` | — |
| `pipeline.review.auto_publish_threshold` | `pipeline.yaml` | YAML | `int \| null` | all | YAML default: `null` | public | worker | — | `tasks/edit.py` | — |

### 3.3 Newsletter Config

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `newsletter.max_articles` | `pipeline.yaml` | YAML | `int` (1–50) | all | YAML default: `10` | public | worker | Pydantic | `tasks/newsletter.py` | — |
| `newsletter.send_time` | `pipeline.yaml` | YAML | `str` (HH:MM) | all | YAML default: `"08:00"` | public | worker | — | `tasks/newsletter.py` | — |
| `newsletter.timezone` | `pipeline.yaml` | YAML | `str` (IANA TZ) | all | YAML default: `"America/New_York"` | public | worker | — | `tasks/newsletter.py` | — |
| `newsletter.site_url` | `pipeline.yaml` | YAML | `str` (URL) | all | YAML default: `"https://ainews.dev"` | public | worker | — | `tasks/newsletter.py`, newsletter templates | — |
| `newsletter.prep_minutes` | `pipeline.yaml` | YAML | `int` (5–60) | all | YAML default: `15` | public | worker | Pydantic | `tasks/newsletter.py` | — |

### 3.4 Newsletter Pipeline Roles (`newsletter_pipeline.reader`, `.writer`, `.editor`)

Each is a `RoleConfig` with the same fields as §3.1. Defaults:

| Key | Default Provider | Default Model | Default max_tokens | Default temperature | Default concurrency |
|-----|------------------|---------------|--------------------|--------------------|---------------------|
| `newsletter_pipeline.reader` | `ollama-local` | `qwen3:8b` | `4096` | `0.0` | `2` |
| `newsletter_pipeline.writer` | `ollama-local` | `qwen3:8b` | `2048` | `0.4` | `1` |
| `newsletter_pipeline.editor` | `ollama-local` | `qwen3:8b` | `2048` | `0.0` | `1` |

### 3.5 Subagent Config

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `subagent.default` | `pipeline.yaml` | YAML | `SubagentStageConfig` | all | YAML default (disabled) | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.research` | `pipeline.yaml` | YAML | `SubagentStageConfig` | all | YAML default (enabled) | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.edit` | `pipeline.yaml` | YAML | `SubagentStageConfig` | all | YAML default (enabled) | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains` | `pipeline.yaml` | YAML | `dict[str, SubagentChainConfig]` | all | YAML default: `{}` | public | worker | — | `services/subagent/runner.py` | — |

#### SubagentStageConfig Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `subagent.{stage}.enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: `false` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.{stage}.provider` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` (inherits from role) | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.{stage}.model` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` (inherits from role) | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.{stage}.max_tokens` | `pipeline.yaml` | YAML | `int` (256–128000) | all | YAML default: `4096` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.{stage}.temperature` | `pipeline.yaml` | YAML | `float` (0.0–2.0) | all | YAML default: `0.0` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.{stage}.timeout_seconds` | `pipeline.yaml` | YAML | `int` (10–600) | all | YAML default: `120` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.{stage}.system_prompt` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.{stage}.max_retries` | `pipeline.yaml` | YAML | `int` (0–5) | all | YAML default: `1` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.{stage}.retry_delay` | `pipeline.yaml` | YAML | `float` (0.0–60.0) | all | YAML default: `5.0` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.{stage}.task_template` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | `services/subagent/runner.py` (prompt file path) | — |
| `subagent.{stage}.tools` | `pipeline.yaml` | YAML | `list[str]` | all | YAML default: `[]` | public | worker | — | `services/subagent/tools.py` | — |
| `subagent.{stage}.max_iterations` | `pipeline.yaml` | YAML | `int` (1–20) | all | YAML default: `5` | public | worker | Pydantic | `services/subagent/runner.py` | — |

#### SubagentChainConfig Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `subagent.chains.{name}.enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: `false` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.max_length` | `pipeline.yaml` | YAML | `int` (1–10) | all | YAML default: `5` | public | worker | Pydantic | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.steps` | `pipeline.yaml` | YAML | `list[SubagentChainStep]` | all | YAML default: `[]` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.steps[].task_type` | `pipeline.yaml` | YAML | `str` | all | YAML required | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.steps[].prompt_data_template` | `pipeline.yaml` | YAML | `str` | all | YAML default: `""` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.steps[].response_model` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | `services/subagent/runner.py` | — |
| `subagent.chains.{name}.steps[].condition` | `pipeline.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | worker | — | `services/subagent/runner.py` | — |

### 3.6 Memory Config

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `memory.ttl_days_low` | `pipeline.yaml` | YAML | `int` | all | YAML default: `7` | public | worker | — | `services/trend_memory.py` | — |
| `memory.ttl_days_medium` | `pipeline.yaml` | YAML | `int` | all | YAML default: `30` | public | worker | — | `services/trend_memory.py` | — |
| `memory.ttl_days_high` | `pipeline.yaml` | YAML | `int` | all | YAML default: `0` (infinite) | public | worker | — | `services/trend_memory.py` | — |
| `memory.consolidation_cooldown_hours` | `pipeline.yaml` | YAML | `int` | all | YAML default: `24` | public | worker | — | `tasks/cleanup.py` | — |
| `memory.max_entries_per_propose` | `pipeline.yaml` | YAML | `int` | all | YAML default: `3` | public | worker | — | `services/trend_memory.py` | — |
| `memory.consolidation_merge_window_hours` | `pipeline.yaml` | YAML | `int` | all | YAML default: `72` | public | worker | — | `tasks/cleanup.py` | — |
| `memory.truncation_llm_enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: `true` | public | worker | — | `services/trend_memory.py` | — |
| `memory.truncation_llm_threshold` | `pipeline.yaml` | YAML | `int` | all | YAML default: `2000` | public | worker | — | `services/trend_memory.py` | — |
| `memory.truncation_llm_max_tokens` | `pipeline.yaml` | YAML | `int` | all | YAML default: `512` | public | worker | — | `services/trend_memory.py` | — |
| `memory.truncation_llm_temperature` | `pipeline.yaml` | YAML | `float` | all | YAML default: `0.0` | public | worker | — | `services/trend_memory.py` | — |

### 3.7 Experiments Config

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `experiments.enabled` | `pipeline.yaml` | YAML | `bool` | all | YAML default: (from dict) | public | worker | — | `services/experiments.py` | — |
| `experiments.assignment_salt` | `pipeline.yaml` | YAML | `str` (`${EXPERIMENT_SALT}`) | all | env var via `${}` | secret | worker | — | `services/experiments.py` | — |
| `experiments.prompt_variants` | `pipeline.yaml` | YAML | `dict[str, dict[str, str]]` | all | YAML default: `{}` | public | worker | — | `services/experiments.py`, LLM prompt selection | — |
| `experiments.prompt_variants.{role}.{variant}` | `pipeline.yaml` | YAML | `str` (prompt text) | all | YAML | public | worker | — | `services/experiments.py` | — |

### 3.8 Stages Config (Tool Registry)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `stages.{stage}.tools` | `pipeline.yaml` | YAML | `list[str]` | all | YAML default: `[]` | public | worker | — | `services/subagent/tools.py` | — |

### 3.9 Schedule Config (Celery Beat)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `schedule.crawl_interval_minutes` | `pipeline.yaml` | YAML | `int` | all | YAML default: `30` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.retry_stuck_interval_minutes` | `pipeline.yaml` | YAML | `int` | all | YAML default: `60` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_old_logs_hour` | `pipeline.yaml` | YAML | `int` (0–23) | all | YAML default: `3` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_old_versions_hour` | `pipeline.yaml` | YAML | `int` (0–23) | all | YAML default: `3` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_expired_verifications_interval_minutes` | `pipeline.yaml` | YAML | `int` | all | YAML default: `15` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.publish_scheduled_interval_minutes` | `pipeline.yaml` | YAML | `int` | all | YAML default: `5` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_stale_limiter_interval_minutes` | `pipeline.yaml` | YAML | `int` | all | YAML default: `5` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.generate_newsletters_hour` | `pipeline.yaml` | YAML | `int` (0–23) | all | YAML default: `8` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.consolidate_trend_memory_hour` | `pipeline.yaml` | YAML | `int` (0–23) | all | YAML default: `3` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_inactive_subscribers_hour` | `pipeline.yaml` | YAML | `int` (0–23) | all | YAML default: `1` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_inactive_subscribers_minute` | `pipeline.yaml` | YAML | `int` (0–59) | all | YAML default: `0` | public | scheduler | — | `config.py:get_beat_schedule` | — |
| `schedule.cleanup_old_versions_days_to_keep` | `pipeline.yaml` | YAML | `int` | all | YAML default: `90` | public | worker | — | `tasks/cleanup.py` | — |

---

## 4 — sources.yaml

### 4.1 Source Definition (`sources[]`)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `sources[].id` | `sources.yaml` | YAML: `sources[].id` | `str` (pattern: `^[a-z0-9_]+$`) | all | YAML required | public | — | Pydantic | `tasks/crawl.py`, `services/crawling.py` | — |
| `sources[].name` | `sources.yaml` | YAML: `sources[].name` | `str` (1–128 chars) | all | YAML required | public | — | Pydantic | UI display | — |
| `sources[].type` | `sources.yaml` | YAML: `sources[].type` | `str` (`rss`/`api`/`web`) | all | YAML required | public | — | Pydantic `validate_type` | `services/crawling.py` → adapter dispatch | — |
| `sources[].enabled` | `sources.yaml` | YAML: `sources[].enabled` | `bool` | all | YAML default: `true` | public | — | — | `tasks/crawl.py:run_all_sources` | — |
| `sources[].schedule_minutes` | `sources.yaml` | YAML: `sources[].schedule_minutes` | `int` (5–1440) | all | YAML default: `30` | public | — | Pydantic | `tasks/crawl.py` | — |
| `sources[].config` | `sources.yaml` | YAML: `sources[].config` | `dict` (type-specific schema) | all | YAML default: `{}` | varies | — | Pydantic `validate_adapter_config` | Adapter classes | — |
| `sources[].topics` | `sources.yaml` | YAML: `sources[].topics` | `TopicMatchConfig` | all | YAML default | public | — | Pydantic | `services/crawling.py`, `tasks/select.py` | — |
| `sources[].topics.match_mode` | `sources.yaml` | YAML | `str` (`keyword`/`contextual`) | all | YAML default: `"keyword"` | public | — | Pydantic | `tasks/select.py` | — |
| `sources[].topics.include` | `sources.yaml` | YAML | `list[str]` | all | YAML default: `["other"]` | public | — | Pydantic | `tasks/select.py` | — |
| `sources[].topics.min_confidence` | `sources.yaml` | YAML | `float` (0.0–1.0) | all | YAML default: `0.5` | public | — | Pydantic | `tasks/select.py` | — |

### 4.2 RSS Source Config Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `sources[].config.feed_url` | `sources.yaml` | YAML | `str` (URL, required) | all | YAML required | public | — | Pydantic | `adapters/rss.py` | — |
| `sources[].config.max_items` | `sources.yaml` | YAML | `int` (1–200) | all | YAML default: `50` | public | — | Pydantic | `adapters/rss.py` | — |
| `sources[].config.request_timeout` | `sources.yaml` | YAML | `int` (5–60) | all | YAML default: `15` | public | — | Pydantic | `adapters/rss.py` | — |
| `sources[].config.user_agent` | `sources.yaml` | YAML | `str` | all | YAML default: `"AINewsBot/1.0"` | public | — | — | `adapters/rss.py` | — |
| `sources[].config.min_content_length` | `sources.yaml` | YAML | `int` (0–5000) | all | YAML default: `200` | public | — | Pydantic | `adapters/rss.py` | — |

### 4.3 API Source Config Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `sources[].config.list_url` | `sources.yaml` | YAML | `str` (URL, required) | all | YAML required | public | — | Pydantic | `adapters/api.py` | — |
| `sources[].config.list_method` | `sources.yaml` | YAML | `str` (`json_array`/`json_object_items`) | all | YAML default: `"json_array"` | public | — | Pydantic | `adapters/api.py` | — |
| `sources[].config.list_items_path` | `sources.yaml` | YAML | `str \| null` (JSONPath) | all | YAML default: `null` | public | — | — | `adapters/api.py` | — |
| `sources[].config.max_items` | `sources.yaml` | YAML | `int` (1–200) | all | YAML default: `30` | public | — | Pydantic | `adapters/api.py` | — |
| `sources[].config.item_url` | `sources.yaml` | YAML | `str \| null` (template with `{id}`) | all | YAML default: `null` | public | — | — | `adapters/api.py` | — |
| `sources[].config.item_method` | `sources.yaml` | YAML | `str` | all | YAML default: `"json_object"` | public | — | — | `adapters/api.py` | — |
| `sources[].config.fields` | `sources.yaml` | YAML | `dict[str, str]` | all | YAML default: `{}` | public | — | — | `adapters/api.py` | — |
| `sources[].config.filters` | `sources.yaml` | YAML | `list[dict]` | all | YAML default: `[]` | public | — | — | `adapters/api.py` | — |
| `sources[].config.metadata` | `sources.yaml` | YAML | `dict[str, str]` | all | YAML default: `{}` | public | — | — | `adapters/api.py` | — |
| `sources[].config.pagination` | `sources.yaml` | YAML | `PaginationConfig` | all | YAML default (disabled) | public | — | Pydantic | `adapters/api.py` | — |
| `sources[].config.pagination.enabled` | `sources.yaml` | YAML | `bool` | all | YAML default: `false` | public | — | — | `adapters/api.py` | — |
| `sources[].config.pagination.type` | `sources.yaml` | YAML | `str` (`next_link`/`query_param`/`none`) | all | YAML default: `"next_link"` | public | — | Pydantic | `adapters/api.py` | — |
| `sources[].config.pagination.next_link_selector` | `sources.yaml` | YAML | `str \| null` (JSONPath) | all | YAML default: `null` | public | — | — | `adapters/api.py` | — |
| `sources[].config.pagination.max_pages` | `sources.yaml` | YAML | `int` | all | YAML default: `3` | public | — | — | `adapters/api.py` | — |
| `sources[].config.request_timeout` | `sources.yaml` | YAML | `int` | all | YAML default: `15` | public | — | — | `adapters/api.py` | — |
| `sources[].config.user_agent` | `sources.yaml` | YAML | `str` | all | YAML default: `"AINewsBot/1.0"` | public | — | — | `adapters/api.py` | — |
| `sources[].config.api_key` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | sensitive | — | — | `adapters/api.py` | — |
| `sources[].config.auth_header` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/api.py` | — |

### 4.4 Web Source Config Fields

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `sources[].config.base_url` | `sources.yaml` | YAML | `str` (URL, required) | all | YAML required | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.listing_url` | `sources.yaml` | YAML | `str` (URL, required) | all | YAML required | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.listing` | `sources.yaml` | YAML | `ListingConfig` | all | YAML required | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.listing.card_selector` | `sources.yaml` | YAML | `str` (CSS selector, required) | all | YAML required | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.listing.link_selector` | `sources.yaml` | YAML | `str` (CSS selector, required) | all | YAML required | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.listing.link_attribute` | `sources.yaml` | YAML | `str` | all | YAML default: `"href"` | public | — | — | `adapters/web.py` | — |
| `sources[].config.listing.pagination` | `sources.yaml` | YAML | `PaginationConfig` | all | YAML default (disabled) | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.article` | `sources.yaml` | YAML | `ArticleSelectors` | all | YAML default (all null) | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.article.title_selector` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/web.py` | — |
| `sources[].config.article.author_selector` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/web.py` | — |
| `sources[].config.article.date_selector` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/web.py` | — |
| `sources[].config.article.date_attribute` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/web.py` | — |
| `sources[].config.article.body_selector` | `sources.yaml` | YAML | `str \| null` | all | YAML default: `null` | public | — | — | `adapters/web.py` | — |
| `sources[].config.max_items` | `sources.yaml` | YAML | `int` (1–200) | all | YAML default: `50` | public | — | Pydantic | `adapters/web.py` | — |
| `sources[].config.request_delay_min` | `sources.yaml` | YAML | `float` | all | YAML default: `1.5` | public | — | — | `adapters/web.py` | — |
| `sources[].config.request_delay_max` | `sources.yaml` | YAML | `float` | all | YAML default: `4.0` | public | — | — | `adapters/web.py` | — |
| `sources[].config.max_retries` | `sources.yaml` | YAML | `int` | all | YAML default: `3` | public | — | — | `adapters/web.py` | — |
| `sources[].config.user_agent` | `sources.yaml` | YAML | `str` | all | YAML default: `"AINewsBot/1.0"` | public | — | — | `adapters/web.py` | — |

---

## 5 — topics.yaml

### 5.1 Topic Definition (`topics`)

| Key | Destination | Env / Path | Type | Profiles | Default Source | Secret | Restart | Validators | Consumers | Deprecated |
|-----|-------------|------------|------|----------|----------------|--------|---------|------------|-----------|------------|
| `topics.{key}` | `topics.yaml` | YAML: `topics.{key}` | `TopicDef` | all | YAML | public | web | Pydantic | `schemas/topic.py`, templates, `tasks/select.py` | — |
| `topics.{key}.display_name` | `topics.yaml` | YAML | `str` | all | YAML required | public | — | Pydantic | UI display | — |
| `topics.{key}.description` | `topics.yaml` | YAML | `str` | all | YAML required | public | — | Pydantic | LLM prompts (topic context) | — |
| `topics.{key}.color` | `topics.yaml` | YAML | `str` (color name) | all | YAML default: `"blue"` | public | — | Pydantic | Templates, CSS variables | — |
| `topics.{key}.icon` | `topics.yaml` | YAML | `str \| null` (SVG path) | all | YAML default: `null` | public | — | — | Templates | — |

---

## 6 — Derived / Computed Values

These values are not directly configured but derived from other settings at runtime.

| Key | Derivation | Source Keys | Consumers |
|-----|-----------|-------------|-----------|
| `derived.database_path` | Extracted from `SQLALCHEMY_DATABASE_URI` (strips `sqlite:///`) | `sqlalchemy_database_uri` | `scripts/`, backup scripts |
| `derived.redis_broker_db` | Extracted from `CELERY_BROKER_URL` path (default: `0`) | `celery_broker_url` | `extensions.py` |
| `derived.redis_result_db` | Extracted from `CELERY_RESULT_BACKEND` path (default: `1`) | `celery_result_backend` | Celery app |
| `derived.redis_limiter_db` | Broker URL path replaced with `/15` | `celery_broker_url` | `extensions.py:_get_limiter_storage_uri` |
| `derived.redis_config_cache_db` | Hardcoded `1` | — | `services/config_cache.py` |
| `derived.beat_schedule` | Built from `schedule.*` keys in `pipeline.yaml` | `schedule.*` | Celery beat |
| `derived.safe_fetch_limits` | `SafeFetchLimits(max_redirects, max_bytes, connect_timeout, read_timeout, total_timeout)` | `safe_fetch_*` | `services/safe_fetch.py` |
| `derived.subagent_provider_override` | `subagent.{stage}.provider` falls back to `pipeline.{role}.provider` | `subagent.*`, `pipeline.*` | `services/subagent/runner.py` |
| `derived.subagent_model_override` | `subagent.{stage}.model` falls back to `pipeline.{role}.model` | `subagent.*`, `pipeline.*` | `services/subagent/runner.py` |
| `derived.search_provider_chain` | `search_providers` filtered by `enabled=true`, first is default | `search_providers`, `default_search_provider` | `services/search/__init__.py` |
| `derived.llm_provider_chain` | `providers` filtered by `enabled=true`, ordered by YAML position | `providers`, `default_provider` | `services/llm/__init__.py:get_provider_chain` |
| `derived.experiment_salt` | Resolved from `${EXPERIMENT_SALT}` env var | `experiments.assignment_salt` | `services/experiments.py` |

---

## 7 — Cross-File References

Configuration values frequently reference IDs defined in other files. These cross-references must remain consistent.

| Source Key | References | Target File | Target Key | Validation |
|------------|-----------|-------------|------------|------------|
| `pipeline.{role}.provider` | Provider ID | `providers.yaml` | `providers[].id` | `ProductionConfig._validate_llm_providers` (production) |
| `pipeline.researcher.web_search_provider` | Search provider ID | `providers.yaml` | `search_providers[].id` | Runtime fallback to `default_search_provider` |
| `subagent.{stage}.provider` | Provider ID (or null → inherits role) | `providers.yaml` | `providers[].id` | `resolve_subagent_config` |
| `subagent.{stage}.tools` | Tool names | `services/subagent/tools.py` | Registry keys | `services/subagent/tools.py:register_tools` |
| `subagent.chains.{step}.task_type` | Role name | `pipeline.*` | Role config | `services/subagent/runner.py` |
| `subagent.chains.{step}.response_model` | Pydantic model name | `services/subagent/` | Response model class | `services/subagent/runner.py` |
| `sources[].topics.include` | Topic keys | `topics.yaml` | `topics.{key}` | `tasks/select.py` (runtime) |
| `sources[].type` | Adapter type | `adapters/` | Adapter class | `schemas/source.py:validate_type` |
| `experiments.prompt_variants` | Role names | `pipeline.*` | Role config | `services/experiments.py` |
| `stages.{stage}.tools` | Tool names | `services/subagent/tools.py` | Registry keys | `services/subagent/tools.py` |
| `themes_default_dark` / `themes_default_light` | Theme ID | `resources/themes/` | Registry ID | `services/themes/loader.py` (fallback to emergency) |
| `newsletter.site_url` | URL | — | — | Used in templates and RSS feeds |
| `schedule.*` | Hour values (0–23) | — | — | `config.py:get_beat_schedule` (crontab) |

---

## 8 — Configuration Precedence

Values are resolved in the following order (highest priority first):

1. **Environment variable** (set in shell or `.env` file)
2. **`.env` file** (loaded by `python-dotenv` at `config.py` import time)
3. **YAML file default** (value specified in `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`)
4. **Code default** (hardcoded in `config.py` Config class, Pydantic `Field(default=...)`, or `constants.py`)

**YAML env var interpolation**: YAML files support `${ENV_VAR}` syntax resolved by `schemas/common.py:resolve_env_var()` at load time. Unresolved vars log a warning and resolve to `""`.

**Config caching**: YAML configs are cached via `services/config_cache.py` with Redis L2 + in-memory L1 and mtime-based invalidation. Changing a YAML file requires either waiting for TTL (300s default) or the cache detecting the mtime change.

**Flask config propagation**: All env vars in `config.py` are set as Flask `current_app.config` keys. Services can access them via `current_app.config["KEY"]` or via `services/config_utils.py:get_config_with_default()`.

---

## 9 — Restart Impact Legend

| Value | Meaning |
|-------|---------|
| `web` | Requires restarting the web server (Flask/Granian process) |
| `worker` | Requires restarting Celery worker processes |
| `scheduler` | Requires restarting Celery beat scheduler |
| `all` | Requires restarting all processes (web + worker + scheduler) |
| `none` | No restart needed; value is read at runtime per-request/task |

**Notes**:
- YAML file changes (`pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`) are picked up automatically via mtime-based cache invalidation for most values. The `schedule.*` keys in `pipeline.yaml` require a scheduler restart because Celery beat caches the schedule at startup.
- Environment variable changes always require a full process restart because they are read once at import time.
- Theme configuration changes (`THEMES_*`) require a web restart because the theme registry is built once at startup.

---

## 10 — Process Distribution Summary

| Process | Reads |
|---------|-------|
| **Web (Flask/Granian)** | `SECRET_KEY`, `ADMIN_PASSWORD`, `SESSION_*`, `SMTP_*`, `THEMES_*`, `DNS_CACHE_*`, `L1_CACHE_MAXSIZE`, `LOGIN_*`, `MIN_CONTENT_LENGTH`, `VERIFICATION_EXPIRY_SECONDS`, `DB_QUERY_LOG_LEVEL`, `OTEL_*`, `SAFE_FETCH_*`, all YAML configs (via cache) |
| **Worker (Celery)** | `CELERY_*`, `MAX_STAGE_RETRIES`, `MAX_TOTAL_RETRIES`, `PIPELINE_TIMEOUT_SECONDS`, `MAX_CONSECUTIVE_FAILURES`, `STUCK_THRESHOLD_MINUTES`, `RETRY_SOFT_CUTOFF_MINUTES`, `MIN_CONTENT_LENGTH`, `SAFE_FETCH_*`, all YAML configs (via cache) |
| **Scheduler (Celery Beat)** | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `pipeline.yaml:schedule.*` |
