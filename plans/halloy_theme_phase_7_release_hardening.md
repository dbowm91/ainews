# Halloy Theme Phase 7 — Release Hardening and Closure

## Purpose

Complete the Halloy-compatible theme roadmap by hardening runtime behavior, measuring operational cost, verifying security boundaries, removing obsolete binary-theme assumptions, and producing a release-ready closure record.

Phase 6 proves integrated behavior. Phase 7 converts that evidence into a stable release contract and removes temporary or ambiguous implementation paths that should not remain after migration.

This phase should not add new customization features. It is a release-readiness and simplification pass.

## Current state

The implementation now includes:

- typed Halloy parsing and deterministic translation;
- packaged bundled themes;
- external custom-theme loading;
- startup-built immutable registry;
- emergency fallback;
- palette-only CSS delivery;
- separate application and palette stylesheet ownership;
- versioned local browser preference;
- system-mode resolution;
- accessible selector;
- validation CLI;
- authenticated diagnostics;
- documentation and provenance records;
- focused parser, registry, route, CSS, preference, packaging, and diagnostics tests;
- a corrective closure pass for stylesheet lifecycle and diagnostics accuracy.

The remaining work is to prove acceptable cost, close security and artifact risks, simplify compatibility code, and define the final release checklist.

## Outcomes

At completion:

1. Theme startup, memory, response, and first-paint costs are measured and acceptable.
2. Security review confirms no arbitrary CSS injection, path escape, unsafe symlink handling, or public path leakage.
3. CSP, caching, conditional requests, and failure recovery are release-correct.
4. Docker and release artifacts are verified to contain the intended bundled themes and documentation.
5. Obsolete dark/light-only implementation assumptions are removed without breaking legacy preference migration.
6. Operational configuration, diagnostics, and rollback behavior are explicit.
7. The roadmap definition of done is verified item by item.
8. A release sign-off and rollback plan are available.

---

## Workstream 1 — Performance and resource measurements

Measure rather than infer the cost of the full shipped theme set.

### Startup measurements

Measure:

- time to load manifest;
- time to discover bundled themes;
- time to scan configured external directory;
- TOML parsing time;
- translation and contrast-check time;
- CSS serialization time;
- total registry construction time;
- startup behavior with no external themes;
- startup behavior with a realistic external set;
- startup behavior at configured external file-count limit.

Record warm and cold filesystem observations where practical.

### Memory measurements

Estimate or measure:

- registry object size;
- parsed/translated theme objects;
- generated CSS strings;
- metadata payload;
- diagnostics/provenance structures;
- incremental cost per external theme.

Do not optimize prematurely. Establish a threshold and only change architecture if measured cost is material for expected deployment sizes.

### HTTP measurements

Measure:

- CSS response size per representative theme;
- metadata endpoint size with all bundled themes;
- first request latency;
- conditional request latency;
- 304 behavior;
- cache hit behavior through the deployed reverse proxy if one is standard;
- effect of theme metadata on base HTML size.

### Browser measurements

Measure or inspect:

- theme stylesheet fetch timing;
- first contentful paint impact;
- visible flash of fallback palette;
- layout shift during theme activation;
- selector initialization cost;
- theme switch latency;
- repeated switch behavior.

### Threshold policy

Define explicit release thresholds, for example:

- theme registry construction remains a small fraction of total startup;
- metadata payload remains comfortably below a documented size target;
- theme CSS remains compact and independently cacheable;
- no measurable layout shift is introduced;
- theme activation does not block critical content rendering;
- no repeated TOML reads occur on normal requests.

Use repository-appropriate values rather than arbitrary universal targets.

### Acceptance criteria

- Measurements and environment are documented.
- No normal request reparses theme files.
- No unbounded memory growth occurs across repeated requests or switches.
- Any optimization is justified by evidence and covered by tests.

---

## Workstream 2 — Security boundary review

Treat bundled and external TOML as untrusted input for serialization purposes.

### CSS injection review

