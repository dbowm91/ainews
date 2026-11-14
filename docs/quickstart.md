# Quick Start Guide

Run ainews locally for development. This guide assumes a source checkout and Python 3.12 or newer.

> **Onboarding limitation:** `ainews onboard` currently collects and validates selections but does not write the staged configuration or start services. Follow the manual configuration steps below, then use `ainews start`.

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Redis, either already reachable or installed locally so the development supervisor can start it
- An LLM provider, such as Ollama, an OpenAI-compatible server, or a cloud API

For local inference with Ollama, install it from [ollama.ai](https://ollama.ai). Start the server in one terminal:

```bash
ollama serve
```

In another terminal, pull a model:

```bash
ollama pull qwen3:8b
```

Keep the Ollama server running while using ainews.

## Install and configure

Clone the repository and install its dependencies:

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
uv sync
```

Create a local environment file and select development mode:

```bash
cp .env.example .env
```

Edit `.env` and set `FLASK_CONFIG=development`. Generate independent values for `SECRET_KEY` and `CELERY_TASK_SECRET` by running this command once for each variable:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

For an admin password hash, run the helper and follow its prompts:

```bash
uv run python scripts/hash_password.py
```

Copy its `ADMIN_PASSWORD=...` output into `.env`. The helper requires a strong password. Do not pass your password as a command-line argument.

## Configure an LLM provider

Review `providers.yaml` before starting. The shipped configuration enables `local`, an OpenAI-compatible endpoint at `http://127.0.0.1:1234/v1`, and `opencode`. Disable providers you do not use, or configure their endpoints and credentials. If no server is listening at the `local` endpoint, select a working provider.

For Ollama, disable unused providers, enable `ollama-local`, set its `host` to `http://localhost:11434`, and set `default_provider: ollama-local`. For a cloud provider, enable it in `providers.yaml` and put its API key in `.env`. See [Configuration](configuration.md#providersyaml-llm-providers) for examples.

List configured provider IDs and test the one you enabled. Replace `local` with that provider's ID if needed:

```bash
uv run ainews providers-list
uv run ainews providers-test local
```

## Start the development stack

Use the supervisor so web, worker, Beat, and any locally started Redis share one lifecycle:

```bash
bash scripts/dev.sh start
bash scripts/dev.sh status
```

The web app is at `http://localhost:5000`. Check its health endpoint, then visit `http://localhost:5000/admin/login` in a browser:

```bash
curl http://localhost:5000/health
```

To stop the stack:

```bash
bash scripts/dev.sh stop
```

Use the admin interface to trigger a crawl. The development supervisor manages child processes and stops only the Redis process it started. Avoid running the web, worker, and Beat in separate terminals for normal development.

## Docker Compose

For a Docker setup, including production secrets, Redis networking, Ollama options, and reverse-proxy guidance, follow the [Deployment Guide](deployment.md#docker-compose). Compose overrides the localhost Redis settings in `.env.example` with the internal `redis` service URLs.

## Common checks

```bash
uv run ainews doctor --quick
uv run ainews config check
```

See [Troubleshooting](troubleshooting.md) for common startup, Redis, provider, source, and database problems. For all environment variables and YAML settings, see [Configuration](configuration.md).
