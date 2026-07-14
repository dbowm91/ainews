# CLI Reference

The `ainews` operator CLI provides configuration management and system diagnostics. It is independent of the Flask application and works outside the repository directory.

## Installation

```bash
pip install -e .
```

This registers the `ainews` console command via `pyproject.toml` `[project.scripts]`.

## Global Options

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Verbose output |
| `--quiet`, `-q` | Suppress non-error output |
| `--json`, `-j` | Output in JSON format |
| `--no-color` | Disable colored output |

## Commands

### `ainews version`

Show package version, Python version, and git commit (when available).

**Output:** Human-readable version info, or JSON with `version`, `python`, `git_commit` fields.

---

### `ainews config path`

Show all resolved configuration paths with provenance, existence, and writability.

**Output:** Table with columns: Path, Provenance, Exists, Writable.

**Provenance values:**
- `explicit` — CLI option override
- `environment` — Environment variable
- `install_metadata` — Install metadata file
- `platform_default` — OS canonical location
- `development` — Repository-local fallback

---

### `ainews config show`

Show effective configuration values grouped by file. Secrets are redacted by default.

**Options:**
- `--show-secrets` — Reveal secret values (unsafe, not recommended)

---

### `ainews config check`

Run offline syntax, schema, semantic, and production-policy validation.

**Options:**
- `--production` — Include production-specific checks
- `--json` — Machine-readable output

**Exit codes:**
- `0` — All checks passed
- `3` — Validation errors found

---

### `ainews config get KEY`

Return a typed value by dotted key. Secrets are redacted.

**Arguments:**
- `KEY` — Configuration key in dotted notation (e.g., `pipeline.writer.model`)

**Exit codes:**
- `0` — Value found and displayed
- `5` — Key not found

---

### `ainews config set KEY VALUE`

Set a configuration value. Parses through the field registry, stages the change, validates, and commits atomically.

**Arguments:**
- `KEY` — Configuration key in dotted notation
- `VALUE` — New value (parsed according to field type)

**Options:**
- `--dry-run` — Show what would change without writing

**Exit codes:**
- `0` — Value set successfully
- `2` — Configuration error
- `7` — Lock acquisition failed

---

### `ainews config set-secret KEY`

Set a secret configuration value. Reads from stdin or prompts interactively.

**Arguments:**
- `KEY` — Configuration key in dotted notation

**Note:** Do not pass secret values as command arguments — they would appear in shell history.

---

### `ainews config unset KEY`

Remove an optional configuration override, restoring the default.

**Arguments:**
- `KEY` — Configuration key in dotted notation

**Exit codes:**
- `0` — Override removed
- `2` — Attempted to remove a required value

---

### `ainews config diff`

Compare current configuration with packaged defaults.

**Options:**
- `--baseline SNAPSHOT` — Compare with a specific rollback snapshot

**Output:** Diff showing added, changed, and removed values (secrets redacted).

---

### `ainews config rollback`

List available rollback snapshots or restore a specific one.

**Options:**
- `--list` — List all available snapshots
- `--restore TRANSACTION_ID` — Restore a specific snapshot

---

### `ainews doctor`

Run offline system and configuration diagnostics.

**Options:**
- `--production` — Include production-specific checks

**Checks performed:**
- Package version availability
- Resolved path existence
- Directory writability
- YAML config file parsing
- Cross-file configuration validation
- Secret file permissions
- Docker/Compose availability
- Python/uv availability
- Database directory writability

**Exit codes:**
- `0` — All checks passed
- `1` — One or more checks failed

## Exit Codes

| Code | Name | Description |
|------|------|-------------|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `GENERAL_ERROR` | Unrecoverable error |
| `2` | `CONFIG_ERROR` | Configuration file error |
| `3` | `VALIDATION_ERROR` | Configuration validation failed |
| `4` | `IO_ERROR` | File system error |
| `5` | `NOT_FOUND` | Requested resource not found |
| `6` | `PERMISSION_ERROR` | Insufficient permissions |
| `7` | `LOCK_ERROR` | Could not acquire configuration lock |
| `8` | `ROLLBACK_ERROR` | Rollback operation failed |

## Configuration Precedence

The CLI resolves configuration through this precedence chain:

1. **Explicit CLI options** (highest priority)
2. **Environment variables** (e.g., `AINEWS_CONFIG_DIR`)
3. **Install metadata** (`install-metadata.json`)
4. **Platform canonical location** (`~/.config/ainews/` on Linux)
5. **Repository-local fallback** (development mode, when `.git` detected)

## Secret Handling

- Secrets are redacted in all output by default (`***` or `****xxxx`)
- `config set-secret` reads from stdin to avoid shell history exposure
- `--show-secrets` is not available in Release 1
- Secret file permissions (`.env`) are checked by `doctor`
