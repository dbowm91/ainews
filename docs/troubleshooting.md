# Troubleshooting Guide

Start with the CLI diagnostics. They report configuration, service, and connectivity problems without requiring manual database or Redis changes.

```bash
ainews doctor
ainews status
ainews logs
ainews config check --production
```

For Docker Compose logs, use `docker compose logs -f SERVICE`. Do not paste secrets, API keys, passwords, or private URLs into support requests.

## Application will not start

1. Run `ainews doctor` and read the failing check's remediation.
2. Run `ainews config check --production` to find invalid settings.
3. Inspect `ainews logs web` or `docker compose logs web`.
4. Confirm Redis and the database are reachable, then check migration status:

```bash
ainews migrations status
ainews migrations plan
```

Production startup fails closed when required secrets or provider configuration are missing or invalid. Check `.env` without printing its contents. `ainews config show` redacts secrets by default.

For production, `SECRET_KEY` must be a 64-character hex string, `CELERY_TASK_SECRET` must contain at least 32 characters, and `ADMIN_PASSWORD` must be a supported password hash. Generate a password hash with `uv run python scripts/hash_password.py` in a project environment.

## Redis connection errors

For a host Redis service:

```bash
redis-cli ping
```

A healthy server returns `PONG`. Check that `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` point to the reachable Redis instance.

For Docker Compose:

```bash
docker compose ps redis
docker compose logs redis
```

Inside Compose, Redis is reached by the service name `redis`, not `localhost`. Do not use `redis-cli FLUSHDB` as a troubleshooting step; it can delete live task, lock, and cache data.

## LLM provider failures

Test provider connectivity and check its configuration:

```bash
ainews providers-test
ainews config check
```

Common causes include an invalid endpoint, a missing or expired API key, provider rate limits, and a model name that is unavailable to the account. Confirm that the selected provider is enabled and matches `default_provider` in `providers.yaml`.

For Ollama, verify that the server is running and that the model is installed. `localhost` is correct only when the app runs on the same host as Ollama. In Docker, use `http://ollama:11434` for the Compose service or `http://host.docker.internal:11434` for a host service. On Linux, the latter may require the `host-gateway` mapping. See [Deployment](deployment.md#ollama-options).

## Source fetch failures

Test a source and inspect its status:

```bash
ainews sources-test SOURCE_ID
ainews doctor --network
```

The safe fetch client blocks private, loopback, link-local, and reserved IP addresses. Use publicly reachable source URLs. Other common causes include DNS failures, an invalid feed URL, a slow server, or a response content type that does not match the source adapter.

Do not disable SSRF checks to make an internal URL work. Check the source's URL and DNS configuration instead.

## Celery tasks are delayed or failing

Check the worker and Beat services:

```bash
ainews status
ainews logs celery-worker
ainews logs celery-beat
```

Confirm Redis is healthy and provider tests pass. For articles that are stuck or routed to review, inspect their status and diagnostics in the admin interface before reprocessing them. Do not revoke or reset tasks blindly; a task may still be running or may have already changed data.

## Database lock or migration errors

A database lock can indicate overlapping processes or a long-running transaction. Check service status and logs, then restart the managed stack if necessary. Do not delete `-journal`, `-wal`, or `-shm` files while the application is running.

Before applying migrations, create and verify a backup. Review the migration plan, then apply through the CLI:

```bash
ainews backup create --tag before-migration
ainews migrations status
ainews migrations plan
ainews migrations apply
```

If a migration fails, preserve the logs and database. Do not manually run migration SQL or stamp a revision to bypass the failure. For database restoration, use `ainews restore BACKUP_ID --dry-run`, review the plan, and follow the confirmation prompts.

## Newsletter email is not delivered

- Confirm that SMTP settings are correct and the relay permits the configured sender.
- Confirm that the global email switch and the selected newsletter profile's switch are enabled.
- Check the edition's delivery status in the admin interface and inspect worker logs.
- Verify that the public site URL uses HTTPS and that the unsubscribe link works.

An `unknown` SMTP outcome may mean the relay accepted the message but the acknowledgement was lost. Do not automatically retry it. Review the recipient's delivery record and use the explicit retry action only when an operator has confirmed the risk of a duplicate email.

## Port 5000 is already in use

Find the process listening on port 5000, then either stop the conflicting service or change the app's configured port. For Docker Compose, update the `web` service port mapping and keep it bound to loopback when using a reverse proxy.

## Theme changes do not appear

The theme registry and custom theme files are read at application startup. Restart ainews after changing theme configuration or files. Confirm the theme ID and custom directory in configuration, then check the web logs for theme diagnostics.

## Still stuck?

Collect `ainews doctor --json`, the relevant service logs, and the exact command that failed. Review the output before sharing it and redact secrets, tokens, private addresses, and source URLs where needed. See [Operations](operations.md) for recovery procedures and [Configuration](configuration.md) for setting details.
