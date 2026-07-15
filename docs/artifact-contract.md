# Artifact Contract

Machine-oriented specification of the release tarball layout, naming, checksums, and post-install directory structure. This document is the source of truth for what the installer downloads, extracts, and places on disk.

---

## 1 — Artifact Naming

Release artifacts follow a deterministic naming convention:

```
ainews-{version}-{platform}.tar.gz
```

| Component | Values | Notes |
|-----------|--------|-------|
| `{version}` | Semver string (e.g. `1.2.0`) | Stripped from `v` tag prefix; matches `pyproject.toml` `[project].version` |
| `{platform}` | `linux-x86_64`, `linux-aarch64`, `macos-x86_64`, `macos-aarch64` | Derived from `uname -s` + `uname -m` at build time |

**Main channel例外:** `ainews-main-{commit:0:8}-{platform}.tar.gz` — uses the first 8 hex chars of the commit SHA instead of a semver version. Not for production use.

Each artifact is accompanied by a `SHA256SUMS` file at the same release URL:

```
ainews-{version}-{platform}.SHA256SUMS
```

---

## 2 — Tarball Structure

The tarball is a gzip-compressed tar archive. All entries live under a single top-level `ainews/` directory:

```
ainews-{version}-{platform}.tar.gz
└── ainews/
    ├── ainews                          # Wrapper entry point script
    ├── .venv/                          # Python virtual environment (platform-specific)
    ├── pyproject.toml
    ├── docker-compose.yml
    ├── docker-compose.ollama.yml
    ├── .env.example
    ├── providers.yaml
    ├── migrations/
    ├── resources/themes/
    ├── static/
    ├── templates/
    ├── services/
    ├── models/
    ├── adapters/
    ├── tasks/
    ├── routes/
    ├── schemas/
    ├── utils/
    ├── ainews_cli/
    └── ainews_config/
```

### 2.1 Required Entries

The release workflow validates these entries exist before packaging. Missing entries cause a build failure:

**Directories:**
`migrations`, `resources/themes`, `static`, `templates`, `services`, `models`, `adapters`, `tasks`, `routes`, `schemas`, `utils`, `ainews_cli`, `ainews_config`

**Files:**
`pyproject.toml`, `.env.example`, `providers.yaml`, `ainews` (wrapper script)

**Docker manifests:**
`docker-compose.yml`, `docker-compose.ollama.yml`

### 2.2 Exclusions

The following are excluded from the tarball (via `rsync` in the release workflow):

- `.git/`, `.github/` — repository metadata
- `.venv/` before assembly, re-added after — ensures clean platform-specific venv
- `staging/`, `htmlcov/`, `*.pyc`, `__pycache__/` — build artifacts
- `.mypy_cache/`, `.ruff_cache/` — linter caches
- `instance/` — development database directory
- `*.egg-info/`, `dist/`, `build/` — Python packaging artifacts

### 2.3 Safety Validation

The installer rejects tarballs containing:
- Absolute paths (e.g. `/etc/passwd`)
- `..` path traversal (e.g. `ainews/../../etc/passwd`)
- Symlinks escaping the extraction root
- Device nodes, FIFOs, or Unix sockets
- Hardlinks

---

## 3 — Wrapper Entry Point

The `ainews` script at the tarball root is a thin Bash wrapper:

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/.venv/bin/ainews" "$@"
```

It delegates to the CLI installed inside `.venv/`. The installer creates a symlink from the platform bin directory to this script.

---

## 4 — Post-Install Directory Layout

The installer extracts the tarball to `app_dir` and creates four operator-managed directories outside the application root:

```
install_root/                          # Varies by mode (see §4.1)
├── app/                               # app_dir — immutable after install
│   ├── ainews                         # Wrapper entry point
│   ├── .venv/                         # Python virtual environment
│   ├── pyproject.toml
│   ├── docker-compose.yml
│   ├── docker-compose.ollama.yml
│   ├── .env.example
│   ├── providers.yaml                 # Default provider config
│   ├── migrations/
│   ├── resources/themes/
│   ├── static/
│   ├── templates/
│   ├── services/
│   ├── models/
│   ├── adapters/
│   ├── tasks/
│   ├── routes/
│   ├── schemas/
│   ├── utils/
│   ├── ainews_cli/
│   └── ainews_config/
├── config/                            # config_dir — operator-managed
│   ├── install-metadata.json
│   ├── .env                           # Secrets (not in app root)
│   ├── providers.yaml                 # Operator overrides
│   ├── pipeline.yaml
│   ├── sources.yaml
│   └── topics.yaml
├── data/                              # data_dir — operator-managed
│   ├── instance/                      # SQLite database, embeddings
│   └── backups/                       # Versioned backups
├── state/                             # state_dir — operator-managed
│   ├── logs/
│   └── cache/
└── bin/                               # bin_dir — CLI symlink
    └── ainews -> ../app/ainews
