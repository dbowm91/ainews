# Deployment Guide

This guide covers the supported release installer, Docker Compose, and bare-metal operation. Read [Configuration](configuration.md) for the full environment and YAML reference.

> **Onboarding limitation:** `ainews onboard` currently collects and validates selections, but does not write the staged configuration or start services. Its `--start` option is deferred as well. The installer can invoke onboarding, but that does not finish configuration. Configure the required files and secrets as described below before starting the application.

## Production checklist

Before exposing ainews to users:

- Set `FLASK_CONFIG=production`.
- Set `SECRET_KEY`, `CELERY_TASK_SECRET`, and a hashed `ADMIN_PASSWORD`.
- Enable and configure at least one LLM provider in `providers.yaml`.
- Make Redis and the database available to the application.
- Put public traffic behind HTTPS. Do not expose the application port directly to the Internet.
- Back up the database and configuration before upgrades, and test restore procedures.

Generate application secrets with Python 3:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Generate the admin password hash in an environment with project dependencies installed. The helper prompts for the password and prints an `ADMIN_PASSWORD` hash:

```bash
uv run python scripts/hash_password.py
```

The helper requires a password of at least 12 characters with upper- and lowercase letters, a digit, and a special character. Never put a plaintext password in `.env` for production.

## Release installer

The installer downloads a release artifact, verifies its checksum, and installs the CLI. It does not provision the host's Docker, Redis, or reverse proxy.

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
```

The default is the stable channel and a user installation. To select another channel or system paths, download the script and run it with options:

```bash
curl -fsSLO https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh
sudo bash install.sh --channel stable --system
```

Supported release targets are Linux x86_64, Linux arm64, and macOS arm64. Windows users need WSL. `stable` is the default channel; `prerelease` is for testing and `main` is for development or evaluation.

| Install mode | Application | Configuration | Data | CLI |
|---|---|---|---|---|
| User | `~/.local/share/ainews/app/` | `~/.config/ainews/` | `~/.local/share/ainews/data/` | `~/.local/bin/ainews` |
| System | `/opt/ainews/app/` | `/etc/ainews/` | `/var/lib/ainews/` | `/usr/local/bin/ainews` |

The installer may offer to run onboarding. Because onboarding does not currently apply staged values, complete configuration manually before running `ainews start`. See [Configuration](configuration.md) and [CLI reference](cli-reference.md).

## Docker Compose

The repository Compose file builds the application, runs database migrations, and starts the web app, Celery worker, Beat scheduler, and Redis.

### Prepare configuration

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
cp .env.example .env
uv sync
```

Edit `.env` and set `FLASK_CONFIG=production`, `SECRET_KEY`, `CELERY_TASK_SECRET`, and the hashed `ADMIN_PASSWORD`. Keep secrets out of version control. The shipped `providers.yaml` enables `local` and `opencode`; configure each enabled provider with a reachable endpoint and any required credentials, or disable providers you will not use. For a cloud provider, put its API key in `.env` and reference it from the YAML file.

Compose sets the Celery URLs to `redis://redis:6379/0` and `redis://redis:6379/1`, and supplies the container database URL. These are internal service settings. Do not replace them with `localhost` values from the example environment file.

### Ollama options

For an Ollama service in the Compose network:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
docker compose exec ollama ollama pull qwen3:8b
```

Set the provider host in `providers.yaml` to `http://ollama:11434`.

For Ollama on the host, use `http://host.docker.internal:11434`. Docker Desktop supports this on macOS and Windows. On Linux, add `host.docker.internal:host-gateway` under `extra_hosts` for the services that need host access. `localhost` inside a container refers to that container, not the host.

### Start and verify

The base Compose file publishes port 5000 on all interfaces. For a reverse-proxy deployment, change the `web` port mapping in `docker-compose.yml` to bind only to loopback:

```yaml
ports:
  - "127.0.0.1:5000:5000"
```

Then start and check the services:

```bash
docker compose up -d
docker compose ps
curl http://localhost:5000/health
```

Configure the proxy for HTTPS and forward the original `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers. Set trusted proxy addresses in the application configuration. Keep Redis and the database volume private.

Useful Compose commands:

```bash
docker compose logs -f web
docker compose logs -f celery-worker
docker compose restart web celery-worker celery-beat
docker compose down
```

`docker compose down -v` also deletes named data volumes. Use it only when you intentionally want to remove the database and Redis data.

## Bare-metal deployment

Bare-metal deployments need Python 3.12 or newer, `uv`, Redis, and a process manager for production. A source checkout can install the CLI and dependencies with:

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
uv sync
source .venv/bin/activate
```

Configure `.env` and the YAML files using [Configuration](configuration.md). Start and inspect the services with `ainews start`, `ainews status`, and `ainews logs`. For systemd unit generation and installation, use `ainews service` rather than copying hand-written unit files; see the [CLI reference](cli-reference.md#service-management).

The deployment profile called `bare-metal` describes foreground services and does not install or configure systemd. The release installer's `--system` option selects installation paths; it does not create a system account or provision system services.

## Updates

For an installation managed by the release installer, check and apply updates through the CLI:

```bash
ainews update check
ainews update plan
ainews update apply
```

The update workflow verifies the downloaded artifact and creates a pre-update backup. Review the plan before applying an update.

For a source checkout deployed with Compose, update the checkout and rebuild the Compose services:

```bash
git pull --ff-only
docker compose up -d --build
```


## Backups and restore

Use the CLI backup commands for installations managed by ainews:

```bash
ainews backup create --tag before-upgrade
ainews backup list
ainews backup verify BACKUP_ID
ainews restore BACKUP_ID --dry-run
ainews restore BACKUP_ID
```

Keep copies outside the application host. Verify backups regularly and review the restore plan before applying it. The older shell scripts under `scripts/` assume a particular filesystem layout and are not a substitute for configuring backups for your install paths.

## Further reading

- [Configuration reference](configuration.md)
- [CLI reference](cli-reference.md)
- [Operations guide](operations.md)
- [Troubleshooting guide](troubleshooting.md)
