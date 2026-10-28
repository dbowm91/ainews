# Eggsearch Retrieval Corrective 02 — CI Qualification, Deployment, and Rollout Decision

**Status:** PLANNED — release/validation corrective handoff (2026-10-28).
**Depends on:** [Corrective 01](eggsearch_web_retrieval_corrective_01_result_semantics_fallback.md) for accurate result and fallback semantics. This plan closes remaining Phase 3 gates; it does **not** itself authorize a default change.
**Baseline:** `plan/eggsearch-web-retrieval-20261028` at `c5d2c3596ee16340202ca7cb2515cfa3e458d290`.
**Security constraint:** Only expose eggsearch's search tool in this line; no repo/local tools and no `web_fetch`/browser/PDF fetching from the eggsearch client. Continue using `services/safe_fetch.py` for untrusted article content.

## Verified progress and remaining gap

Published `eggsearch==0.4.4` is available on PyPI, pinned under `[project.optional-dependencies].eggsearch`, and present in `uv.lock`. The existing qualification record verifies release wheel hashes and imports/tool fingerprints on local macOS arm64/CPython 3.14 and x86_64/CPython 3.12; a bounded live DuckDuckGo-only eggsearch search returned three results with no provider failures. This is useful smoke evidence, **not** broad search quality, resource safety or deployment qualification.

The record reports 75 targeted research/subagent tests passing, an 11-test published-wheel focus run, `uv lock --check` passing, and 89.86% targeted adapter coverage. The full suite and mypy did not complete on that workstation because of Python-architecture mismatches and the locked Torch wheel incompatibility; do not label those as source-code test failures or successes without reproducing in a supported environment.

The branch has no PR or recorded standard CI check-runs. `.github/workflows/ci.yml` runs on `main`, `develop`, or PRs targeting them; `uv sync --frozen --all-extras` installs the new optional eggsearch dependency in CI. A CD run reports failure with zero executed jobs on this feature branch; it must not be presented as evidence of an application test failure.

The Phase 3 status sentence predated the PyPI publication and incorrectly says no release artifact exists. Update status/progress descriptions and source-version claims to the verified 0.4.4 release, retaining outstanding gates.

## Workstream A — Reproducible integration CI (P0)

- After Corrective 01 passes local focused regression tests, open a PR targeting `main` from the existing eggsearch branch so the repository's real CI required jobs execute. Do not force-push or merge while gates fail. Record the PR, run URLs, head SHA, commands, test summaries and failing jobs in `docs/eggsearch-retrieval-qualification.md`.
- Run on the repository's supported CPython 3.12 Linux x86_64 with `uv sync --frozen --all-extras`; verify that `eggsearch==0.4.4` resolves as a **binary wheel**, not an implicit Rust build, and import `eggsearch.AsyncEggsearch` succeeds. Exercise `uv run ruff check .`, `uv run mypy .`, `uv run pytest tests/ -x -q`, lock check, pip-audit, Docker/Compose smoke, and other existing CI gates. Preserve exact commands rather than inventing a new baseline.
- Investigate environment-only failures separately: earlier local `torch==2.12.0` resolution and no-sync missing `duckduckgo-search`; determine whether `uv.lock` is satisfiable on the documented supported targets. Fix reproducibility at the dependency/install layer; do not skip broad tests or relax required checks merely to make eggsearch green.
- Distinguish CD workflow trigger/no-job behavior from actual CI errors. If branch PR CI is unexpectedly absent, verify workflow triggers, branch/PR permissions, and status-check setup before claiming readiness.
- Keep ordinary deterministic tests offline and mock upstream search. Opt-in native wheel ABI tests may run in CI without outbound search; live provider smoke must be separately labeled, bounded, and non-blocking for transient upstream availability.
- Verify full search-provider registry behavior and backward compatibility with DDG, Google, SearXNG and SQLite FTS5/hybrid search. Existing `services/safe_fetch.py` security tests remain required.

## Workstream B — Platform, deployment and operator configuration (P1)

- Qualify clean-host binary-only install and imports for Linux x86_64 and Linux aarch64/ARM64 at minimum, matching maintained CPython versions (3.12+ under ainews; package advertises <3.16). Include macOS arm64, previously proven x86_64 and Docker build/worker runtime where supported. Record platform, Python ABI, wheel filename, checksum and upstream tool-contract fingerprint. SBCs must consume precompiled wheels, not compile eggsearch Rust from source.
- Test `uv sync --frozen` default installation separately from `uv sync --frozen --extra eggsearch` or `--all-extras` to demonstrate eggsearch remains optional in production. If Docker production image does not use the extra, document that explicitly; don't silently add binary size/Rust runtime requirements.
- Exercise Celery prefork and thread lifecycle, `AsyncEggsearch` creation/close, worker shutdown/restart, max concurrent searches, total request deadlines, memory and CPU use, and cancellation. Repeated native calls should not leak resources or silently retain unexpected network access.
- Validate `providers.yaml`/search schema with the operator CLI/config engine and `ainews doctor` in repo, system and user installs. Inactive eggsearch with no wheel/config is allowed; explicitly selected eggsearch with an absent wheel/config must be clearly diagnosed. Confirm env/secrets redaction and profile path resolution. The current `config_path` requirement is an explicit absolute path; qualify Docker mapping and canonical install path behavior before claiming system-install parity.
- Keep `eggsearch` configuration with `search.mode` and explicit upstream providers under operator control; verify disabled `fetch` and `local` in the intended profile. Prevent unapproved engine expansion/API-key exfiltration. Document API-key/egress/privacy policy for each enabled upstream engine.
- If optional native ABI fails on a supported architecture, document it as unsupported/blocked and retain the legacy provider. Do not introduce a required sidecar, fall back to compiling on an SBC, or silently bypass package hashes.

