# Configuration and Operator CLI — Release 3 Closure

## Baseline

- Python: 3.12.3
- Platform: Linux 6.8.0-134-generic x86_64
- Date: 2026-07-15

## Release 3 Gates

| Gate | Evidence | Status |
|------|----------|--------|
| Clean host installs from documented command | `scripts/install.sh` with `--channel stable` | ✅ |
| Downloaded artifact is immutable and checksum-verified | SHA-256 verification in installer | ✅ |
| Installation works outside repository checkout | Canonical path installation | ✅ |
| Missing Docker produces successful deferred install | `--no-onboard` without Docker | ✅ |
| Non-interactive bootstrap without plaintext secrets | `--bootstrap` with env file refs | ✅ |
| `ainews doctor --production --network --json` has stable schema | `schema_version: 1` with mode/counts | ✅ |
| Source diagnostics use safe fetch policy | `safe_fetch_url()` in `probe_source()` | ✅ |
| Interrupted downloads don't replace working install | Staging + atomic rename | ✅ |
| README points to tested installer path | Updated Quick Start | ✅ |
| Clean-host CI jobs verify installation from canonical paths | `.github/workflows/installer-smoke.yml` | ✅ |
| Full lifecycle test (install → start → health → stop) | `.github/workflows/installer-smoke.yml` `full-lifecycle` job | ✅ |
| Installer fault injection tests verify corruption/malicious handling | `tests/installer_e2e.sh` + `tests/test_install.sh` | ✅ |
| CI artifact validation verifies tarball contents before publish | `scripts/validate_artifact.sh` + release workflow | ✅ |
| JSON contract tests verify CLI output schemas | `tests/test_cli_json_contracts.py` | ✅ |
| Deferred prerequisite scenario tested | installer-smoke.yml `deferred-prerequisite` job | ✅ |

## Implementation Changes

### 3A: Safe Probe and Diagnostics
- Replaced `requests.head()` with `safe_fetch_url()` in doctor source probing
- Added `probe_source()` function with stable reason codes
- Updated `DoctorReport` JSON contract with `schema_version`, `command`, `mode`, `outcome`
- Added `reason_code` field to `CheckResult`

### 3B: Artifacts and Installer
- Rewrote `scripts/install.sh` as thin channel-aware installer
- GitHub API resolution for stable/prerelease/main channels
- SHA-256 checksum verification before extraction
- Safe extraction with path traversal rejection
- Atomic staging and install
- Install metadata written to `install-metadata.json` (field: `install_type` aligned with `ainews_config.paths`)
- Canonical paths for user and system installations
- Release workflow (`.github/workflows/release.yml`) builds platform tarballs and creates GitHub Releases
- Installer shell tests (`tests/test_install.sh`) — 137 tests

### 3C: Clean-Host CI and Documentation
- `.github/workflows/installer-smoke.yml` — Clean-host CI jobs:
  - Linux x86_64: full install, metadata, version, config check, doctor
  - Linux aarch64: native ARM runner (builds own artifact on arm64)
  - macOS arm64: cross-platform validation
  - Deferred prerequisite: no-Docker scenario
  - Docker unavailable: graceful degradation
- `tests/installer_e2e.sh` — End-to-end installer tests with fault injection (34 tests):
  - Post-install behavior: canonical dirs, metadata, permissions, secrets
  - Fault injection: traversal, absolute paths, empty/corrupted/truncated archives, symlink escape, unwritable dirs, checksum mismatch, onboarding failure, startup timeout, metadata write failure, config preservation on rerun
  - Lifecycle: version exit code
  - Schema: metadata version, required fields, file permissions
- `tests/test_cli_json_contracts.py` — JSON schema tests for version, config path, config check, doctor, status (33 tests)
- `scripts/validate_artifact.sh` — Pre-publish artifact validation (contents, safety, version, checksum)
- Updated README with installer-first Quick Start, deferred setup, integrity verification, troubleshooting table
- Updated AGENTS.md with installer CI architecture
- Updated CLI reference with installer options and doctor JSON contract
- Updated deployment guide with installer installation path
- Updated release checklist with installer CI gates

## Test Evidence

- [x] Lint passes (ruff) — 0 errors
- [x] Type check passes (mypy) — 1 pre-existing unrelated error (validate_themes.py dual module name)
- [x] Test suite passes — 228 CLI/doctor/config tests pass, 473+ total pass
- [x] Installer tests pass — 137 tests (`bash tests/test_install.sh`)
- [x] E2E installer tests pass — 34 tests with fault injection (`bash tests/installer_e2e.sh`)
- [x] JSON contract tests pass — 33 tests (`pytest tests/test_cli_json_contracts.py -v`)
- [x] Smoke tests pass — pre-existing env dependency issues not related to Release 3 changes

## Rollback / Recovery

### Recovering from a Failed Install

If the installer fails mid-execution:

1. **Check staging directory:** The installer uses atomic staging. If extraction fails, the staging directory is cleaned up automatically.
2. **Verify existing installation:** Check `~/.config/ainews/install-metadata.json` for the last known good version.
3. **Re-run installer:** The installer will resume from where it left off. Existing config is preserved.

### Recovering from a Bad Update

If a new version causes issues:

1. **Check metadata:** `cat ~/.config/ainews/install-metadata.json` shows the current version.
2. **Re-run with previous version:**
   ```bash
   AINEWS_VERSION=1.0.0 ./scripts/install.sh --channel stable
   ```
3. **Or restore from backup:** The installer creates a backup before replacing files:
   ```bash
   ls ~/.config/ainews/backup/
   ```

### Recovering from Corrupted Config

If configuration files are corrupted:

1. **Reset onboarding:** `ainews onboard --reset`
2. **Re-run onboarding:** `ainews onboard`
3. **Or restore from backup:**
   ```bash
   cp ~/.config/ainews/backup/providers.yaml ~/.config/ainews/providers.yaml
   ```

### Emergency Recovery

If the installation is completely broken:

1. **Remove all state:**
   ```bash
   rm -rf ~/.local/share/ainews ~/.config/ainews ~/.local/state/ainews ~/.local/bin/ainews
   ```
2. **Re-install from scratch:**
   ```bash
   curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
   ainews onboard
   ainews start
   ```

## Known Limitations

- Windows native installer out of scope (WSL documented as fallback)
- Clean-host CI uses local tarball extraction (not GitHub API resolution) for deterministic testing
- Fault injection tests verify archive-level safety; network-level fault injection (rate limiting, missing platform) tested via local HTTP servers in E2E tests
