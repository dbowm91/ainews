"""Opt-in read-only agent JSON API over the shared public read service."""
from __future__ import annotations

import hashlib

from flask import current_app, jsonify, request

from routes.public import public_bp
from services.agent_access import admit_request, get_policy
from services.public_read import (
    ArticleFilters,
    EditionFilters,
    PublicReadError,
    get_article,
    get_categories,
    get_edition,
    get_tags,
    list_articles,
    list_editions,
    parse_date,
    search_articles,
)
from services.newsletter_editions import serialize_edition
from services.publication import serialize_public_article


@public_bp.before_request
def _public_api_access_gate():
    if request.path.startswith("/api/public/v1/"):
        return admit_request()


def _json_response(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    # Reader-key responses include quota state and must never enter shared
    # caches. Conditional handling happens only after the before_request gate.
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    response.set_etag(hashlib.sha256(response.get_data()).hexdigest())
    response.make_conditional(request)
    if hasattr(request, "agent_quota_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(request.agent_quota_remaining)
    return response


def _limit() -> int:
    raw_limit = request.args.get("limit", "20")
    try:
        return min(max(int(raw_limit), 1), 50)
    except (TypeError, ValueError):
        raise PublicReadError("invalid_limit", "limit must be an integer from 1 to 50") from None


def _params() -> tuple[int, str | None, str | None, str]:
    limit = _limit()
    category = request.args.get("category", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    sort = request.args.get("sort", "recent").strip()
    if sort not in {"recent", "published", "impact"}:
        raise PublicReadError("invalid_sort", "sort must be recent, published, or impact")
    return limit, category, tag, sort


def _date_filter(name: str):
    return parse_date(request.args.get(name), name)


def _public_error(exc: PublicReadError):
    status = 404 if exc.code == "disabled" else 400
    return _json_response({"error": {"code": exc.code, "message": str(exc)}}, status)


@public_bp.route("/api/public/v1/articles")
def api_articles():
    try:
        limit, category, tag, sort = _params()
        filters = ArticleFilters(limit, category, tag, sort, request.args.get("cursor"),
                                 _date_filter("from"), _date_filter("to"))
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise PublicReadError("invalid_date_range", "from must not be after to")
        return _json_response(list_articles(filters))
    except PublicReadError as exc:
        return _public_error(exc)


@public_bp.route("/api/public/v1/articles/<public_id>")
def api_article(public_id: str):
    article = get_article(public_id)
    if article is None:
        return _json_response({"error": {"code": "not_found", "message": "Article not found"}}, 404)
    return _json_response({"item": serialize_public_article(article)})


@public_bp.route("/api/public/v1/search")
def api_search():
    try:
        limit, category, tag, sort = _params()
        filters = ArticleFilters(limit, category, tag, sort, request.args.get("cursor"),
                                 _date_filter("from"), _date_filter("to"), request.args.get("q", "").strip())
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise PublicReadError("invalid_date_range", "from must not be after to")
        return _json_response(search_articles(filters))
    except PublicReadError as exc:
        return _public_error(exc)


@public_bp.route("/api/public/v1/categories")
def api_categories():
    return _json_response({"items": get_categories()})


@public_bp.route("/api/public/v1/tags")
def api_tags():
    return _json_response({"items": get_tags()})


@public_bp.route("/api/public/v1/newsletters")
def api_newsletters():
    try:
        filters = EditionFilters(
            limit=_limit(),
            profile=request.args.get("type", "").strip() or None,
            cursor=request.args.get("cursor"),
            date_from=_date_filter("from"),
            date_to=_date_filter("to"),
        )
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise PublicReadError("invalid_date_range", "from must not be after to")
        return _json_response(list_editions(filters))
    except PublicReadError as exc:
        return _public_error(exc)


@public_bp.route("/api/public/v1/newsletters/<public_id>")
def api_newsletter(public_id: str):
    edition = get_edition(public_id)
    if edition is None:
        if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
            return _json_response({"error": {"code": "disabled", "message": "Newsletter archive is disabled"}}, 404)
        return _json_response({"error": {"code": "not_found", "message": "Newsletter not found"}}, 404)
    return _json_response({"item": serialize_edition(edition)})


@public_bp.route("/api/public/openapi.json")
def public_openapi():
    def operation(summary: str) -> dict:
        return {"summary": summary, "security": [{"AgentReader": []}], "responses": {
            "200": {"description": "Published public content"},
            "400": {"description": "Invalid filter or cursor"},
            "401": {"description": "Reader credential required or invalid"},
            "404": {"description": "Not found or feature disabled"},
            "429": {"description": "Request quota reached; includes Retry-After"},
            "503": {"description": "Quota service unavailable"}}}

    common_params = [
        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}},
        {"name": "cursor", "in": "query", "schema": {"type": "string", "maxLength": 2048}},
        {"name": "from", "in": "query", "schema": {"type": "string", "format": "date-time"}},
        {"name": "to", "in": "query", "schema": {"type": "string", "format": "date-time"}},
    ]
    article_params = common_params + [
        {"name": "category", "in": "query", "schema": {"type": "string", "maxLength": 64}},
        {"name": "tag", "in": "query", "schema": {"type": "string", "maxLength": 128}},
        {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["recent", "published", "impact"], "default": "recent"}},
    ]
    paths = {
        "/api/public/v1/articles": {"get": operation("List published articles with keyset pagination")},
        "/api/public/v1/articles/{public_id}": {"get": operation("Get one published article")},
        "/api/public/v1/search": {"get": operation("Search published articles using bounded full-text search")},
        "/api/public/v1/categories": {"get": operation("List categories with published articles")},
        "/api/public/v1/tags": {"get": operation("List tags attached to published articles")},
        "/api/public/v1/newsletters": {"get": operation("List immutable published editions")},
        "/api/public/v1/newsletters/{public_id}": {"get": operation("Get one published edition")},
    }
    path_id = {"name": "public_id", "in": "path", "required": True, "schema": {"type": "string"}}
    paths["/api/public/v1/articles/{public_id}"]["get"]["parameters"] = [path_id]
    paths["/api/public/v1/newsletters/{public_id}"]["get"]["parameters"] = [path_id]
    paths["/api/public/v1/articles"]["get"]["parameters"] = article_params
    paths["/api/public/v1/search"]["get"]["parameters"] = article_params + [
        {"name": "q", "in": "query", "required": True, "schema": {"type": "string", "minLength": 1, "maxLength": 256}}
    ]
    paths["/api/public/v1/newsletters"]["get"]["parameters"] = common_params + [
        {"name": "type", "in": "query", "schema": {"type": "string", "maxLength": 80}}
    ]
    return jsonify({"openapi": "3.1.0", "info": {"title": "AInews Public Read API", "version": "1.0.0"},
        "components": {"securitySchemes": {"AgentReader": {"type": "http", "scheme": "bearer", "bearerFormat": "agent_<id>.<secret>"}}},
        "paths": paths})


