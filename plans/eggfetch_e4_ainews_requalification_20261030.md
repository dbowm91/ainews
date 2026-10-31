# E4 — AInews Transport Conformance and ASGI Requalification

**Status:** IMPLEMENTED LOCALLY; ADOPTION QUALIFICATION OPEN — EggFetch 0.3.0 closes the upstream E1–E3 release gate and the AInews integration is in the worktree. Native Apple Silicon frozen install and focused contracts pass. Full-suite regressions are diagnosed and being corrected; Linux target checks and some ASGI scenarios remain.
**Priority:** P1 adoption decision gate.
**Parent:** [EggFetch HTTP transport pilot](eggfetch_transport_pilot_20261030.md).
**Dependencies:** [E1 transport bridge](eggfetch_e1_sdk_transport_bridge_20261030.md), [E2 timeout semantics](eggfetch_e2_read_timeout_semantics_20261030.md), [E3 platform/release qualification](eggfetch_e3_platform_release_qualification_20261030.md).

## Objective

After a released EggFetch candidate closes upstream blockers, establish that AInews's provider, timeout, retry, streaming, cancellation, concurrency, process cleanup, packaging, and ASGI behavior remain within the existing HTTPX contract. Produce the final Adopt / Adopt after upstream work / Defer decision with rollback instructions.

## User-directed qualification scope — 2026-10-31

This scope supersedes any broader matrix or gate below where they conflict:

- Qualify behavior AInews actually uses. Do not reproduce a full HTTPX-versus-EggFetch provider parity matrix for every SDK and every possible protocol feature. Use targeted adapter construction/smoke coverage for the configured provider paths; focus deeper behavioral qualification on the active OpenAI-compatible local inference path and the AInews pipeline contracts.
- OpenCode Go is an acceptable external provider for supplemental tests. Local LM Studio is also explicitly approved for loopback-only disposable qualification; credential handling is not a blocker in this environment.
- Do not require every large-prompt request to exceed five minutes. Runtime depends on the selected model, context size, and hardware. Record prompt size, token count, and elapsed time, and demonstrate that configured client/Celery limits allow a successful slow-prefill request. The already completed 95,223-input-token request (146.3 seconds) is valid slow-prefill evidence; a separate 629.9-second generation demonstrates long read-timeout behavior.
- Linux qualification may run in remote CI or on a user-provided local Linux host. Intel macOS is excluded.
- EggFetch 0.3.0 provenance is accepted for this adoption decision. Unsigned-tag cleanup is deferred manual repository maintenance, not an adoption blocker.
- Proxy testing is out of scope. Direct ASGI testing is sufficient here.

## Guardrails

- Qualify the candidate in an isolated worktree/environment, database, port, and process group. Preserve the live disposable development instance and its workers.
- Use a separate worktree/environment, database, port, and process group for any app instance. Preserve the live disposable development instance and its workers.
- Exercise app-level qualification through the ASGI server directly. Proxy-based testing is out of scope and handled separately.
- Test on CPython 3.12 for Linux x86_64, Linux aarch64, and macOS arm64. Intel macOS is not a target.
- Use exact released EggFetch, HTTPX, and SDK versions; record the app and upstream SHAs.

## Qualification sequence

### 1. Deterministic provider contract suite

Run the relevant contract checks for AInews's EggFetch bridge using a local stub server. Compare HTTPX and EggFetch only where the baseline comparison provides useful evidence. Cover the active OpenAI-compatible path deeply and use focused construction/request smoke for configured Anthropic, Ollama, and Google GenAI adapters:

- client construction, base URL/auth, configured timeouts, and close/retirement lifecycle for supported adapters;
- active OpenAI-compatible normal and structured/tool calls, streaming, errors, and response cleanup;
- slow-prefill and long-response timeout behavior, retry ownership, and no duplicate inference request;
- enforcement of the configured concurrency ceiling and cancellation/worker teardown without stuck task state or leaked clients.

Set Anthropic SDK retries to zero and confirm Google GenAI retry behavior. Use Ollama's documented transport constructor argument and verify the AInews adapter's corrected client setup if Ollama remains in scope.

