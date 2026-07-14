# Configuration Reference

All configuration is managed through YAML files in the project root and environment variables in `.env`.

## Environment Variables (`.env`)

### Required

Production startup fails without these.

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session signing key (64-char hex) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | Admin dashboard password (hashed) | `scrypt:32768:8:1$salt$hash...` |
| `CELERY_TASK_SECRET` | HMAC signing secret for Celery tasks (>=32 chars) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CELERY_BROKER_URL` | Redis URL for Celery | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis URL for Celery results | `redis://localhost:6379/1` |
| `DATABASE_URL` | SQLite database URL | `sqlite:///instance/ainews.db` |
| `FLASK_CONFIG` | Set to `production` for production deployments | `production` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `localhost` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | | SMTP username |
| `SMTP_PASSWORD` | | SMTP password |
| `SMTP_FROM` | `noreply@ainews.dev` | Sender email address |
| `SMTP_USE_TLS` | `true` | Enable TLS for SMTP |
| `OLLAMA_MODEL` | `llama3.1` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API URL |
| `OPENAI_API_KEY` | | OpenAI API key |
| `ANTHROPIC_API_KEY` | | Anthropic API key |
| `SAFE_FETCH_MAX_REDIRECTS` | `5` | Maximum redirect hops for safe fetch client |
| `SAFE_FETCH_MAX_BYTES` | `2000000` | Maximum response body size (bytes) |
| `SAFE_FETCH_CONNECT_TIMEOUT` | `5` | TCP connection timeout (seconds) |
| `SAFE_FETCH_READ_TIMEOUT` | `10` | Read timeout (seconds) |
| `SAFE_FETCH_TOTAL_TIMEOUT` | `20` | Total timeout (seconds) |

### Generate a hashed admin password

```bash
# Interactive (recommended)
python scripts/hash_password.py

# As argument (may appear in shell history)
python scripts/hash_password.py mypassword
```

## Safe Fetch Configuration

All outbound HTTP requests go through the safe fetch client (`services/safe_fetch.py`). The following environment variables control its behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `SAFE_FETCH_MAX_REDIRECTS` | `5` | Maximum redirect hops before aborting |
| `SAFE_FETCH_MAX_BYTES` | `2000000` | Maximum response body size (bytes) |
| `SAFE_FETCH_CONNECT_TIMEOUT` | `5` | TCP connect timeout (seconds) |
| `SAFE_FETCH_READ_TIMEOUT` | `10` | Read timeout per chunk (seconds) |
| `SAFE_FETCH_TOTAL_TIMEOUT` | `20` | Total timeout including all redirects (seconds) |

**Production notes:**

- These values are read at process start and cached. Changing them requires a service restart.
- Malformed environment variables (e.g., non-numeric strings) produce safe defaults via `_safe_int_env()` / `_safe_float_env()` helpers instead of raising `ValueError` at construction time. The default values are logged for visibility.
- The byte limit prevents memory exhaustion when fetching untrusted content. Increase only if you have verified the source returns large but legitimate responses (e.g., full article HTML).
- The total timeout is a hard ceiling enforced before each redirect follow and each chunk read in the streaming loop. If `SAFE_FETCH_TOTAL_TIMEOUT` is less than `SAFE_FETCH_CONNECT_TIMEOUT + SAFE_FETCH_READ_TIMEOUT`, the connect timeout takes precedence.

## Theme Subsystem Configuration

The theme registry is built once at startup. The following environment variables
control its behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `THEMES_ENABLED` | `true` | Set `false` to disable the theme system; only the code-defined emergency theme remains. |
| `THEMES_CUSTOM_DIR` | empty | Directory of operator-provided Halloy-compatible `.toml` files. Empty disables external discovery. |
| `THEMES_ALLOW_CUSTOM` | `true` | When `false`, the custom directory is ignored even if configured. |
| `THEMES_DEFAULT` | empty | Fallback ID used before per-appearance defaults resolve. |
| `THEMES_DEFAULT_DARK` | `catppuccin-mocha` | Default theme for dark-mode requests. |
| `THEMES_DEFAULT_LIGHT` | `catppuccin-latte` | Default theme for light-mode requests. |
| `THEMES_MAX_FILE_BYTES` | `262144` | Per-file byte limit for external themes. Validated `1024..1048576`. |
| `THEMES_STRICT_CONTRAST` | `false` | When `true`, treats non-fatal contrast warnings as errors during theme validation. |

