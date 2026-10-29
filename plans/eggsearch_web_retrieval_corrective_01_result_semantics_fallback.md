# Eggsearch Retrieval Corrective 01 — Result Semantics, Fallback, and Worker Concurrency

**Status:** IN PROGRESS — local semantics, opt-in deadline fallback, bounded concurrency, and research/tool propagation are implemented with focused regressions; supported-host worker lifecycle and full CI evidence remain open (2026-10-28).
**Baseline:** `plan/eggsearch-web-retrieval-20261028` at `c5d2c3596ee16340202ca7cb2515cfa3e458d290`, `eggsearch==0.4.4`, upstream source/tag `13fcac0b7ac0125d38e4e9775ebe1d62028fda72`.
**Related roadmap:** [eggsearch_web_retrieval_roadmap.md](eggsearch_web_retrieval_roadmap.md); closes corrective portions of Phase 1 and Phase 2.
**Priority:** Complete this before a default-provider switch, release qualification, or live research canary.
**Boundary:** Ainews search/research only. No eggsearch repository changes, new MCP service, ingestion rewrite, or direct eggsearch web_fetch.

## Confirmed current behavior to correct

1. `services/search/eggsearch.py` sets `partial = bool(failures) or bool(warnings) ...`; upstream always emits informational `generic_context_untrusted` in `structured_warnings`. Successful live results can therefore be labeled PARTIAL without an actual provider failure.
2. `_request_search()` asks for `response_detail="compact"`; upstream `src/mcp/projection.rs::project_web_search` removes `retrieval_summary` and `capability_enforcement`, inserting `retrieval_status` and `capability_summary`. The adapter reads the removed fields, so failure/freshness diagnostics are lost. With full output, a naive `bool(value)` is still wrong: enforcement is a structured list of enforced/approximated/unenforced capabilities, not `dict[str, bool]`.
3. Upstream `src/mcp/tools/web_search.rs` emits failed-provider entries with `error_class`; the adapter asks for `failure_class`, degrading them all to a generic reason.
4. `services/search/__init__.py::search_web_detailed` and legacy `search_web` select a provider but do not retry a different explicitly enabled backend on runtime failure. `services/provider_base.py::get_with_fallback` only retries provider **construction**, not searches. Legacy providers may swallow failure and return `[]`; never reinterpret a legitimate empty legacy response as a proven outage.
5. `EggsearchSearchProvider.last_outcome` is mutated on cached provider instances, so concurrent Celery/subagent requests can overwrite the outcome for a different query.
6. `tasks/research.py::_perform_web_search_and_synthesis` still calls list-returning `search_web` or `get_search_provider(...).search`. The new error and freshness metadata cannot yet inform research-stage degradation/fallback; explicitly selected provider override semantics need to remain clear.
7. New `tests/test_search_eggsearch.py` fixtures claim `response_detail="compact"` and `capability_enforcement: {"freshness": false}` as if they were a native compact payload, so tests currently conceal the mismatch.

## Workstream A — Correct real upstream payload mapping (P0)

**Files:** `services/search/eggsearch.py`, `services/search/evidence.py`, `tests/test_search_eggsearch.py`, native contract tests.

