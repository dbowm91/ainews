# Milestone C Final Polish Plan

## Purpose

This plan captures final polish items after the safe-fetch transport closure pass. The latest implementation replaced the global socket monkeypatch approach with custom urllib3 connection/pool classes, uses fresh sessions per redirect hop, disables environment proxy usage, records selected IPs, validates malformed `SAFE_FETCH_*` env values through `ConfigValidationResult`, and keeps content extraction routed through `safe_fetch_url()`.

Milestone C is now close to closure. The remaining work is small but worth doing before declaring the SSRF-safe fetch layer release-ready.

## Current state summary

Implemented:

- `PinnedHTTPConnection` and `PinnedHTTPSConnection` connect to the selected validated IP without assigning to global socket functions.
- `PinnedHTTPConnectionPool`, `PinnedHTTPSConnectionPool`, `PinnedPoolManager`, and `PinnedIPAdapter` provide a thread-safe requests/urllib3 transport path.
- `safe_fetch_url()` creates a fresh `requests.Session()` per hop.
- `session.trust_env = False` and `proxies={}` prevent ambient proxy environment variables from routing untrusted fetches outside safe-fetch controls.
- Redirect hops are independently resolved, validated, and pinned.
- `SafeFetchResult` records both `resolved_ips` and `selected_ips`.
- Total timeout is checked before request, after DNS resolution, during redirect handling, and during streaming.
- Config validation reports malformed safe-fetch env vars as structured production errors.
- Tests cover proxy bypass prevention, selected-IP metadata, concurrent fetch isolation, and malformed config.

## Remaining polish items

### 1. Preserve port in Host header

Current `PinnedIPAdapter.send()` sets:

```python
request.headers["Host"] = self.original_host
```

That omits non-default ports. For URLs using non-default ports, the correct Host header is `hostname:port` unless the port is the default for the scheme.

Implementation steps:

1. Store `original_port` and `scheme` on `PinnedIPAdapter`.
2. Add helper:

```python
def _host_header(host: str, port: int | None, scheme: str) -> str:
    if port is None:
        return host
    if scheme == "http" and port == 80:
        return host
    if scheme == "https" and port == 443:
        return host
    return f"{host}:{port}"
```

3. In `safe_fetch_url()`, pass parsed hostname, port, and scheme into the adapter.
4. Ensure IPv6 literal host formatting is bracketed correctly if future tests allow public IPv6 literals.

Tests:

- Local HTTP server on random port receives `Host: example.test:<port>` through pinned transport.
- Default HTTP port omits `:80`.
- Default HTTPS port omits `:443` if HTTPS test infrastructure exists.

### 2. Close sessions in `finally`

`safe_fetch_url()` closes sessions on normal redirect/non-redirect paths, but exceptions between session creation and explicit close can leave a session unclosed.

Implementation steps:

1. Wrap each hop request in `try/finally`:

```python
session = requests.Session()
try:
    ... request ...
finally:
    session.close()
```

2. Avoid double-close special cases by letting `finally` handle all paths.

Tests:

- Monkeypatch a session class or adapter to raise during request and assert `close()` is called.
- Existing timeout/connection/content-type tests should still pass.

### 3. Clean up obsolete tests and comments

Some tests still reference the old monkeypatch behavior in names/comments, such as “patching is scoped to request.” They no longer reflect the implementation and can confuse future agents.

Implementation steps:

- Rename obsolete tests to reflect transport scoping, not monkeypatch scoping.
- Remove direct manual assignments to `socket.create_connection` from tests unless specifically testing external behavior.
- Update comments that mention global monkeypatching as an expected mechanism.

Acceptance:

- `rg "monkeypatch|patches socket|socket.create_connection =|urllib3.util.connection.create_connection =" tests/test_safe_fetch.py services/safe_fetch.py` shows no obsolete implementation claims, except where tests explicitly assert forbidden behavior.

### 4. Strengthen HTTPS coverage or document HTTPS limitation

Current code includes `PinnedHTTPSConnection`, but HTTPS pinning/SNI/certificate behavior is more subtle than HTTP.

Preferred implementation:

- Add a local TLS test fixture with a test certificate, or a mocked connection-layer test that verifies the selected IP is used while `host` remains the original hostname.
- Verify SNI/certificate hostname behavior against the urllib3 version in the lockfile.

If robust local TLS testing is too heavy:

- Document the exact tested HTTPS behavior and keep a follow-up issue/plan item.
- Do not overclaim certificate/SNI validation beyond what tests prove.

### 5. Ensure selected/resolved IP metadata is useful but safe

The result now records all resolved and selected IPs. This is useful internally but should not be exposed to public-facing errors or templates without review.

Implementation steps:

- Audit any code that might surface `SafeFetchResult` or `SafeFetchError` directly to users.
- Keep detailed IP metadata in logs/metrics/admin-only contexts, not public UI.

## Validation commands

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
uv run pytest tests/test_production_config.py tests/test_smoke_production_config.py -q
uv run pytest tests/ -q
uv run ruff check .
```

Network-call and forbidden-monkeypatch audit:

```bash
rg "socket\.create_connection\s*=|urllib3\.util\.connection\.create_connection\s*=|trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes tests
```

Expected:

- no assignment to global connection functions in `services/`,
- no unreviewed untrusted fetch outside safe fetch,
- no `trafilatura.fetch_url()` usage except tests that assert it is forbidden.

## Acceptance criteria

Milestone C can be considered closed after polish when:

- Host header preserves non-default ports.
- Hop-local sessions close on all exception paths.
- Obsolete comments/tests referring to global monkeypatch mechanics are cleaned up.
- HTTPS pinning behavior is either tested or accurately documented as a remaining limitation.
- Safe-fetch metadata is not exposed through public-facing errors.
- Targeted SSRF tests, production config tests, full suite, and ruff pass.

## Non-goals

This plan does not add browser rendering, robots.txt handling, crawler politeness, JavaScript execution, malware scanning, or public release version/status cleanup.
