# Eggsearch Web Retrieval Phase 3 — Packaging, Qualification, Canary and Rollout

**Status:** BLOCKED FOR DEFAULT ROLLOUT — `eggsearch==0.4.4` is published on PyPI, pinned in an optional extra, and verified against release wheel checksums/fingerprints on local macOS arm64/x86_64, with one bounded live DuckDuckGo search. Corrective result/fallback and doctor/Docker opt-in changes now have focused local coverage, and Linux x86_64/aarch64 plus optional-Docker CI checks are defined but unrun. Green PR CI, clean-host worker qualification, a representative research corpus, upstream-risk disposition, approved canary, and rollback evidence are still missing. DuckDuckGo remains default; Eggsearch remains disabled.
**Depends on:** Phase 1 adapter and Phase 2 evidence work, plus [Corrective 01](eggsearch_web_retrieval_corrective_01_result_semantics_fallback.md) and [Corrective 02](eggsearch_web_retrieval_corrective_02_ci_qualification_rollout.md) registered by the roadmap.
**Goal:** Make optional eggsearch integration operable on supported installations, decide whether it can become the default on evidence, and preserve rollback.

## Workstream 1 — Version/package gate

Release artifact gate is partly satisfied: PyPI publishes `eggsearch==0.4.4`, pinned in the optional extra and `uv.lock`; local macOS arm64 and x86_64 downloads passed checksum, import and tool-contract verification. Upstream documentation still contains stale unpublished-package wording. Recheck published artifact metadata and supported wheels at implementation time; preserve the tested tag/commit and `tool_contracts()` fingerprint in the qualification record. This does **not** prove clean-host Linux or deployment parity.

Preferred production path: published or otherwise reproducibly supplied wheels for the exact supported CPython and platform combinations. No Rust compiler needed on the runtime host. Validate Python 3.12+ supported by ainews and Linux x86_64/aarch64, macOS arm64, plus WSL via Linux path. Verify macOS x86_64 only if it is part of the maintained deployment matrix. Release builders can have Rust/Maturin, but ordinary installs should not compile crates or fetch crates implicitly.

Until the entire target platform/release matrix qualifies, keep eggsearch optional and allow documented wheel-only opt-in installation. A persistent loopback MCP endpoint is an *optional*, separately evaluated transport when native packaging cannot be adopted; do not make it the default, auto-start it per query, or allow public HTTP binding. If choosing this alternative, explicitly document authentication/trust boundaries, service health, lifecycle, container-to-host networking, and version skew.

## Workstream 2 — Operator and deployment integration

The optional `eggsearch==0.4.4` dependency group and `uv.lock` have been added; keep them pinned and synchronized while qualifying their install on supported targets. Include optional native wheel in Docker and release artifact compatibility checks. Preserve default Docker/bare-metal installer profiles unchanged; opt-in profiles should enable diagnostic preflight through the existing CLI, not through an undocumented shell step.

Integrate configuration with schemas/search.py, ainews_config field registry/validation, providers.yaml examples, pipeline research-stage settings, onboarding provider choice, config migration and doctor/probe where applicable. Ensure a consistent config path and permissions for user/system/containers. Operator diagnostics should distinguish: eggsearch not installed, binding import failure, broken binary ABI, config invalid, selected provider unavailable, all upstreams failed, partial search, and actual empty result. Probe only under explicit --network or equivalent; ordinary doctor/config checks stay offline. No secret values in CLI JSON, error strings, metrics or logs.

Update docs/search-providers.md, docs/subagent.md, docs/pipeline.md, docs/configuration.md, docs/deployment.md, docs/operations.md, and README feature guidance as appropriate. Do not imply PubMed/other APIs are automatically enabled or that keyless engines strictly honor freshness constraints.

## Workstream 3 — Reproducible test and release evidence

Run existing validation (uv run ruff check ., uv run mypy ., uv run pytest, bash scripts/validate_release.sh --fast, plus release/installer smoke where affected). In CI add opt-in matrix for native eggsearch import, provider config, CLI doctor, worker task execution, wheel ABI, shutdown/restart, and packaging across supported targets; keep routine unit tests network-free and independent of eggsearch wheel availability.

