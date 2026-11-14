# Operations Guide

Use the `ainews` CLI for service lifecycle and health checks. It selects the configured Docker Compose or bare-metal driver. For command options, see the [CLI reference](cli-reference.md).

## Service lifecycle

```bash
ainews start
ainews status
ainews health
ainews smoke
ainews logs
ainews logs celery-worker
ainews restart
ainews stop
```

Use the CLI to manage the complete service stack. In Docker Compose, avoid stopping or replacing the web, worker, or Beat container independently from its related services. On bare metal, use the installed service manager or `ainews service` commands.

## Diagnostics

```bash
ainews doctor
ainews doctor --quick
ainews doctor --network
ainews config check --production
ainews providers-test
ainews sources-test
```

`doctor --network` checks connectivity and may contact configured providers and sources. `config show` redacts secrets by default. Do not share diagnostic output until you have checked it for private URLs or other sensitive values.

For a local HTTP health check:

```bash
curl http://localhost:5000/health
```

The admin health endpoint requires administrator authentication. Prefer the CLI, admin UI, or an API token rather than embedding credentials in a shell command.

## Configuration changes

Use `ainews config set`, `ainews config unset`, or the provider/source commands to make supported changes. Validate the result before restarting:

```bash
ainews config check --production
ainews providers-test
ainews restart
```

For direct YAML edits, keep backups and validate them with `ainews config check`. Configuration and schedule changes are read by running processes, so restart the stack after changes unless you have deliberately used the authenticated admin configuration reload function.

## Scheduled work

Celery Beat runs crawling, retry, newsletter, maintenance, and optional narration tasks. Schedule values are configurable in the `schedule:` section of `pipeline.yaml`. The exact set of scheduled jobs can change between releases; use the current configuration and service logs rather than relying on a fixed task count.

Check `ainews status` and `ainews logs celery-beat` if scheduled work is delayed. Check `ainews logs celery-worker` for task execution errors. For queue and editorial recovery, inspect the relevant article or edition in the admin interface before retrying work.

## Backups and restores

Create and verify a backup before upgrades or database maintenance:

```bash
ainews backup create --tag before-maintenance
ainews backup list
ainews backup verify BACKUP_ID
```

Preview and then apply a restore only after reviewing the backup and restore plan:

```bash
ainews restore BACKUP_ID --dry-run
ainews restore BACKUP_ID
```

Keep at least one verified copy outside the host. For installer-managed updates, `ainews update apply` creates a pre-update backup. See [Deployment](deployment.md#backups-and-restore) for the deployment workflow.

## Newsletter delivery

Newsletter editions can be published without sending email. Email delivery requires SMTP configuration and the relevant global and profile-level switches. Before enabling scheduled delivery, verify the SMTP account, recipient policy, public HTTPS site URL, and unsubscribe flow.

Review delivery status in the admin interface. An SMTP result marked `unknown` may have been accepted by the relay; do not retry it automatically. Retry only after an operator reviews the result and explicitly confirms the retry. For narration setup and recovery, see [Optional narration](tts.md).

## Safe recovery

- Use `ainews doctor`, `ainews status`, and service logs to diagnose failures before changing state.
- Make and verify a backup before database recovery or migrations.
- Do not delete SQLite journal files, manually stamp migrations, or run `FLUSHDB` as a general recovery step. These actions can cause data loss or corruption.
- Use `ainews migrations status` and `ainews migrations plan` before applying migrations. Never bypass a failed migration by stamping a revision.

See [Troubleshooting](troubleshooting.md) for common errors and recovery steps.
