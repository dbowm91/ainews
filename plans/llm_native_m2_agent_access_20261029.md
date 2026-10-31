# M2 — Read-only agent API, MCP interface, discoverability, and quotas

**Status:** VERIFIED in this worktree; Redis contention and production resource qualification are pending.
**Parent:** [LLM-native roadmap](llm_native_publication_roadmap_20261029.md)
**Dependency:** M1; newsletter list/get endpoints depend on M5 edition service.
**Priority:** P1, with security gates before enabling external exposure.

## Objective and architecture

Expose the common published read model to autonomous consumers through a versioned REST JSON API and an optional read-only MCP interface. Both surfaces use the same service methods, DTOs, publication visibility, search filters, pagination, quota accounting and error semantics. An agent skill is documentation for a consumer; it is not a server-side agent or an inference path.

**Do not** route public readers through existing /api/v1 admin_api_bp or mint existing ApiToken credentials: routes/admin/__init__.py currently treats valid API bearer tokens as administrative authorization, with no read-only scopes.

## REST contract (versioned, suggested paths)

- GET /api/public/v1/articles?category=&tag=&sort=recent|published|impact&from=&to=&limit=&cursor= — recent published articles with bounded filters. Keyset cursor encodes stable ordering, filters and an integrity signature or opaque stored cursor; no unbounded offset traversal. Default 20, hard maximum 50. Return items, next_cursor, has_more; avoid expensive exact total counts by default.
- GET /api/public/v1/articles/<public_id> — single typed article DTO with source provenance and linked original reporting. Unknown, withdrawn and unpublished IDs are indistinguishable to unauthenticated callers.
- GET /api/public/v1/search?q=&category=&tag=&sort=&limit=&cursor= — bounded FTS search, optional hybrid mode only if operationally supported. Enforce query size, max tokens, timeouts and consistent visibility after internal candidate retrieval; ensure search results are not re-exposed when result DTO rows are hidden.
- GET /api/public/v1/categories and /tags — constrained taxonomy; tags sortable by usage or name. No private topic notes, editorial agent memory, configured sources, tags only attached to hidden articles, or internal statistics.
- GET /api/public/v1/newsletters?type=main|<category>&from=&to=&limit=&cursor= and GET /api/public/v1/newsletters/<public_id> — consume M5 immutable public editions; zero deliveries do not hide an edition. No private email HTML with unsubscribe tokens.

Use documented ISO 8601 UTC timestamps, stable fields, canonical URLs, citation lists, published source attribution and explicit structured errors. ETag/If-None-Match, Cache-Control and conditional requests should reduce polling. Pagination must be deterministic with tie-breakers, handle new insertions, and avoid duplicate/omitted rows in tests.

## MCP façade

Expose optional streamable HTTP /mcp using maintained Python MCP SDK where feasible, likely as a small ASGI-mounted endpoint or proxied optional service if Flask/WSGI integration is unsuitable. Do not implement wire protocol from scratch. Determine supported protocol version and dependencies at implementation time. Start with exactly seven read-only tools:
list_articles, search_articles, get_article, list_categories, list_tags, list_newsletters, get_newsletter.
Each tool has compact annotations, strict typed input and output, size caps, external URLs, and no write/subscribe/send/admin functions. For clients unable to authenticate via simple bearer header, document a standards-compliant OAuth protected-resource pathway as a separately gated extension rather than inventing authorization shortcuts.

MCP tools call the same service functions as REST and count against the same per-credential hourly budget, with cost-weighting only if measured and clearly documented. MCP transport errors must not swallow application errors; avoid exposing raw traces and framework secrets.

## Agent credentials and quota design

Add **separate** AgentCredential records: public identifier/prefix, secret hash, display label, scopes limited to public.read, optional expiration, created/revoked/last-used timestamps, enabled flag and per-hour quota override. Creation displays secret once; revoke/rotate in the admin. Never reuse admin ApiToken for agents. Implement actual per-agent identity; User-Agent header alone is not an identity. Anonymous access is optional and identified by a correctly derived/trusted-proxy client IP; note NAT fairness and header-spoofing risks.

Admin controls: master enabled flag for public JSON and MCP (independent if practical); anonymous enable flag; default per-key requests/hour; anonymous IP requests/hour; global flood ceiling; override and revoke per credential; read-only usage counts and last-used; safe key creation. Enforce server-side authorization on all admin writes with session CSRF; audit credential and policy mutations. Follow ainews_config or existing validated settings persistence convention; avoid diverging process-local settings.