**Production notes:**

- All values are read at process start; changes require a service restart.
- `THEMES_MAX_FILE_BYTES` outside the validated range blocks production startup (`_validate_themes()` in `config.py`).
- An invalid theme ID does not block startup; the registry falls back through `THEMES_DEFAULT` → `THEMES_DEFAULT_DARK` → `THEMES_DEFAULT_LIGHT` → the emergency theme (`__emergency__`).
- Setting `THEMES_CUSTOM_DIR` with `THEMES_ALLOW_CUSTOM=false` emits a warning at startup; the directory is otherwise ignored.
- See [`docs/halloy-theme-contract.md` §12](halloy-theme-contract.md) for the full contract (manifest format, external directory discovery rules, registry model, and restart semantics).

## Configuration Files

### `pipeline.yaml` — Processing Pipeline

Controls the AI processing stages: selector, researcher, writer, editor.

```yaml
pipeline:
  selector:
    enabled: true
    provider: ollama-local        # Provider ID from providers.yaml
    model: qwen3:8b
    max_tokens: 1024
    temperature: 0.2
    concurrency: 4
    timeout_seconds: 60
    min_score: 6                   # Minimum score (1-10) to select an article
    system_prompt: |               # Custom system prompt (optional)
      You are a news editor...

  researcher:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 8192
    temperature: 0.0
    concurrency: 2
    timeout_seconds: 180
    web_search: true
    web_search_max_results: 5
    db_related_max: 5
    max_article_text_length: 6000

  writer:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 4096
    temperature: 0.3
    concurrency: 1
    timeout_seconds: 180
    max_key_points: 5

  editor:
    enabled: true
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 4096
    temperature: 0.0
    concurrency: 2
    timeout_seconds: 120
    max_tags: 3

newsletter:
  max_articles: 10
  send_time: "08:00"
  timezone: "America/New_York"
  site_url: "https://ainews.dev"

newsletter_pipeline:
  reader: { ... }   # Same structure as pipeline roles
  writer: { ... }
  editor: { ... }
```

**Role parameters:**

| Parameter | Description |
|-----------|-------------|
| `enabled` | Set `false` to skip this stage entirely |
| `provider` | Provider ID from `providers.yaml` |
| `model` | Model name to use |
| `max_tokens` | Max output tokens |
| `temperature` | Sampling temperature (0.0 = deterministic) |
| `concurrency` | Max parallel requests |
| `timeout_seconds` | Request timeout |
| `system_prompt` | Custom system prompt (uses built-in default if omitted) |

### `sources.yaml` — RSS/API Sources

```yaml
sources:
  - id: hackernews
    name: "Hacker News"
    type: api                          # rss, api, or web
    enabled: true
    schedule_minutes: 30
    config:
      list_url: "https://hacker-news.firebaseio.com/v0/topstories.json"
      list_method: "json_array"
      max_items: 30
      item_url: "https://hacker-news.firebaseio.com/v0/item/{id}.json"
      item_method: "json_object"
      fields:
        external_id: "$.id"
        title: "$.title"
        url: "$.url"
        author: "$.by"
        published_at: "$.time"
        published_at_format: "unix"
        text_content: "$.text"
        raw_score: "$.score"
      filters:
        - field: "$.type"
          equals: "story"
        - field: "$.score"
          min: 20
    topics:
      match_mode: keyword              # keyword or contextual
      include: [ai, privacy, security, programming, hardware]

  - id: techcrunch
    name: "TechCrunch"
    type: rss
    enabled: true
    schedule_minutes: 60
    config:
      feed_url: "https://techcrunch.com/feed/"
      max_items: 50
    topics:
      match_mode: contextual
      include: [ai, security, programming]
```

**Source types:**

| Type | Description |
|------|-------------|
| `rss` | RSS/Atom feed. Requires `feed_url` in config. |
| `api` | JSON API. Requires `list_url`, `item_url`, `fields`. |
| `web` | Web scraping. Requires `base_url`, `listing_url`, CSS selectors. |