Verify the parser rejects or cannot serialize:

- named colors if outside the contract;
- shorthand hex if unsupported;
- `var(...)`;
- `url(...)`;
- gradients;
- semicolons;
- braces;
- comments;
- control characters;
- newline injection;
- escaped CSS tokens;
- malformed alpha values;
- non-string TOML values.

Confirm every emitted CSS value comes from canonical color objects or fixed application aliases.

### Filesystem review

Verify:

- request IDs are resolved through registry entries, never direct paths;
- traversal segments are rejected;
- absolute paths cannot be selected through public routes;
- external discovery remains confined to the configured root;
- symlinks outside the configured root are rejected;
- nested-directory policy is explicit;
- file count and byte limits are enforced before expensive parsing;
- current working directory does not affect resource resolution;
- file errors do not disclose absolute paths publicly.

### Identifier review

Test collisions involving:

- case differences;
- spaces and punctuation;
- Unicode normalization;
- accented names;
- decomposed versus precomposed forms;
- names that normalize to empty strings;
- reserved emergency identifier;
- duplicate bundled IDs;
- external-over-bundled override IDs;
- maximum-length IDs.

Define deterministic collision behavior. Fail closed for ambiguous bundled manifests; record explicit override provenance for external replacements.

### Metadata and template review

Verify:

- display names are JSON-encoded once, not pre-escaped;
- metadata script cannot terminate its own script context;
- selector rendering uses text insertion rather than HTML injection;
- public metadata omits filesystem paths and raw TOML;
- authenticated diagnostics omit sensitive paths by default;
- no untrusted theme field becomes an HTML attribute name or URL.

### Denial-of-service review

Verify bounds for:

- file size;
- file count;
- TOML nesting/complexity where relevant;
- identifier length;
- display-name length;
- diagnostics count;
- metadata size;
- repeated failed stylesheet attempts;
- browser retry loops;
- startup logging volume.

### Acceptance criteria

- Security review findings are documented and classified.
- No high- or critical-severity issue remains.
- Every boundary has a regression test or explicit invariant.
- External themes remain palette-only data, never arbitrary CSS or script.

---

## Workstream 3 — CSP and browser delivery hardening

### CSP compatibility

Verify all supported deployment modes:

- metadata JSON script is allowed under current CSP/Talisman policy;
- theme controller loading is compliant;
- no new inline executable script is required;
- palette CSS endpoint is allowed by `style-src`;
- custom themes do not require `unsafe-inline` or remote origins;
- standalone/admin templates use the same compliant pattern.

If the current metadata script is non-executable `application/json`, document why it is safe and how the CSP treats it in the deployed configuration.

### Stylesheet lifecycle

Confirm:

- application CSS is loaded independently;
- palette CSS follows application CSS in cascade order;
- fallback variables exist before palette CSS arrives;
- successful switches are atomic;
- stale load events cannot overwrite newer intent;
- failed loads leave a usable palette;
- pending links are removed;
- rapid switching does not leak DOM nodes;
- no page accumulates duplicate listeners after HTMX navigation.

### Browser chrome metadata

Review fixed values such as:

- `<meta name="theme-color">`;
- Apple status-bar style;
- manifest theme/background colors;
- favicon or SVG fills.

Decide whether these remain fixed by design or should update from active theme metadata. Do not introduce unstable dynamic behavior merely for cosmetic parity. Document the decision.

### Acceptance criteria

- Production CSP passes without weakening policy.
- All page shells use the same stylesheet ownership contract.
- Browser chrome behavior is intentional and documented.

---

## Workstream 4 — HTTP caching and conditional request policy

### Theme CSS route

Verify:

- `Content-Type: text/css; charset=utf-8`;
- `X-Content-Type-Options: nosniff`;
- strong ETag generation from stable content digest;
- correct `If-None-Match` handling;
- correct HEAD behavior;
- correct 304 response body and headers;
- unknown IDs return controlled 404;
- unavailable registry returns controlled 503;
- cache policy matches process-lifetime immutability.

