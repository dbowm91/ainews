# ainews Configuration and Operator CLI — Release 4A Content Administration and OPML

## Objective

Eliminate routine manual editing of `sources.yaml`, `topics.yaml`, and `pipeline.yaml`. Add typed, transactional CLI administration with dry-run diffs, source testing through the shared safe-probe layer, restart-impact reporting, and idempotent OPML import/export.

## Command surface

```bash
ainews sources list
ainews sources show SOURCE_ID
ainews sources add
ainews sources update SOURCE_ID
ainews sources enable SOURCE_ID
ainews sources disable SOURCE_ID
ainews sources remove SOURCE_ID
ainews sources test SOURCE_ID
ainews sources import-opml FILE
ainews sources export-opml FILE

ainews topics list
ainews topics show TOPIC_ID
ainews topics add
ainews topics update TOPIC_ID
ainews topics remove TOPIC_ID

ainews pipeline show
ainews pipeline validate
ainews pipeline set-profile PROFILE
ainews pipeline assign ROLE PROVIDER_MODEL
ainews pipeline unassign ROLE
ainews pipeline diff
```

## Workstream 1 — Domain models and registries

Define typed service-layer models independent of Typer rendering:

- `SourceDefinition`;
- `SourceAdapterMetadata`;
- `TopicDefinition`;
- `PipelineRoleAssignment`;
- `ContentMutationResult`;
- `RestartImpact`.

Source adapter metadata should drive:

- required and optional fields;
- endpoint fields used for testing;
- authentication classification;
- default polling behavior;
- user-facing prompts;
- redaction rules;
- OPML representability.

Do not spread adapter-specific conditionals across command handlers.

## Workstream 2 — Source CRUD

Implement list/show/add/update/enable/disable/remove through the existing transaction engine.

Requirements:

- validate source IDs and prevent collisions;
- preserve unknown/custom YAML fields unless explicitly replaced;
- support interactive and non-interactive input;
- accept structured files for automation;
- redact credentials and sensitive query parameters;
- display adapter type, enabled state, endpoint summary, schedule, and last known validation state;
- show a redacted diff before commit in interactive mode;
- support `--dry-run` without writing;
- report whether worker restart or schedule refresh is required;
- avoid deleting associated historical data unless a separate future data-purge operation is explicitly requested.

Removal should require confirmation and explain consequences.

## Workstream 3 — Source testing

`ainews sources test` must reuse the Release 3A safe-probe service and, where practical, the source adapter’s parse/validation path.

Test layers:

1. schema validity;
2. URL and SSRF safety;
3. connectivity and authentication;
4. bounded response retrieval;
5. adapter-specific parseability;
6. optional sample-item normalization without persistence.

Output should separate configuration failure, safety block, transport failure, upstream failure, parse failure, and success. Never print response bodies or credentials by default.

## Workstream 4 — Topic CRUD

Implement typed topic administration.

Requirements:

- stable IDs distinct from display names;
- case and Unicode normalization policy;
- duplicate detection;
- include/exclude keyword or rule validation;
- cross-reference validation against pipeline/source configuration;
- transactional mutation;
- deterministic ordering;
- dry-run and JSON output;
- preserve unknown custom fields;
- clearly report whether changes require restart, worker refresh, or no action.

## Workstream 5 — Pipeline administration

Expose current pipeline roles and provider/model assignments without requiring direct YAML edits.

Requirements:

- validate provider existence and enabled state;
- validate model availability when network probing is explicitly requested;
- support offline assignment with a warning when availability cannot be confirmed;
- enforce required roles and role-specific constraints;
- apply named profiles as overlays without discarding custom settings;
- show restart impact;
- support a complete redacted diff;
- prevent partial multi-role updates through transaction staging;
- retain compatibility with provider CLI commands already implemented.

## Workstream 6 — OPML import

Implement safe OPML parsing with bounded XML processing.

Requirements:

- disable external entities and network resolution;
- cap file size, nesting depth, and outline count;
- accept standard RSS fields such as `xmlUrl`, `htmlUrl`, `title`, and category hierarchy;
- normalize and validate URLs through the same source safety policy;
- map categories to supported source metadata without inventing topic semantics silently;
- detect duplicates by normalized endpoint and stable ID;
- provide conflict strategies: skip, merge, replace, rename;
- default to dry-run preview before mutation;
- commit all accepted imports in one transaction;
- emit a machine-readable import report.

## Workstream 7 — OPML export

Export enabled or selected RSS-compatible sources.

Requirements:

- never include API keys, authorization headers, cookies, or secret query values;
- clearly skip non-representable source adapters and report them;
- deterministic ordering and formatting;
- standards-compatible XML escaping;
- atomic file write;
- restrictive permissions when output paths warrant it;
- round-trip tests for supported fields;
- support stdout only when secret-safety and terminal behavior are explicit.

## Workstream 8 — Tests

Add tests for:

- source CRUD and unknown-field preservation;
- duplicate and invalid IDs;
- safe-probe reuse;
- adapter-specific required fields;
- source removal confirmation;
- topic normalization and duplicate detection;
- pipeline cross-reference validation;
- multi-role transactional rollback;
- OPML XML entity rejection;
- oversized/deep OPML rejection;
- duplicate conflict strategies;
- secret-free export;
- import/export round trips;
- dry-run byte-for-byte no-write behavior;
- human/JSON parity and stable exit codes.

## Documentation

Update:

- CLI reference;
- source configuration reference;
- provider/pipeline documentation;
- OPML interoperability guide;
- migration guide from manual YAML editing;
- examples for RSS, API, web, Ollama/EggPool pipeline assignment.

## Acceptance criteria

- common source, topic, and pipeline changes require no manual YAML editing;
- all mutations are typed, transactional, validated, and recoverable;
- source tests use the shared safe-probe implementation;
- dry-run output accurately reflects committed changes;
- OPML import is bounded, entity-safe, and conflict-aware;
- OPML export contains no credentials;
- custom fields survive unrelated updates;
- integration tests cover rollback and representative adapters;
- documentation makes manual editing an advanced path rather than the primary workflow.