- Capture a version-pinned native `web_search` fixture for `standard` and `compact` projections, including results, `providers_failed`, `structured_warnings`, `retrieval_summary` vs `retrieval_status`, and `capability_enforcement` vs `capability_summary`. Keep these as sanitized fixture files (no live network in ordinary tests) and assert their schema in the opted-in native test.
- Prefer `response_detail="standard"` at the **internal service boundary** until compact diagnostics are demonstrably equivalent. Model prompts should still receive short source cards, not whole response objects. If keeping compact for efficiency, map its summarized fields explicitly; do not silently assume full fields exist.
- Define typed, bounded diagnostics at the ainews boundary: failure records should preserve upstream `id` and `error_class`, sanitize and limit any message, and handle unknown fields without manufacturing a failure category. Distinguish real provider failures, deadlines, empty success, malformed payload, no sources surviving URL validation, and optional package/config failures. Keep a compatibility accessor for existing SearchOutcome consumers.
- Separate **informational** warnings (e.g. `generic_context_untrusted`) from degraded retrieval. Warn about prompt injection without automatically treating a successful search as provider failure. Classify partial only when a provider failure, incomplete deadline, missing required capability, or other evidence of reduced retrieval actually applies. A warning may be important without implying partial; retain it in diagnostics.
- Model `requested_capabilities` and per-capability enforcement with explicit states such as `enforced / approximated / not_enforced / unknown`, not truthiness of arbitrary JSON. Publication age is never inferred from a freshness request; if actual enforcement is unproven, mark the result date-unverified. Do not turn `metadata.published_at` into a claim of publisher verification.
- Keep bounded `SearchResult` metadata, verified public HTTP(S) URL normalization, title/snippet limits, and trust-as-untrusted framing.

**Required fixtures:** all-success + generic warning => OK; two providers with one failure => PARTIAL with true `error_class`; all providers fail => FAILED; empty successful search => EMPTY; missing `published_at` => unknown; capability enforced/approximated/unenforced/unknown; compact response received unexpectedly => either correctly mapped or typed compatibility failure (never silent “enforced”); all cards rejected by URL validation => explicit filtering diagnostic.

## Workstream B — Implement opt-in runtime fallback with one deadline (P0)

**Files:** `services/search/__init__.py`, `services/search/evidence.py`, search-focused registry/config code, `tests/test_search.py` plus a new focused fallback suite.

- Put search-specific retry selection and policy in the web-search service rather than changing shared `ProviderManager` behavior for LLM providers.
- Define an explicit search fallback policy in validated `providers.yaml` configuration, defaulting to **no runtime retry** for an explicit `provider_id` override; no hidden provider substitution for research stages deliberately pinned to a backend. For default-provider selection, a fallback list must consist only of configured, enabled search backends; preserve order, avoid loops/duplicate attempts, and make the policy discoverable in operator docs.
- Use a common monotonic deadline covering **every** attempt, local validation, network wait, and close. Pass remaining budget into the native client; don't stack two 20-second search calls. Bound attempts and concurrency. Timeout/cancellation semantics for the legacy DuckDuckGo ThreadPoolExecutor require special care: `future.cancel()` does not necessarily stop already-running work. Document and test the best-effort limitation; do not promise hard cancellation of legacy I/O.
- Retry only on explicitly classified transient failures: unavailable package/service, transport errors, all-provider upstream failure, or timeout when fallback is enabled. A valid `EMPTY` is not by itself retriable. Config/security errors should remain observable and may fail closed depending on explicit environment policy. Do not retry on “informational warning.”
- Preserve `SearchOutcome(provider_attempts, provider_failures, fallback_used, duration_ms)` across attempts with final-success vs partial status clearly represented. Preserve original provider attribution on every result; no synthetic eggsearch source ID on a legacy fallback.
- Existing `search_web()` continues returning `list[SearchResult]` from the **same detailed service** and not an independent, divergent branch. Explicit `get_search_provider(id)` remains available; decide whether fallback is deliberately disallowed at that direct contract and document the choice.
- Legacy providers currently swallow exceptions into `[]`; do not treat their `[]` as proof of failure. An adapter-level typed outcome is needed if policy requires precise retries for those providers.

**Required fixtures:** fallback enabled on primary FAILED, fallback disabled, explicit override fails without substitution, empty primary does not retry, partial primary with useful results does not retry by default, disabled/duplicate fallback skipped, combined deadline reached, fallback itself failed, malformed config fails with redacted diagnostics, no extra provider calls after time budget exhausted.

## Workstream C — Worker-safe result ownership and native lifecycle (P1)

**Files:** `services/search/eggsearch.py`, search API contracts, parallel tests.