### Cache policy decision

The current route may use a short public max-age. Decide whether to retain this or move to one of:

- longer max-age with ETag;
- content-digest/fingerprinted URLs and immutable caching;
- short cache for external themes and long cache for bundled themes.

Choose the simplest policy consistent with deployment and restart semantics.

### Metadata endpoint

Verify:

- response contains only safe fields;
- cache duration reflects registry immutability;
- stale metadata cannot cause persistent breakage because CSS failures recover;
- response size remains bounded;
- conditional caching is considered if useful.

### Reverse-proxy behavior

If the production stack uses a proxy or CDN, smoke-test:

- CSS route caching;
- 304 forwarding;
- content type preservation;
- no cache key dependence on cookies or user identity;
- custom theme changes becoming visible after documented restart/cache expiry.

### Acceptance criteria

- HTTP semantics are standards-compliant.
- Cache policy is documented and tested.
- Theme CSS remains public and user-independent.
- No page HTML cache is fragmented by theme choice.

---

## Workstream 5 — Configuration and operational hardening

### Configuration validation

Validate at startup:

- theme subsystem enabled/disabled behavior;
- custom directory type and path;
- default theme exists;
- dark default exists and is dark-classified or explicitly allowed;
- light default exists and is light-classified or explicitly allowed;
- custom-theme allow flag behavior;
- strict contrast mode;
- file-size limit bounds;
- file-count limit bounds.

Misconfiguration policy must distinguish:

- fatal production configuration errors;
- warnings with deterministic fallback;
- ignored optional custom-theme failures.

### Logging

Ensure startup logs provide:

- total bundled themes;
- total external themes;
- external overrides;
- skipped/invalid themes;
- selected defaults;
- emergency fallback activation;
- registry build duration;
- warning/error counts.

Logs must avoid:

- raw theme contents;
- unredacted sensitive paths where policy forbids them;
- repetitive per-request noise;
- duplicate startup summaries.

### Diagnostics

Verify authenticated diagnostics accurately report:

- actual build timestamp;
- theme counts by origin;
- defaults;
- emergency availability/activation distinction;
- override provenance;
- warning/error counts;
- stable diagnostic codes;
- valid/invalid status.

Clarify whether `emergency_fallback_active` means present or actually selected. Rename fields if semantics are ambiguous.

### Operational refresh policy

The first release uses an immutable process-lifetime registry. Document:

- theme changes require restart;
- how to validate before restart;
- how to roll back a broken custom theme;
- how browser caches behave after restart;
- how to remove an override;
- how stale browser preferences recover.

Do not add live reload in this phase.

### Acceptance criteria

- Production misconfiguration behavior is deterministic.
- Logs and diagnostics agree.
- Operators have a tested restart and rollback procedure.

---

## Workstream 6 — Artifact and release packaging verification

### Repository and source distribution

Verify all approved bundled themes, manifest, provenance, and package markers are included in every supported distribution form.

### Docker image

Assert the final image contains:

- `resources/themes/manifest.json`;
- every manifest-listed TOML file;
- package markers required by resource loading;
- validation command dependencies;
- relevant documentation if documentation is shipped.

Run application startup from the final image, not only the builder stage.

### Reproducibility

Verify:

- manifest entries correspond exactly to packaged files;
- no unapproved root-level import directory is included accidentally;
- no duplicate obsolete theme directory remains;
- image build does not depend on uncommitted local files;
- `.dockerignore` does not exclude required resources;
- release validation fails when canonical theme resources are missing.

### External theme deployment

Document and smoke-test:

- read-only volume mount;
- ownership and permissions;
- missing directory behavior;
- invalid file behavior;
- override behavior;
- restart requirement;
- backup responsibility.

### Acceptance criteria

- Final release artifact contains the intended theme set.
- Artifact verification is blocking in release validation.
- Custom-theme deployment works from documented read-only storage.

---

## Workstream 7 — Remove obsolete binary-theme assumptions

