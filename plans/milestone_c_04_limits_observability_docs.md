# Milestone C.4: Fetch Limits, Observability, and Documentation

## Objective

Make safe-fetch behavior configurable, observable, and documented so future code does not reintroduce unsafe network fetches. Milestone C is not complete unless operators can tune conservative limits, developers can diagnose fetch failures, and coding agents have clear guidance on the required network-fetch path.

## Affected files

Likely files:

- `config.py`
- `.env.example`
- `services/safe_fetch.py` or equivalent
- `services/metrics.py`
- `logging_config.py`
- `docs/security.md`
- `docs/configuration.md`
- `docs/troubleshooting.md`
- `AGENTS.md`
- `.opencode/skills/ainews/SKILL.md`
- tests for docs/env consistency if required

## Configuration plan

Add safe-fetch settings with conservative defaults:

```bash
SAFE_FETCH_MAX_REDIRECTS=5
SAFE_FETCH_MAX_BYTES=2000000
SAFE_FETCH_CONNECT_TIMEOUT=5
SAFE_FETCH_READ_TIMEOUT=10
SAFE_FETCH_TOTAL_TIMEOUT=20
SAFE_FETCH_ALLOWED_CONTENT_TYPES=text/html,application/xhtml+xml,text/plain,application/xml,text/xml,application/rss+xml,application/atom+xml
```

### Validation requirements

Production config should validate:

- max redirects is between 0 and a small upper bound, e.g. 10,
- max bytes is positive and below an upper bound, e.g. 10 MB unless deliberately changed,
- timeouts are positive and bounded,
- allowed content types are non-empty and valid MIME-like strings,
- total timeout is not lower than connect/read defaults if that relationship is enforced.

Development can be permissive, but invalid production values should fail closed or revert to safe defaults with warnings. Prefer fail-closed for malformed numeric config.

## Observability plan

### Structured logs

Log safe-fetch outcomes with these fields where available:

- `event=safe_fetch` or equivalent,
- `outcome=success|blocked|timeout|too_large|content_type_rejected|http_error|redirect_error`,
- `reason`,
- `url_origin`,
- `url_path_hash` or truncated sanitized path,
- `final_origin`,
- `status_code`,
- `redirect_count`,
- `bytes_read`,
- `duration_ms`,
- `content_type`,
- `request_id`.

Do not log full URLs with query strings by default. Query strings may contain credentials, tokens, or email addresses.

### Metrics

If `services/metrics.py` supports counters/timers, add:

- `safe_fetch_requests_total{outcome=...}`
- `safe_fetch_blocked_total{reason=...}`
- `safe_fetch_duration_seconds`
- `safe_fetch_response_bytes`
- `safe_fetch_redirects_total`

If metric cardinality is a concern, do not label by hostname or full URL.

### Admin visibility

If there is an admin metrics dashboard, keep this optional for Milestone C. At minimum, ensure logs and metrics exist. Dashboard integration can be later polish.

## Documentation plan

### `docs/security.md`

Document:

- Untrusted URL fetches must use the safe fetch client.
- Validate-then-third-party-fetch is forbidden.
- Redirects are manually validated at every hop.
- DNS/private-IP policy.
- Response-size and timeout enforcement.
- Extraction libraries parse supplied HTML only.
- How blocked fetches appear in logs/metrics.

### `docs/configuration.md`

Document safe-fetch config variables:

- default values,
- production validation policy,
- operational tuning guidance,
- tradeoffs for max bytes and timeouts,
- content-type allowlist.

### `docs/troubleshooting.md`

Add entries for:

- URL rejected as unsafe,
- redirect blocked,
- response too large,
- unsupported content type,
- upstream timeout,
- DNS resolution failure,
- article extraction empty after successful fetch.

### `AGENTS.md` and skill files

Add explicit coding guidance:

- Never call `trafilatura.fetch_url()` for untrusted URLs.
- Never pass a URL directly to feed/extraction libraries that can fetch internally.
- Use `safe_fetch_url()` or the approved wrapper.
- If adding a new fetch path, add SSRF/redirect tests.
- If adding a new allowed content type, update config docs and tests.

## Release checklist additions

Before marking Milestone C closed, run:

```bash
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

Every remaining direct network call must be classified as one of:

- removed,
- safe-fetch path,
- trusted internal call with documented rationale,
- test-only fixture.

Also run:

```bash
uv run pytest tests/test_safe_fetch.py tests/test_content_extractor_safe_fetch.py tests/test_url_security.py -q
uv run pytest tests/ -q
uv run ruff check .
```

## Acceptance criteria

- Safe-fetch limits are configurable and production-validated.
- Logs and metrics distinguish blocked unsafe URLs from ordinary network failures.
- Docs accurately describe the safe-fetch policy and config.
- Agent guidance forbids third-party network fetches for untrusted URLs.
- Search confirms no unreviewed direct network-fetch call sites remain.

## Handoff cautions

- Avoid high-cardinality metrics labels such as full URL or hostname.
- Avoid logging full query strings.
- Do not expose internal/private IP values in public-facing error messages unless sanitized.
- Keep defaults conservative; operators can loosen only with explicit config.
