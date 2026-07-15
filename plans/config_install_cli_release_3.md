# ainews Configuration and Operator CLI — Release 3 Detailed Plan

## Release objective

Release 3 turns the completed configuration, onboarding, provider, lifecycle, and doctor foundations into a supported installation path. The release must produce a thin, integrity-verified installer, stable install metadata, production-grade diagnostics, and clean-host CI evidence.

Release 3 assumes Releases 1 and 2 are closed. Do not duplicate configuration or onboarding policy in shell. The installer acquires and installs the application, records where it was installed, and delegates setup to `ainews onboard` and validation to `ainews doctor`.

## User-visible result

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash

ainews onboard
ainews start
ainews doctor --production --network
```

Channel selection:

```bash
AINEWS_CHANNEL=stable ./scripts/install.sh
AINEWS_CHANNEL=prerelease ./scripts/install.sh
AINEWS_CHANNEL=main ./scripts/install.sh
```

Non-interactive flow:

```bash
AINEWS_BOOTSTRAP_ADMIN_PASSWORD_FILE=/run/secrets/ainews-admin \
  ./scripts/install.sh --non-interactive --bootstrap ./bootstrap.yaml --start
```

## Release plan index

1. `plans/config_install_cli_release_3a_safe_probe_and_diagnostics.md`
   - route doctor source probes through production-safe fetch policy;
   - finalize pass/warn/fail/skip semantics and stable JSON contracts;
   - verify production and network diagnostic tiers.
2. `plans/config_install_cli_release_3b_artifacts_and_installer.md`
   - define immutable artifacts and checksums;
   - implement the thin channel-aware installer;
   - create canonical directories and install metadata.
3. `plans/config_install_cli_release_3c_clean_host_ci_and_docs.md`
   - exercise install/onboard/start on clean Linux hosts;
   - add installer failure-path and checksum tests;
   - replace the README quick start only after the supported path passes.

## Required architecture

```text
release workflow
  -> immutable versioned archive/wheel/container metadata
  -> SHA-256 manifest

scripts/install.sh
  -> platform and prerequisite detection
  -> channel resolution
  -> artifact and checksum download
  -> integrity verification
  -> atomic extraction or package installation
  -> canonical directory creation
  -> install metadata write
  -> optional `ainews onboard`
  -> optional `ainews start`
```

The shell installer must not:

- generate application secrets itself;
- edit `.env` or YAML configuration directly;
- implement provider-specific behavior;
- run database migrations outside the CLI lifecycle path;
- silently install broad system dependencies;
- execute unverified remote payloads.

## Channel contract

### `stable`

- resolves to the latest non-prerelease GitHub release;
- downloads immutable assets attached to that release;
- requires checksum verification;
- never resolves to a moving branch archive.

### `prerelease`

- resolves to the latest GitHub prerelease;
- clearly marks the installation as prerelease;
- uses the same immutable artifact and checksum rules.

### `main`

- intended for development and evaluation;
- resolves to an exact commit SHA before installation;
- records that SHA in install metadata;
- still verifies a generated archive checksum when feasible;
- must not be presented as the default production path.

## Install metadata

Write a versioned metadata document in the canonical state directory, for example:

```json
{
  "schema_version": 1,
  "channel": "stable",
  "version": "1.4.0",
  "commit": "...",
  "artifact": "ainews-1.4.0-linux-x86_64.tar.gz",
  "artifact_sha256": "...",
  "installed_at": "...",
  "install_root": "...",
  "config_dir": "...",
  "data_dir": "...",
  "state_dir": "...",
  "installer_version": "..."
}
```

Requirements:

- write atomically;
- use restrictive permissions where metadata contains sensitive path information;
- never include credentials or generated secrets;
- preserve enough provenance for later update, rollback, and uninstall commands;
- make the path resolver consume this metadata at the existing precedence level.

## Installation modes

### User installation

Default to user-owned canonical paths and avoid root:

```text
~/.local/share/ainews/app/
~/.config/ainews/
~/.local/state/ainews/
~/.local/bin/ainews
```

### System installation

Require explicit selection and privilege:

```text
/opt/ainews/
/etc/ainews/
/var/lib/ainews/
/var/log/ainews/
/usr/local/bin/ainews
```

Do not silently switch to system mode merely because the installer is run with `sudo`.

## Prerequisite policy

The installer may detect and explain missing requirements. It should not become a distribution-specific package manager abstraction.

Required behavior:

- detect supported OS and architecture;
- detect `curl` or an equivalent downloader;
- detect checksum tooling;
- detect Python/`uv` only when the chosen artifact requires them;
- detect Docker and Compose for Docker profiles;
- allow installation to complete when Docker is absent if onboarding/start are deferred;
- print exact remediation commands or links without executing package-manager changes by default.

## Resumability and idempotency

- rerunning the same installer/version must be safe;
- existing config and data directories must not be overwritten;
- partially extracted artifacts must be staged outside the final install root;
- final replacement must be atomic where the platform permits;
- an interrupted install must leave either the previous complete version or no active installation;
- onboarding may be resumed using its existing state file;
- install metadata is written only after artifact installation succeeds.

## Security requirements

- use `set -eu` and carefully scoped pipe handling;
- quote all variables and paths;
- reject unsafe path traversal and newline-containing inputs;
- use HTTPS endpoints only unless an explicit development override is selected;
- verify SHA-256 before extraction or execution;
- validate archive members before extraction;
- reject symlink or hardlink escapes from the staging root;
- never log secret environment-variable values;
- never pass bootstrap secrets on process command lines when stdin/file references are available;
- preserve restrictive permissions for config and state directories.

## Cross-platform scope

Required for Release 3:

- Linux x86_64;
- Linux arm64;
- macOS arm64 where current dependencies support it.

Windows native installation is out of scope unless the repository already has a supported runtime path. Document WSL as the fallback rather than adding an untested PowerShell installer.

## Ordered implementation

1. Complete Release 3A safe-probe and diagnostic contract work.
2. Define release artifact layout and checksum manifest.
3. Add release workflow generation and validation.
4. Implement installer parsing, platform detection, and channel resolution.
5. Add staging, verification, extraction, and metadata writes.
6. Integrate optional onboarding/start delegation.
7. Add clean-host and fault-injection CI.
8. Replace primary installation documentation.
9. Commit a Release 3 closure record.

## Release gates

Release 3 is complete only when:

- a clean supported host can install from one documented command;
- the downloaded artifact is immutable and checksum-verified;
- installation works outside a repository checkout;
- missing Docker can produce a successful deferred installation;
- non-interactive bootstrap can complete without plaintext secrets in arguments or logs;
- `ainews doctor --production --network --json` has a stable tested schema;
- source diagnostics use the same safe network policy as production fetching;
- clean-host CI installs, onboards, starts, checks health, and stops the stack;
- interrupted and corrupted downloads do not replace a working installation;
- the README points to the tested installer path;
- `docs/config-cli-release-3-closure.md` maps every gate to evidence.
