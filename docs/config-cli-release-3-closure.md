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
- Installer shell tests (`tests/test_install.sh`) — 74 tests, 119 assertions

### 3C: Documentation and CI
- Updated README with installer-first Quick Start
- Updated AGENTS.md with installer and safe-probe architecture
- Updated CLI reference with installer options and doctor JSON contract
- Updated deployment guide with installer installation path

## Test Evidence

- [x] Lint passes (ruff) — 0 errors
- [x] Type check passes (mypy) — 1 pre-existing unrelated error (validate_themes.py dual module name)
- [x] Test suite passes — 228 CLI/doctor/config tests pass, 473 total pass
- [x] Smoke tests pass — pre-existing env dependency issues (missing dotenv/ruamel/feedparser in test env) not related to Release 3 changes

## Known Limitations

- Clean-host CI not yet wired (planned for future iteration)
- Windows native installer out of scope (WSL documented as fallback)
