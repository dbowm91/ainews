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

### Baseline Commands and Results

| Command | Exit Status | Notes |
|---------|-------------|-------|
| `uv sync --all-extras` | 0 | Dependencies installed |
| `uv run ruff check . --exclude .venv` | 0 | 3 complexity warnings (C901), non-blocking |
| `uv run mypy . --exclude .venv` | 0 | 1 pre-existing module collision in scripts/validate_themes.py |
| `uv run pytest` | 0 | 4,434 passed, 8 flaky (pass on re-run), 5 skipped |
| `bash tests/test_install.sh` | 0 | 137 passed |
| `bash tests/installer_e2e.sh` | 0 | 34 passed |

### Test Counts

- **Total pytest tests:** 4,447 collected
- **Passed:** 4,434
- **Flaky (pass on re-run):** 8 (DNS cache state and timing related)
- **Skipped:** 5
- **Shell installer tests:** 137 passed
- **Installer E2E tests:** 34 passed

### Known Pre-existing Issues

1. **Mypy module collision:** `scripts/validate_themes.py` is discoverable under both `validate_themes` and `scripts.validate_themes`. This is a pre-existing issue that prevents mypy from checking the full codebase.
2. **Ruff C901 warnings:** 3 functions in `ainews_cli/service/` exceed complexity threshold (non-blocking).
3. **Flaky DNS tests:** 8 tests related to DNS cache state may fail when run in full suite but pass on re-run.

## Environment Notes

- Tests run on Linux x86_64
- No systemd available in test environment (service manager validation deferred)
- No logrotate available in test environment (logrotate validation deferred)
- Cross-platform validation requires CI runners
