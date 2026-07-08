# Milestone C.3: SSRF, Redirect, and DNS-Rebinding Test Plan

## Objective

Build a deterministic test suite proving the safe fetcher blocks SSRF and resource-exhaustion paths. The tests should catch regressions in direct URL validation, redirect validation, DNS resolution, content limits, and extraction integration.

## Why this needs its own plan

SSRF protections are easy to overestimate with simple unit tests. The critical failures usually occur in interactions:

- validate before fetch but not at fetch time,
- redirects to private networks,
- hostname changes across DNS resolutions,
- HTTP client automatically following redirects,
- libraries doing network I/O behind extraction APIs,
- compressed or chunked responses exceeding intended limits.

The suite should exercise those interactions without relying on external internet access.

## Test infrastructure

### Local HTTP server fixture

Add a reusable local HTTP server fixture using standard library `http.server` or Werkzeug test server. It should support:

- fixed HTML response,
- redirects with configurable `Location`,
- slow response delay,
- large streaming response,
- content-type selection,
- status-code selection,
- chunked response if practical.

The server runs on loopback, which safe fetch should normally block. For allowed-fetch success tests, mock DNS and/or the IP-classification function so a test host maps to an allowed public test IP while the server connection is still local if transport mocking is used.

### Transport mocking

If the safe fetcher uses `httpx`, prefer `MockTransport` for tests that do not need actual sockets. For lower-level behavior, use monkeypatching around DNS resolver and socket/transport construction.

The test suite needs two categories:

1. Policy tests: prove URL/IP/redirect decisions without real network.
2. Integration tests: prove a local HTTP response path enforces limits and content handling.

## Required test categories

### 1. Direct blocked destinations

Tests:

- `http://127.0.0.1/` rejected.
- `http://localhost/` rejected.
- `http://[::1]/` rejected.
- `http://10.0.0.1/` rejected.
- `http://172.16.0.1/` rejected.
- `http://192.168.1.1/` rejected.
- `http://169.254.169.254/latest/meta-data/` rejected.
- `http://0.0.0.0/` rejected.
- multicast/reserved examples rejected.

Assertions:

- Raises `UnsafeFetchError` or project equivalent.
- No HTTP request is attempted after rejection.
- Error metadata includes reason category but not secret query values.

### 2. Unsupported and malformed URLs

Tests:

- `file:///etc/passwd` rejected.
- `ftp://example.com/file` rejected.
- `gopher://example.com` rejected.
- `data:text/plain,hello` rejected.
- `javascript:alert(1)` rejected.
- `//example.com/path` rejected or normalized only if explicitly supported.
- whitespace, empty, relative paths rejected.
- URLs with missing host rejected.

### 3. URL parser edge cases

Tests:

- credentials in URL: `http://user:pass@example.com/` should not leak credentials in logs or redirect headers.
- host confusion: `http://127.0.0.1@example.com/` should treat host as `example.com`.
- suffix confusion: `http://example.com@127.0.0.1/` should treat host as `127.0.0.1` and reject.
- IPv6 bracket handling.
- trailing dot hostname normalization: `example.com.`.
- percent-encoded host confusion where applicable.
- decimal/octal/hex IPv4 forms if the parser accepts them.

### 4. DNS resolution policy

Tests with mocked resolver:

- public hostname -> public IP passes validation.
- public hostname -> private IP rejects.
- public hostname -> mixed public/private IPs rejects under fail-closed policy.
- DNS resolution failure produces fetch error without attempting request.
- repeated fetches do not reuse stale allowed decision after resolver result changes unless the cache explicitly revalidates according to policy.

If the existing DNS cache is reused, add tests that isolate or clear the cache between cases.

### 5. Redirect policy

Use manual redirect fixtures or mocked transport.

Tests:

- allowed URL -> allowed URL succeeds.
- allowed URL -> `http://127.0.0.1/` rejects before following.
- allowed URL -> `http://localhost/` rejects before following.
- allowed URL -> private resolved hostname rejects.
- relative redirect target is resolved then validated.
- redirect loop stops at max redirect count.
- unsupported redirect scheme is rejected.
- missing `Location` on redirect produces controlled error.
- redirect chain is recorded in result/error metadata.

Assertions:

- Underlying HTTP client automatic redirects are disabled.
- Each redirect triggers validation before the next request.

### 6. Response limits

Tests:

- response larger than `max_bytes` raises `FetchTooLargeError`.
- if compressed responses are allowed, decompressed size is limited.
- missing `Content-Length` still enforces streaming byte limit.
- very large `Content-Length` can be rejected before reading body.
- body exactly at limit succeeds.
- body one byte over limit fails.

### 7. Timeout behavior

Tests:

- connect timeout path, if testable with mocked transport.
- read timeout on slow body.
- total timeout if implemented.

Avoid slow flaky tests. Use mock transports or very small timeouts with deterministic local handlers.

### 8. Content-type policy

Tests:

- `text/html` accepted.
- `application/xhtml+xml` accepted.
- `text/plain` accepted if intended.
- RSS/Atom/XML accepted where feed fetching uses safe fetch.
- `application/octet-stream` rejected.
- `application/zip` rejected.
- image/video content types rejected.
- missing content type behavior matches chosen policy.

### 9. Extraction integration

Tests:

- `extract_article(url)` uses `safe_fetch_url()` and passes returned text to extraction.
- monkeypatch `trafilatura.fetch_url` to raise if called.
- extraction from static HTML succeeds with no network.
- unsafe fetch exception maps to expected task/source/article failure.

## CI integration

Run these tests in the normal test suite. They should not require internet. They should not bind privileged ports. They should not depend on host DNS or network state except where explicitly mocked.

Recommended command:

```bash
uv run pytest tests/test_safe_fetch.py tests/test_content_extractor_safe_fetch.py tests/test_url_security.py -q
```

Full suite:

```bash
uv run pytest tests/ -q
```

## Acceptance criteria

- Tests fail against the old validate-then-`trafilatura.fetch_url` implementation.
- Tests pass with first-party safe fetch and extraction-from-HTML integration.
- Redirect-to-private and DNS-rebinding simulations are covered.
- Oversize, timeout, and content-type limits are covered.
- The suite is deterministic and does not require external internet.

## Handoff cautions

- Do not make tests depend on public domains resolving consistently.
- Do not skip localhost/private-IP tests because local test servers use loopback; use mock transport for success paths.
- Avoid sleeps longer than necessary for timeout tests.
- Reset DNS caches/global state between tests.
