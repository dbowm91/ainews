# Provider Management CLI

The `ainews providers-*` commands manage LLM provider configuration — adding, testing, discovering models, assigning roles, and removing providers.

## Architecture

Provider management uses an adapter-based architecture:

```
ainews_cli/providers/
  protocol.py    # ProviderSetupAdapter Protocol, dataclasses
  base.py        # BaseAdapter with common logic
  registry.py    # ADAPTERS dict, get_adapter(), list_adapters()
  commands.py    # CLI command implementations
  ollama.py      # Ollama adapter
  openai.py      # OpenAI adapter
  anthropic.py   # Anthropic adapter
  gemini.py      # Google Gemini adapter
  eggpool.py     # EggPool adapter
  generic.py     # Generic OpenAI-compatible adapter
```

### ProviderSetupAdapter Protocol

Each adapter implements:

```python
class ProviderSetupAdapter(Protocol):
    type_id: str
    display_name: str

    def fields(self) -> list[ProviderInputField]: ...
    def normalize_endpoint(self, context: dict) -> ProviderEndpoint: ...
    def build_definition(self, values: dict) -> ProviderDefinition: ...
    def probe(self, definition, credentials) -> ProviderProbeResult: ...
    def discover_models(self, definition, credentials) -> ModelDiscoveryResult: ...
    def remediation(self, error: Exception) -> list[str]: ...
```

### Dataclasses

- `ProviderInputField`: Interactive form field (name, type, default, sensitive flag)
- `ProviderEndpoint`: Resolved base URL and API type
- `ProviderDefinition`: Complete provider config (id, type, endpoint, config dict)
- `ProviderProbeResult`: Connectivity test result (success, latency, error, remediation hints)
- `ModelInfo`: Discovered model metadata (id, display name, context window, tool support)
- `ModelDiscoveryResult`: Model list with provenance (discovered/catalog/configured)

## Adding Providers

### Interactive

```bash
ainews providers-add
```

Without `--type`, lists available adapter types:

```
Available provider types:
  ollama: Ollama (local inference)
  openai: OpenAI
  anthropic: Anthropic
  gemini: Google Gemini
  eggpool: EggPool
  generic: Generic OpenAI-compatible
```

With `--type`, collects fields interactively:

```bash
ainews providers-add --type openai
```

Fields vary by adapter. For OpenAI:
- API key (password field, hidden input)
- Base URL (default: `https://api.openai.com/v1`)
- Default model (default: `auto`)

After field collection, a connectivity probe runs automatically:

```
Probing provider...
Probe succeeded (245ms)
Provider 'openai-prod' added.
```

Use `--skip-probe` to suppress the probe.

### Declarative (providers.yaml)

Providers can be added directly to `providers.yaml`:

```yaml
default_provider: ollama-local

providers:
  ollama-local:
    type: ollama
    enabled: true
    config:
      base_url: http://localhost:11434/v1
      default_model: auto

  openai-prod:
    type: openai
    enabled: true
    config:
      base_url: https://api.openai.com/v1
      default_model: gpt-4o
```

Then validate with `ainews config check`.

## Provider Testing

### Test All Providers

```bash
ainews providers-test
```

Tests all configured providers. Output:

```
  ollama-local: ok (12ms)
  openai-prod: ok (312ms)
  anthropic-staging: Connection refused (Hint: Check API key)
```

### Test Single Provider

```bash
ainews providers-test openai-prod
```

### JSON Output

```bash
ainews providers-test --json
```

```json
{
  "results": [
    {
      "id": "openai-prod",
      "type": "openai",
      "success": true,
      "latency_ms": 312.5,
      "endpoint_resolved": true,
      "auth_success": true
    }
  ]
}
```

### Probe Behavior

The probe checks:
1. **Endpoint resolution**: DNS lookup or direct connection
2. **Authentication**: Validates credentials against the provider API
3. **Latency**: Measures round-trip time

Probe failures produce remediation hints:
- "Check API key" — authentication failed
- "Verify endpoint URL" — connection refused
- "Rate limit exceeded — wait and retry"

Probe failures don't block provider addition — the provider is saved anyway. Use `ainews providers-test` to diagnose later.

## Model Discovery

```bash
ainews providers-models ollama-local
```

Output:

```
Provenance: Discovered
Model ID         Display Name       Context Window  Tools
qwen3:8b         Qwen 3 8B          32768           yes
llama3:8b        Llama 3 8B         8192            yes
codellama:13b    CodeLlama 13B       16384           -
```

