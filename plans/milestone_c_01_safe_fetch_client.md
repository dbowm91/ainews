# Milestone C.1: Safe Fetch Client

## Objective

Implement a first-party safe fetch client for untrusted URLs. The client must own URL parsing, DNS resolution, IP-range blocking, redirect handling, timeout enforcement, response-size limits, and content-type checks. It should return fetched content to callers without delegating network I/O to extraction libraries.

## Problem

A validate-then-fetch pattern is not sufficient for SSRF protection. If the application validates a URL and then a separate library performs the actual request, the library may re-resolve DNS, follow redirects, or connect to a different destination than the one validated. The safe fetcher must bind validation to the outbound network operation.

## Affected files

Likely files:

- `services/url.py`
- `utils/url.py`
- new `services/safe_fetch.py` or `services/http_fetch.py`
- `services/content_extractor.py`
- `tests/test_safe_fetch.py`
- `tests/test_url_security.py`
- `docs/security.md`
- `AGENTS.md`

## Public API design

Add a small typed API. Suggested shape:

```python
@dataclass(frozen=True)
class SafeFetchLimits:
    max_redirects: int = 5
    max_bytes: int = 2_000_000
    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    total_timeout: float = 20.0
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
    )

@dataclass(frozen=True)
class SafeFetchResult:
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    text: str
    content_type: str | None
    redirect_chain: tuple[str, ...]
    resolved_ips: tuple[str, ...]

class SafeFetchError(Exception): ...
class UnsafeFetchError(SafeFetchError): ...
class FetchTimeoutError(SafeFetchError): ...
class FetchTooLargeError(SafeFetchError): ...
class FetchContentTypeError(SafeFetchError): ...


def safe_fetch_url(url: str, *, limits: SafeFetchLimits | None = None) -> SafeFetchResult:
    ...
```

Keep this API small and framework-independent. Route handlers/tasks should convert exceptions into user-facing status/log events.

## URL validation requirements

The safe fetcher must reject:

- Empty or whitespace-only URLs.
- Relative URLs.
- Unsupported schemes.
- URLs with no hostname.
- Local path-like inputs.
- `file:`, `ftp:`, `gopher:`, `data:`, `javascript:`, `mailto:` and any non-HTTP(S) scheme.
- Hostnames resolving only to blocked ranges.
- Any connection target in blocked ranges.

Blocked network ranges should include at minimum:

- loopback,
- private RFC1918,
- link-local,
- multicast,
- reserved,
- unspecified,
- IPv6 unique-local / link-local / loopback,
- metadata service IPs such as `169.254.169.254` and IPv6 equivalents where relevant.

Reuse the existing project URL/IP validation code where correct, but avoid duplicating inconsistent policy. If both `utils/url.py` and `services/url.py` define overlapping SSRF logic, choose one canonical location or make one call into the other.

## DNS and connection strategy

### Preferred strategy

Resolve the hostname immediately before connect, reject blocked addresses, and ensure the HTTP client connects to an allowed address. This is easiest if the client library allows explicit transport/socket control. If using a high-level HTTP client that cannot pin the resolved IP, the safe fetcher must still minimize TOCTOU and test redirect/DNS behavior carefully.

Potential approaches:

1. Use `httpx` with manual redirects and custom transport if feasible.
2. Use `urllib` with custom opener and manual redirect handling, but verify it does not re-follow redirects or bypass validation.
3. Use low-level sockets/TLS manually only if necessary; this is higher-risk and more code.

### Minimum acceptable behavior

- Before each request, resolve the candidate URL's hostname.
- Reject if any resolved IP is blocked, or at minimum reject if all usable IPs are blocked. Prefer fail-closed: if any returned address is blocked, reject the host unless there is a strong reason to allow mixed DNS answers.
- Disable automatic redirects and handle redirect hops in application code.
- Validate the redirect target URL before making the next request.
- Enforce max redirect count.

## Redirect policy

Manual redirect handling must support only standard redirect statuses:

- 301
- 302
- 303
- 307
- 308

For every redirect:

1. Read `Location`.
2. Resolve relative locations against the current URL.
3. Normalize and validate the new URL.
4. Resolve host and reject blocked ranges.
5. Stop after `max_redirects`.
6. Preserve a redirect chain for logging/testing.

Do not forward sensitive headers across redirects. For this use case, avoid credentials entirely.

## Request policy

Use a conservative request profile:

- Method: `GET` only.
- Headers:
  - `User-Agent: ainews-safe-fetch/<version>` or similar.
  - `Accept: text/html,application/xhtml+xml,application/xml,text/xml,text/plain;q=0.8,*/*;q=0.1`.
- No cookies.
- No auth headers.
- No proxy usage unless explicitly configured and still validated.
- No automatic decompression without byte-limit accounting.

If automatic decompression is enabled, enforce max bytes on decompressed output, not only compressed wire bytes. If this is hard with the chosen client, disable compression by sending `Accept-Encoding: identity`.

## Response policy

Enforce:

- Status code policy: accept 2xx as success; handle redirects manually; treat others as fetch errors with status metadata.
- Content type allowlist before reading large bodies if `Content-Type` is present.
- Max response bytes during streaming.
- Decode text using declared charset or robust fallback such as UTF-8 with replacement.
- Do not write fetched content to disk by default.

If `Content-Type` is missing, allow small bodies and let extraction decide, but still enforce size limits. Consider a stricter production config toggle if needed.

## Configuration

Add config settings with safe defaults:

- `SAFE_FETCH_MAX_REDIRECTS=5`
- `SAFE_FETCH_MAX_BYTES=2000000`
- `SAFE_FETCH_CONNECT_TIMEOUT=5`
- `SAFE_FETCH_READ_TIMEOUT=10`
- `SAFE_FETCH_TOTAL_TIMEOUT=20`
- `SAFE_FETCH_ALLOWED_CONTENT_TYPES=...`

These should be parsed using existing safe env helpers and documented.

## Logging and metrics

Log structured, non-sensitive fetch decisions:

- rejected scheme,
- rejected hostname/IP range,
- redirect blocked,
- timeout,
- too large,
- content-type rejected,
- final status code,
- redirect count,
- response byte count.

Do not log full query strings if they may contain secrets. Prefer normalized origin and path truncation.

## Tests

Add `tests/test_safe_fetch.py` with local HTTP server fixtures. Required tests:

- Reject `http://127.0.0.1/`.
- Reject `http://localhost/`.
- Reject private IPv4 and IPv6 literal URLs.
- Reject unsupported schemes.
- Reject malformed URLs.
- Allow public-looking host when DNS is mocked to public IP.
- Reject public-looking host when DNS is mocked to private IP.
- Reject redirect from allowed host to private IP.
- Reject redirect from allowed host to localhost hostname.
- Enforce max redirect count.
- Enforce max bytes on large response.
- Enforce read/connect timeout, using deterministic fixtures where possible.
- Reject disallowed content types.
- Preserve redirect chain in result or error metadata.

## Acceptance criteria

- All untrusted fetches have a safe, first-party fetch path available.
- Automatic redirects are disabled in the underlying client.
- Every redirect target is validated before following.
- Private/reserved destinations are blocked before request body read.
- Size, timeout, content-type, and redirect limits are enforced and tested.
- No third-party extraction library performs network I/O for untrusted URLs.

## Handoff cautions

- Do not rely only on pre-fetch URL validation.
- Do not call `trafilatura.fetch_url()` inside the safe-fetch implementation.
- Do not allow environment proxy variables to silently route safe fetches unless proxy behavior is explicitly designed and tested.
- Be careful with class-level or module-level caches that make DNS-rebinding tests flaky.