@public_bp.route("/agents")
def agents_landing():
    if not get_policy()["api_enabled"]:
        return "Agent access is disabled.", 404
    return """<!doctype html><title>AInews for AI agents</title><h1>For AI agents</h1>
<p>Read published articles through the versioned, read-only API. Use pagination and cite article URLs.</p>
<p><a href='/api/public/openapi.json'>OpenAPI</a> · <a href='/llms.txt'>llms.txt</a> · <a href='/SKILL.md'>Consumer skill</a></p>"""


@public_bp.route("/llms.txt")
def llms_txt():
    if not get_policy()["api_enabled"]:
        return "", 404
    return "AInews publishes provenance-bearing articles. Read via /api/public/v1. Respect quotas and cite canonical article URLs.\n/agents\n/api/public/openapi.json\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@public_bp.route("/SKILL.md")
def consumer_skill():
    if not get_policy()["api_enabled"]:
        return "", 404
    return """# AInews consumer skill\n\nUse GET /api/public/v1/articles with limit <= 50 and follow next_cursor. Search uses bounded FTS and returns only published articles. Cite each item's canonical_url. Reader credentials are read-only; never probe private/admin routes. REST responses are private, no-store. Respect HTTP 429 and Retry-After.\n""", 200, {"Content-Type": "text/markdown; charset=utf-8"}
