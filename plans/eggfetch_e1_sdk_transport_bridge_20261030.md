# E1 — SDK-Compatible EggFetch Transport Bridge

**Status:** UPSTREAM GATE CLOSED in EggFetch 0.3.0; AInews adapter qualification continues in E4.
**Priority:** P0 adoption blocker.
**Parent:** [EggFetch HTTP transport pilot](eggfetch_transport_pilot_20261030.md).
**Next:** [E2 read timeout semantics](eggfetch_e2_read_timeout_semantics_20261030.md) is independent and may proceed in parallel. E4 depends on E1–E3.

## Objective

Provide a supported way for AInews's pinned LLM SDKs to use EggFetch for network I/O while preserving SDK-facing HTTPX client identity and public APIs. The integration must be distributable and maintainable; replacing the public `httpx` namespace, monkeypatching SDK internals, and depending on private request fields are out of scope.

## Verified constraint

The pinned OpenAI and Anthropic SDKs require injected clients to be instances of `httpx.Client` or `httpx.AsyncClient`. EggFetch's compat client is a distinct class. Its existing compat `HTTPTransport` also consumes EggFetch-specific request internals, so it cannot simply be passed to a real HTTPX client.

HTTPX's documented extension points are `httpx.BaseTransport` and `httpx.AsyncBaseTransport`. The recommended design is an optional EggFetch integration that implements those interfaces and delegates requests to EggFetch, while the SDK continues to use a genuine HTTPX client configured with that transport.

## Implementation scope

1. In EggFetch, add a documented optional integration module/extra that bridges public HTTPX request/response objects to EggFetch without private fields. Avoid a circular dependency by keeping the HTTPX integration optional and declaring a compatible HTTPX range.
2. Implement sync transport first because AInews's current provider calls are synchronous. Add async only with its own lifecycle and cancellation contract; do not imply async support before it is qualified.
3. Bridge method, URL/query, headers, request body streaming, timeout extensions, response metadata, and response body streaming. Define ownership and closure for both clients and response streams.
4. Translate EggFetch failures into the matching HTTPX exception hierarchy and attach the original HTTPX request, including connect/read/write/pool/total timeout distinctions where supported.
5. Keep transport retries disabled. The application/provider retry layer remains authoritative.
6. Add a focused URL compatibility regression for OpenAI 2.29.0's `URL.copy_with(raw_path=...)` use and a downstream SDK construction/request fixture.
7. Document supported HTTPX versions, lifecycle, unsupported behavior, sync/async status, and installation extra.

## Adapter integration requirements for E4

- OpenAI and Anthropic receive a genuine HTTPX client with the EggFetch transport.
- Anthropic retries are explicitly set to zero to avoid multiplying the application's retry policy; OpenAI remains at zero.
- Google GenAI's exact locked sync and async HTTPX configuration paths are exercised using its documented `client_args`, `async_client_args`, or custom-client options. Confirm SDK retry behavior on the locked version.
- Ollama's SDK-created HTTPX client receives the transport through its supported constructor kwargs (`transport=`). Correct AInews's current `client=` usage if Ollama remains in the claimed provider set.
- Do not alter model-specific request behavior or the shared provider abstraction to work around transport details.

## Acceptance criteria

- The integration installs without shadowing or replacing the public `httpx` distribution and without conflicting dependency resolution.
- Exact-version OpenAI, Anthropic, Ollama, and Google GenAI construction paths work for each provider claimed as supported.
- Contract tests cover regular and streamed requests, request/response closure, cancellation, URL/query/body fidelity, exception mapping, and zero hidden retries.
- Async support is either independently qualified or explicitly excluded from the release claim.
- The change is merged/released upstream at an immutable revision suitable for downstream qualification.

## Stop conditions

If SDKs cannot be supported through documented public extension points, or the bridge requires private APIs/public namespace replacement, record the limitation and keep AInews on HTTPX. Do not add a local-only shim to AInews production dependencies.

## Implementation and evidence — 2026-10-30

- Added optional `eggfetch.integrations.httpx.EggFetchTransport` implementing
  public `httpx.BaseTransport` and the `httpx-transport` extra (`httpx>=0.28,
  <0.29`). It translates public HTTPX requests/responses and timeout extensions,
  keeps EggFetch retries at zero, and maps EggFetch transport failures to
  HTTPX exceptions with the original request attached.
- Added user documentation at EggFetch `docs/python/httpx-transport.md`.
  The supported scope is synchronous HTTPX 0.28.x, HTTP/1.1 and HTTP/2. Async
  clients/streams and experimental HTTP/3 are explicitly not claimed.
- On CPython 3.12.13 with HTTPX 0.28.1 and AInews's locked SDKs (OpenAI
  2.29.0, Anthropic 0.87.0, Ollama 0.6.1, Google GenAI 1.75.0), the SDK
  construction fixture passed for all four clients. An OpenAI chat-completion
  request also passed against a local stub through EggFetch.
- EggFetch Python bridge + URL suite: 115 passed, 1 warning on CPython
  3.12.13 / HTTPX 0.28.1 (`test_httpx_transport_bridge.py`,
  `test_httpx_transport_sdk_construction.py`, `test_url_query.py`).
- EggFetch 0.3.0 publishes the synchronous `httpx-transport` extra and user
  documentation, with HTTPX 0.28.x client identity and EggFetch retries set to
  zero. The release's wheel workflow smoke-tested supported platform wheels.
- Downstream integration remains E4 work: verify AInews SDK adapters,
  retries, streams, timeouts, and resource lifecycle against this immutable
  release. See [EggFetch v0.3.0](https://github.com/eggstack/eggfetch/releases/tag/v0.3.0).
