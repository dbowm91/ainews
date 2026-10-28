# Eggsearch Retrieval Qualification Record

**Assessment date:** 2026-10-28  
**Status:** NOT RELEASE-QUALIFIED — remain disabled/opt-in.  
**Roadmap:** [Eggsearch retrieval roadmap](../plans/eggsearch_web_retrieval_roadmap.md)

## Implemented in this worktree

- Added lazy optional `eggsearch` provider registration and a structured-result mapping adapter. It requires an explicit absolute existing `config_path`, validates result URLs with ainews SSRF validation, bounds result count/snippet size, preserves source/provider/date/trust metadata, and uses a per-call async lifecycle with configured timeout and bounded cleanup.
- Added the additive `SearchEvidence`, `SearchOutcome`, and `SearchStatus` contracts and `search_web_detailed()`. Existing `SearchResult` positional fields and list-returning `search_web()` remain compatible.
- Preserved citations in researcher/subagent prompts, labeled provider text `external_untrusted`, and added explicit anti-injection, corroboration, and unknown-date instructions.
- Added an inactive Eggsearch sample provider. The follow-up packaging change adds `eggsearch==0.4.4` only as an optional extra; no mandatory dependency, MCP service, Rust compiler requirement, ingestion fetch change, or default change was introduced.

## Upstream facts rechecked

On 2026-10-28, PyPI JSON and upstream `main` were both checked. PyPI publishes `eggsearch 0.4.4` (`>=3.11,<3.16`), uploaded 2026-10-28; Git tag `v0.4.4` resolves to the tested source commit `13fcac0b7ac0125d38e4e9775ebe1d62028fda72`. Current upstream `main` has advanced to `2ac49f6e945f3d940218587f75c18a9c573abe9d`. The published project description still says “not published to PyPI,” so that description is stale.

