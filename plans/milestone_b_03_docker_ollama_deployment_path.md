# Milestone B.3: Docker and Ollama Deployment Path

## Objective

Make the Docker quickstart and production Compose path unambiguous and executable. The current default provider story points local Ollama at `http://localhost:11434`, which is correct for bare-metal app execution but usually wrong from inside the app container. This plan defines a container-aware deployment path and ensures docs, examples, and validation messages match runtime behavior.

## Current risk

A new operator can follow Docker quickstart, enable the default Ollama provider, and still fail because `localhost` inside the `web` container refers to the container itself, not the host machine running Ollama. This creates a false-positive setup path: the app may start, but the LLM pipeline will fail later.

## Deployment modes to support

Support and document these modes explicitly:

### Mode A: Docker Compose with cloud LLM provider

The simplest production Docker mode:

- `web`, `worker`, `beat`, `redis`, migration service.
- Cloud provider API key configured through `.env`.
- No local Ollama dependency.

### Mode B: Docker Compose with Ollama as a Compose service

Operator runs Ollama in the same Compose project/network:

- Add an optional `ollama` service or provide a documented override file.
- Provider host should be `http://ollama:11434`.
- Operator pulls the model before first use or the docs explain model pull behavior.

### Mode C: Docker Compose app connecting to host Ollama

Operator runs Ollama on the host:

- Linux may use `http://host.docker.internal:11434` only if configured; on some Docker setups this requires `extra_hosts` mapping to `host-gateway`.
- macOS/Windows Docker Desktop usually supports `host.docker.internal`.
- Docs should make platform differences explicit.

### Mode D: Bare-metal app with local Ollama

App runs directly on the same host as Ollama:

- Provider host `http://localhost:11434` is valid.

## Implementation plan

### Step 1: Decide default Docker recommendation

Recommended default for public quickstart:

- Docker quickstart should use a cloud provider example or an explicit Ollama Compose override.
- Do not leave `localhost:11434` as the implied Docker default without explanation.

For privacy/self-hosted audience, an optional `docker-compose.ollama.yml` override is useful:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"

volumes:
  ollama-data:
```

Then provider config should point to `http://ollama:11434` inside Compose.

### Step 2: Add or update Compose override examples

Possible files:

- `docker-compose.ollama.yml`
- `docs/examples/docker-compose.ollama.yml`
- `docs/examples/providers.ollama-docker.yaml`

If adding a real Compose override, make sure it works with the main `docker-compose.yml` and does not unexpectedly expose Ollama publicly. Binding port `11434:11434` is convenient but can expose the service; prefer documenting local-only binding if supported:

```yaml
ports:
  - "127.0.0.1:11434:11434"
```

If the app container only needs internal access, omit host port publishing entirely.

### Step 3: Update provider config examples

Document examples for:

Bare-metal local Ollama:

```yaml
providers:
  ollama-local:
    enabled: true
    type: ollama
    config:
      host: http://localhost:11434
      model: qwen3:8b
```

Compose service Ollama:

```yaml
providers:
  ollama-local:
    enabled: true
    type: ollama
    config:
      host: http://ollama:11434
      model: qwen3:8b
```

Host Ollama from container:

```yaml
providers:
  ollama-local:
    enabled: true
    type: ollama
    config:
      host: http://host.docker.internal:11434
      model: qwen3:8b
```

### Step 4: Improve validation warnings/errors

Production validation should not perform live Ollama calls, but it can detect suspicious Docker-localhost configuration if enough context is available.

Options:

- If `FLASK_CONFIG=production`, running in Docker, and enabled provider host is `localhost` or `127.0.0.1`, emit a clear warning or fail depending on chosen strictness.
- Strict fail is safer if Docker detection is reliable.
- Warning may be better if operators intentionally run sidecar/network namespace configurations.

Recommended behavior:

- Fail only on clearly invalid or empty URL.
- Warn for `localhost` in Docker with a message explaining `ollama` or `host.docker.internal` alternatives.
- Docs should cover the decision.

Docker detection options:

- `/.dockerenv` exists.
- `AINEWS_RUNNING_IN_DOCKER=1` env var set in Dockerfile/Compose.

Prefer explicit env var if added.

### Step 5: Add smoke checks for deployment paths

Add tests/scripts that validate config shape without requiring live Ollama:

- Parse providers config for Docker Ollama example.
- Validate default provider is enabled and host URL is syntactically valid.
- Optional: Compose config validation using `docker compose config` in CI if Docker is available.

Do not require model download in CI unless a separate slow/manual workflow is created.

### Step 6: Update README quickstart

README Docker quickstart should explicitly say one of:

- Use a cloud provider and set its API key, or
- Use the Ollama Compose override and set host to `http://ollama:11434`, or
- Use host Ollama with platform-specific host mapping.

Also list required secrets:

- `SECRET_KEY`
- hashed `ADMIN_PASSWORD`
- `CELERY_TASK_SECRET`
- Redis URLs if not using Compose defaults
- provider/default-provider config

## Test and validation plan

Commands:

```bash
docker compose config
```

If an Ollama override is added:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml config
```

Provider validation tests:

```bash
uv run pytest tests/ -k "ollama or provider or docker" -q
```

Docs smoke, if a script exists:

```bash
uv run python scripts/check_docs_commands.py
```

## Acceptance criteria

- Docker docs no longer imply `localhost:11434` is generally correct inside containers.
- There is a documented working path for cloud providers.
- There is a documented working path for Ollama in Compose or host Ollama.
- Provider examples match production validation behavior.
- Compose config validates.
- The operator sees a clear warning or error for suspicious Docker-localhost Ollama setup.

## Handoff cautions

- Do not require GPU availability for the default CI path.
- Do not expose Ollama on all interfaces unless explicitly documented as a local development convenience.
- Do not make live model download part of standard CI.
- If adding an Ollama service, avoid making it mandatory for cloud-provider deployments.