### 2. Target packaging and build checks

With the final lock and artifact, run frozen installation, import and minimal request smoke on the three platform targets. Build the AInews container on supported Linux architectures. Confirm macOS qualification runs under native arm64 Python rather than interpreting a process architecture tag as host hardware.

### 3. Direct ASGI and local inference

Use an isolated AInews database and ASGI server, not the currently running development instance. Do not use a proxy. Compare equivalent HTTPX and EggFetch requests and record exact request counts, end-to-end time, queue/wait time, timeout outcomes, failures/retries, concurrency, CPU/memory where available, and pipeline state.

When local inference is available, record at least one successful large-prompt request with modest output and at least one long response. Elapsed thresholds are evidence, not fixed gates: model and hardware throughput vary. Also run two requests through the configured concurrency limiter, one streaming request, and one structured/tool path used by the active pipeline. Trigger and cancel a disposable in-flight task; verify worker/resource cleanup and no stale pipeline state. If local inference is unavailable, record that fact and limit conclusions to stubs.

### 4. Decision and rollback

Select exactly one outcome:

- **Adopt:** all compatibility, timeout, retry, resource, platform and ASGI gates pass. Keep the prior HTTPX construction available as the documented rollback.
- **Adopt after upstream work:** specify the remaining upstream issue/release and repeat only affected qualification after it lands.
- **Defer/no-go:** retain HTTPX and record the blocking evidence and a precise resume condition.

## Acceptance criteria

- Relevant AInews adapter and pipeline contracts pass on the candidate; targeted baseline comparisons are recorded where they are useful.
- No short hidden timeout cuts off long local inference; no duplicate inference request, hidden retry, concurrency cap bypass, resource leak, cancellation regression, or pipeline-state divergence is observed.
- Direct ASGI outcomes are recorded, with stub and real-inference evidence clearly separated. Proxy testing is not required.
- Exact test commands, versions, platform details, EggFetch artifact provenance, AInews revision, outcomes and limitations are recorded in the pilot report.
- Decision and rollback steps are documented before any runtime switch is merged.

## Stop conditions

Any unexplained contract regression, unqualified supported platform, or timeout/retry ambiguity keeps AInews on HTTPX. The local-inference timing evidence is hardware-specific and no fixed five-minute threshold applies under the user-directed scope above.

## Implementation progress — 2026-10-31

- EggFetch 0.3.0 with the `httpx-transport` extra is now pinned in the AInews project. OpenAI, Anthropic, Ollama, and synchronous Google GenAI use EggFetch behind a genuine HTTPX client/transport boundary. EggFetch's own retries remain disabled; Anthropic SDK retries are explicitly disabled so AInews owns retries.
- Added `asgi.py` as the direct ASGI-server entry point around the Flask app; use an ASGI server such as Uvicorn for isolated qualification.
- Corrected Ollama construction to pass the supported HTTPX `transport` argument instead of the unsupported `client` keyword.
- Provider cache clearing and replacement retire clients without interrupting in-flight long requests; current and retired SDK clients close at process exit.
- Removed Intel macOS from uv's required environments and release artifacts. Installer rejects Intel macOS; README and artifact documentation now match the Apple Silicon target.
- No proxy testing is required. Proxy qualification remains a separate testing activity.
- Latest execution evidence and the precise remaining gates are recorded below. Do not treat this locally implemented pilot as an approved release switch until the open gates are closed.
- EggFetch 0.3.0's unsigned tag is accepted for this adoption. Repository release-signing cleanup is tracked as later manual maintenance.

## Qualification results — 2026-10-31

### Deterministic contract and static checks

