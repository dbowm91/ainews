# Milestone C Transport Closure Plan

## Purpose

This is the next-step closure plan for Milestone C after the first corrective pass. The repo now has a safe-fetch client, manual redirect handling, DNS fail-closed validation, extraction integration, response limits, redaction improvements, and tests. The remaining issue is implementation quality: `PinnedIPAdapter` currently closes the DNS-rebinding gap by monkeypatching process-global socket connection functions during request execution. That is not safe enough for a multi-threaded Flask/Celery crawler.

This plan replaces the global monkeypatch approach with a thread-safe transport strategy, fixes malformed safe-fetch environment validation, and strengthens tests so they prove the actual connection target and concurrency behavior.

## Current state to preserve

Keep these properties:

- Untrusted extraction uses `safe_fetch_url()`.
- `trafilatura.fetch_url()` is not used for untrusted URLs.
- Automatic redirects are disabled.
- Redirect hops are independently validated.
- DNS resolution fails closed if any resolved IP is private/reserved/blocked.
- Response body is streamed and bounded.
- `Accept-Encoding: identity` is used.
- Content-type allowlist is enforced.
- Query strings, fragments, and credentials are redacted from logs.
- Total timeout checks exist during redirects and streaming.
- Safe fetch emits metrics without high-cardinality URL labels.

## Current issues

### 1. Global socket monkeypatching is unsafe

`PinnedIPAdapter.send()` temporarily assigns:

- `socket.create_connection = _pinned_socket_cc`
- `urllib3.util.connection.create_connection = _pinned_util_cc`

This is process-global mutable state. In concurrent workers, request A can affect request B while the monkeypatch is active. This is a serious race hazard in a crawler and task-processing system.

### 2. Tests do not prove thread-safe pinning

The current adapter tests verify adapter attributes and Host header behavior, but they do not strongly prove that:

- the actual socket destination is the validated pinned IP,
- no global socket monkeypatch is used,
- concurrent safe fetches cannot cross-pin each other,
- each redirect hop uses the hop-specific selected IP.

### 3. Malformed env values silently default

`SafeFetchLimits()` now avoids crashing on invalid env values, which is good for runtime robustness. But production validation uses already-defaulted `SafeFetchLimits()` values, so malformed values such as `SAFE_FETCH_MAX_BYTES=abc` do not produce structured validation errors. Production validation should report malformed values.

## Workstream 1: Replace global monkeypatch pinning

### Objective

Use a thread-safe mechanism that connects to a selected validated IP without mutating process-global socket functions.

### Preferred design: custom urllib3 connection/pool/adapter

Implement a custom urllib3 connection path under `services/safe_fetch.py` or a small dedicated module such as `services/safe_fetch_transport.py`.

Desired structure:

```python
class PinnedHTTPConnection(urllib3.connection.HTTPConnection):
    def __init__(self, *args, pinned_ip: str, original_host: str, **kwargs): ...
    def _new_conn(self):
        # call urllib3.util.connection.create_connection((self.pinned_ip, self.port), ...)
        # no global monkeypatch

class PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
    def __init__(self, *args, pinned_ip: str, original_host: str, **kwargs): ...
    def _new_conn(self):
        # connect to pinned_ip
    def connect(self):
        # ensure SNI/server_hostname and assert_hostname use original_host

class PinnedHTTPConnectionPool(urllib3.connectionpool.HTTPConnectionPool):
    ConnectionCls = PinnedHTTPConnection

class PinnedHTTPSConnectionPool(urllib3.connectionpool.HTTPSConnectionPool):
    ConnectionCls = PinnedHTTPSConnection

class PinnedPoolManager(urllib3.PoolManager):
    # create pools with pinned_ip/original_host

class PinnedIPAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(...):
        self.poolmanager = PinnedPoolManager(...)
```

The exact urllib3 extension point may vary by installed urllib3 version. Implement against the version in the repo lockfile and test directly.

### Required semantics

For HTTP:

- TCP connects to `selected_ip`.
- Request target/URL path remains correct.
- `Host` header remains original host plus port when non-default.
- No secondary DNS lookup controls the socket destination.

