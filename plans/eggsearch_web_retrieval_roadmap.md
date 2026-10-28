# Eggsearch External Web Retrieval Integration Roadmap

**Status:** IN PROGRESS — opt-in adapter/evidence groundwork implemented and `eggsearch==0.4.4` is now pinned as an optional extra. Published macOS arm64/x86_64 wheels and a bounded DuckDuckGo live smoke have been tested; runtime fallback, clean-host/Linux qualification, upstream symlink-containment and DNS-pinning concerns, broad comparison, and canary gates remain open. See docs/eggsearch-retrieval-qualification.md.
**Date:** 2026-10-28
**Baseline:** ainews main 97b5ec25f855a3b1d3b248ae64cb2242831ab1c1; eggstack/eggsearch main 13fcac0b7ac0125d38e4e9775ebe1d62028fda72 (Cargo 0.4.4). Recheck both at implementation start.
**Owner:** ainews retrieval/research maintainers.
**Decision:** Make eggsearch a selectable external-web-search backend; retain ainews-owned editorial orchestration, database search, RSS/API ingestion, and first-party safe fetch.
**Default policy:** opt-in until packaged, benchmarked, and release-qualified.

## Motivation and verified baseline

Ainews already splits external search (services/search/base.py, duckduckgo.py, google.py, searxng.py, __init__.py) from internal article search (sqlite_fts.py, hybrid.py). The externally-facing compatibility seam is search_web(query, max_results) returning SearchResult(title, url, snippet, source). Both tasks/research.py and services/subagent/tools.py use it. Ainews's subagent web_search formats only title and truncated snippet, losing URLs, despite the primary research task formatting URLs. ProviderManager.get_with_fallback chooses another provider when initialization fails but does not retry a different backend after a selected provider returns [] at runtime. Empty results and provider outages are conflated.

Eggsearch provides live metasearch, RRF aggregation, stable source identifiers, bounded web fetch, structured warnings/provider failures, trust markers, optional publication metadata, and freshness/date/domain hints with capability-enforcement telemetry. Its AsyncEggsearch Python binding performs in-process Rust SDK operations. Version 0.4.4 is published on PyPI and is available through ainews's optional extra; published macOS wheels have been smoke-tested locally, while documented wheel support and broader platform/deployment compatibility remain subject to CI/release qualification. There is no justification for requiring an additional background MCP server by default.

## Scope and ownership

- External discovery for the research stage and research subagents only, initially via an optional provider implementation.
- Preserve public function/tool names where possible; evolve result/evidence contracts additively.
- Keep article index/search, trend memory, deduplication, news selection, source allow/deny policy, publication-date verification, claim attribution, and quality gates under ainews.
- Keep all ingestion/unknown-URL fetches on services/safe_fetch.py. Do not silently replace its DNS-pinned, redirect-validated transport with eggsearch web_fetch.
- Do not create a second metasearch implementation or vendor eggsearch Rust into ainews.
- Do not make broad schema/database migrations, run a new sidecar by default, or add all ten eggsearch MCP tools to the agent's tool menu.
- No changes to eggsearch are authorized by this roadmap; missing upstream support is an explicit tracked dependency for a later separately scoped change.

## Target architecture

Celery research task and approved subagent tool -> ainews search service/typed outcome -> registered EggsearchSearchProvider -> optional in-process AsyncEggsearch -> eggsearch configured upstream engines. Existing legacy providers remain independently available. The internal SQLite FTS5/vector DAL is a separate and unchanged path. Ainews maps results to its own source IDs/URLs and evidence metadata; eggsearch's upstream provider IDs must not become ainews provider registry IDs.

## Execution order and detailed handoffs

1. **Phase 1 — transport, provider and configuration:** plans/eggsearch_web_retrieval_phase_1_provider_adapter.md. Implement optional provider, choose and qualify a native/Python transport, preserve current search behavior and fallback.
2. **Phase 2 — evidence and research contracts:** plans/eggsearch_web_retrieval_phase_2_evidence_and_research.md. Preserve URLs, provenance, published-at uncertainty, failures, and trust across tool and prompt layers; define controlled source hydration without weakening safe fetch.
3. **Phase 3 — distribution, qualification and rollout:** plans/eggsearch_web_retrieval_phase_3_release_and_rollout.md. Gate native wheels, Docker/installer/CLI support, observe realistic news runs, compare against baseline, and only then decide on default/retirement.

Implementation sequencing is strict: Phase 1 opt-in adapter and tests before Phase 2; Phase 2 evidence before any production use of new agent fetching; Phase 3 default decision only after complete evidence. Documentation and offline tests accompany each phase.

## Registered corrective handoffs — 2026-10-28

**Baseline for corrective work:** `c5d2c3596ee16340202ca7cb2515cfa3e458d290` (`plan/eggsearch-web-retrieval-20261028`). These are implementation tasks, not completion assertions; the earlier Phase 1–3 plans remain the scope authority.