### `topics.yaml` — Topic Categories

```yaml
topics:
  ai:
    display_name: "AI & Machine Learning"
    description: "Large language models, neural networks, AI safety..."
    color: purple
    icon: "svg/ai.svg"

  privacy:
    display_name: "Privacy"
    description: "Data protection, surveillance, encryption, GDPR..."
    color: orange
    icon: "svg/privacy.svg"

  security:
    display_name: "Security"
    description: "Vulnerabilities, CVEs, exploits, malware..."
    color: red
    icon: "svg/security.svg"

  programming:
    display_name: "Programming"
    description: "Languages, compilers, open source, developer tools..."
    color: green

  hardware:
    display_name: "Hardware"
    description: "GPUs, chips, semiconductors, processors..."
    color: blue
```

### `providers.yaml` — LLM Providers

```yaml
# Bare-metal Ollama (app runs on same host as Ollama):
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: "http://localhost:11434"
      model: "qwen3:8b"

  - id: openai
    type: openai
    enabled: false
    config:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"

  - id: anthropic
    type: anthropic
    enabled: false
    config:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-sonnet-4-5-20250929"

  - id: minimax
    type: openai
    enabled: false
    config:
      api_key: "${MINIMAX_API_KEY}"
      base_url: "https://api.minimax.io/v1"
      model: "MiniMax-M2.5"

  - id: deepseek
    type: openai
    enabled: false
    config:
      api_key: "${DEEPSEEK_API_KEY}"
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"

default_provider: ollama-local
```

**Provider types:**

| Type | Config keys |
|------|-------------|
| `ollama` | `host`, `model`, `max_tokens` |
| `openai` | `api_key`, `base_url`, `model`, `max_tokens` |
| `anthropic` | `api_key`, `model`, `max_tokens` |
| `gemini` | `api_key`, `model`, `max_tokens` |

Any `openai`-type provider is handled by the OpenAI-compatible adapter and works with MiniMax, DeepSeek, Zai (BigModel.cn), Groq, TogetherAI, and similar providers.

**Docker Ollama host values:**

| Deployment | Ollama `host` value |
|------------|---------------------|
| Bare metal | `http://localhost:11434` |
| Docker Compose Ollama service | `http://ollama:11434` |
| Host Ollama from container | `http://host.docker.internal:11434` |

