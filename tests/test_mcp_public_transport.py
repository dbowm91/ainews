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