For HTTPS:

- TCP connects to `selected_ip`.
- TLS SNI uses `original_host`.
- Certificate verification uses `original_host`.
- The `Host` header uses `original_host` plus port when non-default.
- If this cannot be implemented safely, explicitly disable HTTPS in safe fetch until implemented. Do not silently run HTTPS through an unpinned path.

For proxies:

- Disable environment proxy use for safe fetch by default: `session.trust_env = False`.
- Do not allow `HTTP_PROXY` / `HTTPS_PROXY` to route untrusted fetches through an unvalidated path unless a separate proxy threat model is implemented.

### Implementation notes

- Remove all assignment to `socket.create_connection` and `urllib3.util.connection.create_connection`.
- Do not monkeypatch module/global state.
- Build one adapter per request hop, or one short-lived session per hop, to avoid connection pool reuse across pinned IPs.
- Disable keep-alive or close the session after each hop if that simplifies correctness.
- Record `selected_ip` separately from `resolved_ips`.

Suggested result model addition:

```python
@dataclass(frozen=True)
class SafeFetchResult:
    ...
    selected_ips: tuple[str, ...]  # one selected IP per hop, optional but useful
```

## Workstream 2: Strengthen redirect-hop pinning

### Objective

Every redirect hop must independently resolve, validate, select, and pin.

### Implementation details

For each loop iteration:

1. Resolve and validate current URL.
2. Select IP.
3. Create hop-local session or adapter pinned to that IP and hostname.
4. Perform request with redirects disabled.
5. If redirect, validate target only as a preliminary parse/security check.
6. Continue loop; the next iteration performs full resolution and pinning for the new URL.

Avoid using a long-lived session with adapters remounted by scheme unless tests prove old pools are not reused. Safer approach: use a fresh `requests.Session()` per hop or explicitly close adapters after each request.

## Workstream 3: Add concurrency tests that fail under global monkeypatching

### Required test: no global monkeypatch usage

Add a test that monkeypatches `socket.create_connection` with a sentinel that records attempts to replace it. The safe fetch adapter must not assign to the module attribute.

Possible strategy:

```python
class SocketModuleGuard:
    def __setattr__(self, name, value):
        if name == "create_connection":
            raise AssertionError("global socket.create_connection must not be monkeypatched")
```

Use carefully; monkeypatching modules is awkward. A simpler static assertion can inspect the adapter source for forbidden assignment, but a runtime guard is stronger.

### Required test: concurrent fetch isolation

Create two local HTTP servers. Use a test-only transport hook or resolver map:

- `a.test` should pin to server A.
- `b.test` should pin to server B.
- Run both fetches concurrently in a `ThreadPoolExecutor` many times.
- Server A returns `A`; server B returns `B`.
- Assert `a.test` never receives `B` and `b.test` never receives `A`.

This test should be able to fail under global monkeypatch-based cross-pinning.

### Required test: actual socket target equals selected IP

Instrument the transport at the connection creation layer and assert the socket destination is the selected IP.

Test should prove:

- The requested URL hostname is not directly resolved by the underlying connect path after validation.
- If the underlying DNS resolver would return a private IP, the pinned connection still uses the selected validated IP, or the fetch rejects before attempting connection.

### Required test: redirect hop selected IPs

Use a resolver map:

- `first.test` -> server A IP
- `second.test` -> server B IP

Server A redirects to `http://second.test:<port>/end`.

Assert:

- first request connects to A,
- second request connects to B,
- result records both selected IPs or test instrumentation observes both.

### HTTPS test requirement

If HTTPS remains supported:

- Add a local TLS server with a test certificate if practical.
- Verify SNI/Host uses original host.
- Verify certificate verification behavior is intentional.

If HTTPS is temporarily disabled:

- Add a test that HTTPS raises a clear `SafeFetchError` or `UnsafeFetchError` explaining that HTTPS pinning is not yet supported.
- Update docs accordingly.

## Workstream 4: Fix malformed safe-fetch env validation

### Objective

Malformed safe-fetch env vars must produce structured production validation issues. Runtime defaulting is acceptable only outside validation after the validation layer has had a chance to report malformed values.

