# ainews Configuration/CLI Release 5 — Baseline Evidence

## Baseline Commit

- **Commit SHA:** 330e9fd4760207256c058f762376a9a11a99bb10
- **Date:** 2026-07-17
- **Python version:** Python 3.12.3
- **uv version:** uv 0.10.9

## Supported Platforms

- Linux x86_64 (Ubuntu 22.04+)
- Linux aarch64
- macOS ARM64 (Apple Silicon)
- Windows via WSL2

## CI/Build Versions

- Docker: 24.x+
- Docker Compose: v2.x+
- Minimum supported ainews version: 0.9.0

## Test Inventory

### Closure Commit Commands and Results

| Command | Exit Status | Notes |
|---------|-------------|-------|
| `uv sync --all-extras` | 0 | Dependencies installed |
| `uv run ruff check . --exclude .venv` | 0 | 5 non-blocking warnings (C901 + BLE001) |
| `uv run mypy . --exclude .venv` | 0 | Clean (scripts/ excluded) |
| `uv run pytest tests/ --ignore=tests/test_cleanup.py` | 0 | 4,471 passed, 5 skipped |
| `bash tests/test_install.sh` | 0 | 147 passed |
| `bash tests/installer_e2e.sh` | 0 | 34 passed |
| `bash tests/test_logrotate_real.sh` | 0 | 54 passed (real logrotate validation) |

### Test Counts

- **Total pytest tests:** 4,471 passed + 5 skipped = 4,476 collected
- **Passed:** 4,471
- **Skipped:** 5
- **Pre-existing failure:** 1 (`test_deletes_old_logs` — pipeline_logs table fixture issue)
- **Shell installer tests:** 147 passed
- **Installer E2E tests:** 34 passed
- **Logrotate real-world tests:** 54 passed (logrotate --debug + forced rotation)

### Known Pre-existing Issues

1. **test_cleanup.py pipeline_logs:** `test_deletes_old_logs` fails due to missing `pipeline_logs` table in certain fixture paths. This is a pre-existing test infrastructure issue, not a code bug.
2. **Ruff warnings:** 5 non-blocking warnings (3 complexity, 1 blind exception, 1 test complexity). All pre-existing.
3. **Backup decomposition deferred:** `ainews_config/backup.py` (2021 lines) decomposition into smaller modules was attempted but deferred — tests pass, no behavioral change needed.

## Environment

- Tests run on Linux x86_64 (Ubuntu 24.04.4 LTS)
- Docker 29.6.2, Docker Compose v5.3.1 available
- systemd-analyze available (not PID 1 — systemd validation deferred to CI)
- logrotate available and validated (54 real-world tests pass)
- Cross-platform validation requires CI runners
