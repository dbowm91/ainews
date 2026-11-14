# ainews

AI-powered news aggregation and newsletter software. ainews collects stories from configured RSS and API sources, processes them through an LLM pipeline, and publishes reviewed articles and newsletters.

## Getting started

Choose the guide for your setup:

- [Quick start](docs/quickstart.md) for local development.
- [Deployment](docs/deployment.md) for Docker Compose, installer, and bare-metal deployments.
- [Configuration](docs/configuration.md) for environment variables and YAML files.

The release installer downloads and verifies a prebuilt artifact:

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
```

It defaults to the stable channel and a user-owned installation. The installer may offer to run `ainews onboard`. Note that onboarding currently collects and validates selections but does not write the staged configuration or start services. Use the deployment and configuration guides to complete setup, then run `ainews start`.

For a source checkout, Docker Compose reads `.env` and the YAML configuration files. Compose supplies its own Redis and database URLs; see the deployment guide before changing them.

## What ainews includes

- A multi-provider LLM pipeline for article selection, research, writing, and editing.
- Source, topic, and pipeline configuration with command-line management.
- Review routing and editorial eligibility checks before publication.
- Search, article feeds, newsletter generation, metrics, and health endpoints.
- Optional themes, webhooks, and narration support.

The application uses Flask, Celery, Redis, and SQLite by default. SQLite is intended for single-node deployments. Background processing requires a reachable Redis service.

## Command-line interface

The operator CLI supports configuration checks and edits, provider and source management, service lifecycle, backups, updates, and diagnostics. Command names are not all nested: for example, provider and source commands use names such as `ainews providers-list` and `ainews sources-test`.

See the [CLI reference](docs/cli-reference.md) for exact command names and options. The `ainews onboard` command currently does not apply the configuration it stages, so do not treat a successful onboarding summary as proof that an installation is ready.

## Documentation

| Guide | Covers |
|---|---|
| [Quick start](docs/quickstart.md) | Local development setup |
| [Onboarding](docs/onboarding.md) | Onboarding workflow, profiles, and bootstrap-file validation |
| [Configuration](docs/configuration.md) | Environment variables and YAML configuration |
| [Deployment](docs/deployment.md) | Installer, Docker Compose, bare metal, updates, and backups |
| [CLI reference](docs/cli-reference.md) | Operator commands and options |
| [Operations](docs/operations.md) | Health checks, logs, backups, and recovery |
| [Troubleshooting](docs/troubleshooting.md) | Common setup and runtime problems |
| [Pipeline](docs/pipeline.md) | Processing stages and review routing |
| [Responsible use](docs/responsible-use.md) | Source rights, attribution, and AI content guidance |
| [Security](SECURITY.md) | Vulnerability reporting |
| [Contributing](CONTRIBUTING.md) | Development setup and contribution process |

## Limitations

- Production deployments require valid secrets, an enabled LLM provider, Redis, and a secure HTTPS setup.
- Docker containers cannot reach host services through `localhost`. For host Ollama, use `host.docker.internal`; for Ollama in Compose, use the `ollama` service name.
- Human editorial review is recommended before publishing generated content.
- SMTP is needed only for email delivery. Newsletter editions can be published without email.

## License

See [LICENSE](LICENSE).