### Implementation design

Add explicit parser for validation:

```python
def _parse_env_int_issue(result, name, default, min_value=None, max_value=None) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        result.add(field=name, message=f"{name} must be an integer", fix_hint="...")
        return default
    ...
```

Do the same for floats.

Use this in `_validate_safe_fetch()` instead of constructing `SafeFetchLimits()`.

### Required tests

Add production config tests:

- `SAFE_FETCH_MAX_BYTES=abc` raises `RuntimeError` mentioning `SAFE_FETCH_MAX_BYTES`.
- `SAFE_FETCH_CONNECT_TIMEOUT=bad` raises `RuntimeError` mentioning `SAFE_FETCH_CONNECT_TIMEOUT`.
- `SAFE_FETCH_MAX_REDIRECTS=0` still raises structured issue.
- `SAFE_FETCH_MAX_BYTES=20000001` raises upper-bound issue.
- valid env values pass.

## Workstream 5: Tighten total-timeout behavior

### Objective

Total timeout must cover the whole operation: resolution, redirects, request start, and body streaming.

### Implementation details

- Call `_check_timeout()` before each DNS/validation step.
- Call after DNS resolution.
- Call before request execution.
- Call after response headers.
- Call during streaming.
- Call before following redirects.

Current code checks redirects and streaming; add checks around DNS/request boundaries.

### Tests

- Slow DNS mock triggers total timeout or controlled DNS timeout.
- Many redirect hops with small delays hit total timeout.
- Slow response header phase maps to timeout.

Keep tests deterministic with mocks when possible.

## Workstream 6: Remove or quarantine proxy behavior

### Objective

Prevent environment proxies from bypassing SSRF controls.

### Implementation

Set on every safe-fetch session:

```python
session.trust_env = False
```

Also pass no proxies:

```python
session.get(..., proxies={})
```

### Tests

- Set `HTTP_PROXY` / `HTTPS_PROXY` in env.
- Assert safe fetch does not use the proxy for untrusted URLs.
- If proxies are needed later, require an explicit `SAFE_FETCH_PROXY_URL` design with its own validation.

## Workstream 7: Documentation updates

Update:

- `docs/security.md`: explain thread-safe IP pinning, no global monkeypatching, proxy behavior.
- `docs/configuration.md`: explain malformed env validation and bounds.
- `docs/troubleshooting.md`: add entries for pinning/HTTPS/proxy failures.
- `AGENTS.md`: state that safe-fetch code must not monkeypatch global socket functions.
- architecture docs: describe safe-fetch transport at a high level.

## Validation commands

Targeted tests:

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
```

Production validation tests:

```bash
uv run pytest tests/test_production_config.py tests/test_smoke_production_config.py -q
```

Full suite:

```bash
uv run pytest tests/ -q
```

Lint:

```bash
uv run ruff check .
```

Network-call audit:

```bash
rg "socket\.create_connection\s*=|urllib3\.util\.connection\.create_connection\s*=|trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes tests
```

Expected result:

- No assignment to global socket/urllib3 connection functions.
- No `trafilatura.fetch_url` usage outside tests that assert it is forbidden.
- Direct `requests.get` only inside approved safe-fetch transport internals, or removed.

## Final acceptance criteria

This closure pass is complete when:

- Safe fetch no longer monkeypatches process-global socket or urllib3 connection functions.
- The actual socket destination is the selected validated IP.
- Concurrent safe fetches cannot cross-pin or interfere with one another.
- Redirect hops are independently resolved, validated, and pinned.
- Proxy environment variables do not bypass safe-fetch controls.
- Malformed safe-fetch env values produce structured production validation issues.
- Total timeout covers DNS, redirect, request, and streaming phases.
- Tests fail against the old global monkeypatch implementation and pass with the thread-safe transport.
- Docs and agent guidance accurately describe the final design.

## Non-goals

This plan does not add browser rendering, JavaScript execution, robots.txt policy, crawler politeness, external malware scanning, or full crawler observability dashboards. Those are later release-hardening items.
