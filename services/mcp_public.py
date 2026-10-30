"""Optional Streamable HTTP MCP transport over the shared public read service."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from services.public_read import (
    ArticleFilters,
    EditionFilters,
    PublicReadError,
    get_article as read_get_article,
    get_categories as read_get_categories,
    get_edition as read_get_edition,
    get_tags as read_get_tags,
    list_articles as read_list_articles,
    list_editions as read_list_editions,
    parse_date,
    search_articles as read_search_articles,
)
from services.publication import serialize_public_article
from services.newsletter_editions import serialize_edition

flask_app = None


def _safe_read(callable_):
    try:
        return callable_()
    except PublicReadError as exc:
        return {"error": {"code": exc.code, "message": str(exc)}}


def build_mcp_asgi_app():
    if flask_app is None:
        raise RuntimeError("Build the Flask application before the MCP ASGI app")
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as exc:
        raise RuntimeError("PUBLIC_MCP_ENABLED requires the optional 'agent' dependencies") from exc

    site_url = flask_app.config.get("SITE_URL") or flask_app.config.get("NEWSLETTER_SITE_URL") or "http://localhost"
    parsed_site = urlsplit(site_url)
    host = parsed_site.netloc or "localhost"
    allowed_hosts = [host]
    if parsed_site.hostname and parsed_site.port is None:
        allowed_hosts.append(f"{parsed_site.hostname}:{int(os.environ.get('PORT', '5000'))}")
    server = FastMCP("AInews public read API", instructions="Read published AInews articles and editions. All tools are read-only.",
        json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts))

    @server.tool()
    def list_articles(category: str | None = None, tag: str | None = None, sort: str = "recent",
                      date_from: str | None = None, date_to: str | None = None, limit: int = 20,
                      cursor: str | None = None) -> dict:
        """List published articles, bounded to 50 items."""
        with flask_app.app_context():
            return _safe_read(lambda: read_list_articles(ArticleFilters(
                limit, category, tag, sort, cursor, parse_date(date_from, "from"), parse_date(date_to, "to"))))

    @server.tool()
    def search_articles(query: str, category: str | None = None, tag: str | None = None,
                        sort: str = "recent", date_from: str | None = None, date_to: str | None = None,
                        limit: int = 20, cursor: str | None = None) -> dict:
        """Search published articles using bounded full-text search."""
        with flask_app.app_context():
            return _safe_read(lambda: read_search_articles(ArticleFilters(
                limit, category, tag, sort, cursor, parse_date(date_from, "from"), parse_date(date_to, "to"), query)))

    @server.tool()
    def get_article(public_id: str) -> dict:
        """Get a published article by its public identifier."""
        with flask_app.app_context():
            article = read_get_article(public_id)
            return {"item": serialize_public_article(article)} if article else {"error": {"code": "not_found", "message": "Article not found"}}

    @server.tool()
    def list_categories() -> dict:
        """List categories that contain published articles."""
        with flask_app.app_context():
            return {"items": read_get_categories()}

    @server.tool()
    def list_tags() -> dict:
        """List tags attached to published articles."""
        with flask_app.app_context():
            return {"items": read_get_tags()}

    @server.tool()
    def list_newsletters(profile: str | None = None, date_from: str | None = None,
                         date_to: str | None = None, limit: int = 20,
                         cursor: str | None = None) -> dict:
        """List published immutable newsletter editions."""
        with flask_app.app_context():
            return _safe_read(lambda: read_list_editions(EditionFilters(
                limit, profile, cursor, parse_date(date_from, "from"), parse_date(date_to, "to"))))

    @server.tool()
    def get_newsletter(public_id: str) -> dict:
        """Get a published newsletter edition by its public identifier."""
        with flask_app.app_context():
            edition = read_get_edition(public_id)
            return {"item": serialize_edition(edition)} if edition else {"error": {"code": "not_found", "message": "Newsletter not found"}}

    return server.streamable_http_app()


class PublicASGI:
    """Route MCP through the SDK transport and all other paths to Flask WSGI."""

    def __init__(self, wsgi_app, flask_application, mcp_app=None):
        from asgiref.wsgi import WsgiToAsgi
        self.wsgi = WsgiToAsgi(wsgi_app)
        self.mcp = mcp_app
        self.flask_app = flask_application

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] == "lifespan":
            if self.mcp is not None:
                await self.mcp(scope, receive, send)
            else:
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            return
        if path == "/mcp" or path.startswith("/mcp/"):
            with self.flask_app.app_context():
                from services.agent_access import get_policy
                mcp_enabled = bool(get_policy()["mcp_enabled"])
            if not mcp_enabled:
                await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"MCP disabled"}'})
                return
            if self.mcp is None:
                await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"MCP SDK is not installed"}'})
                return
            authorization = {key.lower(): value for key, value in scope.get("headers", [])}.get(b"authorization", b"").decode("latin1")
            bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
            with self.flask_app.app_context():
                from services.agent_access import admit_bearer
                allowed, status, reason, _remaining, retry_after = admit_bearer(bearer)
            if not allowed:
                headers = [(b"content-type", b"application/json")]
                if status == 429:
                    headers.append((b"retry-after", str(retry_after).encode()))
                await send({"type": "http.response.start", "status": status, "headers": headers})
                await send({"type": "http.response.body", "body": ('{"error":"' + reason + '"}').encode()})
                return
            await self.mcp(scope, receive, send)
            return
        await self.wsgi(scope, receive, send)
