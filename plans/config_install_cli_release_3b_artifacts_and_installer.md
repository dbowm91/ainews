# ainews Configuration and Operator CLI — Release 3B Artifacts and Installer

## Objective

Create the supported acquisition and installation path for ainews. The result must be a small auditable shell installer backed by immutable release artifacts, checksums, atomic staging, canonical paths, and install metadata. All application policy remains in the Python CLI.

## Workstream 1 — Define artifact contract

Choose and document the installable artifact layout for each supported platform.

The artifact must contain or reference:

- the application package and locked runtime dependencies;
- the `ainews` console entry point;
- Docker Compose manifests and required templates;
- migrations and packaged default configuration;
- static assets and Halloy themes;
- version and build provenance;
- license and minimum installation documentation.

Artifact names must be deterministic, for example:

```text
ainews-1.4.0-linux-x86_64.tar.gz
ainews-1.4.0-linux-aarch64.tar.gz
ainews-1.4.0-macos-arm64.tar.gz
SHA256SUMS
SHA256SUMS.sig            # optional future signing layer
```

Define exactly which files are mutable after installation and keep config/data outside the immutable application root.

## Workstream 2 — Release workflow

Add a release workflow that:

1. checks out an exact tag or commit;
2. installs locked dependencies;
3. runs lint, type checks, and the relevant test suite;
4. builds each platform artifact;
5. validates artifact contents;
6. computes SHA-256 checksums;
7. uploads immutable assets to the GitHub release;
8. records build provenance in a manifest.

The workflow must fail when:

- tracked files are missing from the artifact;
- generated assets differ from committed manifests;
- package version and tag disagree;
- checksums are missing;
- tests fail;
- the archive contains absolute paths or traversal entries.

## Workstream 3 — Installer command-line contract

Implement `scripts/install.sh` with explicit options:

```text
--channel stable|prerelease|main
--version VERSION
--commit SHA
--user
--system
--prefix PATH
--non-interactive
--bootstrap PATH
--start
--no-onboard
--download-only
--dry-run
--yes
--help
```

Environment variables may mirror options, but command-line precedence must be documented. Sensitive values must use file, stdin, or environment references consumed by the CLI, never installer positional arguments.

The parser must reject unknown flags, conflicting modes, invalid channels, empty paths, and unsafe values.

## Workstream 4 — Platform and prerequisite detection

Detect:

- operating system;
- CPU architecture;
- libc requirements if relevant;
- writable destination locations;
- downloader availability;
- checksum tool availability;
- archive extraction tools;
- Docker and Docker Compose when startup is requested.

Normalize architecture names (`x86_64`, `amd64`, `aarch64`, `arm64`) to artifact identifiers.

Do not automatically run apt, dnf, yum, pacman, brew, or other package managers. Print targeted remediation and support deferred onboarding/start.

## Workstream 5 — Channel and version resolution

Implement deterministic resolution:

- stable: latest non-prerelease release or explicit version;
- prerelease: latest prerelease or explicit version;
- main: exact commit SHA, resolving the branch head once and recording it;
- reject ambiguous or mutable version specifications after resolution;
- print the resolved version/commit before download in interactive mode;
- include resolved URLs in dry-run output without credentials.

Use GitHub API responses defensively and handle rate limits, missing assets, malformed metadata, and partial responses.

## Workstream 6 — Download and integrity verification

- download to a private temporary directory;
- use bounded retries with clear failure messages;
- download checksum manifest separately;
- select the exact artifact entry;
- calculate SHA-256 locally;
- compare using constant-format normalized lowercase hex;
- fail closed on missing, duplicate, malformed, or mismatched checksum entries;
- never extract or execute before successful verification;
- clean temporary files through traps.

`--download-only` should leave the verified artifact and checksum in an explicit destination and print their paths.

## Workstream 7 — Safe extraction and atomic installation

Before extraction, inspect archive members and reject:

- absolute paths;
- `..` traversal;
- device nodes;
- FIFO/socket entries;
- symlink or hardlink targets escaping the staging root;
- unexpected top-level directories.

Extract into a staging directory adjacent to the final install root. Validate the expected manifest and executable entry point, then atomically rename into place where supported.

For an existing installation:

- never delete config, data, state, or backups;
- preserve the current application version until the new version is fully staged;
- Release 3 may refuse replacement and direct operators to the future update command unless explicit same-version repair behavior is defined;
- do not implement an unsafe ad hoc upgrade path ahead of Release 4 backup/restore.

## Workstream 8 — Canonical paths and metadata

Create user or system directories with documented permissions. Write install metadata atomically after successful installation.

Ensure the installed CLI can resolve:

- application root;
- config directory;
- data directory;
- state directory;
- backup directory;
- Compose manifest location.

Add `ainews version --json` or equivalent output that includes installed version, channel, commit, and metadata path without leaking private information.

## Workstream 9 — Delegation to onboarding and lifecycle

After installation:

- default interactive behavior may prompt to run `ainews onboard`;
- `--non-interactive --bootstrap` delegates directly to the existing onboarding command;
- `--start` delegates to `ainews start` only after onboarding/config validation succeeds;
- propagate CLI exit codes;
- print the exact resume command on failure;
- do not roll back the installed artifact merely because onboarding was deferred or failed, unless the installation itself is invalid.

## Workstream 10 — Tests

Add shell tests using Bats or the repository’s preferred harness for:

- argument parsing and precedence;
- platform normalization;
- stable/prerelease/main resolution;
- checksum success and mismatch;
- missing checksum entry;
- interrupted download;
- malicious archive members;
- unwritable destination;
- rerun/idempotency;
- deferred Docker behavior;
- onboarding delegation and exit-code propagation;
- secrets absent from process arguments and logs;
- user versus system path selection.

Use local fixture servers or mocked commands; normal tests must not download public release assets.

## Acceptance criteria

- release assets are immutable, versioned, and checksum-verified;
- installer shell code contains no application configuration policy;
- installation never extracts an unverified artifact;
- unsafe archive members are rejected;
- config/data/state survive reruns and failed installs;
- install metadata is complete, atomic, and consumed by path resolution;
- installation can succeed without Docker when startup is deferred;
- interactive and non-interactive onboarding delegate to the same CLI path;
- shell tests cover success and failure paths;
- installer output is actionable and contains no secrets.
