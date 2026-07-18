# Migrating from Repository-Local to Installer-Based Installation

This guide walks through migrating a repository checkout-based ainews installation to the supported installer-based path. The installer provides version tracking, in-place updates, managed backups, and proper uninstall — none of which are available when running directly from a `git clone`.

## Who Should Use This Guide

You should migrate if:

- You cloned the repository and run ainews from the checkout directory
- Config files (`.env`, `providers.yaml`, `pipeline.yaml`, etc.) live in the repo root
- The database sits in `instance/` or alongside the source code
- You have no `install-metadata.json` in your config directory

You do **not** need this guide if you already installed via `scripts/install.sh` or the curl one-liner.

## Step 1: Detect Repository-Local Mode

The fastest way to check is the `ainews config path` command. It shows provenance for every resolved path.

```bash
ainews config path
```

If the provenance column shows `development` for most paths, you are running from a repository checkout:

```
Path                                Provenance         Exists    Writable
----                                ----------         ------    --------
~/.config/ainews/                   development        true      true
~/.local/share/ainews/              development        true      true
/home/user/projects/ainews/.env     development        true      true
/home/user/projects/ainews/providers.yaml  development  true    true
```

A `development` provenance means the path resolver detected `.git` or `pyproject.toml` in a parent directory and fell back to repository-local directories (`config/`, `instance/`).

You can also check for the absence of install metadata:

```bash
ls ~/.config/ainews/install-metadata.json 2>/dev/null || echo "No install metadata — repository-local install"
```

If the file does not exist, you have a repository-local installation.

## Step 2: Back Up Before Migration

Always create a backup before migrating. The `ainews backup create` command captures config files and the database in a single versioned snapshot.

```bash
ainews backup create --tag pre-migration
```

Expected output:

```
[INFO]  Creating backup...
[INFO]  Checksumming config files...
[INFO]  Snapshotting database (SQLite backup API)...
[INFO]  Writing manifest...
[INFO]  Backup created: 2026-07-18T041500Z-5.0.0-pre-migration
```

Verify the backup is valid:

```bash
ainews backup list
ainews backup verify 2026-07-18T041500Z-5.0.0-pre-migration
```

Store the backup directory path. If anything goes wrong during migration, you can restore from this snapshot.

## Step 3: Stop Running Services

Stop any running processes before copying files:

```bash
# If using Docker Compose
docker compose down

# If using systemd
sudo systemctl stop ainews-web ainews-celery-worker ainews-celery-beat

# If using dev script
# Stop the process running scripts/dev.sh (Ctrl+C)
```

## Step 4: Run the Installer

The installer downloads a release artifact and places it in the canonical install directory. It does **not** touch your existing config files or database.

### Option A: Curl one-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
```

### Option B: Run from the repository

```bash
bash scripts/install.sh --channel stable
```

### Option C: System-wide install

```bash
sudo bash scripts/install.sh --channel stable --system
```

The installer writes `install-metadata.json` to the config directory. This file tells the CLI where to find the application and configuration — it is the key difference from a repository-local install.

### What the Installer Creates

| Path (user install) | Purpose |
|---------------------|---------|
| `~/.local/share/ainews/app/` | Installed application code |
| `~/.config/ainews/` | Configuration directory |
| `~/.local/state/ainews/` | State (locks, staging, metadata) |
| `~/.local/bin/ainews` | CLI entry point |

After installation, `ainews config path` should show `install_metadata` as the provenance for the config and data directories:

```bash
ainews config path
```

```
Path                                Provenance         Exists    Writable
----                                ----------         ------    --------
~/.config/ainews/                   install_metadata   true      true
~/.local/share/ainews/              install_metadata   true      true
```

## Step 5: Import Existing Configuration Files

The installer creates a fresh config directory. You need to copy your existing config files into it. The five files that matter:

| File | Purpose |
|------|---------|
| `.env` | Secrets, SMTP settings, API keys |
| `providers.yaml` | LLM provider configuration |
| `pipeline.yaml` | Pipeline stages, role assignments, model selection |
| `sources.yaml` | RSS/API content sources |
| `topics.yaml` | Topic classification categories |

### Copying files

```bash
# User install target
CONFIG_DIR=~/.config/ainews

