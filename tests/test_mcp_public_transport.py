"""Optional real MCP transport conformance smoke test."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
import pytest

from extensions import db
from models import AgentAccessConfig, Article, Source
from services.agent_access import create_credential


def test_streamable_http_exposes_seven_read_only_tools_and_public_dto(app, monkeypatch):
    pytest.importorskip("mcp")
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from services.mcp_public import PublicASGI, build_mcp_asgi_app
    import services.mcp_public as mcp_public

    with app.app_context():
        source = Source(source_key="mcp-test", name="MCP test source", source_type="rss")
        db.session.add(source)
        db.session.flush()
        article = Article(source_id=source.id, original_title="Visible MCP story", pipeline_status="done",
            final_article=json.dumps({"headline": "Visible MCP story", "body": "Public text."}), publicly_visible=True)
        db.session.add_all([article, AgentAccessConfig(id=1, public_api_enabled=True, public_mcp_enabled=True)])
        db.session.commit()
        public_id = article.public_id
        _credential, token = create_credential("mcp transport test")
    monkeypatch.setattr("services.agent_access._quota", lambda identity, limit: (True, limit - 1, 0))
    monkeypatch.setattr(mcp_public, "flask_app", app)
    mcp_app = build_mcp_asgi_app()
    asgi = PublicASGI(app.wsgi_app, app, mcp_app)

    def client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(base_url="http://localhost:5000", transport=httpx.ASGITransport(app=asgi),
            headers=headers, timeout=timeout, auth=auth)

    async def exercise():
        headers = {"Authorization": f"Bearer {token}"}
        async with client_factory(headers=headers) as http_client:
            response = await http_client.get("/api/public/v1/articles?limit=1")
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "private, no-store"
            assert "Authorization" in response.headers.get("Vary", "")
            api_payload = response.json()
            assert api_payload["items"][0]["public_id"] == public_id
            assert "pipeline_status" not in api_payload["items"][0]

            async with streamable_http_client("http://localhost:5000/mcp", http_client=http_client) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert names == {"list_articles", "search_articles", "get_article", "list_categories", "list_tags", "list_newsletters", "get_newsletter"}
                    result = await session.call_tool("list_articles", arguments={"limit": 1})
                    assert not result.isError
                    payload = json.loads(result.content[0].text)
                    assert payload["items"][0]["public_id"] == public_id
                    assert "pipeline_status" not in payload["items"][0]

    async def run_with_lifespan():
        async with mcp_app.router.lifespan_context(mcp_app):
            await exercise()

    # Some pytest plugins or earlier tests leave an event loop active in the
    # main thread; give the SDK client a private loop so this remains order-safe.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, run_with_lifespan()).result()


def test_reader_policy_matrix_runs_through_asgi_transport(app, monkeypatch):
    from datetime import datetime, timezone

    from redis.exceptions import RedisError
    from services.mcp_public import PublicASGI
    import services.agent_access as agent_access

    with app.app_context():
        source = Source(source_key="asgi-policy-test", name="ASGI policy test", source_type="rss")
        db.session.add(source)
        db.session.flush()
        article = Article(source_id=source.id, original_title="ASGI policy story", pipeline_status="done",
            final_article=json.dumps({"headline": "ASGI policy story", "body": "Public text."}), publicly_visible=True,
            published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        config = AgentAccessConfig(id=1, public_api_enabled=True, public_mcp_enabled=False, anonymous_enabled=False)
        db.session.add_all([article, config])
        db.session.commit()
        _first, first_token = create_credential("ASGI reader one")
        second_credential, second_token = create_credential("ASGI reader two")
        limited, limited_token = create_credential("ASGI limited reader", requests_per_hour=1)
        second_id = second_credential.public_id
        limited_id = limited.public_id

    counts: dict[str, int] = {}

    def quota(identity: str, limit: int) -> tuple[bool, int, int]:
        counts[identity] = counts.get(identity, 0) + 1
        used = counts[identity]
        return used <= limit, max(0, limit - used), 90 if used > limit else 0

    monkeypatch.setattr(agent_access, "_quota", quota)
    asgi = PublicASGI(app.wsgi_app, app, None)

    async def exercise():
        async with httpx.AsyncClient(base_url="http://localhost", transport=httpx.ASGITransport(app=asgi)) as client:
            assert (await client.get("/api/public/v1/articles")).status_code == 401
            malformed = await client.get("/api/public/v1/articles", headers={"Authorization": "Bearer malformed"})
            assert malformed.status_code == 401

            first_headers = {"Authorization": f"Bearer {first_token}"}
            first = await client.get("/api/public/v1/articles", headers=first_headers)
            assert first.status_code == 200
            assert first.headers["Cache-Control"] == "private, no-store"
            assert "Authorization" in first.headers["Vary"]
            conditional = await client.get("/api/public/v1/articles", headers={
                **first_headers, "If-None-Match": first.headers["ETag"],
            })
            assert conditional.status_code == 304
            assert conditional.headers["Cache-Control"] == "private, no-store"
            assert counts[f"key:{first_token[6:].split('.', 1)[0]}"] == 2

            second = await client.get("/api/public/v1/articles", headers={"Authorization": f"Bearer {second_token}"})
            assert second.status_code == 200
            assert counts[f"key:{second_id}"] == 1
            assert (await client.get("/api/v1/health", headers=first_headers)).status_code == 401

            limited_headers = {"Authorization": f"Bearer {limited_token}"}
            assert (await client.get("/api/public/v1/articles", headers=limited_headers)).status_code == 200
            over_limit = await client.get("/api/public/v1/articles", headers=limited_headers)
            assert over_limit.status_code == 429
            assert over_limit.headers.get("Retry-After") == "90"
            assert counts[f"key:{limited_id}"] == 2

            with app.app_context():
                credential = db.session.query(AgentAccessConfig).filter_by(id=1).one()
                credential.public_api_enabled = False
                db.session.commit()
            disabled = await client.get("/api/public/v1/articles", headers=first_headers)
            assert disabled.status_code == 404

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, exercise()).result()

    with app.app_context():
        credential = db.session.query(AgentAccessConfig).filter_by(id=1).one()
        credential.public_api_enabled = True
        revoked = db.session.query(AgentAccessConfig).filter_by(id=1).one()
        db.session.commit()
        from models import AgentCredential
        revoked_credential = db.session.query(AgentCredential).filter_by(public_id=second_id).one()
        revoked_credential.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

    async def check_revoked_and_redis_failure():
        async with httpx.AsyncClient(base_url="http://localhost", transport=httpx.ASGITransport(app=asgi)) as client:
            assert (await client.get("/api/public/v1/articles", headers={
                "Authorization": f"Bearer {second_token}",
            })).status_code == 401
            monkeypatch.setattr(agent_access, "_quota", lambda *_args: (_ for _ in ()).throw(RedisError("unavailable")))
            unavailable = await client.get("/api/public/v1/articles", headers={
                "Authorization": f"Bearer {first_token}",
            })
            assert unavailable.status_code == 503

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, check_revoked_and_redis_failure()).result()
