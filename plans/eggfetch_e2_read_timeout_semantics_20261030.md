# E2 — Phase-Correct Response-Header Read Timeout

**Status:** UPSTREAM GATE CLOSED for the HTTPX bridge's H1/H2 scope in EggFetch 0.3.0; general experimental HTTP/3 header semantics remain outside that scope.
**Priority:** P0 adoption blocker.
**Parent:** [EggFetch HTTP transport pilot](eggfetch_transport_pilot_20261030.md).
**Next:** E1 is independent and may proceed in parallel. E4 depends on E1–E3.

## Objective

Make EggFetch enforce the configured read timeout while waiting for response headers/first bytes, without charging connect or request-upload time to the read budget or changing total-timeout semantics.

## Reproduction and expected behavior

The pilot's local server delayed headers for 1.2 seconds. HTTPX with a 0.1-second read timeout raised `ReadTimeout` promptly; EggFetch returned HTTP 200 after the delay. Add a deterministic EggFetch regression using its delayed-response test server, with a total timeout long enough not to win.

## Implementation scope

1. Trace every supported send path to the shared point where response headers become available, including direct and custom transports used by the AInews bridge.
2. Start the read phase after request-body completion while preserving servers that respond before upload completion. Race response-header waiting against this read deadline.
3. Do not wrap the complete request future in a blanket read timeout: connection establishment and upload must continue to use connect and write budgets.
4. Preserve the absolute total deadline and deterministic total-timeout precedence on ties. Apply read timeout per response chunk, resetting it when data arrives.
5. Define behavior across redirects and any retry attempts, ensuring each hop cannot escape the total deadline and cancellation releases the in-flight connection/stream.
6. Map the result to EggFetch's `Read` timeout error. E1's bridge must convert this into `httpx.ReadTimeout` associated with the original request.

## Required regression matrix

- Header delay over read and below total => `Read` timeout near the configured budget.
- Header delay below read and total => success.
- Connect delay over connect => `Connect`, not `Read`.
- Slow request-body producer over write => `Write`.
- Stalled response body => `Read`; regularly delivered body chunks reset the read budget.
- Total expires before read during connection, upload, or header wait => `Total`.
- Early server response during upload preserves the documented behavior and correct phase classification.
- Cancellation and error paths close response/body resources.
- The delayed-header result is consistent for every transport path included in EggFetch's support claim.

## Acceptance criteria

- The delayed-header regression fails before the fix and passes after it; the 1.2s/0.1s reproduction now terminates promptly.
- Full timeout-phase tests pass with correct classification, per-chunk read behavior, total-deadline precedence, and no timing flakes under the project's supported test method.
- Bridge-level verification maps EggFetch `Read` to HTTPX `ReadTimeout`, then to the provider SDK timeout caught by AInews's existing policy.
- No transport retry occurs; the application gets one timeout event to classify and retry according to its existing policy.
- Upstream change is qualified on a clean exact SHA before E4 uses it.

## Stop conditions

Do not compensate in AInews with a shorter Celery task limit or an outer timeout that kills the worker/request. If correct phase ownership cannot be implemented in the shared transport pipeline, defer adoption and document the unsupported case.

## Implementation and evidence — 2026-10-30

- The Hyper request-body wrapper now signals when request body production is
  complete. Hyper and UDS dispatch race that boundary against response-header
  arrival, applying `Timeout.read` only after upload completion; early responses
  remain eligible to return before upload completes. Connect and write phases
  stay under their existing owners. H1/H2 proxy, direct, SNI, custom, and native
  frame paths are wired through the shared helper.
- Total remains the outer owner and wins when its remaining budget is earlier
  or tied with the read deadline. Existing per-chunk read-body behavior is
  retained. Read timeout documentation now states the route boundary.
- Added deterministic delayed-header, early-response-during-upload, and
  total-precedence regressions; strengthened write/connect phase tests; and
  added native frame API delayed-header coverage including an empty request
  body. Latest focused runs: `cargo test -p eggfetch-core --all-features
  --test timeout_tests -- --test-threads=1` (15 passed) and
  `cargo test -p eggfetch-core --all-features --test native_http_body_tests
  -- --test-threads=1` (16 passed).
- `HyperRequestBody::is_end_stream()` mirrors the wrapped body's signal exactly
  and publishes the timeout phase boundary when that signal is observed,
  including empty bodies. This preserves Hyper's body framing contract; both
  focused suites passed again after this correction.
- The HTTPX bridge delayed-header regression maps the result to
  `httpx.ReadTimeout`; its 0.05-second read timeout terminates against a
  0.3-second delayed response. Python bridge + SDK + URL suites: 115 passed.
- Explicit limitation: experimental HTTP/3 still applies `Timeout.read` to
  response-body progress only; response-header waiting remains total-bounded.
  HTTPX's transport bridge selects H1/H2 only, so H3 is excluded from its
  support claim. Completing a general H3 phase-correct header timeout remains
  upstream work before an EggFetch-wide timeout claim can be made.
- These local results were superseded by the EggFetch 0.3.0 release and its
  exact-SHA qualification. E4 still must prove AInews's configured long timeout
  and provider exception handling with the released package. See
  [EggFetch v0.3.0](https://github.com/eggstack/eggfetch/releases/tag/v0.3.0).
