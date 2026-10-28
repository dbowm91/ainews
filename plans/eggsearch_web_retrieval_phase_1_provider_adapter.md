# Eggsearch Web Retrieval Phase 1 — Optional Native Provider Adapter

**Status:** PLANNED
**Depends on:** plans/eggsearch_web_retrieval_roadmap.md.
**Goal:** Ainews can select eggsearch for search without changing the default, adding an always-on MCP server, or breaking the existing SearchResult contract.

## Baseline / relevant implementation

- services/search/base.py defines BaseSearchProvider and SearchResult(title,url,snippet,source).
- services/search/__init__.py imports providers and exposes get_search_provider(), search_web(), and get_article_search_provider().
- services/provider_base.py selects the configured provider and falls back at *initialization*, not after an empty runtime response.
- schemas/search.py loads search_providers/default_search_provider from providers.yaml; tests/test_search.py exercises current providers.
- tasks/research.py uses a stage-specific web_search_provider override or the default; services/subagent/tools.py has a separate web_search entry.
- Eggsearch exposes the in-process AsyncEggsearch API with web_search(**kwargs) returning a dictionary with results, providers_queried, providers_failed, retrieval_summary, capability_enforcement, and warnings. Native Python wheel is not yet published; verify the exact version/tool fingerprint before coding.

## Workstream 1 — Define stable ownership and transport contract

Implement a small transport-neutral backend abstraction in services/search/ (for instance eggsearch_client.py) behind the existing provider contract. Select native AsyncEggsearch as preferred transport, not MCP stdio or persistent HTTP by default. Explicitly document initialization, configuration path selection, ownership, close/aclose semantics, cancellation, worker process fork lifecycle, timeout, and concurrent calls. Native bindings document one process-scoped Rust runtime and a 32-operation admission limit; account for that limit rather than multiplying it by Celery workers.

Current BaseSearchProvider.search is synchronous, while native AsyncEggsearch.web_search is async. Provide a deliberate sync-to-async bridge for Celery workers and threaded subagent invocation, with cancellation and bounded cleanup; do not call asyncio.run inside a running event loop or globally share a loop-bound AsyncEggsearch instance across forked processes or unrelated threads. A scoped asyncio.run per search is acceptable for the first opt-in proof if its overhead is measured and client closure/cancel behavior is tested. No background orphan loops or unbounded queueing.

Do not force an unpublished eggsearch wheel into pyproject.toml's mandatory dependencies. Lazy-load optional native support; inject a fake client/transport in tests. Distinguish binding unavailable, tool-schema mismatch, disabled mode, invalid config, network failure, all-provider failure, partial success, and legitimate empty results.

## Workstream 2 — Provider registration and result mapping

Create services/search/eggsearch.py (or equivalent) registering provider type eggsearch; add import in services/search/__init__.py. Map source cards with validated public HTTP(S) URLs to SearchResult(title, url, snippet, source="eggsearch") while retaining upstream provider_id, source ID, metadata.published_at, and trust diagnostics in an optional side channel defined in Phase 2.

Use provider output results[] as structured data rather than rendering/parsing the text-format CLI or MCP user-facing display. Preserve deterministic order and bounded result count. Reject malformed cards safely; don't infer publication dates or downgrade an upstream error into a fabricated no-results claim.

Add a *detailed outcome* API compatible with existing list-returning search_web() so caller code can reason about partial provider failures. Evaluate whether the runtime fallback belongs in search_web() rather than ProviderManager globally: do not alter LLM-provider fallback behavior. Only fall back on defined transient failures or configured policies, not unconditionally on a valid empty result. Use one aggregate deadline shared by the attempted backends.

## Workstream 3 — Configuration and diagnostics

Extend schemas/search.py and provider type validation, providers.yaml example, ainews_config field registry, CLI/provider doctor diagnostics, and documentation as required by current config conventions. Eggsearch is opt-in with explicit config_path and/or a resolved native config profile; config paths must be resolved deterministically for repository, user, system and Docker installs. Never accidentally use the current working directory or developer-local TOML. Establish which engine list and limits ainews chooses versus what eggsearch's own TOML controls. Keep API keys only in the operator's secret environment/config controls.

Document whether optional eggsearch absence is a skip for inactive configuration or a fail/diagnostic for explicitly selected configuration. Production configured-but-invalid credentials/configuration must not be disguised as fallback success. Ensure no global search admission limit is bypassed through threads.

## Workstream 4 — Deterministic tests and acceptance

Add tests/test_search_eggsearch.py and update tests/test_search.py, tests/test_services_search_session.py, tests/test_pipeline_research.py, tests/test_subagent_tools.py and config/doctor tests where appropriate. Test:
- opt-in registration and legacy/default parity;
- native module absent, wheel binary import failure, invalid TOML, disabled search mode, schema/version mismatch;
- success, empty success, partial providers, all providers failed, timeout/cancellation, invalid/unsafe URL, malformed result, result clamp;
- explicit per-stage provider override and documented transient fallback ordering/deadline;
- worker concurrency/repeated calls and no leaked tasks/clients;
- config resolution/redaction for user/system/container and reset/reload behavior.

All ordinary tests use injected fake eggsearch dictionaries; no live network or Rust build needed in the base CI. Explicitly use the upstream tool_contracts() fingerprint to detect schema drift during native integration qualification, not on every routine request.

## Exit criteria

- [ ] Registered eggsearch backend is selectable, disabled by default, and consumes structured result JSON.
- [ ] Existing search_web() and SearchResult consumers retain baseline behavior.
- [ ] No always-on MCP service, required Rust toolchain, or mandatory eggsearch dependency is introduced.
- [ ] Native lifecycle and cancellation are bounded in Celery and subagent threads.
- [ ] Empty, degraded, and failed retrievals remain distinguishable to the new detailed API.
- [ ] Config and diagnostics are correct across supported deployment modes, with secrets redacted.
- [ ] Existing search, research, provider, and offline CI tests pass; implementation/CI commit recorded in the roadmap.

## Out of scope

Do not turn on eggsearch as the default, replace SQLite/hybrid article search, migrate ingestion fetching, delete DuckDuckGo/Google/SearXNG, or add advanced research_search/security_search tools to agents in this phase.
