"""Opt-in read-only agent JSON API over the shared publication read model."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from flask import current_app, jsonify, request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from itsdangerous import BadSignature, URLSafeSerializer

from extensions import db
from models import Article, NewsletterEdition, Tag, article_tags
from routes.public import public_bp
from services.agent_access import admit_request
from services.publication import published_article_query, serialize_public_article
from services.newsletter_editions import get_public_edition, serialize_edition


@public_bp.before_request
def _public_api_access_gate():
    if request.path.startswith("/api/public/v1/"):
        return admit_request()


def _cursor_encode(payload: dict) -> str:
    return _cursor_serializer().dumps(payload)


def _cursor_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.secret_key, salt="ainews-public-cursor-v1")


def _cursor_decode(value: str | None, expected: dict) -> dict | None:
    if not value:
        return None
    try:
        payload = _cursor_serializer().loads(value)
        if not isinstance(payload, dict):
            return None
        if any(payload.get(k) != v for k, v in expected.items()):
            return None
        return payload
    except (BadSignature, ValueError, TypeError, json.JSONDecodeError):
        return None


def _json_response(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "public, max-age=60"
    response.set_etag(hashlib.sha256(response.get_data()).hexdigest())
    response.make_conditional(request)
    if hasattr(request, "agent_quota_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.agent_quota_remaining)
    return response


def _params():
    limit = request.args.get("limit", default=20, type=int)
    if limit < 1:
        limit = 1
    limit = min(50, limit)
    category = request.args.get("category", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    sort = request.args.get("sort", "recent").strip()
    if sort not in {"recent", "published", "impact"}:
        sort = "recent"
    return limit, category, tag, sort


def _date_filter(name: str):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise ValueError(name)


def _cursor_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@public_bp.route("/api/public/v1/articles")
def api_articles():
    limit, category, tag, sort = _params()
    try:
        start, end = _date_filter("from"), _date_filter("to")
    except ValueError as exc:
        return _json_response({"error": {"code": "invalid_date", "message": f"{exc.args[0]} must be ISO 8601"}}, 400)
    if start and end and start > end:
        return _json_response({"error": {"code": "invalid_date_range", "message": "from must not be after to"}}, 400)
    expected = {"category": category, "tag": tag, "sort": sort, "from": request.args.get("from"), "to": request.args.get("to")}
    cursor = _cursor_decode(request.args.get("cursor"), expected)
    if request.args.get("cursor") and cursor is None:
        return _json_response({"error": {"code": "invalid_cursor", "message": "Cursor is invalid for these filters"}}, 400)
    q = published_article_query().options(joinedload(Article.tags), joinedload(Article.source), joinedload(Article.citations))
    if category:
        q = q.where(Article.category == category)
    if tag:
        q = q.where(Article.tags.any(Tag.slug == tag))
    if start:
        q = q.where(Article.published_at >= start)
    if end:
        q = q.where(Article.published_at <= end)
    if sort == "impact":
        if cursor:
            q = q.where(or_(Article.impact_score < cursor["v"], (Article.impact_score == cursor["v"]) & (Article.id < cursor["id"])))
        q = q.order_by(Article.impact_score.desc(), Article.id.desc())
        key = lambda a: {**expected, "v": a.impact_score or 0, "id": a.id}
    else:
        col = Article.published_at if sort == "published" else Article.created_at
        if cursor:
            stamp = _cursor_stamp(cursor["v"])
            q = q.where(or_(col < stamp, (col == stamp) & (Article.id < cursor["id"])))
        q = q.order_by(col.desc(), Article.id.desc())
        key = lambda a: {**expected, "v": (a.published_at if sort == "published" else a.created_at).replace(tzinfo=timezone.utc).isoformat(), "id": a.id}
    rows = db.session.scalars(q.limit(limit + 1)).unique().all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _cursor_encode(key(rows[-1])) if more and rows else None
    return _json_response({"items": [serialize_public_article(a) for a in rows], "next_cursor": next_cursor, "has_more": more})


@public_bp.route("/api/public/v1/articles/<public_id>")
def api_article(public_id: str):
    article = db.session.scalar(published_article_query().where(Article.public_id == public_id).options(
        joinedload(Article.tags), joinedload(Article.source), joinedload(Article.citations)))
    if article is None:
        return _json_response({"error": {"code": "not_found", "message": "Article not found"}}, 404)
    return _json_response({"item": serialize_public_article(article)})


@public_bp.route("/api/public/v1/search")
def api_search():
    query = request.args.get("q", "").strip()
    if len(query) < 2 or len(query) > 256 or len(query.split()) > 12:
        return _json_response({"error": {"code": "invalid_query", "message": "q must contain 2 to 256 characters and at most 12 terms"}}, 400)
    limit, category, tag, sort = _params()
    try:
        start, end = _date_filter("from"), _date_filter("to")
    except ValueError as exc:
        return _json_response({"error": {"code": "invalid_date", "message": f"{exc.args[0]} must be ISO 8601"}}, 400)
    terms = [term[:64] for term in query.split()[:12]]
    expected = {"q": hashlib.sha256(query.encode()).hexdigest(), "category": category, "tag": tag, "sort": sort,
                "from": request.args.get("from"), "to": request.args.get("to")}
    cursor = _cursor_decode(request.args.get("cursor"), expected)
    if request.args.get("cursor") and cursor is None:
        return _json_response({"error": {"code": "invalid_cursor", "message": "Cursor is invalid for this query"}}, 400)
    q = published_article_query().options(joinedload(Article.tags), joinedload(Article.source), joinedload(Article.citations))
    for term in terms:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        q = q.where(or_(Article.original_title.ilike(pattern, escape="\\"), Article.final_article.ilike(pattern, escape="\\")))
    if category:
        q = q.where(Article.category == category)
    if tag:
        q = q.where(Article.tags.any(Tag.slug == tag))
    if start:
        q = q.where(Article.published_at >= start)
    if end:
        q = q.where(Article.published_at <= end)
    if sort == "impact":
        if cursor:
            q = q.where(or_(Article.impact_score < cursor["v"], (Article.impact_score == cursor["v"]) & (Article.id < cursor["id"])))
        q = q.order_by(Article.impact_score.desc(), Article.id.desc())
        next_payload = lambda a: {**expected, "v": a.impact_score or 0, "id": a.id}
    else:
        col = Article.published_at if sort == "published" else Article.created_at
        if cursor:
            stamp = _cursor_stamp(cursor["v"])
            q = q.where(or_(col < stamp, (col == stamp) & (Article.id < cursor["id"])))
        q = q.order_by(col.desc(), Article.id.desc())
        next_payload = lambda a: {**expected, "v": col_value(a, sort), "id": a.id}
    rows = db.session.scalars(q.limit(limit + 1)).unique().all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _cursor_encode(next_payload(rows[-1])) if more and rows else None
    return _json_response({"items": [serialize_public_article(a) for a in rows], "next_cursor": next_cursor, "has_more": more})


def col_value(article: Article, sort: str) -> str:
    value = article.published_at if sort == "published" else article.created_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@public_bp.route("/api/public/v1/categories")
def api_categories():
    rows = db.session.execute(select(Article.category, func.count(Article.id)).where(Article.publicly_visible.is_(True), Article.final_article != "", Article.category.is_not(None)).group_by(Article.category).order_by(Article.category)).all()
    return _json_response({"items": [{"key": key, "count": count} for key, count in rows]})


@public_bp.route("/api/public/v1/tags")
def api_tags():
    rows = db.session.execute(select(Tag.name, Tag.slug, func.count(article_tags.c.article_id)).join(article_tags, Tag.id == article_tags.c.tag_id)
        .join(Article, Article.id == article_tags.c.article_id).where(Article.publicly_visible.is_(True), Article.final_article != "")
        .group_by(Tag.id).order_by(func.count(article_tags.c.article_id).desc(), Tag.name).limit(200)).all()
    return _json_response({"items": [{"name": name, "slug": slug, "count": count} for name, slug, count in rows]})


def _edition_payloads():
    return db.session.scalars(select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
        .order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.id.desc()).limit(50)).all()


@public_bp.route("/api/public/v1/newsletters")
def api_newsletters():
    if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        return _json_response({"error": {"code": "disabled", "message": "Newsletter archive is disabled"}}, 404)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 50)
    profile = request.args.get("type", "").strip() or None
    try:
        start, end = _date_filter("from"), _date_filter("to")
    except ValueError as exc:
        return _json_response({"error": {"code": "invalid_date", "message": f"{exc.args[0]} must be ISO 8601"}}, 400)
    expected = {"type": profile, "from": request.args.get("from"), "to": request.args.get("to")}
    cursor = _cursor_decode(request.args.get("cursor"), expected)
    if request.args.get("cursor") and cursor is None:
        return _json_response({"error": {"code": "invalid_cursor", "message": "Cursor is invalid for these filters"}}, 400)
    q = select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
    if profile:
        q = q.where(NewsletterEdition.profile_key == profile)
    if start:
        q = q.where(NewsletterEdition.published_at >= start)
    if end:
        q = q.where(NewsletterEdition.published_at <= end)
    if cursor:
        stamp = _cursor_stamp(cursor["v"])
        q = q.where(or_(NewsletterEdition.published_at < stamp, (NewsletterEdition.published_at == stamp) & (NewsletterEdition.id < cursor["id"])))
    rows = db.session.scalars(q.order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _cursor_encode({**expected, "v": rows[-1].published_at.replace(tzinfo=timezone.utc).isoformat(), "id": rows[-1].id}) if more and rows else None
    return _json_response({"items": [serialize_edition(e) for e in rows], "next_cursor": next_cursor, "has_more": more})


@public_bp.route("/api/public/v1/newsletters/<public_id>")
def api_newsletter(public_id: str):
    if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        return _json_response({"error": {"code": "disabled", "message": "Newsletter archive is disabled"}}, 404)
    edition = get_public_edition(public_id)
    if edition is None:
        return _json_response({"error": {"code": "not_found", "message": "Newsletter not found"}}, 404)
    return _json_response({"item": serialize_edition(edition)})


@public_bp.route("/api/public/openapi.json")
def public_openapi():
    def operation(summary: str, *, security: bool = True) -> dict:
        value = {"summary": summary, "responses": {
            "200": {"description": "Published public content"},
            "400": {"description": "Invalid filter or cursor"},
            "429": {"description": "Request quota reached"},
            "503": {"description": "Quota service unavailable"}}}
        if security:
            value["security"] = [{"AgentReader": []}]
        return value

    paths = {
        "/api/public/v1/articles": {"get": operation("List published articles with keyset pagination")},
        "/api/public/v1/articles/{public_id}": {"get": operation("Get one published article")},
        "/api/public/v1/search": {"get": operation("Search published articles")},
        "/api/public/v1/categories": {"get": operation("List visible categories")},
        "/api/public/v1/tags": {"get": operation("List tags attached to visible articles")},
        "/api/public/v1/newsletters": {"get": operation("List immutable published editions")},
        "/api/public/v1/newsletters/{public_id}": {"get": operation("Get one published edition")},
    }
    paths["/api/public/v1/articles/{public_id}"]["get"]["parameters"] = [{"name": "public_id", "in": "path", "required": True, "schema": {"type": "string"}}]
    paths["/api/public/v1/newsletters/{public_id}"]["get"]["parameters"] = [{"name": "public_id", "in": "path", "required": True, "schema": {"type": "string"}}]
    return jsonify({"openapi": "3.1.0", "info": {"title": "AInews Public Read API", "version": "1.0.0"},
        "components": {"securitySchemes": {"AgentReader": {"type": "http", "scheme": "bearer", "bearerFormat": "agent_<id>.<secret>"}}},
        "paths": paths})


@public_bp.route("/agents")
def agents_landing():
    from services.agent_access import get_policy
    if not get_policy()["api_enabled"]:
        return "Agent access is disabled.", 404
    return """<!doctype html><title>AInews for AI agents</title><h1>For AI agents</h1>
<p>Read published articles through the versioned, read-only API. Use pagination and cite article URLs.</p>
<p><a href='/api/public/openapi.json'>OpenAPI</a> · <a href='/llms.txt'>llms.txt</a> · <a href='/SKILL.md'>Consumer skill</a></p>"""


@public_bp.route("/llms.txt")
def llms_txt():
    from services.agent_access import get_policy
    if not get_policy()["api_enabled"]:
        return "", 404
    return "AInews publishes provenance-bearing articles. Read via /api/public/v1. Respect quotas and cite canonical article URLs.\n/agents\n/api/public/openapi.json\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@public_bp.route("/SKILL.md")
def consumer_skill():
    from services.agent_access import get_policy
    if not get_policy()["api_enabled"]:
        return "", 404
    return """# AInews consumer skill\n\nUse GET /api/public/v1/articles with limit <= 50 and follow next_cursor. Search with GET /api/public/v1/search?q=... . Cite each item's canonical_url and preserve citations. Treat results as partial when has_more is true. Respect HTTP 429 and Retry-After. Reader credentials are read-only; never probe private/admin routes.\n""", 200, {"Content-Type": "text/markdown; charset=utf-8"}
