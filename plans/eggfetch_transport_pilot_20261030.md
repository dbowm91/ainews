# EggFetch HTTP Transport Pilot

**Status:** AInews INTEGRATION IMPLEMENTED LOCALLY; ADOPTION QUALIFICATION NEAR COMPLETE — upstream E1–E3 gates are closed by EggFetch 0.3.0. User-approved qualification excludes broad provider parity, proxy tests, fixed five-minute prefill duration, Intel macOS, and tag-signing cleanup. Slow-prefill, long-response, structured-output, streaming/disconnect, limiter-cap, and full non-browser suite evidence is recorded. Linux target qualification is the remaining environment-dependent item. See [E4 qualification results](eggfetch_e4_ainews_requalification_20261030.md#qualification-results--2026-10-31).
**Date:** 2026-10-30
**Owner:** AInews maintainers, with upstream EggFetch collaboration for compatibility findings.
**Registry:** [Master implementation plan](plan.md#active-plan-registry--eggfetch-http-transport-pilot-2026-10-30).

## Objective

Evaluate replacing AInews's HTTPX-backed LLM SDK transports with EggFetch, an owned transport project already used by other projects. The pilot should establish whether EggFetch can serve AInews's multi-provider adapter and long-running local-inference workload, identify any missing or incompatible behavior, and turn actionable findings into focused EggFetch upstream work.

This is a qualification plan, not a decision to replace HTTPX. The pilot may conclude that adoption is not currently justified. Keep the implementation provider-neutral: do not design around one model vendor or add model-specific behavior to solve a transport concern.

## Constraints and guardrails

- Keep the currently running disposable AInews development server, its database, supervisor, web process, Celery worker, Beat process, and Redis state untouched during planning and any later isolated pilot setup. Do not restart, reconfigure, migrate, or repoint it as part of this workstream.
- Do not change production dependency resolution, `pyproject.toml`, `uv.lock`, or deployed runtime behavior during the isolated feasibility phase.
- Exercise the application through its ASGI server for application-level qualification. Proxy-specific testing is out of scope for this pilot.
- Preserve the existing `services/llm/` provider abstraction. The initial workload may use the configured local OpenAI-compatible endpoint, but the transport contract must be checked against all affected adapters and supported SDK integration paths.
- Treat EggFetch compatibility claims as hypotheses to verify against the exact EggFetch and SDK versions selected for the pilot. Record the version and commit/release for every result.
- Keep a straightforward rollback to the current pinned HTTPX transport until the adoption gate is met.
- No switch is justified by a synthetic microbenchmark alone. Measure the actual AInews request path and constrained local-inference scenario; transport replacement is not expected by itself to reduce model generation time.

## Current integration points to inspect

The current dependency set pins `httpx==0.28.1`, `openai==2.29.0`, `anthropic==0.87.0`, and `ollama==0.6.1`; Google GenAI is also an active adapter dependency. Reconfirm these values at pilot start rather than assuming they remain unchanged.

- `services/llm/openai.py` constructs an HTTPX client with connection limits and a provider timeout, injects it into the OpenAI SDK, and sets SDK retries to zero so application-level retry policy remains authoritative. It supports OpenAI-compatible endpoints, including local inference servers.
- `services/llm/anthropic.py` injects an HTTPX client into the Anthropic SDK and uses its provider timeout.
- `services/llm/ollama.py` injects the client into the Ollama SDK and also passes its timeout through the SDK configuration.
- `services/llm/gemini.py` uses the Google GenAI client path and expresses its timeout in milliseconds. Verify whether and how that SDK uses HTTPX before including it in any global dependency substitution; do not force it into the EggFetch path without evidence that it is affected.
- `services/llm/base.py`, `services/llm/errors.py`, and provider tests define the application-facing response, error, retry, streaming, and fallback contracts. Preserve these contracts independently of transport choice.

The prior research identified a material integration risk: the installed OpenAI and Anthropic SDKs perform nominal HTTPX client type checks. `eggfetch.compat.httpx` may expose compatible behavior but a distinct Python class, so passing it directly may fail at SDK construction. EggFetch documents a controlled replacement/shim approach; establish class identity and packaging behavior experimentally before considering it. Do not solve the issue by an undocumented monkeypatch or by relying on private SDK internals.

## Pilot phases

### P0 — Capture baseline and define the comparison

1. Record current branch/revision, Python and platform, lockfile versions, local inference endpoint and model identifier, configured LLM timeout, app concurrency cap, worker topology, and ASGI command.
2. Record baseline results for the checks in P3 and P4 using the current HTTPX transport. Use the same machine, provider configuration, prompt payloads, and concurrency in the EggFetch comparison.
3. Inventory every direct HTTPX import and every SDK-owned/custom HTTP client construction in LLM adapters and related tests. Separate LLM transport use from unrelated HTTPX use elsewhere in the repository.
4. Document existing timeout semantics end to end: SDK timeout configuration, connect/read/write/pool behavior, application retry classification and count, rate-limiter slot lifetime, streaming behavior, and pipeline task timeout/retry settings. Identify which layer can declare a request timed out and which layer can retry it.

**Exit:** A reproducible baseline and an explicit list of call surfaces and timeout/retry owners exist before EggFetch is introduced.

### P1 — Isolated compatibility and packaging spike

1. Use a temporary worktree or isolated virtual environment. Keep the active development server's environment and files unchanged.
2. Test the ordinary EggFetch HTTPX facade against each relevant SDK constructor at the exact pinned versions. Capture pass/fail and the complete exception for nominal client checks.
3. If the facade fails, evaluate the documented controlled replacement in isolation. Check import identity (`httpx.Client` as imported by the SDK and application), installed distribution metadata, dependency resolution, and whether the approach can be built reproducibly by the project's `uv` development, CI, Docker, and release-install paths.
4. Check whether EggFetch has a supported native-client integration path for each SDK. Do not assume an SDK accepts arbitrary HTTP transports simply because the public methods look similar.
5. Verify that coexistence and rollback are practical. If EggFetch requires shadowing the public `httpx` namespace, document the namespace, wheel provenance, supply-chain and packaging implications, and safeguards against publishing a private replacement under the public `httpx` distribution name.
6. Produce a compatibility matrix for OpenAI/OpenAI-compatible, Anthropic, Ollama, and Google GenAI: transport injection point, SDK type constraints, streaming/tool-call paths, timeout mapping, exception translation, and whether EggFetch would actually be used.

**Exit:** One supported integration strategy is demonstrated without private monkeypatches, or a concise upstream issue is prepared describing the blocker and the smallest supported extension needed. If neither is viable, stop adoption work and report the reason.

### P2 — EggFetch behavior gap review and upstream feedback

Compare the exact pilot EggFetch version with the AInews transport contract. Investigate gaps in:

- SDK-required client surface and class identity;
- long request timeouts, including delayed first byte and slow streaming responses;
- connection pooling and configured connection limits;
- request/response headers, base URL handling, TLS verification and custom CA configuration used by supported deployments;
- sync behavior and resource closure across the web and Celery processes;
- streaming chunk delivery, response closure, and cancellation when a pipeline task is stopped or times out;
- transport exception types and mapping to AInews's retryable, timeout, rate-limit, and terminal provider errors;
- retry ownership, to prevent transport-level retries from multiplying application/SDK retries or repeating completed inference work;
- required platform wheels/install behavior on the Python/platform combinations supported by AInews.

For each issue, include a minimal reproducer, expected/actual behavior, exact versions, and a regression test proposal. Route EggFetch defects or missing APIs upstream as focused issues or patches in the owned EggFetch project. Keep AInews-specific workarounds out of the provider layer unless they are small, documented, and independently justified. Track upstream change IDs/commits and the EggFetch release that contains a fix.

**Exit:** Every material gap is either fixed upstream and available in a pinned pilot build, accepted as a documented limitation with no impact on AInews requirements, or recorded as a no-go condition.

### P3 — AInews transport contract tests

In an isolated AInews branch/worktree, add a transport conformance suite that can run against the baseline HTTPX adapter and the EggFetch candidate. Keep tests deterministic with a local stub HTTP server; external network access is not required.

Cover, for each applicable adapter:

1. Client creation through the actual provider SDK, including configured base URL, authentication header, timeout, connection limits where supported, and clean close.
2. Normal response parsing, provider/model metadata, usage fields, structured JSON responses, tool/function calls, and malformed/error responses.
3. Streaming first chunk, multiple chunks, completion, mid-stream server failure, consumer cancellation, and cleanup.
4. Timeout classification for connect failure, delayed response headers/first byte, stalled response body, and total elapsed request. Assert that a five-minute-or-longer configured local inference request is not cut off by a shorter hidden SDK or transport default.
5. Error normalization and retry behavior: a timed-out request reaches the existing retry policy once, does not trigger an invisible transport retry, and terminal/auth/rate-limit errors keep their established classification.
6. Concurrent requests obey the existing AInews request cap; swapping transports must not create a second independent concurrency policy or increase in-flight calls beyond the configured bound.
7. Process/task teardown closes resources without affecting another provider client or leaving Celery tasks blocked on leaked connections.

Use parameterized tests where practical so the same application-level expectations run against both transports. SDK-specific differences belong in narrowly scoped adapter tests, not in model-name conditionals.

**Exit:** The same AInews behavior contracts pass for the candidate and baseline wherever the SDK's supported surface is shared; intentional differences are documented and accepted.

### P4 — ASGI and local-inference qualification

Run the isolated candidate build through the application's ASGI server. Do not test through a proxy. Preserve the live disposable server throughout; use a separate port, environment, database, and process group for this pilot if an application instance is needed.

1. Verify health and admin access without changing or sharing the live disposable instance's database or credentials.
2. Run one representative LLM-backed operation against a local OpenAI-compatible inference endpoint with a request that takes more than five minutes, if the endpoint is available for the isolated pilot.
3. Repeat with two simultaneous requests and with the configured lower concurrency cap. Record queue/wait time, request count, end-to-end time, inference completion, timeout behavior, and task state.
4. Run one representative streaming operation and one structured/tool-call path if those are used in the configured pipeline.
5. Trigger and stop a disposable in-flight pipeline task, verifying that task cancellation/worker cleanup and transport response closure behave as before.
6. Compare HTTPX and EggFetch using equivalent payloads and repeated runs. Record latency distribution, throughput, CPU, memory, connection count, and failure/retry counts. Separate transport overhead from local model generation and scheduler wait time.

If no local endpoint is available in the isolated pilot environment, complete the stub-based suite and mark the real-inference comparison as pending; do not infer a performance result from stub timings.

**Exit:** No unexpected timeout, duplicated inference request, retry amplification, leaked task/client, concurrency-cap bypass, or pipeline state divergence; performance results and their limitations are recorded.

### P5 — Adoption decision, rollout, and rollback

Choose one outcome:

- **Adopt:** EggFetch meets all compatibility, correctness, packaging, and operational gates. Pin an explicit released EggFetch version or immutable source revision. Update dependencies and all relevant installation/build paths in a separate implementation change. Keep rollback instructions to restore the previous HTTPX dependency and client construction.
- **Adopt after upstream work:** The pilot exposes fixable EggFetch gaps. Land upstream changes and release them first; then repeat the affected P1–P4 checks against the released artifact.
- **Defer/no-go:** SDK coupling, packaging replacement requirements, behavioral gaps, unsupported platforms, or measured regressions make the change too risky. Preserve HTTPX and retain the evidence and upstream issues so the work can resume later.

Adoption requires all of the following:

- SDK client construction works via a documented, supportable integration path for every adapter the change claims to affect.
- Long local inference, streaming, error classification, retries, cancellation, resource cleanup, and the admin-configured concurrency limit meet the existing application contract.
- AInews test, lint, type-check, lock consistency, and supported packaging/build gates pass on the final candidate revision.
- ASGI qualification evidence clearly distinguishes tests against stubs from real local inference.
- No proxy test is required for this pilot.
- Upstream findings and any accepted EggFetch limitations are linked from the final report.

## Deliverables

1. A versioned compatibility and integration matrix.
2. A concise baseline-versus-candidate report, including environment, commands, raw outcome counts, and measured performance or an explicit statement that real inference was unavailable.
3. Reproducers and upstream EggFetch issues/patches for actionable defects, linked by ID/commit and fixed release.
4. A decision record selecting Adopt, Adopt after upstream work, or Defer/no-go, with rollback steps.
5. If adopted, a separate implementation change containing code, tests, dependency/build updates, and documentation. Do not mark this pilot plan complete until the decision and its required evidence are recorded.

## Pilot execution record — 2026-10-30

### Decision

**Defer adoption.** The controlled replacement demonstrates a path to SDK compatibility, but two blockers make a runtime switch unsafe: EggFetch's HTTPX-compatible client does not enforce the configured read timeout while waiting for response headers, and the ordinary EggFetch facade does not satisfy the SDKs' nominal HTTPX client checks. The current architecture's Linux/aarch64 release path also lacks a published wheel and a validated source-build path. Do not change AInews dependency resolution until these gates have a supported answer.

### Evidence by phase

| Phase | Result | Evidence |
|---|---|---|
| P0 | Baseline captured | AInews pins HTTPX 0.28.1, OpenAI 2.29.0, Anthropic 0.87.0, and Ollama 0.6.1. The existing provider adapters inject HTTPX clients into the OpenAI/Anthropic SDKs. |
| P1 | Controlled shim path demonstrated; direct facade injection rejected | `eggfetch.compat.httpx.Client` is not an instance of the real `httpx.Client`, so current OpenAI/Anthropic SDK guards reject it. The controlled replacement satisfies class identity. A real HTTPX client plus EggFetch's current `HTTPTransport` is not a working alternative: the transport expects EggFetch's private request `_stream` field and fails with a standard HTTPX request. |
| P2 | Blockers found; one focused EggFetch patch prepared | OpenAI 2.29.0 requires `URL.copy_with(raw_path=...)`; the baseline EggFetch facade did not implement that form. A focused implementation and regression tests are present in the isolated EggFetch worktree at `/tmp/ainews-eggfetch-pilot/eggfetch` (based on EggFetch commit `873ea285`). This worktree is uncommitted and has not passed EggFetch's full Tier 1 or exact-SHA requalification, so it is a pilot patch, not a qualified EggFetch release. |
| P3 | Partial SDK and request qualification; timeout gate failed | With the controlled shim and the focused URL patch, client construction passed for OpenAI 2.29.0, Anthropic 0.87.0, Ollama 0.6.1, and Google GenAI 1.75.0. OpenAI completion, a 1.2-second delayed response, and SSE streaming passed against a local stub. The EggFetch URL compat suite passed: 107 passed. No Gemini-backed model inference was run. |
| P4 | Not run | The pilot stopped before ASGI/local-inference qualification because the read-timeout comparison failed and installation is not reproducible through the current project build paths. The live AInews instance was left running and untouched. |
| P5 | Defer | Reopen after EggFetch closes the timeout behavior gap and provides a supported Python 3.12 wheel or a reproducible, supported Rust build path across AInews's development, Docker, and installer flows. |

### Timeout reproduction

A local HTTP server delayed response headers by 1.2 seconds. With a 0.1-second read timeout, stock HTTPX 0.28.1 raised `ReadTimeout` after 0.10 seconds; EggFetch's HTTPX facade returned HTTP 200 after 1.35 seconds. This is a material behavior difference for non-streaming local inference: a provider timeout can exceed its configured read limit while the server has not sent response headers. Celery task limits may eventually terminate the task, but they are not a substitute for the configured provider request timeout.

### Packaging and runtime evidence

- The first packaging probe ran under a CPython 3.12 process reporting `macosx x86_64`; the user has clarified that the host is Apple Silicon and Intel Macs are not a target. Treat that as the interpreter's platform tag, not as evidence that native Apple Silicon lacks a wheel. The probe did not verify which architecture the Python process was running under. EggFetch 0.2.2 publishes a CPython 3.12 macOS arm64 wheel.
- The local test environment used Python 3.11 for EggFetch SDK compatibility tests because the available local EggFetch extension was built for CPython 3.11. The AInews live server remains on its existing Python 3.12 environment.
- No AInews dependency, lockfile, adapter, database, or running process was modified for the pilot.

### Qualification follow-up — 2026-10-30

This follow-up supersedes the packaging interpretation above where the public
release artifact list provides newer evidence.

- AInews's documented deployment targets are Linux x86_64, Linux aarch64,
  and macOS arm64; Windows is supported through WSL. Its current package
  requires Python 3.12+, and CI uses Python 3.12. Intel macOS is not a target.
- EggFetch 0.2.2's published CPython 3.12 wheels cover Linux x86_64 and macOS
  arm64, so those AInews targets can use binary wheels. EggFetch documents
  Linux aarch64 as source-build-only and not built or tested in its release
  CI. AInews supports native Linux aarch64, while its Docker builder installs
  `build-essential` but no Rust/Cargo; that path needs either an EggFetch
  aarch64 wheel with release smoke coverage or a deliberate and validated
  Rust/maturin source-build stage. Sources: [EggFetch 0.2.2 release files on
  PyPI](https://pypi.org/project/eggfetch/) and [EggFetch platform
  support](https://github.com/eggstack/eggfetch/blob/main/docs/getting-started/installation.md).
- The native Apple Silicon target is covered by EggFetch's published CPython
  3.12 macOS arm64 wheel. The earlier `macosx x86_64` package probe came from
  the selected interpreter's platform tag, not the host's hardware. Re-run
  packaging and application qualification with a native arm64 Python 3.12
  interpreter; no Intel Mac wheel is required.
- EggFetch supports Python 3.10–3.15, but AInews's current minimum and CI
  target are Python 3.12. The adoption qualification matrix should therefore
  pin and test Python 3.12 on each supported AInews platform rather than
  expanding to every EggFetch Python version.
- AInews's `pyproject.toml` still lists `darwin x86_64` in `uv.required-environments`,
  while the deployment docs and release smoke coverage list macOS arm64 only.
  This resolver marker is stale relative to the supported deployment matrix
  and should not make an Intel EggFetch wheel a pilot gate; remove or reconcile
  it in a separate dependency-metadata cleanup if the platform contract is
  being normalized.
- The controlled `httpx` replacement artifact is explicitly local-only and
  must never be published to PyPI. It is currently a qualification mechanism,
  not an installable production integration strategy. This leaves a material
  SDK construction blocker: OpenAI and Anthropic require the supplied client
  to pass nominal `httpx.Client` type checks, while the ordinary EggFetch
  facade has a different class identity. Adoption needs a documented,
  distributable integration strategy that preserves those SDK contracts and
  the no-public-`httpx`-replacement rule.
- EggFetch's core timeout suite passed (12 tests), and the `URL.copy_with`
  compatibility suite passed (107 tests) against the isolated uncommitted
  patch. The HTTPX-vs-EggFetch delayed-header reproducer remains a failure:
  HTTPX enforces the configured read timeout while EggFetch returns after the
  delay. The existing EggFetch timeout tests exercise stalled response bodies
  but do not close this response-header gap. A blanket timeout around the
  transport future would incorrectly consume connect and upload budgets, so a
  phase-correct response-header deadline is still needed upstream.
- EggFetch Tier 1 was run three times. It did not complete cleanly: the first
  run hit `eggfetch-bench::forwards_complete_origin_form_requests_and_repeated_gets`,
  the second hit `hyper_connect_proxy_reconnect_honors_short_current_total`,
  and the third hit the benchmark proxy test again. Both failure types passed
  at least once when rerun alone, but the benchmark proxy case also failed on a
  later isolated rerun, so it remains unresolved rather than being dismissed
  as transient. Because source/test inputs remain dirty and uncommitted, these
  runs are evidence only and do not qualify an exact SHA under EggFetch's
  verification policy.
- The pilot still does not enter AInews P3/P4. The no-go gates are the
  unsupported SDK integration path and the missing read timeout while waiting
  for response headers. P4 remains an ASGI/local-inference follow-up after
  those upstream gates close; proxy testing is not required.

**Current qualification:** E1–E3 upstream gates are closed in EggFetch 0.3.0:
the released package provides the SDK-compatible HTTPX transport bridge, the
H1/H2 response-header read timeout behavior is qualified, and the published
artifact includes Linux aarch64 wheels. AInews's integration is implemented in
this worktree and has passed 106 focused tests on both the initial x86_64
environment and a native Apple Silicon CPython 3.12.13 environment. The native
arm64 frozen dependency/dev sync passed. A direct ASGI request to local LM
Studio completed in 629.9 seconds, exceeding five minutes through long
generation. A later 95,223-token prompt completed successfully in 146.3 seconds
and provides the slow-prefill evidence.

The 629.9-second ASGI result was long-generation with only 112 input tokens.
It proves the configured 1,800-second provider read/request timeout can cover a
long response. A subsequent successful 444 KB/95,223-input-token request
completed in 146.3 seconds and establishes slow-prefill behavior. No fixed
five-minute prefill duration is required because timing is model- and
hardware-dependent.

The user-directed 2026-10-31 scope supersedes the original broad matrix and
unsigned-tag gate: qualify AInews paths in use, accept EggFetch 0.3.0
provenance, exclude Intel macOS, and do not require proxy testing or a fixed
five-minute prefill duration. The successful 95,223-token ASGI request and
629.9-second response qualify large-prompt and long-read behavior. Adoption is
still open only for Linux x86_64/aarch64 install/build checks through remote CI
or native Linux. Direct ASGI checks now cover structured output,
stream completion and disconnect cleanup, and two concurrent requests under a
model/global concurrency cap of one. The full non-browser suite passed 5,044
tests; two additional focused cancellation tests pass. Detailed evidence and rollback steps are in
[E4](eggfetch_e4_ainews_requalification_20261030.md).

### Original research gates (superseded by E1–E4)

This list records the gates identified by the original pilot research. E1–E3
have since closed in EggFetch 0.3.0; the AInews-specific open work is tracked in
the current qualification above and in E4.

1. **Closed in E2/EggFetch 0.3.0:** HTTPX-compatible H1/H2 response-header read timeout with regression coverage.
2. **Closed in E1/EggFetch 0.3.0:** the SDK-compatible transport bridge and OpenAI SDK compatibility fixture.
3. **Upstream release gate closed in E3/EggFetch 0.3.0:** Python 3.12 Linux aarch64 wheel publication and release smoke. AInews's native install/build qualification on Linux x86_64 and Linux aarch64 remains open.
4. **Still open in E4:** complete direct ASGI qualification, including high-prefill local inference, concurrency, streaming/tool use, and cancellation/cleanup. The active development server remains untouched.
5. **Closed in E4 implementation:** Ollama 0.6.1 transport construction was corrected to use its documented `transport=` argument and is covered by the focused provider suite.

Until these AInews-specific gates close, keep this as a local pilot change and
do not merge/release the EggFetch runtime switch. If qualification fails, use
the documented HTTPX rollback path. The release-provenance caveat is accepted
by the user for this adoption; unsigned-tag cleanup is deferred manual work.

### Blocker closure research — 2026-10-30

This section turns the open gates into ordered work packages, with a recommended
technical path and objective evidence required to reopen the adoption decision.
It is research and does not authorize changing AInews's runtime dependency or
the running development instance.

The registered implementation handoffs are listed in [plans/plan.md](plan.md#active-plan-registry--eggfetch-http-transport-pilot-2026-10-30): E1 (SDK transport bridge), E2 (read timeout), E3 (platform and upstream release qualification), and E4 (AInews requalification). This pilot remains **Defer** until E1–E4 close.

#### B1 — Provide a supported SDK-compatible transport integration

**Why this blocks adoption:** OpenAI and Anthropic at the pinned versions
validate injected clients by nominal `httpx.Client` / `httpx.AsyncClient`
identity. EggFetch's compatibility client is a different class, and its
existing `HTTPTransport` consumes EggFetch request internals rather than the
public HTTPX transport request contract. The controlled namespace replacement
proved a test path, but is not a safe distributable integration.

**Recommended work:** Implement an optional EggFetch HTTPX transport bridge
(for example, `eggfetch.integrations.httpx`) that subclasses the public
`httpx.BaseTransport` and, if the supported scope includes async SDK calls,
`httpx.AsyncBaseTransport`. Keep the real HTTPX client as the SDK-facing
facade, so SDK identity checks, client configuration, and SDK lifecycle remain
ordinary HTTPX behavior; the bridge delegates actual network I/O to EggFetch.
HTTPX documents these public transport base classes as its extension point for
custom request/response transports. The bridge must convert method, URL,
headers, body stream, timeout extensions, response headers and response body
stream without using private fields from either library.

The first qualification target should be the synchronous path used by
AInews's current provider adapters. Qualify async separately before claiming
async SDK support. Map each HTTPX timeout phase to EggFetch and translate
EggFetch connection, timeout, TLS, and protocol failures into the matching
HTTPX exception types with the original HTTPX request attached. For streamed
responses, close both the EggFetch response and the HTTPX-facing response on
normal completion, consumer cancellation, exceptions, and client shutdown.
Keep EggFetch retries disabled at this boundary so the existing provider
retry policy remains the sole retry owner.

**Adapter follow-through:** OpenAI and Anthropic can continue receiving a real
HTTPX client configured with the bridge. Google GenAI documents HTTPX as its
default and exposes `HttpOptions.client_args` / `async_client_args` and
custom HTTPX clients; test the bridge on the exact locked sync and async
construction paths. Ollama constructs its own HTTPX client from constructor
arguments; test passing the bridge through its supported `transport=`
argument. AInews's current Ollama `client=` argument is not the documented
client injection point and must be corrected if Ollama is included in the
rollout. Disable Anthropic SDK retries explicitly (its pinned default is two
retries) so transport adoption does not multiply calls; keep OpenAI retries at
zero, and verify Google GenAI retry options on the pinned release.

**Acceptance evidence:** A separately installable, documented integration
works with exact pinned SDK versions without replacing the public `httpx`
package, monkeypatching SDK internals, or importing EggFetch private request
members. Contract tests prove sync client creation and request/response
handling for every claimed adapter, streaming cleanup, error mapping, and
zero hidden retries. The optional integration's dependency metadata must be
installable in the project's locked environment without creating a dependency
cycle or conflicting HTTPX version.

#### B2 — Make read timeout cover response-header wait

**Why this blocks adoption:** HTTPX defines read timeout as the maximum wait
for a response data chunk; this includes waiting for the first response bytes
and headers. The reproduced EggFetch behavior applies the read budget to the
body stream but can wait beyond it for response headers. A request can
therefore outlive the configured provider timeout while local inference is
still generating its first response.

**Recommended upstream change:** Add a phase-correct response-header deadline
in EggFetch's shared request pipeline. Start the read phase after the request
body has been sent (while preserving early server responses), and race the
response-header wait against that deadline. Do not put a blanket `read`
timeout around the full request future: that incorrectly charges connection
setup and upload time to the read phase. Preserve the absolute total deadline
and its precedence on ties; maintain a per-chunk read deadline for response
bodies. Reset phase budgets appropriately for redirects/retries and ensure
cancellation drops/cleans up the in-flight request.

Add deterministic tests using the existing delayed-response test server:

1. delayed headers exceed read but not total -> `Read` timeout near the read
   limit;
2. connect delay exceeds connect -> `Connect`, not `Read`;
3. slow request-body producer exceeds write -> `Write`;
4. delayed headers below read and total -> success;
5. stalled response body -> `Read`, while regularly delivered chunks reset
   the read budget;
6. total expires before read -> `Total`, including when upload or headers are
   in progress;
7. behavior is consistent across each transport route EggFetch claims to
   support, including direct and custom transports used by AInews.

At the AInews bridge boundary, verify that this becomes `httpx.ReadTimeout`
and then the provider SDK's established timeout exception, with one
application-level retry decision and no repeated transport inference call.

**Acceptance evidence:** The delayed-header regression fails on the old
behavior and passes on the candidate. The complete timeout matrix passes,
including connect/write classification and total precedence; the prior
1.2-second delay / 0.1-second read reproducer fails promptly on EggFetch as it
does on HTTPX.

#### B3 — Close Linux aarch64 packaging support

**Platform correction:** AInews's target set for this pilot is Python 3.12 on
Linux x86_64, Linux aarch64, and macOS arm64. Windows deployments use WSL.
Intel macOS is not a target. The earlier `macosx x86_64` interpreter tag was
not evidence about the Apple Silicon host and must not be used as a gate.
EggFetch 0.2.2 publishes CPython 3.12 wheels for Linux x86_64 and macOS arm64,
but not Linux aarch64; its source-build path requires Rust/maturin, which the
AInews Docker builder does not currently install.

**Preferred work:** Add manylinux aarch64 wheel builds to EggFetch's release
matrix and run an import/request smoke test on native Linux aarch64 CI before
publishing. Keep the supported Python matrix consistent with EggFetch's
declared compatibility, while AInews's adoption gate only needs CPython 3.12
on its three documented platforms. If upstream cannot provide the wheel,
prototype and document a pinned Rust/maturin source build in AInews's Docker
builder and installer flows; ensure Rust is builder-only and that resulting
artifacts are reproducible and tested on native aarch64. A source build that
works only on the developer workstation does not close this gate.

**Acceptance evidence:** Frozen-lockfile install, wheel import, a minimal
request, and AInews image/build smoke pass on native Linux x86_64, native Linux
aarch64, and native macOS arm64 with Python 3.12. Reconcile the stale
`darwin x86_64` uv required-environment marker separately if needed; it does
not establish an Intel Mac support requirement.

#### B4 — Qualify the exact upstream candidate before AInews integration

The isolated EggFetch URL compatibility patch (`URL.copy_with(raw_path=...)`)
is useful pilot work but is dirty and not a qualified release. EggFetch Tier 1
also has an unresolved flaky benchmark proxy test: repeated suite runs failed
there, and a later isolated rerun failed too. The separate proxy reconnect
test failed once and passed when rerun. Proxy-specific qualification is not
required by this AInews pilot, but EggFetch's own Tier 1 failures still need
resolution under its project policy.

**Required order:**

1. Upstream the URL query/`raw_path` compatibility patch with a focused test
   and a downstream OpenAI 2.29.0 fixture.
2. Diagnose the flaky benchmark case and the one-off proxy reconnect failure;
   make the complete required EggFetch Tier 1 suite clean and repeatable.
3. Run EggFetch's prescribed checks on a frozen, clean exact commit SHA. Do
   not carry forward qualification results from a dirty worktree or a
   different SHA.
4. Publish or identify the immutable EggFetch artifact containing B1–B3
   fixes, then verify its package provenance and platform availability.
5. Only then resume AInews P3 and P4. P3 uses deterministic local HTTP stubs;
   P4 uses the AInews ASGI server on an isolated database/port and available
   local inference endpoint. No proxy testing is required. The live disposable
   development instance remains untouched.

**Final reopening gate:** The decision may move from Defer only when B1–B4
have evidence, AInews P3 passes against the released candidate on each target,
and ASGI P4 records available real-inference results (or explicitly records
that a real local endpoint was unavailable). Include a request taking more
than five minutes when such an endpoint is available, plus streaming,
structured output/tool calls, configured concurrency, cancellation, resource
closure, and retry counts. Compare against HTTPX with equivalent payloads;
do not infer inference performance from stub timings.

#### Primary references

- [HTTPX custom transports](https://www.python-httpx.org/advanced/transports/)
  documents `BaseTransport` and `AsyncBaseTransport` as the supported custom
  transport extension points.
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/) defines
  read timeout as the maximum wait for a response data chunk.
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/) says
  HTTPX is the default and documents sync/async client arguments and client
  lifecycle.
- [EggFetch 0.2.2 on PyPI](https://pypi.org/project/eggfetch/) lists the
  published wheel platforms and provenance; [EggFetch installation support](https://github.com/eggstack/eggfetch/blob/main/docs/getting-started/installation.md)
  describes Linux aarch64 source-build status.
- Exact pinned OpenAI and Anthropic SDK behavior was inspected in the
  isolated Python environment and should be rechecked if their lock versions
  change: nominal HTTPX client checks and retry defaults are version-specific.

## Research references

- [EggFetch project](https://github.com/eggstack/eggfetch)
- [EggFetch HTTPX 0.28.1 compatibility profile](https://github.com/eggstack/eggfetch/blob/main/compat/httpx/0.28.1/README.md)
- [EggFetch controlled HTTPX replacement notes](https://github.com/eggstack/eggfetch/blob/main/compat/httpx-controlled-replacement/README.md)
- [AInews LLM provider adapter architecture](../architecture/llm-providers.md)

The EggFetch compatibility and packaging documents are upstream references that may change. Recheck them against the selected EggFetch release before implementation.