```

### 4.1 Default Paths by Install Mode

| Directory | User mode | System mode |
|-----------|-----------|-------------|
| `app_dir` | `~/.local/share/ainews/app/` | `/opt/ainews/app/` |
| `config_dir` | `~/.config/ainews/` | `/etc/ainews/` |
| `data_dir` | `~/.local/share/ainews/data/` | `/var/lib/ainews/` |
| `state_dir` | `~/.local/state/ainews/` | `/var/log/ainews/` |
| `backup_dir` | `~/.local/share/ainews/backups/` | `/var/lib/ainews/backups/` |
| `bin_dir` | `~/.local/bin/` | `/usr/local/bin/` |

All paths can be overridden via environment variables (`AINEWS_CONFIG_DIR`, `AINEWS_DATA_DIR`, etc.) or the `--prefix` installer flag.

---

## 5 — Immutability Contract

### 5.1 Immutable (Application Root)

The `app_dir` is **read-only after installation**. Operators must not edit files inside it. The upgrade path is:

1. Installer backs up current `app_dir` to `backup_dir`
2. Installer extracts new tarball to staging, then copies into `app_dir`
3. Previous `app_dir` contents are replaced atomically

Application source, virtual environment, migrations, static assets, and templates are all part of the immutable application root.

### 5.2 Mutable (Operator Directories)

These directories are **managed by operators** and persist across upgrades:

| Directory | Contents | Mutated by |
|-----------|----------|------------|
| `config_dir` | `.env`, `providers.yaml`, `pipeline.yaml`, `sources.yaml`, `topics.yaml`, `install-metadata.json` | Operator, `ainews config set`, `ainews onboard` |
| `data_dir` | SQLite database (`ainews.db`), embedding index | Application runtime |
| `state_dir` | Application logs, L1/L2 caches | Application runtime |
| `backup_dir` | Timestamped copies of previous `app_dir` | Installer on upgrade |

### 5.3 Configuration Layering

Operator config files in `config_dir` override defaults in `app_dir`:

- `providers.yaml` in `config_dir` merges with (or replaces) `providers.yaml` in `app_dir`
- `.env` in `config_dir` provides secrets never shipped in the tarball
- `pipeline.yaml`, `sources.yaml`, `topics.yaml` in `config_dir` override application defaults

---

## 6 — Install Metadata

The installer writes `install-metadata.json` to `config_dir`:

```json
{
  "schema_version": 1,
  "install_type": "stable",
  "version": "1.2.0",
  "commit": "",
  "artifact": "ainews-1.2.0-linux-x86_64.tar.gz",
  "artifact_sha256": "abc123...",
  "installed_at": "2026-07-15T12:00:00Z",
  "install_root": "/home/user/.local/share/ainews",
  "config_dir": "/home/user/.config/ainews",
  "data_dir": "/home/user/.local/share/ainews/data",
  "state_dir": "/home/user/.local/state/ainews",
  "installer_version": "1.0.0"
}
```

This file is consumed by `ainews_config.paths.resolve_paths()` to locate directories at runtime. The `install_type` field distinguishes `stable`, `prerelease`, and `main` channel installations.

---

## 7 — Checksum Verification

The installer performs checksum verification before extraction:

1. Download `SHA256SUMS` file from the same release URL as the tarball
2. Compute SHA-256 of the downloaded tarball
3. Compare against the expected checksum
4. Abort with a user-facing error on mismatch (suggests deleting cached artifact and retrying)

The checksum is also recorded in `install-metadata.json` for auditability.

---

## 8 — Upgrade Flow

Upgrades follow the same installer path as fresh installs:

1. Existing `app_dir` is backed up to `backup_dir` as `ainews-backup-{timestamp}/`
2. New tarball is extracted to a temporary staging directory
3. Staging contents are copied into `app_dir`, replacing previous files
4. `config_dir`, `data_dir`, and `state_dir` are **not touched** — operator state persists
5. New `install-metadata.json` is written with updated version and checksum

Rollback: copy a previous backup from `backup_dir` back into `app_dir`.
