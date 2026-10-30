# C02 — Shared REST/MCP read layer, opaque cursors, cache safety and bounded search

**Status:** IMPLEMENTED; local REST/MCP contract tests pass. Direct ASGI-server runtime qualification remains under C05; reverse-proxy/cache deployment testing is handled separately.
**Parent:** [corrective pass](llm_native_corrective_pass_overview_20261030.md).
**Dependency:** C01 shared publication predicate and migration graph. Can develop isolated read-service code in parallel.
**Activation gate:** before enabling API/MCP for external agents or putting authenticated routes behind a caching proxy.

## Verified implementation findings

- routes/public/api.py constructs signed keyset cursors containing a numeric Article.id or NewsletterEdition.id. itsdangerous URLSafeSerializer signs and detects tampering but does **not encrypt** payload data. services/mcp_public.py repeats this and imports private cursor helpers from routes.public.api, reversing service-to-route layering. Random external public IDs were specifically introduced to avoid enumerated public identities.
- Baseline finding: routes/public/api.py marked credential-protected responses `Cache-Control: public, max-age=60` and emitted `X-RateLimit-Remaining`, which could let a shared cache bypass application reauthentication. The implementation now uses private/no-store for API responses. Reverse-proxy/shared-cache behavior is an independent deployment concern handled separately; C05 verifies the application response directly through ASGI.
- services/mcp_public.py duplicates public article, category/tag, search and newsletter list queries instead of invoking a common services/public_read.py; filters, counters and status semantics can diverge between REST and MCP.
- The new public JSON article search uses chained ILIKE on Article.original_title and Article.final_article, while the project already has SQLite FTS5 and a bounded hybrid index. This makes long, high-volume scans possible under small request counts and can increase load on SQLite/SBC installations.
- categories/tags routes check publicly_visible and final_article, but not the full published_article_query predicate. Some date/sort validation differs between MCP and REST. Reader-key authentication must never be promoted to admin auth.

## Target seam

Create a single services/public_read.py (or coherent package) whose typed inputs include:
- PublicArticleFilter(category/tag/date_from/date_to/query), bounded PageRequest(limit <= 50, cursor, sort) and PublicReaderPolicy.
- list_articles(), search_articles(), get_article(), list_categories(), list_tags(), list_editions(), get_edition().
- Typed results with items, next_cursor, has_more and relevant error categories. Serialize through existing publication/newsletter allowlist DTO builders. Services may import models/SQLAlchemy/schemas; adapters and MCP transport must NOT import Flask route modules or duplicate SQL. Keep public read services read-only, with no inference calls.

Keep privacy/pagination policy under this service, and pass the same read DTO to REST, HTML archive (where useful) and MCP tools. Admin search and its internal IDs remain separately authorized.

## Corrective tasks

1. Extract all public list/search/filter/cursor logic from routes/public/api.py and services/mcp_public.py to the single service. Centralize publication criteria from C01. Assert identical ordering, filters, errors, canonical URLs and DTOs on all seven MCP tools and all corresponding REST endpoints. Eliminate MCP _cursor_helpers() import from routes.public.api.
2. Redesign keyset cursors: use ordered public_id (or an opaque authenticated/encrypted random nonce backed by stored cursor state) as tie-breaker, never numeric DB IDs or serialized sensitive/internal identifiers. A MAC signature alone does not provide confidentiality. Preserve keyset stability with insertion/deletion and identical impact/time scores. Bind cursor to filters/query hash, sort, API version and issued_at/expiry if appropriate; test tamper, key rotation, stale cursor, page-edge inserts, cross-credential reuse policy. Avoid easily predictable numeric pagination leaks in ETag/link metadata.
3. Fix request/caching policy: any credential-restricted API response should default Cache-Control: private, no-store or an equivalent proven secure design. If anonymous publicly cacheable GET responses are intentionally enabled, authorize/cache-key by access mode, set correct Vary: Authorization (and relevant headers), and never cache X-RateLimit-Remaining or personalized error responses in shared caches. Ensure ETag/If-None-Match after authentication and quota admission, and 304 semantics match policy. Separate deliberately public HTML/RSS caching from key-gated REST.
4. Replace raw full-JSON ILIKE scans with bounded, parameterized FTS5 via the existing search provider/public FTS index, or a documented bounded fallback when FTS is absent. Query terms, query size, time budget and candidate scan must be hard capped; verify FTS table membership on withdrawn/hidden articles. Do not alter admin full-text privileges. Search and list source rankings may differ, but publication eligibility and DTO must not.
5. Quota and credential hardening: the existing Redis fixed-hour + minute counters remain authoritative for REST/MCP across workers, but validate concurrent access, global cap, invalid bearer behavior, token revocation, expiry and proxy identity. A request with malformed or unknown Authorization should not silently be downgraded to anonymous when anonymous mode is on unless this behavior is explicit and tested. Fail closed on Redis unavailability and do not mint or reinterpret existing admin API tokens.
6. Review OpenAPI schema generation and consumer SKILL.md as executable contract docs: parameter schemas (limits, dates, cursor, tags, sort), JSON success/error DTOs, security/anonymous modes, quota headers, 429 Retry-After and canonical attribution. Maintain versioned endpoints; document MCP transport/runtime deployment and optional dependency. Avoid changing reader-visible semantics by accident.