### Provenance

- **discovered**: Models listed from the provider's live API
- **catalog**: Models from a built-in catalog (when API is unavailable)
- **configured**: Models from the provider's config file

### Per-Adapter Discovery

| Adapter | Discovery Method | Notes |
|---------|-----------------|-------|
| `ollama` | `GET /api/tags` | Only locally pulled models |
| `openai` | `GET /v1/models` | All models accessible by API key |
| `anthropic` | Catalog | Known Claude models |
| `gemini` | Catalog | Known Gemini models |
| `eggpool` | API query | Managed model catalog |
| `generic` | Config fallback | Returns configured model |

## Pipeline Role Assignment

### Assign to All Roles

```bash
ainews providers-assign openai-prod gpt-4o
```

Assigns `openai-prod/gpt-4o` to selector, researcher, writer, and editor.

### Assign to Specific Roles

```bash
ainews providers-assign openai-prod gpt-4o --roles selector,writer
```

### Role Definitions

| Role | Pipeline Stage | Purpose |
|------|---------------|---------|
| `selector` | Select | Article relevance scoring and ranking |
| `researcher` | Research | Deep research brief generation |
| `writer` | Write | Article draft generation |
| `editor` | Edit | Quality review and revision |

### Multi-Provider Assignments

Different providers can serve different roles:

```bash
ainews providers-assign ollama-local qwen3:8b --roles selector
ainews providers-assign openai-prod gpt-4o --roles researcher,writer,editor
```

This uses Ollama for fast, cheap selection and OpenAI for high-quality research and writing.

### View Current Assignments

```bash
ainews providers-list
```

```
ID            Type      Endpoint                    Enabled  Default  Roles
ollama-local  ollama    http://localhost:11434/v1    yes      yes      selector
openai-prod   openai    https://api.openai.com/v1    yes               researcher, writer, editor
```

## Setting Default Provider

```bash
ainews providers-set-default openai-prod
```

The default provider is used when a pipeline role doesn't have an explicit provider assignment. It's also the first provider checked in the fallback chain.

## Removing Providers

### Simple Removal

```bash
ainews providers-remove old-provider
```

Fails if the provider is assigned to pipeline roles.

### Removal with Reassignment

```bash
ainews providers-remove old-provider --reassign-to openai-prod
```

Reassigns all pipeline roles from `old-provider` to `openai-prod` before removal. Also updates the default provider if it was the removed provider.

## EggPool-Specific Setup

EggPool is a managed inference provider. Configuration:

```bash
ainews providers-add --type eggpool
```

Fields:
- **API key**: Your EggPool API key (from the dashboard)
- **Base URL**: Default `https://api.eggpool.io/v1` (or custom endpoint)
- **Default model**: Choose from available models

Model discovery queries EggPool's model catalog for available models and pricing tiers.

## Docker Networking

When running in Docker, provider endpoints must be reachable from within the container network:

### Ollama in Docker

**Wrong** (won't work):
```yaml
config:
  base_url: http://localhost:11434/v1
```

**Correct** (Docker Compose service):
```yaml
config:
  base_url: http://ollama:11434/v1
```

**Correct** (host machine):
```yaml
config:
  base_url: http://host.docker.internal:11434/v1
```

### Cloud Providers

Cloud providers (OpenAI, Anthropic, Gemini) work from Docker with no special configuration — they're accessed over the public internet.

### Bare Metal

Local providers use `localhost` directly. No Docker networking considerations.

## Configuration Files

Provider configuration is stored in `providers.yaml`:

```yaml
default_provider: ollama-local

providers:
  ollama-local:
    type: ollama
    enabled: true
    config:
      base_url: http://localhost:11434/v1
      default_model: auto
```

Pipeline role assignments are stored in `pipeline.yaml`:

```yaml
pipeline:
  selector:
    provider: ollama-local
    model: qwen3:8b
  writer:
    provider: openai-prod
    model: gpt-4o
```

Use `ainews config show` to see the effective configuration.

## Exit Codes

| Code | Name | Description |
|------|------|-------------|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `GENERAL_ERROR` | Unrecoverable error |
| `3` | `VALIDATION_ERROR` | Configuration validation failed |
| `5` | `NOT_FOUND` | Provider not found |
| `7` | `LOCK_ERROR` | Could not acquire configuration lock |