- Remove `last_outcome` as the authoritative per-call result. Return independent immutable or independently-owned SearchOutcome for each invocation; if retaining an observational `last_outcome` for debugging, document it as nondeterministic and never read it for pipeline correctness. Avoid nested mutable collections being shared between requests.
- Make the bridge's `asyncio.run` per-call lifecycle an explicitly benchmarked initial choice, not an assumed optimal long-term worker architecture. Validate SDK creation/closure around threadpool tasks and Celery prefork children, no reuse of clients across forks or incompatible event loops, bounded native admission and thread use, cancellation, timeout and shutdown behavior.
- Ensure request timeout and close timeout are bounded jointly where feasible. Concurrency/resource ceilings should be set once per Celery worker and align with eggsearch's process-level native limits. Avoid blocking an event-loop thread with the synchronous `search_web` facade; reject it explicitly or expose a separate async entrypoint for that caller.
- Test two concurrent queries on one cached provider returning distinct source IDs/statuses and verify no cross-talk, plus repeated sequential calls, cancellation, and worker restart.

## Workstream D — Propagate outcome semantics to research (P1)

**Files:** `tasks/research.py`, `services/subagent/tools.py`, relevant research/quality-gate prompts and tests.

- Migrate research orchestration to the detailed search seam without breaking the existing `web_results` list/synthesis shape. Preserve the requested explicit provider and fallback policy. Record `status`, deadline, attempts, capability states, upstream failures, and warning codes in task-side evidence/log metadata; never leak credentials or whole untrusted upstream response to prompts.
- A missing date or unenforced freshness filter must remain unknown in researcher output; do not allow “searched in last day” to become “published today.” No fabricated URL or cited timestamp.
- Make tool responses distinguish “no results” from “search unavailable” without broadening model tool access or adding eggsearch `web_fetch`; retain the already-correct URL and source ID formatting.
- Preserve first-party `services/safe_fetch.py` for article content; the external search integration only discovers candidate URLs.

## Workstream E — Corrective verification / acceptance

- Unit: `tests/test_search_eggsearch.py`, new detailed/fallback suite, `tests/test_subagent_tools.py`, `tests/test_tasks_research_new.py`, `tests/test_pipeline_research.py`; add deadline/fork/concurrency fixtures with deterministic fakes and no network.
- Native: opt-in test on published eggsearch 0.4.4 wheel checks schema fingerprint for `web_search`, behavior of `standard` projection and real generic warning handling.
- Re-run `uv run ruff check .`, `uv run mypy .`, targeted pytest and the repository's complete offline suite in the qualified Python environment (CI evidence handled by Corrective 02). Do not claim tests pass without exact command, runner and exit status.
- Update `docs/eggsearch-retrieval-qualification.md` with each pass/failure, implementation SHA and limitations. No production/default switch in this corrective pass.

## Closure criteria

- [x] Generic `generic_context_untrusted` warning with useful results no longer yields false PARTIAL (local regression).
- [x] Upstream `error_class`/`failure_class`, compact/standard status, and capability enforcement semantics are preserved conservatively for the selected projection (fixture regressions).
- [x] Success, partial, empty, failure and security filtering are distinguishable in the service/research/tool paths (local regressions).
- [x] Runtime fallback policy is explicit, opt-in, deadline-bounded at the caller, accurately attributed, and regression-tested; legacy thread termination remains best-effort.
- [ ] Concurrent native lifecycle/close stress and worker shutdown/restart are verified on supported worker hosts; the eight-slot bound and per-call ownership have local fake-provider regressions.
- [x] Research and subagents consume detailed outcomes; unavailable is not rendered as “no results,” and requested-but-unenforced freshness is marked date-unverified (local regressions).
- [ ] All operational checks required by this corrective plan are cited; no unsupported “fully completed” claims.

**Implementation order:** A -> B -> C -> D -> E. The Phase 3 rollout gate cannot close until all checked.