## Regression and performance qualification

- **Visible-set parity:** REST, MCP, HTML and feeds show exactly published rows under identical filters. Count aggregations only reflect visible records; unpublished and reprocessing rows never leak via search snippets.
- **Opaque identity:** decode public cursors and assert no internal ID, raw SQL ID, access token or private content. 2 pages with tied timestamps/impact, new insert between pages and late edit do not duplicate/miss rows beyond documented snapshot semantics; tampered cursor is rejected.
- **HTTP response policy:** two reader keys and one anonymous caller cannot reuse an authenticated response through the ASGI-served API to bypass auth/quota. Revocation cannot be defeated by stale application responses. ETag requests always enforce admission or documented safe anonymous policy. Reverse-proxy/shared-cache deployment behavior is handled separately, outside this roadmap gate.
- **Search:** deterministic fixed corpus with title/JSON content, special-character escaping, 50-item cap, hidden/withdrawn FTS candidates, no FTS fallback and invalid date/sort. Compare query plans and p95 on representative SQLite content; no unbounded LIKE over final_article on main public search path.
- **MCP SDK:** call real Streamable HTTP tools with a client, compare exact DTO and pagination against REST; confirm auth/quotas/disabled behavior including multiple tool calls within one MCP session. Exclude write/send/admin tools.
- **Quota:** repeated and concurrent REST+MCP calls on same token hit one shared budget, global cap and burst cap; Redis outage fails closed. Exercise the ASGI server directly. Forwarded-header and proxy/NAT behavior belongs to the separate proxy deployment test.

## Files

routes/public/api.py; services/mcp_public.py; services/publication.py; services/agent_access.py; new services/public_read.py and schemas/public_read.py; services/search/sqlite_fts.py and public FTS indexing lifecycle; extensions.py; run.py; docs/api.md, docs/agent-access.md and /SKILL.md generator; tests/test_llm_native_publication.py, tests/test_mcp_public_transport.py and new tests/test_public_read_contract.py, tests/test_public_api_cache_boundary.py. Prefer smallest dependency surface: no new DB or remote indexing service.

## Stop/closure

Keep REST, anonymous and MCP default-off until source parity, private/no-store response, auth and quota tests pass on branch and through the target ASGI server. Reverse-proxy/shared-cache deployment qualification is separate and not required by this roadmap. Record exact curl/httpx/MCP conformance commands, request outcomes and realistic SQLite query latency, plus implementation SHA. C05 determines integration-ready status; C02 alone does not establish public-product readiness.

## Implementation evidence — 2026-10-30

- REST and MCP delegate to `services/public_read.py`; MCP no longer imports Flask route helpers or owns parallel SQL. Cursor payloads bind public IDs, filter digest, sort, version and expiry.
- API responses are `private, no-store`, vary on Authorization, and conditional handling follows the auth/quota gate. Unknown/malformed Authorization fails closed. Search uses FTS5 with a 500-candidate cap and bounded title-only fallback.
- OpenAPI documents bounded query parameter schemas; invalid limit/sort/date values return structured errors. Feature flags remain default-off.
- Local tests exercise cursor ordering, ETags/auth gating, reader API and MCP parity. A workspace-local Granian ASGI smoke on implementation SHA `70710e0` passed REST privacy headers, a live Redis-backed 5-call quota/429 boundary, and real MCP SDK article reads over Streamable HTTP. Intended-host runtime/load qualification remains C05; reverse-proxy/shared-cache testing is handled separately.
