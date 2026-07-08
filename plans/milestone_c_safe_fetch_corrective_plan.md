# Milestone C Safe Fetch Corrective Plan

## Purpose

This plan closes the remaining gaps found after the first Milestone C implementation pass. The repo now has a first-party `services/safe_fetch.py`, content extraction routes through `safe_fetch_url()`, `trafilatura.fetch_url()` is no longer used in the inspected extractor path, safe-fetch configuration/docs exist, and large SSRF-focused test suites were added.

The remaining issue is narrower but security-significant: the current safe fetcher validates DNS before `requests.get()`, but the actual HTTP connection still uses the normal `requests`/urllib3 resolution path. That leaves a DNS rebinding / time-of-check-time-of-use gap between validation and connect. This corrective pass should either eliminate that gap with pinned connection semantics or explicitly downgrade the security claim if full pinning is deferred. Preferred path: implement pinning.

## Current implementation state

Observed current behavior:

- `safe_fetch_url()` calls `_validate_and_resolve(current_url)` before every request.
- `_validate_and_resolve()` calls `validate_url_safe(url)` and `_resolve_and_check(hostname)`.
- The request is then made with `requests.Session().get(current_url, allow_redirects=False, ...)`.
- Because `requests` connects to `current_url` by hostname, the underlying stack can perform a fresh DNS lookup after validation.
- Redirects are handled manually, but each redirected request has the same re-resolution gap.
- `SafeFetchLimits` reads environment values directly at dataclass default construction with `int()` / `float()`.
- `_validate_safe_fetch()` also parses env vars with direct `int()`, so malformed env values can raise outside structured validation.

Good current behavior to preserve:

- No automatic redirects.
- Redirect targets are validated before follow.
- `Accept-Encoding: identity` reduces decompression bomb risk.
- Streaming byte limit is enforced.
- Content-type allowlist is enforced.
- Extraction uses `trafilatura.bare_extraction()` on already fetched HTML.
- Tests guard against `trafilatura.fetch_url()` being called.

## Workstream 1: Implement validated-IP connection pinning

### Objective

Ensure the connection uses the same allowed IP that the safe fetcher validated. DNS resolution must not occur again inside the underlying HTTP client after validation, or if it does, it must not affect the socket destination.

### Preferred design

For each request hop:

1. Parse URL.
2. Resolve hostname to candidate IPs.
3. Reject if any resolution is blocked under the chosen fail-closed policy.
4. Select an allowed IP.
5. Connect to that IP directly.
6. Preserve the original hostname in:
   - HTTP `Host` header,
   - TLS SNI for HTTPS,
   - certificate verification hostname for HTTPS.
7. Disable automatic redirects.
8. Validate and pin each redirect hop independently.

### Implementation options

#### Option A: Custom urllib3/requests adapter

Implement a small `requests` adapter or urllib3 connection class that connects to the validated IP while preserving the original host for SNI and certificate verification.

Conceptual behavior:

- Rewrite request URL netloc to the selected IP for the socket connection.
- Set `Host: original_host[:port]`.
- Ensure TLS `server_hostname` remains the original hostname.
- Ensure certificate verification checks the original hostname, not the IP.
- Prevent proxies from changing the connection path unless explicitly configured and tested.

This is possible but easy to get subtly wrong. Use targeted tests for SNI/Host behavior if this route is chosen.

#### Option B: Use `httpx` with a custom transport/resolver if already available

If `httpx` is already a dependency or acceptable, explore whether a custom transport can connect to selected IPs while preserving Host/SNI. Do not assume default `httpx.get()` solves this; default clients also resolve during connect.

#### Option C: Low-level stdlib socket client

Implement minimal HTTP/HTTPS GET using `socket.create_connection()` to the pinned IP and `ssl.wrap_socket(server_hostname=original_host)` for HTTPS.

Pros:

- Most explicit pinning semantics.
- No hidden DNS lookup after validation.

Cons:

- More code to handle TLS, headers, chunked transfer, redirects, status parsing, and streaming limits.
- Higher risk of HTTP behavior bugs.