> **Warning:** `localhost` inside a Docker container refers to the container itself, not the host. Using `http://localhost:11434` from Docker containers will silently fail at LLM call time. See [Deployment Guide](deployment.md#docker-with-ollama).

**Production validation:** In production (`FLASK_CONFIG=production`), provider config is validated at startup:
- At least one provider must be enabled
- `default_provider` must point to an existing, enabled provider with valid configuration
- Enabled cloud providers (`openai`, `anthropic`, `gemini`) must have valid `api_key` (non-empty, resolved from env vars)
- Unknown provider types are rejected (must be `ollama`, `openai`, `anthropic`, or `gemini`)
- Disabled providers with placeholder keys are silently skipped
- Validation errors raise `RuntimeError` and prevent startup (fail-closed)

### `subagent:` — Subagent Configuration

Subagents are lightweight AI tasks that run within pipeline stages. Configuration lives under `subagent:` in `pipeline.yaml`:

```yaml
subagent:
  default:
    enabled: false
    provider: ollama-local
    model: qwen3:8b
    max_tokens: 2048
    temperature: 0.0
    timeout_seconds: 120
    max_retries: 1
    retry_delay: 5.0
  research:
    enabled: true
    tools:
      - web_search
      - context_notes
      - related_articles
  edit:
    enabled: true
    tools:
      - context_notes
      - related_articles
      - trend_memory
```

The `tools:` list controls which subagent tools are available for each stage. Available tools: `web_search`, `context_notes`, `related_articles`, `trend_memory`.

### `memory:` — Trend Memory Configuration

Tiered, LLM-judged memory for the editor. After each article is finalized, the LLM extracts 0–3 high-signal memory entries. The system is configurable:

```yaml
memory:
  ttl_days_low: 7              # Low-importance entries expire after 7 days
  ttl_days_medium: 30           # Medium-importance entries expire after 30 days
  ttl_days_high: 0              # High-importance entries never expire
  consolidation_cooldown_hours: 24      # Don't re-consolidate a topic within 24h
  max_entries_per_propose: 3     # LLM extracts max 3 entries per article
  consolidation_merge_window_hours: 72  # Low entries within 72h of a high entry get promoted
```

**Importance tiers:**
- `1` (low): Short-lived observations, expires in 7 days unless consolidated
- `2` (medium): Valid observations promoted by consolidation, expires in 30 days
- `3` (high): Major developments, no expiry — triggers consolidation of overlapping low entries

**How it works:**
1. After an article is finalized (`DONE`), `propose_trend_memory()` asks the LLM to extract 0–3 entries and stores them with tier-based TTL
2. The `edit_contextualization` subagent receives `{trend_memory}` in its prompt, letting the editor see prior patterns
3. Nightly at 3:30 AM, `consolidate_trend_memory` promotes low-importance entries to medium when a high-importance entry exists for the same topic, and purges expired entries

## Pipeline Stages

Articles flow through these stages:

```
crawl → extract → select → research → write → edit → done
```

| Stage | Description | Skippable |
|-------|-------------|-----------|
| `crawl` | Fetch RSS/API items from sources | No |
| `extract` | Extract full text from article URLs | No |
| `select` | LLM evaluates newsworthiness (score 1-10) | Yes — set `enabled: false` |
| `research` | LLM compiles research brief with external sources | Yes |
| `write` | LLM drafts condensed article | Yes |
| `edit` | LLM reviews and polishes draft, assigns tags | Yes |

If a stage is skipped, the article advances to the next stage with default content. If a stage fails after retries, it degrades gracefully and continues.

## Celery Beat Schedule

Scheduled tasks run via Celery Beat:

```python
Config.get_beat_schedule()  # reads from pipeline.yaml schedule: section
```

| Task | Default Schedule | Purpose |
|------|-----------------|---------|
| `run-all-sources` | Every 30 min | Crawl all active RSS/API sources |
| `retry-stuck-articles` | Every 60 min | Retry articles stuck in pipeline |
| `generate-newsletters` | Daily 8:00 AM | Generate and send newsletters |
| `cleanup-old-logs` | Daily 3:00 AM | Purge old pipeline logs |
| `cleanup-expired-verifications` | Every 15 min | Clean expired subscriber tokens |
| `cleanup-stale-limiter-slots` | Every 5 min | Release stale rate limiter slots |
| `consolidate-trend-memory` | Daily 3:30 AM | Promote low-importance memory |
| `cleanup-old-article-versions` | Daily 3:45 AM | Purge old article versions |
| `publish-scheduled-articles` | Every 5 min | Publish time-scheduled articles |
| `backfill-embeddings` | Daily 2:00 AM | Backfill missing article embeddings |
| `retry-failed-newsletter-deliveries` | Every 2 hours | Retry permanently failed newsletter emails |
| `recalculate-impact-scores` | Daily 4:00 AM | Recalculate article impact scores |
| `cleanup-inactive-subscribers` | Daily 1:00 AM | Remove inactive subscribers |

### Reloading Schedule

After modifying `pipeline.yaml`, call:

```python
from config import Config
from celery_app import celery_app
Config.reload_beat_schedule(celery_app)
```

Or via the admin API:

```bash
curl -X POST http://localhost:5000/admin/api/config/reload \
  -H "X-CSRFToken: ..."
```

All schedules are configurable via the `schedule:` section in `pipeline.yaml`.

### Schedule Configuration

```yaml
schedule:
  crawl_interval_minutes: 30
  retry_stuck_interval_minutes: 60
  generate_newsletters_hour: 8
  cleanup_old_logs_hour: 3
  cleanup_old_versions_hour: 3
  cleanup_old_versions_days_to_keep: 90
  cleanup_expired_verifications_interval_minutes: 15
  publish_scheduled_interval_minutes: 5
  cleanup_stale_limiter_interval_minutes: 5
  consolidate_trend_memory_hour: 3
  cleanup_old_versions_minute: 45
  backfill_embeddings_hour: 2
  retry_failed_newsletter_interval_hours: 2
  recalculate_impact_scores_hour: 4
  cleanup_inactive_subscribers_hour: 1
```