# Copy from your repository checkout
cp .env "$CONFIG_DIR/.env"
cp providers.yaml "$CONFIG_DIR/providers.yaml"
cp pipeline.yaml "$CONFIG_DIR/pipeline.yaml"
cp sources.yaml "$CONFIG_DIR/sources.yaml"
cp topics.yaml "$CONFIG_DIR/topics.yaml"
```

For system-wide installs:

```bash
sudo cp .env /etc/ainews/.env
sudo cp providers.yaml /etc/ainews/providers.yaml
sudo cp pipeline.yaml /etc/ainews/pipeline.yaml
sudo cp sources.yaml /etc/ainews/sources.yaml
sudo cp topics.yaml /etc/ainews/topics.yaml
```

### Adjusting paths in .env

If your `.env` contains absolute paths pointing into the repository (e.g., `DATABASE_URL=sqlite:///home/user/projects/ainews/instance/ainews.db`), update them to use the installer's canonical locations:

```bash
# Old (repository-local)
DATABASE_URL=sqlite:///home/user/projects/ainews/instance/ainews.db

# New (installer-managed)
DATABASE_URL=sqlite:////home/user/.local/share/ainews/ainews.db
```

Or leave `DATABASE_URL` unset — the CLI resolves it automatically through the path chain.

### Copying the database (if needed)

If your database lives in `instance/ainews.db` in the repository and you want to preserve article history, copy it to the data directory:

```bash
cp instance/ainews.db ~/.local/share/ainews/ainews.db
```

For system-wide installs:

```bash
sudo cp instance/ainews.db /var/lib/ainews/ainews.db
```

If the database is in Docker volumes, the Docker Compose stack manages it separately — you typically do not need to copy it.

## Step 6: Understand Canonical Path Precedence

The path resolver in `ainews_config/paths.py` evaluates five levels in order. Understanding this chain helps you debug path resolution after migration.

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | **Explicit** | CLI flags like `--config-dir` |
| 2 | **Environment** | `AINEWS_CONFIG_DIR`, `AINEWS_DATA_DIR`, etc. |
| 3 | **Install metadata** | Values from `install-metadata.json` |
| 4 | **Platform default** | `~/.config/ainews/`, `~/.local/share/ainews/` |
| 5 | **Development** | Repository `config/` and `instance/` directories |

**How it works:**

- After installation, the `install-metadata.json` file records where config and data live. Priority 3 takes over and the development fallback (Priority 5) is no longer used.
- If you set environment variables like `AINEWS_CONFIG_DIR`, they override everything except explicit CLI flags (Priority 2).
- Development fallback is only active when the CLI detects `.git` or `pyproject.toml` in a parent directory.

**Verify after migration:**

```bash
ainews config path
```

All paths should show `install_metadata`, `platform_default`, or `explicit` — not `development`.

## Step 7: Validate Providers and Pipeline

Run configuration validation to ensure the copied files are consistent:

```bash
ainews config check
```

Expected output:

```
✅ Configuration valid
  Providers: 1 enabled (default: ollama-local)
  Pipeline: all stages configured
  Sources: 12 sources configured
```

If there are issues, the check reports them with fix hints:

```
❌ Configuration invalid
  - providers.yaml: default_provider "ollama-local" not found in providers list
    Fix: ainews providers-list to see available providers
  - .env: SECRET_KEY is missing
    Fix: ainews config set-secret SECRET_KEY
```

Run doctor for comprehensive system diagnostics:

```bash
ainews doctor --production
```

This checks:
- Installation metadata integrity
- Configuration file parseability
- Provider connectivity
- Database accessibility
- Redis availability

## Step 8: Start the Installed Deployment

With config files in place and validation passing, start services:

```bash
ainews start
```

The start command:
1. Runs prerequisite checks (doctor, migrations)
2. Starts Docker Compose or systemd services
3. Waits for the health endpoint
4. Reports status

