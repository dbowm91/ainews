# ainews Configuration and Operator CLI — Release 3A Safe Probe and Diagnostics

## Objective

Close the remaining diagnostic correctness gap before installer work depends on `ainews doctor`. Source connectivity checks must use the same SSRF, redirect, DNS, timeout, and response-size policies as production source fetching. Production and network diagnostic modes must also expose stable status and JSON contracts suitable for automation.

## Current baseline

The doctor package already provides:

- `CheckStatus` with pass, warn, fail, and skip;
- separate check modules;
- quick, production, and network tiers;
- non-invasive Docker inspection;
- source URL extraction for adapter-specific `feed_url`, `list_url`, and `listing_url` fields.

The remaining issue is that source connectivity is still documented as a direct `requests.head()` probe. This duplicates transport policy and may behave differently from runtime fetches.

## Workstream 1 — Inventory production-safe fetch primitives

Identify the exact runtime path used by RSS, API, and web source adapters.

Record:

- URL normalization and scheme restrictions;
- hostname and IP validation;
- private, loopback, link-local, multicast, and metadata-address policy;
- DNS resolution and rebinding protections;
- redirect limits and per-hop validation;
- connect/read/total timeout behavior;
- response-size bounds;
- accepted methods and status codes;
- proxy and environment-variable behavior;
- TLS verification policy;
- user-agent behavior;
- exception taxonomy and redaction.

Do not create a second independent SSRF implementation for doctor.

## Workstream 2 — Extract or reuse a probe service

Create a Flask-free diagnostic probe abstraction in the lowest appropriate package, for example:

```text
services/safe_fetch.py
services/source_probe.py
```

or reuse an existing safe-fetch client directly.

Recommended interface:

```python
@dataclass(frozen=True)
class ProbeRequest:
    url: str
    source_type: str
    timeout_seconds: float
    max_bytes: int
    method_preference: tuple[str, ...] = ("HEAD", "GET")

@dataclass(frozen=True)
class ProbeResult:
    outcome: Literal["reachable", "degraded", "blocked", "unreachable", "skipped"]
    final_url_redacted: str | None
    status_code: int | None
    latency_ms: int | None
    reason_code: str | None
    message: str
```

Requirements:

- all redirect targets pass the same safety validation;
- credentials, query secrets, authorization headers, and upstream body data are never logged;
- `HEAD` may fall back to a bounded `GET` for endpoints that reject or mishandle `HEAD`;
- no full feed or article body is retained for connectivity testing;
- the service is deterministic under injected resolver/session/clock dependencies;
- exceptions map to stable reason codes rather than raw library strings.

## Workstream 3 — Source schema-aware probing

Doctor must traverse the actual loaded source document, including the root `sources` collection.

For each enabled source:

- identify adapter type;
- select the primary endpoint using adapter metadata rather than hardcoded conditionals where practical;
- skip disabled sources explicitly;
- reject missing endpoint fields as configuration failures;
- cap the number of default probes to avoid long runs;
- support an explicit all-sources or named-source mode if needed;
- report how many sources were tested, skipped, blocked, degraded, and failed.

Suggested source endpoint metadata:

```python
SourceAdapterMetadata(
    type="rss",
    probe_fields=("feed_url",),
    probe_kind="feed",
)
```

Do not silently treat an unrecognized source schema as “no sources configured.”

## Workstream 4 — Status mapping

Use consistent status mapping:

- `PASS`: endpoint safely reached and returned an acceptable response;
- `WARN`: endpoint reached with a nonfatal condition, such as `HEAD` rejection followed by successful bounded `GET`;
- `FAIL`: configured endpoint is invalid, unreachable, authentication-required when it should be public, or returns a persistent failure;
- `SKIP`: source disabled, network checks not requested, or required optional dependency unavailable;
- blocked SSRF destinations should be `FAIL` in production mode and at minimum `WARN` otherwise, with an explicit safety reason code.

The backwards-compatible `passed` property must not hide the distinction in JSON output.

## Workstream 5 — Production/network doctor contract

Define and test the command tiers:

```bash
ainews doctor --quick
ainews doctor
ainews doctor --production
ainews doctor --network
ainews doctor --production --network
ainews doctor --production --network --json
```

Requirements:

- `--quick` performs no outbound network activity;
- default mode performs no outbound source/provider probes;
- `--network` enables bounded external checks;
- `--production` tightens unsafe configuration and permissions from warning to failure where documented;
- network checks have a global deadline as well as per-check timeouts;
- JSON includes schema version, command version, mode flags, timestamps, duration, aggregate counts, and stable check records;
- exit code is nonzero for any `FAIL`, while warnings and skips remain machine-visible;
- ordering of checks is deterministic.

Recommended JSON shape:

```json
{
  "schema_version": 1,
  "command": "doctor",
  "mode": {"quick": false, "production": true, "network": true},
  "outcome": "failed",
  "counts": {"pass": 12, "warn": 1, "fail": 1, "skip": 2},
  "checks": [
    {
      "name": "source_connectivity.rss.example",
      "status": "fail",
      "reason_code": "ssrf_private_address",
      "message": "Source endpoint resolves to a disallowed address",
      "remediation": "Use a publicly reachable source endpoint"
    }
  ]
}
```

## Workstream 6 — Tests

Add unit tests for:

- public hostname accepted;
- loopback/private/link-local/metadata addresses blocked;
- DNS result changes between redirect hops;
- redirect to private address blocked;
- excessive redirects rejected;
- malformed URL and unsupported scheme;
- TLS and timeout failures;
- `HEAD` success;
- `HEAD` 405 followed by bounded `GET` success;
- oversized response termination;
- secrets redacted from exceptions and JSON;
- RSS/API/web source endpoint extraction;
- disabled and malformed sources;
- deterministic check ordering and counts.

Add integration tests with local fake servers and an injected resolver. Do not depend on public internet availability in the normal test suite.

## Workstream 7 — Documentation and closure evidence

Update:

- `AGENTS.md` with the single safe-probe architecture;
- `docs/cli-reference.md` with diagnostic modes and exit behavior;
- `docs/troubleshooting.md` with blocked-address and timeout remediation;
- `docs/config-cli-release-closure.md` to note the safe-probe follow-up;
- Release 3 closure evidence with test names and CI runs.

## Acceptance criteria

- no doctor source check calls raw `requests.head()` or an equivalent unrestricted client directly;
- doctor and runtime share the same URL safety policy;
- every redirect hop is validated;
- source schema extraction covers all supported adapter types;
- default doctor remains offline and non-invasive;
- `--production --network --json` has a versioned deterministic schema;
- fake-server integration tests cover success, fallback, block, redirect, and timeout paths;
- logs and JSON contain no credentials or sensitive query values;
- all existing Release 1 and Release 2 tests remain green.
