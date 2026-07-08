# Milestone C Overview: SSRF-Safe Fetch Pipeline

## Purpose

Milestone C closes the remaining network-fetch security gap: URL validation must be coupled to the actual outbound request path. The current architecture has strong URL-validation primitives, but the article extraction path historically validated a URL and then delegated the network request to a third-party fetcher. That creates a time-of-check/time-of-use gap because DNS resolution, redirects, final destination selection, socket connection, body download, and response limits are controlled outside the validated path.

The goal is to introduce a first-party safe fetch client and make all article/content fetches flow through it. Third-party extraction libraries may still parse already-fetched HTML, but they should not perform network I/O for untrusted URLs.

## Scope

Milestone C includes these detailed plans:

- `plans/milestone_c_01_safe_fetch_client.md`
- `plans/milestone_c_02_content_extractor_integration.md`
- `plans/milestone_c_03_ssrf_redirect_dns_tests.md`
- `plans/milestone_c_04_limits_observability_docs.md`

## Threat model

Protect against these classes of SSRF and resource-exhaustion issues:

- Direct private/reserved/link-local/multicast IP URLs.
- Hostnames resolving to blocked IP ranges.
- Redirects from public URLs to blocked private/reserved targets.
- DNS rebinding between validation and fetch.
- URL parser confusion around credentials, IPv6 literals, decimal/octal IP forms, encoded hostnames, and trailing-dot domains.
- Oversized responses and decompression bombs.
- Slowloris / hanging upstreams.
- Unexpected schemes such as `file:`, `gopher:`, `ftp:`, `data:`, or local path-like inputs.
- Content-type mismatch where a URL returns binary or archive content instead of parseable HTML/text.

## Desired final architecture

The safe-fetch path should be:

1. Parse and normalize URL.
2. Reject unsupported schemes.
3. Resolve hostname.
4. Reject blocked IPs before connect.
5. Connect using the validated destination path.
6. Follow redirects manually, validating each hop before connection.
7. Enforce hop count, timeout, max bytes, and content-type rules.
8. Return a structured `SafeFetchResult` containing final URL, status code, headers, body bytes/text, and fetch metadata.
9. Pass fetched HTML/text into extraction/parsing libraries without allowing those libraries to perform network I/O.

## Candidate implementation locations

Likely files:

- `services/url.py`
- `utils/url.py`
- `services/content_extractor.py`
- `adapters/web.py` or equivalent web adapter files
- `services/article.py`
- `tasks/research.py`
- `tests/test_url_security.py`
- new `tests/test_safe_fetch.py`
- new `tests/test_content_extractor_safe_fetch.py`
- `docs/security.md`
- `docs/configuration.md`
- `AGENTS.md`

## Recommended high-level implementation

Use Python's standard library or already-present HTTP dependencies. If `httpx` is already in the dependency graph, it is a good fit because it supports explicit redirect control, streaming, and timeouts. If not, use `urllib.request` carefully with custom redirect handling and strict byte limits. Do not add a large dependency solely for this milestone unless the existing dependency set cannot support safe redirect/timeout behavior.

Key design constraint: do not call `trafilatura.fetch_url()` or any third-party network fetcher for untrusted URLs. Use trafilatura only for extraction from supplied HTML/text.

## Milestone exit criteria

Milestone C is complete when:

- There is a first-party safe fetch client for untrusted URLs.
- Every redirect hop is validated before following.
- DNS resolution is performed by the safe fetcher at the point of connection.
- Response size, timeout, redirect count, and allowed content-type limits are enforced.
- Content extraction receives already-fetched HTML/text and cannot perform its own network fetch.
- Tests cover private IPs, localhost, IPv6, redirects to private ranges, DNS rebinding simulation, malformed URLs, unsupported schemes, oversize responses, timeout behavior, and content-type rejection.
- Docs and agent guidance state that untrusted network fetches must use the safe fetch client.

## Non-goals

Milestone C does not implement a full browser, JavaScript execution, crawler politeness/rate-limit policy, robots.txt policy, paywall handling, or external malware scanning. Those can be later hardening items if needed.