Use a separate controlled live-smoke job for providers with fixtures/canned expected constraints. Never require an unstable HTML search engine to respond in normal CI. Test fake-provider failure and injected timeout path; test systemd/docker startup when eggsearch is absent, installed but unconfigured, and selected. Verify staged upgrade/rollback and installed application version are observable.

Create a concise evidence record under docs/ (e.g. docs/eggsearch-retrieval-qualification.md) with source version/fingerprint, commands, exit codes, platform/wheel hashes, target run, timestamp, failures, and policy dispositions. No unverified "tests passed" status.

## Workstream 4 — A/B comparison and decision gate

Build a reproducible evaluation corpus sampled from ainews's actual topic mix and research titles, spanning same-day breaking stories, 1–7 day releases, scientific papers, older evergreen articles, ambiguous terminology, and deliberately irrelevant/offline/failed-provider scenarios. Keep original article and topic inputs fixed. Compare current DuckDuckGo implementation versus eggsearch:
- unique relevant sources/query, primary-source hit rate, URL validity, independent-domain coverage, duplicate rate;
- correct publication-date evidence and false-recent rate (particularly when upstream lacks enforcement);
- proportion of research briefs with verifiable citations / unsupported-claim rate, reviewer corrections;
- p50/p95 wall time per search, per-article research duration, Celery throughput, upstream calls, CPU/RSS, and cache effectiveness;
- fraction of successful/partial/empty/failed responses, timeout recovery, circuit/fallback behavior, and provider availability;
- tokens used in search tool and synthesis prompts, LLM cost, and extra fetch cost.

Define numerical acceptance thresholds before the experiment using measured baseline distributions rather than invented targets. Include failures as well as quality results; record sample size, selection criteria, environment, exact versions, and significant uncertainty. Do not judge solely by the quantity of search hits or RRF score. Audit outbound-query privacy before turning on additional external engines; operator-defined domain restrictions and credentials must work as expected.

Run a feature-flagged canary with explicit rollback: legacy-only -> eggsearch opt-in for a small subset -> wider opt-in -> default only if accepted. Record a decision (retain opt-in / become default / reject) with rationale and complete quality/security/packaging evidence.

## Workstream 5 — Cleanup only after approved default decision

If default approved: change configuration defaults and user-facing docs in a separate implementation commit; retain the legacy provider type and explicit rollback setting for at least one release. Remove duckduckgo-search as mandatory Python dependency only when no retained provider, test, setup or diagnostic path requires it. Preserve Google and SearXNG backends if operator compatibility matters; no unilateral deletion. Document version pin, wheel acquisition, fallback modes, offline constraints, and unsupported platforms.

If not approved: retain optional provider, document the blocking metrics/issues, and close only the accomplished opt-in work. Never report the full migration complete in this case.

## Exit criteria

- [ ] Native wheels or approved alternative transport have reproducible installation/rollback on every claimed target.
- [ ] Existing default installation works without the eggsearch package/service.
- [ ] User/system/Docker/CI config, health/doctor behavior, and secret redaction are qualified.
- [ ] No new SSRF, timeout, or resource-exhaustion bypass is introduced.
- [ ] Baseline vs eggsearch evaluation has real corpus, metrics, uncertainty, and a decision record.
- [ ] Ainews can turn eggsearch on/off without code edits or database changes; rollback tested.
- [ ] Default changes/legacy retirement occur only by an independently reviewed decision, not by plan completion.
- [ ] Final tests, build artifacts, docs and commit evidence are linked from plans/eggsearch_web_retrieval_roadmap.md.

## Escalation and upstream blockers

Missing or incompatible native wheels, changing eggsearch tool schema/IDs, unacceptable freshness enforcement, dependency build failures, or unresolved web_fetch DNS/redirect safety equivalence are explicit blockers. Document issues in the appropriate repository, but do not silently implement an upstream eggsearch change under this ainews plan.