- [Python library](https://raw.githubusercontent.com/eggstack/eggsearch/main/docs/python-library.md) documents `AsyncEggsearch(config_path=None)`, `web_search(**kwargs)`, and an `aclose()` lifecycle. Its platform/wheel statements remain conditional on candidate CI qualification.
- [Tool matrix](https://raw.githubusercontent.com/eggstack/eggsearch/main/docs/tool-matrix.md) documents structured `SourceCard` fields (`id`, `title`, `url`, `snippet`, `provider_id`, `trust`, `metadata`), `providers_failed`, `retrieval_summary`, `capability_enforcement`, and compact projection.
- [Safety](https://raw.githubusercontent.com/eggstack/eggsearch/main/docs/safety.md) explicitly says DNS preflight is not connection-time pinning and does not eliminate DNS-rebinding TOCTOU risk. Eggsearch `web_fetch` therefore remains unused; ainews fetch policy remains authoritative.
- `cargo test -p eggsearch --features mock --locked` on the pinned commit ran **3,350 Rust tests: 3,348 passed, 2 failed**. One is a macOS `/private/var` vs `/var` path-equivalence assertion at [`state.rs:685`](https://github.com/eggstack/eggsearch/blob/13fcac0b7ac0125d38e4e9775ebe1d62028fda72/src/mcp/state.rs#L685). The other is security-significant: [`safe_open.rs` documents that safe symlink following is unsupported off Linux](https://github.com/eggstack/eggsearch/blob/13fcac0b7ac0125d38e4e9775ebe1d62028fda72/src/meta/safe_open.rs#L117-L135), but the macOS test [`structure_file_reader_rejects_symlink_escape_even_when_following_is_enabled`](https://github.com/eggstack/eggsearch/blob/13fcac0b7ac0125d38e4e9775ebe1d62028fda72/src/meta/repo_mapper.rs#L1288-L1306) fails because the outside-root symlink is followed. The isolated test reproduced this. No upstream source changes were made.

The build and API checks below were performed against a pinned source commit, not inferred from these mutable links alone.

## Local source build and runtime evidence

- Upstream commit: `13fcac0b7ac0125d38e4e9775ebe1d62028fda72` (`eggstack/eggsearch`, `main` at build time).
- Upstream Python package version: `0.4.4`; Rust 1.89.0; Maturin 1.9.5; built using `maturin build --manifest-path bindings/python/Cargo.toml --locked --release`.
- Local ARM64 artifact: `build/output/eggsearch-0.4.4-cp311-abi3-macosx_11_0_arm64.whl`; SHA-256 `8e6133bbb27a72c9d83dbf4e90b3e6e8f2879e6ce8f6d2bd72a363e4b869cf05`.
- Local source-built x86_64 artifact: `build/output/eggsearch-0.4.4-cp311-abi3-macosx_10_12_x86_64.whl`; SHA-256 `e7fc2c27371eff3cc253894b87608458f243e9ee250313868499dd12bec8c688`.
- PyPI ARM64 wheel SHA-256: `adaadee8bd530f302b642a48886ca723f19c245c5249e107aa885a0cfe78349e` (verified against PyPI JSON after download). PyPI x86_64 wheel SHA-256: `cb5dd563ee71f1aa8844c4c454effad17c1838ce315c01f14776dbf2733db7ad` (also verified against PyPI JSON). Published artifacts differ byte-for-byte from local builds, as expected, but expose the same tool contract.
- Both PyPI wheels report native `tool_contracts()` fingerprint `f9f3b0125d4d09fc` (10-tool inventory). The ARM64 wheel was installed/imported on CPython 3.14 arm64; x86_64 was installed/imported on CPython 3.12 x86_64. Tool-contract checks and client close passed on both.
- On ARM64, the published wheel passed the config/provider-status smoke test and actual ainews adapter round-trip in `search.mode = off` — **2 passed**. A separate bounded live smoke used only Eggsearch's DuckDuckGo provider (`max_results=3`), with fetch and workspace access disabled: **3 results, no provider failures**, and warning `generic_context_untrusted`; observed domains were `blog.trailofbits.com`, `pypi.org`, and `pyo3.rs`. This is a connectivity smoke, not a quality evaluation or canary.
- Upstream binding tests against the ARM64 wheel: **22 passed, 6 debug-only skips, 1 external all-operations smoke test deselected**. This covers typed tool schemas, invalid/oversized input handling, cancellation/close behavior, sequential event loops, local trusted search, config path/default behavior, and structured errors.

## Evidence collected

- Static lint: `ruff check` on changed Python files — **passed**.
- Syntax: `python3 -m py_compile` on changed Python modules — **passed**.
- Patch hygiene: `git diff --check` — **passed**.
- Targeted mypy invocation — **blocked** because the installed mypy native extension is ARM64 while the selected Python 3.14 interpreter is x86_64.
- `uv run --no-sync pytest tests/test_search_eggsearch.py tests/test_subagent_tools.py tests/test_tasks_research_new.py tests/test_pipeline_research.py -q` — **75 passed** (one upstream pytest-asyncio deprecation warning).
- `uv run --no-sync pytest tests/test_search_eggsearch.py --cov=services.search.eggsearch --cov-report=term -q` — **9 passed; Eggsearch adapter coverage 89.86%**.
- Follow-up validation: `uv lock --check` — **passed**; focused Eggsearch adapter + published x86_64 wheel tests — **11 passed**; research/subagent integration regression set — **75 passed**. The first combined attempt accidentally mixed ARM64 native dependencies with an x86_64 interpreter and failed collection; rerunning with the matching published x86_64 wheel passed.
- Including `tests/test_search.py` in the broader run fails two unaffected DuckDuckGo tests because `duckduckgo_search` is missing from the no-sync environment. The initial synced `uv run pytest ...` is blocked because the locked `torch==2.12.0` has no wheel matching this host. No full-suite pass is claimed.
- Upstream documentation was fetched successfully (links above); its prose still contains a stale unpublished-status statement. Published PyPI artifacts are independently installed and tested above; their checksums match the PyPI metadata.

Keep usage constrained to the ainews `web_search` call path, with fetch disabled and local workspace access disabled. Do not expose `repo_search`/`repo_fetch` or Eggsearch `web_fetch` through ainews until the symlink containment and DNS-pinning gaps are resolved upstream and re-tested.

## Unresolved release gates

1. PyPI 0.4.4 release metadata and available wheel checksums are verified, and local macOS x86_64/CPython 3.12 and arm64/CPython 3.14 published-wheel imports/tool contracts are proven. Still run clean-host installation and the complete import/ABI matrix, then Docker, worker shutdown/restart, CLI/doctor, and rollback tests on supported Linux x86_64/aarch64 and maintained targets.
3. Run the full ainews offline test suite under its supported Python 3.12 setup and achieve the required project type/lint gates. The current 75-test targeted run is not a full-suite substitute.
4. Add or qualify explicitly enabled runtime fallback with one shared request deadline before claiming provider outage recovery. Legacy providers may collapse errors to empty lists, so tests must distinguish that limitation.
5. Run a representative, fixed-input baseline-vs-Eggsearch evaluation and a feature-flagged canary. Record citation/source quality, freshness evidence, failures, p50/p95 latency, resource cost, privacy review, sample selection, uncertainty, and rollback evidence.
6. Source hydration remains deliberately unchanged. Any selected-source fetch must use `services/safe_fetch.py`; Eggsearch `web_fetch` has not passed equivalence review and is not used.

## Decision

Keep DuckDuckGo as the default and keep Eggsearch disabled unless/until every release gate above is satisfied. No claim of default migration, completed rollout, upstream compatibility, test-suite success, or live quality improvement is made by this record.