## Workstream C — Explicit security scope and upstream disposition (P1)

- Record that the upstream 0.4.4 source Rust run was 3,348 passed / 2 failed. One macOS path-equivalence assertion is platform-specific; the other reproduced a symlink-escape bug in repo mapping when symlink following is enabled off Linux. These issues must remain visible with their exact affected tool/surface and upstream issue disposition.
- The symlink issue does not automatically prevent **web_search-only** use when repo/local tools and directory roots remain disabled. Demonstrate with config checks and tests that ainews has no model/tool access to `repo_search`, `repo_fetch`, `repo_map`, and local roots. If that isolation cannot be proven, block rollout. Opening those tools later requires fresh upstream fix and boundary review.
- Upstream `web_fetch` safety documentation does not establish destination pinning against DNS rebinding; continue disallowing it. Search result URL validation alone does not authorize following any result link with an unrestricted client. All article hydration remains under the existing pinned `safe_fetch` transport.
- Test prompt-injection framing, malicious snippets, IP-literal/localhost or redirectbait URLs, blocked/private destinations, oversized payloads, untrusted source labels, timeout and no-host-access behavior. Record accepted limitations; no blanket claim that eggsearch is “secure” based solely on Rust unit-test counts.

## Workstream D — Comparative evaluation and staged activation (P1)

- Construct a reproducible, fixed-input corpus from representative research requests spanning breaking model releases, Python/Rust/cybersecurity, scientific papers/medical evidence, obscure entities, stale articles, and intentionally ambiguous/empty cases. Avoid selection based on eggsearch's successes. Publish a sanitized fixture manifest and record seed, dates, topic distribution, provider versions and upstream search config.
- Compare current DuckDuckGo search against native eggsearch using the **same** query, result cap, content-fetch policy and model/research prompts. Capture source relevance, unique independent domains, primary-source hits, dedup, link safety, publication-date verification, unsupported citation rate, p50/p95 latency, failed/partial/empty queries, fallback incidence, per-query upstream requests, CPU/RSS and token cost.
- Include real cases where `freshness` is only a best-effort provider hint. Verify the mapped capability state and classify article age from publication evidence, not requested freshness. Preserve uncertainty and separate publication, retrieval and indexing dates.
- Define numerical pass/fail thresholds from an independently measured baseline **before** the canary. Do not fabricate benchmark gains or infer higher quality from more hits. Use a separate network-enabled smoke/canary job with strict rate/cost/timeout limits and a clear rollback switch.
- Rollout stages: legacy default remains; eggsearch manually selected in a controlled test environment; operator-visible canary; assess editorial and operational effects; only then deliberate a default change. Explicit outcome record must be one of `remain opt-in`, `make default`, or `reject/defer`, with evidence and rationale. Default switch belongs in a separate reviewed implementation commit.
- Retain legacy search provider implementations and downgrade/rollback path for at least one release after any default switch; never replace local FTS5/hybrid or safe-fetch.

## Workstream E — Documentation, status, handoff closure

- Update `docs/eggsearch-retrieval-qualification.md`, `docs/search-providers.md`, operator/installation docs, and `plans/eggsearch_web_retrieval_phase_3_release_and_rollout.md` so PyPI publication claims agree with observed release artifacts. Avoid stale “no PyPI” assertions.
- Keep the central [roadmap](eggsearch_web_retrieval_roadmap.md) as authoritative registry. Add links to Corrective 01 and Corrective 02 in the roadmap and to this follow-on from `plans/plan.md`; do not reopen historical completed waves.
- Status protocol: PLANNED -> IN PROGRESS -> VERIFIED based only on inspected code, tests and CI evidence. “Wheel verified” is not “all platforms qualified”; “smoke returned results” is not “search quality approved”; “CI workflow failed with no jobs” is not “test suite failed.”
- After fixes land, link the implementation commits, PR, test/CI runs and decision record; close remaining checkbox gates rather than simply replacing status text.

## Completion criteria

- [ ] PR CI runs on the actual implementation branch with green mandatory checks and exact run evidence (or explicit unresolved blockers).
- [ ] Published 0.4.4 binary-wheel install/import, tool-contract fingerprint, and rollback validated for every claimed target, including Linux x86_64/aarch64.
- [ ] Base installation works with eggsearch extra absent; opt-in installation works without Rust compilation on target systems.
- [ ] Operator config, worker lifecycle, deadline/CPU/RAM behavior, safe-fetch boundaries and disabled local/repo/fetch tools are proven.
- [ ] Corrective 01 result semantics/fallback and full offline suite are complete; code paths are covered by release CI.
- [ ] Fixed-input A/B corpus, evaluation thresholds, measured results, and explicit canary/rollback outcome are recorded.
- [ ] Default DuckDuckGo remains until a reviewed separate decision authorizes otherwise; upstream risks have explicit scope/disposition.
- [ ] Roadmap and documentation agree with tested release/artifact evidence.

**Implementation order:** Corrective 01 -> A -> B/C -> D -> E; independently unblock packaging/test failures as practical, but do not reverse the decision gate.
