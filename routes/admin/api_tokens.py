import secrets

from flask import Blueprint, jsonify, request

from extensions import db
from models import ApiToken
from routes.decorators import authenticate_request, require_auth

api_tokens_bp = Blueprint("api_tokens", __name__)


@api_tokens_bp.before_request
def _require_api_token_auth():
    """Blueprint-level auth guard — all routes in this blueprint require auth."""
    auth_result = authenticate_request()
    if auth_result is not None:
        return auth_result


@api_tokens_bp.route("/api-tokens", methods=["GET"])
@require_auth
def list_tokens():
    """List all API tokens (without exposing hashes)."""
    tokens = ApiToken.query.all()
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
    expires_in = data.get("expires_in")  # seconds

    # Generate token
    plain_token = secrets.token_urlsafe(32)
    token_hash = secrets.token_hex(32)

    # Store hash, not plain token
    from werkzeug.security import generate_password_hash
    api_token = ApiToken(
        token_hash=generate_password_hash(token_hash),
        raw_token_hash=token_hash,
        name=name,
    )

    if expires_in:
        from datetime import datetime, timedelta, timezone
        api_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    db.session.add(api_token)
    db.session.commit()

    return jsonify({
        "id": api_token.id,
        "name": api_token.name,
        "token": plain_token + "." + token_hash,
        "created_at": api_token.created_at.isoformat(),
        "expires_at": api_token.expires_at.isoformat() if api_token.expires_at else None,
    }), 201


@api_tokens_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
@require_auth
def delete_token(token_id):
    """Delete an API token."""
    api_token = ApiToken.query.get_or_404(token_id)
    db.session.delete(api_token)
    db.session.commit()
    return "", 204
