# Agent read access

AInews can expose published article and newsletter snapshots to external clients. REST, MCP and the newsletter archive are off by default on existing installs. They read the same published-content boundary as the website and cannot trigger generation, subscription changes, delivery or administrative actions.

## Enablement

1. Open Admin → Agent access and enable the REST API, MCP, and anonymous access independently. The same policy can be managed through authenticated `/api/v1/agent-access` routes.
2. Issue a reader credential under Admin → Agent access. Its secret is shown once; store it in the consumer's secret store. Credentials are separate from admin API tokens, limited to `public.read`, optionally expiring, individually revocable and optionally assigned a quota override.
3. Set hourly limits for credentials and anonymous clients. Anonymous identity uses the socket peer address and ignores forwarded headers, so reverse proxy deployments must set and validate their client-IP boundary deliberately.
4. Configure `SITE_URL` to the operator-controlled public origin. Article, edition, unsubscribe and MCP host validation must not derive trusted links from inbound `Host` values.

The REST API is available at `/api/public/v1`. Read [API documentation](api.md) and `/api/public/openapi.json` for its contract. The consumer skill at `/SKILL.md` is a public client guide, not an internal agent instruction or server-side agent.

## MCP

Install the optional `agent` dependency extra to provide the maintained Python MCP SDK. The ASGI entrypoint in `run.py` mounts Streamable HTTP at `/mcp`. MCP requires an `Authorization: Bearer agent_<id>.<secret>` reader key; anonymous MCP access is not supported. The API and MCP consume the same per-key fixed UTC-hour Redis counter. If Redis is unavailable, credentialed access fails closed. MCP has seven read-only tools: `list_articles`, `search_articles`, `get_article`, `list_categories`, `list_tags`, `list_newsletters`, and `get_newsletter`.

## Quotas and failure behavior

REST defaults to 600 requests per credential per UTC hour and anonymous access defaults to 120 requests per peer IP per UTC hour. A second fixed window caps per-minute bursts at one tenth of the hourly allowance (minimum 5, maximum 60); a separate global ceiling defaults to 60,000 per hour. Admin policy can change per-key and anonymous hourly limits, and each reader key can override its credential limit. Hour boundaries can still permit adjacent-window bursts; consumers should poll conservatively and honor `429` plus `Retry-After`. Redis quota errors return `503`; they never silently bypass admission. Anonymous API access should be paired with an upstream request ceiling for expensive search traffic.

Never put reader keys in URLs, logs, source code or public examples. Revocation takes effect on the next request. Admin changes and credential issuance/revocation are audited without storing the secret.