Perform a repository-wide audit for legacy assumptions.

### Search targets

Search for:

- `data-theme="light"` selectors;
- `[data-theme="light"]` palette blocks;
- hard-coded `dark`/`light` toggle labels;
- `ainews-theme` storage reads outside migration code;
- binary toggle icons and aria labels;
- documentation claiming only dark/light support;
- tests asserting only two themes;
- server cache keys containing theme;
- inline scripts applying old binary state;
- fixed default theme IDs duplicated outside configuration/registry metadata.

### Compatibility policy

Retain only the legacy migration path needed for existing users. Isolate it clearly and document the intended removal window.

Do not remove:

- `data-theme-appearance` or equivalent light/dark classification used for appearance-specific behavior;
- system-mode mapping to configured light/dark defaults;
- tests protecting legacy migration during the compatibility period.

### Static fallback

Retain a complete static fallback palette in application CSS or critical CSS so pages remain usable before palette CSS loads or if the theme system is unavailable.

### Cleanup

Remove:

- dead helper functions;
- unused serializer maps;
- obsolete comments referring to implementation phases;
- duplicate generated CSS variables;
- stale documentation;
- temporary diagnostics names;
- unused CSS classes or selector markup from the old toggle.

Regenerate bundled/minified assets after source cleanup.

### Acceptance criteria

- No active binary-only theme implementation remains.
- Legacy storage migration is isolated and tested.
- Static fallback remains complete.
- Generated assets match sources.

---

## Workstream 8 — Documentation closure

Review all theme documentation as a coherent set.

### Required documents

Ensure consistency across:

- `README.md`;
- `AGENTS.md`;
- `docs/frontend.md`;
- `docs/configuration.md`;
- `docs/halloy-theme-contract.md`;
- `docs/theme-authoring.md`;
- `docs/theme-preferences.md`;
- `docs/theme-provenance.md`;
- `docs/theme-troubleshooting.md`;
- `docs/themes-inventory.md`;
- validation/release documentation.

### Content requirements

Document:

- bundled versus custom precedence;
- identifier normalization;
- supported Halloy fields;
- ignored fields;
- color syntax;
- contrast policy;
- validation commands;
- restart semantics;
- cache behavior;
- emergency fallback;
- system mode;
- browser-local preference storage;
- legacy migration;
- custom directory security constraints;
- diagnostics endpoint authentication;
- rollback procedure;
- known theme exclusions or warnings.

### Accuracy pass

Cross-check every path, command, configuration key, endpoint, and default against current code. Remove roadmap-phase language from user/operator docs unless it remains historically useful.

### Acceptance criteria

- Documentation describes current behavior, not planned behavior.
- No conflicting configuration names or restart semantics remain.
- Operators can install, validate, override, troubleshoot, and roll back a custom theme using documentation alone.

---

## Workstream 9 — Full release validation

Run the repository's complete release sequence from a clean checkout.

### Required checks

At minimum:

- bundled theme validation;
- strict validation where release policy requires it;
- theme manifest/package consistency;
- theme-focused unit/integration tests;
- full `pytest` suite;
- coverage threshold;
- Ruff;
- mypy;
- CSS/JS build regeneration and clean-tree check;
- critical CSS synchronization check;
- JavaScript bundle/source-map synchronization;
- Docker build;
- Docker startup smoke;
- external-theme mount smoke;
- security/failure-mode smoke;
- representative browser validation from Phase 6.

### Clean-tree rule

After generation and validation, the working tree must be clean. Any generated artifact differences must be committed or the generation process corrected.

### Failure policy

Do not waive:

- missing packaged themes;
- application stylesheet removal;
- CSS injection possibility;
- path/symlink escape;
- invalid default fallback;
- critical unreadable text/control contrast;
- stale generated assets;
- release validation failures.

Non-critical palette warnings may be accepted only when documented.

### Acceptance criteria