Options:

```bash
ainews start --skip-doctor      # Skip prerequisite checks
ainews start --skip-migrations  # Skip database migrations
ainews start --no-wait          # Start without waiting for health
```

Verify:

```bash
curl http://localhost:5000/health
ainews status
```

## Step 9: Rollback to Repository-Local Operation

If the installed version does not work and you need to revert:

1. **Stop installed services:**

```bash
ainews stop
```

2. **Restore from backup:**

```bash
ainews restore 2026-07-18T041500Z-5.0.0-pre-migration
```

3. **Resume repository-local operation:**

```bash
cd /path/to/ainews-repo
# Start with your existing method (Docker Compose, dev script, systemd)
```

4. **Optionally remove the installation:**

```bash
ainews uninstall --remove-app-only
```

This removes the installed application files but preserves config and data, so you can try again later.

## Step 10: Remove Obsolete Files

After verifying the installed deployment works correctly for a few days, clean up the repository checkout:

### Safe to remove from the old repo directory

| Path | Notes |
|------|-------|
| `.env` | Now in `~/.config/ainews/.env` (or `/etc/ainews/.env`) |
| `providers.yaml` | Now in config directory |
| `pipeline.yaml` | Now in config directory |
| `sources.yaml` | Now in config directory |
| `topics.yaml` | Now in config directory |
| `instance/ainews.db` | Now in data directory |
| `instance/` | Empty after database migration |
| `.venv/` | Python virtual environment (installer manages its own) |

### Do NOT remove yet

| Path | Notes |
|------|-------|
| `backups/` | Verify migration backup works before deleting |
| `instance/` | Keep until you confirm the new database has your data |

### Clean up the old clone

```bash
# Remove config files (already copied to install location)
rm .env providers.yaml pipeline.yaml sources.yaml topics.yaml

# Remove instance directory (database copied)
rm -rf instance/

# Remove virtual environment
rm -rf .venv/

# Remove __pycache__ and build artifacts
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm -rf *.egg-info build dist
```

If you no longer need the repository:

```bash
cd ..
rm -rf ainews
```

## Verification Checklist

Before cleaning up, confirm the following:

```bash
ainews config path          # All paths show install_metadata or platform_default
ainews config check         # Configuration valid
ainews doctor               # All checks passing
ainews start                # Services start successfully
curl localhost:5000/health  # Returns {"status": "ok"}
ainews backup list          # Migration backup is accessible
```

Then test admin login at `http://localhost:5000/admin/login` and verify articles are processing.

## Troubleshooting

**Config files not found:** Run `ainews config path` to see where the CLI looks. Set `AINEWS_CONFIG_DIR=~/.config/ainews` to override.

**"No install metadata" warning:** Re-run the installer: `bash scripts/install.sh --channel stable`.

**Database not found:** Check `ainews config path` for the expected database path, then copy: `cp /old/path/instance/ainews.db ~/.local/share/ainews/ainews.db`.

**Development fallback still active:** You are inside a directory with `.git` or `pyproject.toml`. Run from outside the repository: `cd ~ && ainews config path`.

**Rolling back a failed migration:**

```bash
ainews stop
ainews restore 2026-07-18T041500Z-5.0.0-pre-migration
ainews uninstall --remove-app-only
cd /path/to/old-repo   # Resume as before
```

## Quick Reference

| Step | Command |
|------|---------|
| Detect mode | `ainews config path` (check for `development` provenance) |
| Back up | `ainews backup create --tag pre-migration` |
| Stop services | `docker compose down` or `systemctl stop ainews-*` |
| Install | `curl -fsSL .../install.sh \| bash` |
| Copy config | `cp .env providers.yaml pipeline.yaml sources.yaml topics.yaml ~/.config/ainews/` |
| Copy database | `cp instance/ainews.db ~/.local/share/ainews/ainews.db` |
| Validate | `ainews config check && ainews doctor` |
| Start | `ainews start` |
| Clean up | Remove old config files, `instance/`, `.venv/` from the repo checkout |