Use Redis atomic sliding/fixed windows or Flask-Limiter with correctly scoped identities. Explicitly define the window; if fixed-hour, document boundary bursts and add independent minute/burst limits. Fail closed for protected/credentialed API on Redis failure; optionally serve low-cost cached public pages under an explicit anonymous fallback, never bypass quota silently. Issue HTTP 429, Retry-After, bounded rate-limit headers; don't log raw credentials. Search must have its own complexity limits and global concurrency guard; rate limiting is not a substitute.

## Site and skill discovery

Add /agents as a concise human and machine readable landing page and a visible footer link labelled "For AI agents"; don't clutter category navigation. Expose /api/public/openapi.json and a browsable reference with generated/validated examples. Offer /llms.txt with only pointers and policy, and an externally consumable, versioned SKILL.md (plus optional zipped skill) describing how/when to use API/MCP, queries, source/citation provenance, quotas, partial results, pagination and respectful usage. A consumer skill must not disclose or duplicate internal development instructions from .opencode/skills/ainews.

Expose optional rel=alternate / describedby Link headers on article pages and NewsArticle JSON-LD; make no guarantees of universal agent discovery. Prevent crawlers from seeing unpublished resources; robots.txt is guidance, not authentication. Advertising /agents should depend on configuration so a fully local/disabled installation doesn't advertise dead endpoints.

## Files and layer touchpoints

New routes/public/api.py or routes/public/api/ (not admin_api_bp); service public content query/serializers from M1; schemas/public_api.py; new services/agent_credentials.py, services/agent_rate_limit.py and admin routes/forms; app.py blueprint registration; extensions.py quota storage configuration; optional MCP transport module; templates/base.html and templates/agents.html; docs/api.md, OpenAPI spec, docs/agent-access.md, docs/security.md; tests for auth/serialization/search/MCP parity.

## Verification

- Token that reads articles cannot access any authenticated admin GET or mutation, token issuance, subscriber list, pipeline/research content or configuration. Cross-test with admin bearer and anonymous modes.
- API results match website and M1 visibility under DONE/SKIPPED, unpublished and reprocessing conditions. No hidden material via tag counts or search snippets.
- All seven MCP tools map to corresponding JSON service behavior, with equivalent visibility/quota handling, error categorization, and response size limits. Conformance test the real transport using an MCP client, not only mocked function calls.
- Counter races across workers enforce hourly and burst caps. Revocation, expiry, per-key overrides, Redis unavailability, forged forwarded headers and heavy FTS requests are tested.
- Contract tests verify OpenAPI examples, pagination, ETags, footer link, SKILL.md discoverability, and API/MCP disabled-state behavior on existing private/local installs.
- Local resource qualification: cached/latest polling, SQLite FTS load under realistic article count, Redis contention, p95 latency and bounded response memory. No public uptime SLA or remote hosted-service launch criterion.

## Stop conditions

Do not enable external agent access if M1 visibility leakage remains; if a reader token inherits admin privileges; if MCP bypasses quotas; if private articles appear in search; or if rate counters fail open under credentialed requests. Independent API and MCP enable flags remain off by default for inherited private deployments.

## Implementation evidence

- Added `/api/public/v1` article/catalog/search/newsletter read routes and OpenAPI JSON; stable signed keyset cursors bind filters, sorting and key IDs. Discovery is at `/agents`, `/llms.txt` and `/SKILL.md`; the public footer advertises the agent page only when access policy is enabled.
- Added independent hashed `agent_` reader credentials and admin controls. Reader keys carry only `public.read`; tests verify they cannot authorize admin API routes. REST and MCP share the same quota identity, fixed UTC-hour budget and minute burst budget; Redis errors fail closed. Anonymous identity ignores forwarded IP headers.
- Added optional MCP Python SDK extra and actual seven-tool Streamable HTTP ASGI façade. `tests/test_mcp_public_transport.py` uses an SDK client through the ASGI app and checks tool names and the public DTO. API coverage checks hidden-row exclusion, cursor ordering, ETag/304, disabled behavior and Redis failure behavior.
- Commands: focused agent/public tests and full local suite; `.venv/bin/mypy . --exclude .venv`; scoped Ruff; `uv lock --check` (see parent evidence for final counts).
- Final local suite: 5,004 passed, 6 skipped; MyPy passed across 510 source files; changed-file Ruff and diff checks passed. Worktree implementation patch SHA-256 (code/docs/tests, plan files excluded): `f5980a4416d736fce98b78d06ad8de6de5de4563212b042a04724761991567ff`.
- Limitations: no concurrent multi-process Redis benchmark, large-corpus FTS stress run, p95 latency/memory measurement, direct target-ASGI runtime test or external client launch was performed. Reverse-proxy deployment testing is handled separately. Both public API/MCP and anonymous access remain off by default.