- Locked versions: EggFetch 0.3.0 and HTTPX 0.28.1. `uv lock --check` passed.
- Focused command: `pytest -q tests/test_llm_adapters/test_eggfetch_transport.py tests/test_provider_manager_lifecycle.py tests/test_llm_adapters/test_openai.py tests/test_llm_adapters/test_anthropic.py tests/test_llm_adapters/test_ollama.py tests/test_llm_adapters/test_google.py tests/test_crawl_task.py tests/test_admin_route_auth.py tests/test_dev_supervisor.py tests/test_tasks_research_new.py::TestResearchArticleTask::test_research_task_budget_exceeds_nested_request_budget --timeout=120` — **108 passed** in 27.22s on native arm64. The x86_64 run passed the first 106 tests in 21.48s; the updated transport contract file passed all five tests on both x86_64 and arm64, including the same OpenAI completion through direct HTTPX and EggFetch.
- Targeted Ruff checks on changed integration, adapter, supervisor, and test files passed. `git diff --check` passed.
- Historical first full-suite attempt: the native arm64 non-browser run stalled at 38% because limiter test mocks selected scripts using an obsolete `INCR` heuristic. The mocks were corrected to match sorted-set lease scripts; after fixing seven additional stale test assumptions, the subsequent full non-browser suite passed (see “Full-suite regression resolution” below). Browser tests remain covered separately by CI.

### Direct ASGI and local inference

- Isolated Uvicorn app, database and port; no proxy; the running development instance was not changed. Provider: LM Studio OpenAI-compatible endpoint with `google/gemma-4-e2b`. The credential was supplied through a process environment variable and was not written to project files.
- A real local inference call completed through the EggFetch-backed OpenAI SDK path in 11.4 seconds (22 input tokens, 2 output tokens). A longer request completed in 156.3 seconds (97 input tokens, 10,789 output tokens; 57,280 response characters). A synthetic 444 KB request completed in **146.3 seconds** with **95,223 input tokens** and 4 output tokens; this confirms successful large-prompt prefill through the ASGI path.
- The active provider's `providers.yaml` timeout is 1,800 seconds. Research Celery soft/hard limits are 21,600/21,660 seconds; the bounded subagent retry/iteration budget is tested against these task limits. The application pipeline's elapsed-time guard is 3,600 seconds. This leaves substantial worker headroom over a single provider request, while the separate high-prefill measurement remains open.
- The final long-generation request completed successfully in **629.9 seconds** (112 input tokens, 26,049 output tokens; 145,519 response characters), with the ASGI request and provider timeout configured for 1,800 seconds. EggFetch/HTTPX logged one 200 response from LM Studio and the app returned a successful response; no retry occurred. This proves the long read/request path remains open for over ten minutes.
- A subsequent 444 KB synthetic prompt completed in **146.3 seconds** with **95,223 input tokens** and 4 output tokens through direct ASGI, providing successful slow-prefill evidence. Earlier 37 KB/110.3-second and 82 KB/634 KB failures are historical attempts and are superseded by this successful request.
- A request exceeding the development app's 64 KB body limit was rejected before inference and was discarded from transport conclusions.
- Still required: live pipeline-task cancellation and worker cleanup evidence, full-suite completion, and Linux install/build qualification. The 95,223-token prefill, 629.9-second long-generation, ASGI concurrency, streaming, and structured-output checks are complete. Full parity comparisons across every adapter are not required.

### ASGI follow-up — 2026-10-31

- Isolated loopback Uvicorn process uses `/tmp/ainews-eggfetch-e4-recheck/providers.yaml`, a disposable database, and Redis DB 14. It is separate from the development instance. No proxy is involved.
- Structured output: `POST /__e4/structured` returned `{"ready": true}` through `provider.chat_structured()`.
- Streaming: the ASGI stream endpoint returned 536 bytes; its generator cleanup flag was set. Disconnecting the client after the first stream chunk also set the cleanup flag.
- Concurrency: two simultaneous ASGI requests acquired the actual `ModelLimiter` with model/global caps set to one. Both completed, total elapsed 4.066 seconds, and the measured peak active count was exactly one; active leases returned to zero.
- These are disposable probe endpoints, not production routes. The probe establishes transport behavior and limiter cleanup.

### Full-suite regression resolution — 2026-10-31

