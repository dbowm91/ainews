# ainews Configuration and Operator CLI — Release 4C Update and Uninstall

## Objective

Add safe channel-aware updates and conservative uninstall behavior on top of the verified Release 3 artifact system and Release 4B backup/restore foundation. Updates must be staged, integrity-verified, migration-aware, health-checked, and automatically recoverable. Uninstall must preserve operator-owned state by default.

## Command surface

```bash
ainews update check
ainews update plan
ainews update apply
ainews update rollback
ainews update status
ainews channel show
ainews channel set stable|prerelease|main

ainews uninstall
ainews uninstall --remove-app-only
ainews uninstall --purge --yes
```

## Preconditions

Do not begin update implementation until:

- immutable artifacts and checksum verification from Release 3 are stable;
- install metadata identifies current version/channel/commit;
- backup create and verify are complete;
- restore and rollback paths pass integration tests;
- migration planning exists for configuration and database state.

## Workstream 1 — Update metadata and state machine

Define persistent update state, for example:

```text
idle
-> checking
-> planned
-> downloading
-> verified
-> backed_up
-> staged
-> migrating
-> activated
-> validating
-> complete
```

Failure states must retain enough metadata to resume or roll back safely.

Record:

- operation ID;
- source and target versions/commits;
- channel;
- artifact and checksum;
- backup ID;
- staging and previous-version paths;
- migration plan/results;
- health validation results;
- final outcome and remediation.

Never store credentials.

## Workstream 2 — Update check and planning

`ainews update check` must:

- resolve the configured channel through the same trusted metadata path as the installer;
- compare semantic versions and exact commits correctly;
- distinguish upgrade, downgrade, reinstall, and no-op;
- handle prerelease ordering;
- report minimum supported source version;
- avoid downloading artifacts unless requested.

`ainews update plan` must additionally report:

- artifact size and checksum identity;
- application/config/database migration steps;
- service downtime or restart impact;
- required backup space;
- incompatibilities and blockers;
- rollback capability;
- paths that will change.

Support JSON and dry-run output.

## Workstream 3 — Artifact acquisition and staging

Reuse Release 3 artifact resolution, download, checksum, and archive-validation code. Do not fork a separate updater downloader.

Requirements:

- stage beside the current immutable application root;
- never overwrite the active version during download/extraction;
- validate artifact manifest and version identity;
- prevent concurrent install/update/restore operations through shared locks;
- preserve at least the immediately previous application version until validation succeeds;
- enforce disk-space preflight;
- clean stale staging directories safely.

## Workstream 4 — Automatic pre-update backup

Before any migration or activation:

- create a full backup through Release 4B;
- verify it;
- record the backup ID in update state;
- refuse the update if no verified backup can be produced, unless an explicit expert override exists and is strongly warned;
- never prune the pre-update backup until the update retention window expires.

## Workstream 5 — Migration and activation

Apply migrations against staged copies where possible.

Recommended sequence:

1. stop or quiesce services;
2. snapshot/backup verified;
3. stage new application;
4. copy mutable config/data to a migration staging root when feasible;
5. run migration preflight;
6. apply configuration and database migrations;
7. validate migrated config and database;
8. atomically switch the active application pointer/path;
9. replace migrated mutable state under rollback protection;
10. start services;
11. run bounded health and smoke checks.

Avoid in-place irreversible mutations before a verified rollback path exists.

## Workstream 6 — Automatic rollback

Rollback triggers include:

- migration failure;
- application startup failure;
- readiness timeout;
- critical doctor failure;
- smoke-test failure;
- operator interrupt during a protected phase where safe recovery is possible.

Rollback must:

- reactivate the previous application artifact;
- restore compatible config/data from the pre-update backup when migrations changed them;
- restore ownership and permissions;
- restart the previous version;
- run health validation;
- retain logs and update state for diagnosis;
- clearly report whether rollback itself succeeded, degraded, or failed.

`ainews update rollback` should support explicit rollback during a documented retention window and refuse when compatibility cannot be guaranteed.

## Workstream 7 — Channel management

`ainews channel set` must:

- validate allowed channels;
- show current and proposed resolution behavior;
- require confirmation when switching to prerelease or main;
- modify install metadata transactionally;
- not implicitly update unless `--apply` is explicitly selected;
- preserve pinned explicit versions when that policy is chosen;
- document downgrade behavior.

## Workstream 8 — Uninstall model

Default uninstall removes only immutable application files, command shims, and service definitions owned by the installation.

Default preservation:

- config;
- database and application data;
- state needed for recovery;
- backups;
- user-created exports.

Before removing anything:

- inspect install metadata;
- verify each target is owned by this installation and lies under approved roots;
- stop/remove installed services through the service abstraction;
- show a deletion plan;
- support dry-run;
- require confirmation.

`--purge` must be separate, explicit, and require `--yes` in non-interactive mode. It should offer or require a final verified backup before deleting mutable state.

Never recursively delete a path derived from empty, root, home, or unresolved variables.

## Workstream 9 — Interrupted operation recovery

On startup of update/uninstall commands, detect incomplete operations and provide:

- resume;
- rollback;
- abandon staging after verification;
- manual recovery instructions.

Do not silently discard operation state.

## Workstream 10 — Tests

Add fixture-server and filesystem integration tests for:

- no update available;
- stable/prerelease/main resolution;
- version ordering and downgrade detection;
- checksum mismatch;
- insufficient disk space;
- concurrent operation lock;
- backup failure blocks update;
- migration success;
- migration failure rollback;
- health-check failure rollback;
- rollback failure reporting;
- interrupted phase recovery;
- channel switch confirmation;
- uninstall app-only preservation;
- malicious/untrusted install metadata path rejection;
- purge confirmation and final backup;
- dry-run byte-for-byte no-write behavior;
- secret-free logs and JSON.

Maintain at least one previous-version fixture that exercises a real migration.

## Documentation

Document:

- channel semantics;
- support window and minimum source version;
- update phases and expected downtime;
- backup and rollback behavior;
- recovery from interrupted updates;
- explicit downgrade limitations;
- default uninstall preservation;
- purge implications;
- manual recovery commands.

## Acceptance criteria

- update check and planning are non-mutating and deterministic;
- updates reuse the verified artifact acquisition implementation;
- every update creates and verifies a pre-update backup;
- activation is staged and previous application artifacts remain available through validation;
- migration/startup/health failures automatically roll back;
- incomplete operations are resumable or recoverable;
- channel changes are explicit and transactional;
- uninstall preserves config/data/backups by default;
- purge requires explicit confirmation and path ownership checks;
- tests cover at least one real previous-version upgrade and rollback.
