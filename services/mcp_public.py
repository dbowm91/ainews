"""Optional Streamable HTTP MCP façade over the published read model."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select

from extensions import db
from models import Article, NewsletterEdition, Tag, article_tags
from services.newsletter_editions import get_public_edition, serialize_edition
from services.publication import published_article_query, serialize_public_article

flask_app = None


def _cursor_helpers():
    from routes.public.api import _cursor_decode, _cursor_encode, _cursor_stamp, col_value
    return _cursor_decode, _cursor_encode, _cursor_stamp, col_value


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _list_articles(category: str | None = None, tag: str | None = None, limit: int = 20,
                   sort: str = "recent", cursor: str | None = None,
                   date_from: str | None = None, date_to: str | None = None):
    sort = sort if sort in {"recent", "published", "impact"} else "recent"
    expected = {"category": category, "tag": tag, "sort": sort, "from": date_from, "to": date_to}
    decode, encode, stamp, col_value = _cursor_helpers()
    page = decode(cursor, expected)
    if cursor and page is None:
        raise ValueError("cursor is invalid for these filters")
    q = published_article_query()
    if category:
        q = q.where(Article.category == category)
    if tag:
        q = q.where(Article.tags.any(Tag.slug == tag))
    start, end = _parse_date(date_from), _parse_date(date_to)
    if start:
        q = q.where(Article.published_at >= start)
    if end:
        q = q.where(Article.published_at <= end)
    if sort == "impact":
        if page:
            q = q.where(or_(Article.impact_score < page["v"], (Article.impact_score == page["v"]) & (Article.id < page["id"])))
        q = q.order_by(Article.impact_score.desc(), Article.id.desc())
        next_payload = lambda article: {**expected, "v": article.impact_score or 0, "id": article.id}
    else:
        col = Article.published_at if sort == "published" else Article.created_at
        if page:
            value = stamp(page["v"])
            q = q.where(or_(col < value, (col == value) & (Article.id < page["id"])))
        q = q.order_by(col.desc(), Article.id.desc())
        next_payload = lambda article: {**expected, "v": col_value(article, sort), "id": article.id}
    rows = db.session.scalars(q.limit(min(max(limit, 1), 50) + 1)).all()
    more = len(rows) > min(max(limit, 1), 50)
    rows = rows[:min(max(limit, 1), 50)]
    return {"items": [serialize_public_article(article) for article in rows],
        "next_cursor": encode(next_payload(rows[-1])) if more and rows else None, "has_more": more}


def _search(query: str, limit: int = 20, category: str | None = None, tag: str | None = None,
            sort: str = "recent", cursor: str | None = None,
            date_from: str | None = None, date_to: str | None = None):
    if len(query) < 2 or len(query) > 256 or len(query.split()) > 12:
        raise ValueError("query must be 2–256 characters and no more than 12 terms")
    sort = sort if sort in {"recent", "published", "impact"} else "recent"
    expected = {"q": hashlib.sha256(query.encode()).hexdigest(), "category": category, "tag": tag,
        "sort": sort, "from": date_from, "to": date_to}
    decode, encode, stamp, col_value = _cursor_helpers()
    page = decode(cursor, expected)
    if cursor and page is None:
        raise ValueError("cursor is invalid for these filters")
    q = published_article_query()
    for term in query.split()[:12]:
        escaped = term[:64].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        q = q.where(or_(Article.original_title.ilike(pattern, escape="\\"), Article.final_article.ilike(pattern, escape="\\")))
    if category:
        q = q.where(Article.category == category)
    if tag:
        q = q.where(Article.tags.any(Tag.slug == tag))
    start, end = _parse_date(date_from), _parse_date(date_to)
    if start:
        q = q.where(Article.published_at >= start)
    if end:
        q = q.where(Article.published_at <= end)
    if sort == "impact":
        if page:
            q = q.where(or_(Article.impact_score < page["v"], (Article.impact_score == page["v"]) & (Article.id < page["id"])))
        q = q.order_by(Article.impact_score.desc(), Article.id.desc())
        next_payload = lambda article: {**expected, "v": article.impact_score or 0, "id": article.id}
    else:
        col = Article.published_at if sort == "published" else Article.created_at
        if page:
            value = stamp(page["v"])
            q = q.where(or_(col < value, (col == value) & (Article.id < page["id"])))
        q = q.order_by(col.desc(), Article.id.desc())
        next_payload = lambda article: {**expected, "v": col_value(article, sort), "id": article.id}
    rows = db.session.scalars(q.limit(min(max(limit, 1), 50) + 1)).all()
    more = len(rows) > min(max(limit, 1), 50)
    rows = rows[:min(max(limit, 1), 50)]
    return {"items": [serialize_public_article(article) for article in rows],
        "next_cursor": encode(next_payload(rows[-1])) if more and rows else None, "has_more": more}


def _categories():
    return [{"key": key, "count": count} for key, count in db.session.execute(
        select(Article.category, func.count(Article.id)).where(Article.publicly_visible.is_(True), Article.final_article != "", Article.category.is_not(None))
        .group_by(Article.category).order_by(Article.category)).all()]


def _tags():
    return [{"name": name, "slug": slug, "count": count} for name, slug, count in db.session.execute(
        select(Tag.name, Tag.slug, func.count(article_tags.c.article_id)).join(article_tags, Tag.id == article_tags.c.tag_id)
        .join(Article, Article.id == article_tags.c.article_id).where(Article.publicly_visible.is_(True), Article.final_article != "")
        .group_by(Tag.id).order_by(func.count(article_tags.c.article_id).desc(), Tag.name).limit(200)).all()]


def _list_newsletters(limit: int = 20, profile: str | None = None, cursor: str | None = None,
                      date_from: str | None = None, date_to: str | None = None):
    app = flask_app
    if app is None or not app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        return {"error": {"code": "disabled", "message": "Newsletter archive is disabled"}}
    expected = {"type": profile, "from": date_from, "to": date_to}
    decode, encode, stamp, _ = _cursor_helpers()
    page = decode(cursor, expected)
    if cursor and page is None:
        raise ValueError("cursor is invalid for these filters")
    q = select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
    if profile:
        q = q.where(NewsletterEdition.profile_key == profile)
    start, end = _parse_date(date_from), _parse_date(date_to)
    if start:
        q = q.where(NewsletterEdition.published_at >= start)
    if end:
        q = q.where(NewsletterEdition.published_at <= end)
    if page:
        value = stamp(page["v"])
        q = q.where(or_(NewsletterEdition.published_at < value, (NewsletterEdition.published_at == value) & (NewsletterEdition.id < page["id"])))
    limit = min(max(limit, 1), 50)
    rows = db.session.scalars(q.order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    value = rows[-1].published_at.replace(tzinfo=timezone.utc).isoformat() if rows and rows[-1].published_at.tzinfo is None else rows[-1].published_at.isoformat() if rows else None
    return {"items": [serialize_edition(row) for row in rows],
        "next_cursor": encode({**expected, "v": value, "id": rows[-1].id}) if more and rows else None, "has_more": more}


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
        """List publicly published articles, bounded to 50 items."""
        with flask_app.app_context():
            return _list_articles(category, tag, limit, sort, cursor, date_from, date_to)

    @server.tool()
    def search_articles(query: str, category: str | None = None, tag: str | None = None, sort: str = "recent",
                        date_from: str | None = None, date_to: str | None = None, limit: int = 20,
                        cursor: str | None = None) -> dict:
        """Search the public article corpus; query limits apply."""
        with flask_app.app_context():
            return _search(query, limit, category, tag, sort, cursor, date_from, date_to)

    @server.tool()
    def get_article(public_id: str) -> dict:
        """Get one published article by its public identifier."""
        with flask_app.app_context():
            article = db.session.scalar(published_article_query().where(Article.public_id == public_id))
            return {"item": serialize_public_article(article)} if article else {"error": {"code": "not_found", "message": "Article not found"}}

    @server.tool()
    def list_categories() -> dict:
        """List public categories and visible article counts."""
        with flask_app.app_context():
            return {"items": _categories()}

    @server.tool()
    def list_tags() -> dict:
        """List public tags and visible usage counts."""
        with flask_app.app_context():
            return {"items": _tags()}

    @server.tool()
    def list_newsletters(profile: str | None = None, date_from: str | None = None, date_to: str | None = None,
                         limit: int = 20, cursor: str | None = None) -> dict:
        """List published newsletter edition snapshots."""
        with flask_app.app_context():
            return _list_newsletters(limit, profile, cursor, date_from, date_to)

    @server.tool()
    def get_newsletter(public_id: str) -> dict:
        """Get one published newsletter edition by public identifier."""
        if not flask_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
            return {"error": {"code": "disabled", "message": "Newsletter archive is disabled"}}
        with flask_app.app_context():
            edition = get_public_edition(public_id)
            return {"item": serialize_edition(edition)} if edition else {"error": {"code": "not_found", "message": "Newsletter not found"}}

    return server.streamable_http_app()


class PublicASGI:
    """Route MCP through the maintained SDK and everything else to Flask WSGI."""
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