#### Option D: Explicitly downgrade security claim

If pinning is deferred, document that safe fetch validates DNS immediately before request and blocks unsafe redirects, but does not fully eliminate DNS rebinding between validation and connect. This should not be the preferred final state for Milestone C.

### Recommended path

Prefer Option A or B if it can be implemented with a small, well-tested adapter. If that becomes too complex, use Option C only for the narrow needs of article fetching: GET, no request body, no cookies/auth, manual redirects, conservative content handling.

Do not mark Milestone C closed while remaining on the current unpinned `requests.get(current_url)` model unless the security claim is explicitly downgraded.

## Workstream 2: Define DNS resolution policy precisely

### Fail-closed resolution rule

Use a clear policy:

- If DNS returns any blocked IP, reject the hostname.
- If DNS returns no usable IPs, reject.
- If DNS resolution fails, reject as fetch failure.
- If both IPv4 and IPv6 answers exist and any are blocked, reject unless there is an explicit allow-mixed policy.

This is stricter than choosing the first public IP and ignoring private answers. It avoids attacker-controlled mixed-answer tricks.

### IP selection

After rejecting mixed blocked results, choose one allowed IP deterministically:

- Prefer IPv4 or IPv6 consistently, or preserve resolver order.
- Record selected IP in `SafeFetchResult`.
- Record all resolved IPs for audit metadata.

### DNS caching

If existing `services.url` DNS cache is reused:

- Ensure tests can clear/isolate the cache.
- Ensure cache TTL is short enough for crawler safety.
- Ensure a cached allowed result does not bypass a later blocked redirect host validation.

## Workstream 3: Add tests that fail against the current unpinned model

### Required tests

Add tests that prove the actual connection uses the validated IP.

Possible strategies:

#### Strategy A: Monkeypatch socket resolution after validation

1. Arrange `_resolve_and_check()` to return a public/allowed IP.
2. Arrange the underlying connection resolver to return `127.0.0.1` if called again.
3. Assert the safe fetcher does not call the underlying resolver, or rejects before connect if it detects the mismatch.
4. This test should fail against current `requests.get(current_url)` behavior.

#### Strategy B: Instrument custom transport

If a custom adapter/transport is used, assert it receives `selected_ip` and `original_host` and never asks DNS again.

#### Strategy C: Local server plus fake hostname pinning

1. Run a local HTTP server on loopback.
2. Mock safe resolver to select the loopback IP as an allowed test-only IP.
3. Request `http://attacker.test:<port>/`.
4. Make the underlying DNS for `attacker.test` fail or point elsewhere.
5. Safe fetch should still connect to the selected IP while sending `Host: attacker.test:<port>`.

Because production must block loopback, this test requires a test-only allow/pin injection. Keep it scoped to the transport layer, not the public safe fetch policy.

### Redirect pinning tests

For redirects:

- First host resolves to allowed IP A and redirects to second host.
- Second host resolves to allowed IP B.
- Assert second connection uses B and not fresh DNS.
- If second host resolver would rebind to private during raw connect, safe fetch still uses the validated/pinned B or rejects.

### HTTPS tests

If HTTPS pinning is implemented now:

- Verify SNI/Host uses original hostname, not selected IP.
- Verify certificate hostname behavior if feasible with local test certs.

If HTTPS pinning is deferred:

- Disable HTTPS support in safe fetch or document HTTPS as not pinned and keep Milestone C open.

## Workstream 4: Fix malformed safe-fetch env handling

### Problem

Current code uses direct `int()` / `float()` parsing in both `SafeFetchLimits` dataclass defaults and `_validate_safe_fetch()`. Malformed env values can raise `ValueError` before structured production validation reports a clean issue.

### Desired behavior

- Runtime limit loading uses safe parsing helpers.
- Production validation accumulates malformed config as `ConfigValidationIssue`, not raw `ValueError`.
- Defaults remain conservative if not configured.

### Implementation steps

1. Add helpers:

```python
def _safe_fetch_int_env(name: str, default: int) -> int:
    ...

def _safe_fetch_float_env(name: str, default: float) -> float:
    ...
```

