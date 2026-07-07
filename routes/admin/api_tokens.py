from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from extensions import db
from models import ApiToken
from routes.decorators import authenticate_request, require_auth
from services.api_tokens import (
    generate_api_token,
    hash_api_token_secret,
)

api_tokens_bp = Blueprint("api_tokens", __name__)

_MAX_NAME_LENGTH = 128
_MAX_EXPIRES_SECONDS = 366 * 24 * 3600  # 366 days


@api_tokens_bp.before_request
def _require_api_token_auth():
    """Blueprint-level auth guard — all routes in this blueprint require auth."""
    auth_result = authenticate_request()
    if auth_result is not None:
        return auth_result


@api_tokens_bp.route("/api-tokens", methods=["GET"])
@require_auth
def list_tokens():
    """List all non-revoked API tokens (without exposing hashes)."""
    tokens = ApiToken.query.filter(ApiToken.revoked_at.is_(None)).all()
    return jsonify([
        {
            "id": t.id,
            "name": t.name,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ])


@api_tokens_bp.route("/api-tokens", methods=["POST"])
@require_auth
def create_token():
    """Create a new API token and return the plain text token."""
    data = request.get_json() or {}
    name = data.get("name", "")
    expires_in = data.get("expires_in")

    if name and len(name) > _MAX_NAME_LENGTH:
        return jsonify({"error": f"Name must be {_MAX_NAME_LENGTH} characters or fewer"}), 400

    if expires_in is not None:
        if not isinstance(expires_in, int) or expires_in <= 0:
            return jsonify({"error": "expires_in must be a positive integer"}), 400
        if expires_in > _MAX_EXPIRES_SECONDS:
            return jsonify({"error": "expires_in must not exceed 366 days"}), 400

    public_token, prefix, raw_secret = generate_api_token()

    api_token = ApiToken(
        token_hash=hash_api_token_secret(raw_secret),
        token_prefix=prefix,
        name=name,
    )

    if expires_in:
        api_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    db.session.add(api_token)
    db.session.commit()

    return jsonify({
        "id": api_token.id,
        "name": api_token.name,
        "token": public_token,
        "created_at": api_token.created_at.isoformat(),
        "expires_at": api_token.expires_at.isoformat() if api_token.expires_at else None,
    }), 201


@api_tokens_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
@require_auth
def delete_token(token_id):
    """Hard delete an API token."""
    api_token = ApiToken.query.get_or_404(token_id)
    db.session.delete(api_token)
    db.session.commit()
    return jsonify({"message": "Token deleted"}), 200