1. **Corrective 01 — result semantics, fallback, worker concurrency** ([plan](eggsearch_web_retrieval_corrective_01_result_semantics_fallback.md); **PLANNED**). Repair false PARTIAL from informational warnings, native compact-vs-standard payload/capability mapping, `error_class` preservation, per-call outcome ownership, shared-deadline opt-in runtime fallback, and end-to-end research failure/freshness reporting. Required before canary or default consideration.
2. **Corrective 02 — CI, deployment qualification, security and rollout** ([plan](eggsearch_web_retrieval_corrective_02_ci_qualification_rollout.md); **PLANNED**). Prove real PR CI/required checks, binary wheels on Linux x86_64/arm64 and maintained environments, worker/CLI/Docker installation, scope isolation of upstream repo/fetch tools, reproducible news-search A/B evaluation, and a documented canary/rollback decision. Depends on Corrective 01 to close the Phase 3 gate.

**Tracking order:** Corrective 01 (runtime correctness) -> Corrective 02 (verification + rollout decision). Changes to `eggsearch==0.4.4` optional packaging and published-wheel smoke are already recorded in `docs/eggsearch-retrieval-qualification.md`; they do not establish complete release readiness. Update plan checkboxes and qualification evidence only with exact commits, test commands, CI run links and observed outcomes. Keep DuckDuckGo default and `eggsearch` disabled until a separate reviewed change explicitly authorizes activation.

## Cross-cutting invariants

1. Default installations and existing deployments work with zero eggsearch dependency, configuration, listener, Rust compiler, or search-provider credential changes.
2. The ordinary public search contract continues to return SearchResult lists; a separate detailed outcome must distinguish empty success, partial result, provider outage, timeout, policy refusal, and configuration error. Preserve existing explicit provider selection.
3. A configured eggsearch failure may trigger documented *runtime* fallback to explicitly enabled legacy search backends, within one shared request deadline; malformed configured production settings are surfaced by validation, not silently papered over.
4. Source URLs and stable IDs survive discovery, synthesis, and attribution. Preserve provider, evidence timestamp, retrieval date/time, and uncertainty where available. Never manufacture an article publication date.
5. Untrusted source text remains framed as data, size-bounded, and untrusted by model instruction policy. Injection-warning heuristics are not a guarantee of safe content.
6. Require evidence of capability enforcement for any requested hard freshness constraint; if unsupported, mark results as date-unverified and independently verify timestamps.
7. Maintain aio/Celery lifecycle correctness: no unbounded detached threads, nested-event-loop assumptions, per-request process spawn, runaway concurrency, or non-terminating network calls.
8. No default use of eggsearch's web_fetch for arbitrary URLs until a side-by-side security and operator-policy equivalence review resolves DNS rebinding, HTTP redirects, destination classification, timeout/byte enforcement, proxy behavior, TLS, and credential disclosure.
9. Keep Flask/CLI/worker configuration consistent through the current ainews_config system and user/system install path resolution; no absolute developer paths or secrets in repository or diagnostics.
10. No live internet in ordinary CI; separate opted-in smoke/canary evidence with pinned versions and recorded outcomes.

## External prerequisite / gate

Eggsearch's Python binding is published as 0.4.4 and pinned in the optional extra. Published macOS arm64/x86_64 wheel checksums and tool fingerprints, and a checksum-verified local install path, are recorded in the qualification record. Still qualify the CPython/OS/architecture matrix (especially clean Linux x86_64/arm64), Rust/sdist requirements, deployment/rollback behavior, and schema stability before calling packaging release-ready. A persistent localhost MCP transport may be evaluated only as an optional alternative; avoid a new mandatory sidecar.

## Release decision / stop conditions

Keep current default unless the phase-3 comparison demonstrates source/citation quality benefits without unacceptable regression in p95 research latency, failed-provider behavior, safe-fetch policy, Celery throughput, resource usage, deployment simplicity, and secret handling. Never delete legacy provider code until the rollback path has been exercised and operator docs updated. Any unmet security/packaging gate means eggsearch remains opt-in.

## Tracking / registration

This roadmap is the active index for the three detailed implementation handoffs. The historical completed master plan at plans/plan.md includes a pointer here for discovery. Mark each plan PLANNED -> IN PROGRESS -> VERIFIED only with code/test/CI artifact references; log unresolved upstream, policy, or deployment work as explicit blockers. Do not mark a task complete on documentation alone.

## References

- ainews: services/search/, services/subagent/tools.py, tasks/research.py, schemas/search.py, services/provider_base.py, services/safe_fetch.py, pipeline.yaml, providers.yaml, ainews_config/, docs/search-providers.md, docs/subagent.md, AGENTS.md.
- eggsearch: docs/python-library.md, docs/tool-matrix.md, docs/config.md, docs/safety.md, docs/deployment.md, bindings/python/python/eggsearch/, src/mcp/tools/web_search.rs, src/mcp/projection.rs.