or reuse existing `safe_int` and add `safe_float` if needed.

2. Consider making `SafeFetchLimits` defaults static constants rather than reading env directly in the dataclass field definitions.

Preferred:

```python
DEFAULT_SAFE_FETCH_LIMITS = SafeFetchLimits(...)

def load_safe_fetch_limits_from_env() -> SafeFetchLimits:
    ...
```

3. Update `safe_fetch_url()` to use `load_safe_fetch_limits_from_env()` when `limits is None`.

4. Update `_validate_safe_fetch()` to use parsing that catches `ValueError` and adds structured validation issues.

### Required tests

- `SAFE_FETCH_MAX_BYTES=abc` produces production validation issue, not uncaught `ValueError`.
- `SAFE_FETCH_CONNECT_TIMEOUT=bad` produces production validation issue.
- default env absence yields expected defaults.
- explicit valid env values load correctly.
- invalid env values do not crash module import.

## Workstream 5: Revisit total timeout enforcement

### Problem

`requests` has connect/read timeouts, while `safe_fetch_url()` uses streaming and comments that total timeout is enforced manually. Verify this is actually true. The current implementation starts a monotonic clock but does not visibly abort inside the chunk loop based on `total_timeout`.

### Required change

During redirect loop and body streaming, enforce:

```python
if time.monotonic() - start > limits.total_timeout:
    raise SafeFetchTimeoutError(...)
```

Apply before each redirect request and during each chunk read.

### Tests

- Slow chunk stream triggers total timeout even if each individual read stays below read timeout.
- Redirect chain with slow hops triggers total timeout.

Avoid flaky sleeps. Prefer mock response/transport where possible.

## Workstream 6: Tighten logging and metrics safety

### Current concern

`_redact_url()` strips query strings but leaves credentials in netloc (`user:pass@example.com`). That can leak secrets embedded as URL userinfo.

### Required change

Sanitize:

- query string removed,
- username/password removed,
- fragment removed,
- path optionally truncated,
- host retained.

Example:

```python
http://user:pass@example.com/path?secret=1#frag
```

should log as:

```python
http://example.com/path
```

or:

```python
http://example.com/<redacted-path>
```

### Tests

- `_redact_url()` removes query, fragment, username, and password.
- metrics labels do not include full URL or hostname.

## Workstream 7: Documentation and acceptance language

Update docs after implementation:

- `docs/security.md`: state whether safe fetch pins connection to validated IP. Preferred final wording: it does.
- `docs/configuration.md`: explain malformed env handling and bounds.
- `docs/troubleshooting.md`: add DNS pinning / unsafe redirect / timeout details.
- `AGENTS.md`: forbid unpinned hostname fetches for untrusted URLs.

If pinning is not implemented, docs must explicitly say Milestone C does not fully prevent DNS rebinding and list it as a known limitation. Do not overclaim.

## Validation commands

Targeted tests:

```bash
uv run pytest tests/test_safe_fetch.py tests/test_content_extractor_safe_fetch.py tests/test_url_security.py -q
```

Production/config tests:

```bash
uv run pytest tests/test_production_config.py tests/test_docs_env_consistency.py -q
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
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

Every remaining direct network call must be safe-fetch internals, trusted/internal with documented rationale, or removed.

## Final acceptance criteria

Milestone C can be closed only when:

- The actual socket connection uses the validated/pinned IP, or the security claim is explicitly downgraded and Milestone C remains open.
- Redirect hops are independently validated and pinned.
- Tests fail against the current unpinned re-resolution model and pass after the fix.
- Malformed safe-fetch env values produce structured production validation errors.
- Total timeout is actually enforced across redirects and streaming body reads.
- Logs redact credentials, query strings, and fragments.
- Content extraction continues to use safe fetch and never calls `trafilatura.fetch_url()` for untrusted URLs.
- Full targeted SSRF tests, full test suite, and ruff pass.

## Non-goals

This corrective pass does not implement browser rendering, JavaScript execution, robots.txt policy, crawler politeness, malware scanning, or full external provider health checks.