- The previous non-browser suite stall came from stale limiter tests selecting a Lua script based on `INCR` even though the lease implementation uses sorted-set operations. The tests now map and verify the scripts registered by `ModelLimiter`; the stage test expects the configured two-hour limiter wait.
- The first complete run exposed eight failures: four editor-context and two research-context tests assumed legacy trend-memory reads despite `memory_v2_enabled: true`; those tests now explicitly select the legacy branch they exercise. One provider failure test performed the real cancellation DB check without an app context; it now isolates that check. Alembic rollback can leave both branch revisions at the merge boundary, so its test checks both revisions and retained schema.
- `pytest -q -m 'not browser' --timeout=120` on native macOS arm64 CPython 3.12.13: **5,044 passed, 2 skipped, 41 deselected in 401.57 seconds**. The new focused cancellation test module adds **2 passed** after this full run.
- `uv lock --check` passed. Targeted Ruff passed for changed tests; repository-wide Ruff still reports five existing findings in unrelated modules. `mypy . --exclude .venv` reports two existing tuple-typing errors in unchanged `services/feed_stats.py`; `mypy tests/test_pipeline_cancellation.py` passes.
- A new admin cancellation test verifies persisted cancelled state, indexed/active/root task revocation with SIGTERM, and task-index cleanup. This is control-path coverage, not a live Celery worker termination rehearsal.

### Platform and release provenance

- The initial behavior environment was CPython 3.12.13, macOS 26.6.2, x86_64 under Rosetta. It is not a target build. `uv sync --frozen` correctly cannot install the target lock on Intel macOS; the source-built local EggFetch package was used only for the x86 behavior run.
- Native Apple Silicon CPython 3.12.13 completed `uv sync --frozen --extra dev --no-install-project` into a separate temporary environment, downloading the published EggFetch 0.3.0 macOS arm64 wheel and resolving the full lock (142 runtime packages plus 22 dev packages). The final focused command listed above passed **108 tests in 27.22s** on native arm64 with `--timeout=120`. The provider subset also passed separately (**64 tests in 12.71s**). An initial combined run used the default 30-second test timeout and hit a cold SciPy import timeout; the warmed, longer-timeout rerun passed.
- Linux x86_64 and Linux aarch64 frozen install/import/request checks and supported Linux container builds remain unverified in this environment. Run them in target-native CI before adoption.
- EggFetch 0.3.0 was published through the recorded upstream release workflow, with 24 wheels and an sdist; native Apple Silicon and Linux aarch64 wheel smoke was recorded upstream. The user accepts its provenance for this adoption; signing cleanup is not a blocker.

### Current decision

**Adopt after qualification; not yet approved for merge/release.** Slow-prefill, long-generation, structured output, stream completion/disconnect, limiter concurrency, and full non-browser suite checks have passed. The focused admin cancellation/revoke test also passes. Remaining: Linux install/build qualification in remote CI or native Linux. Keep the documented HTTPX rollback path available. EggFetch provenance and proxy qualification are closed for this decision.

## Original research snapshot — 2026-10-30 (historical; superseded by current qualification)

- Local Python 3.12.13 construction smoke passed against HTTPX 0.28.1 and the
  locked OpenAI, Anthropic, Ollama, and Google GenAI SDK versions. A single
  OpenAI chat-completion call passed through EggFetch against a local stub.
  This validates constructor compatibility only; it is not the AInews provider
  contract suite or ASGI evidence.
- Google GenAI 1.75.0 retry behavior was checked in the locked SDK source:
  AInews sets no `retry_options`, and the SDK maps `None` to one attempt. If
  retry options are supplied, its documented default is five attempts including
  the initial call. The app retry policy therefore remains the only retry
  layer for the current Gemini configuration; keep this explicit in any E4
  adapter change.
- E4's runtime adapter changes and lockfile remain intentionally untouched
  until E1–E3 provide a clean immutable release candidate. That candidate does
  not yet exist. This prevents this plan from passing its own stated input
  requirement; implementation remains deferred pending the upstream freeze,
  Tier 1/2/3 checks, native ARM build/rehearsal, and immutable release.
- The release candidate has since been published and the subsequent 2026-10-31
  user-directed scope/results above replace this original gate list.