- Full validation passes from a clean checkout.
- Release artifact smoke passes.
- No critical or high-severity finding remains.
- Known warnings have owners or documented acceptance.

---

## Workstream 10 — Rollout and rollback plan

### Rollout

Recommended rollout sequence:

1. Deploy with bundled themes and custom themes disabled or absent.
2. Verify defaults, metadata, CSS route, and browser activation.
3. Enable documented external directory if used.
4. Validate operator-provided themes before deployment.
5. Monitor startup logs, diagnostics, CSS 404/503 rates, and frontend error reporting.

### Rollback

Define a rollback that does not depend on custom themes:

- disable custom theme directory;
- restore configured bundled defaults;
- restart application;
- rely on stale preference recovery;
- retain emergency fallback;
- invalidate proxy cache if policy requires it.

Avoid database migrations for theme preferences; browser-local storage keeps rollback low risk.

### Monitoring

Monitor:

- theme registry startup failures;
- invalid custom-theme counts;
- emergency fallback activation;
- CSS route 404/503 rates;
- unexpected theme metadata failures;
- frontend stylesheet load errors where telemetry exists;
- startup duration regression.

### Acceptance criteria

- Rollout and rollback steps are documented and tested.
- Operators can return to bundled defaults without code changes.
- No user data migration is required for rollback.

---

## Workstream 11 — Roadmap closure audit

Verify every original definition-of-done item explicitly.

Create a checklist for:

1. approved themes packaged with provenance;
2. complete `AinewsTheme` translation;
3. injection/path safety;
4. read-only custom directory support;
5. external override precedence;
6. once-per-process parsing;
7. reader selection and persistence;
8. system light/dark mapping;
9. legacy migration;
10. theme-neutral page and fragment caches;
11. HTMX persistence;
12. critical/generated CSS synchronization;
13. semantic token use on public/admin pages;
14. bundled parser/translation/contrast/artifact validation;
15. custom-theme validation and documentation;
16. Docker/release resource inclusion;
17. emergency fallback independence;
18. full repository validation.

For each item record:

- implementation location;
- test or validation evidence;
- documentation location;
- status;
- any accepted limitation.

### Acceptance criteria

- Every item is closed or explicitly deferred with rationale.
- No item is marked complete solely from a commit message.
- The closure record is suitable for future maintainers.

---

## Recommended implementation order

1. Measure startup, memory, HTTP, and browser cost.
2. Complete security and identifier-collision review.
3. Verify CSP and stylesheet delivery behavior.
4. Finalize cache policy.
5. Harden configuration, logging, and diagnostics semantics.
6. Verify Docker/release artifacts.
7. Remove obsolete binary-theme assumptions and dead code.
8. Reconcile documentation.
9. Run full clean-checkout release validation.
10. Execute rollout/rollback smoke.
11. Complete the roadmap closure audit.

## Files likely to change

Potential files include:

- `services/themes/registry.py`;
- `services/themes/loader.py`;
- `services/themes/translate.py`;
- `services/themes/colors.py`;
- `routes/themes.py`;
- `routes/admin/api/theme_diagnostics.py`;
- `static/js/theme.js`;
- theme-related templates;
- `static/css/variables.css`;
- generated CSS/JS artifacts;
- `config.py`;
- `.env.example`;
- Docker files and ignore rules;
- `scripts/validate_release.sh`;
- theme validation scripts;
- CI workflow files;
- theme and frontend documentation;
- new performance/security/release validation tests.

Keep production changes narrow and evidence-driven.

## Completion criteria

Phase 7 and the Halloy theming roadmap are complete when:

- performance costs are measured and acceptable;
- security review has no unresolved high/critical findings;
- CSP and caching behavior are verified;
- configuration and diagnostics semantics are accurate;
- release artifacts contain the intended theme resources;
- obsolete binary-only paths are removed while migration compatibility remains;
- documentation matches final behavior;
- full clean-checkout release validation passes;
- rollout and rollback are tested;
- all roadmap definition-of-done items have evidence-backed closure.
