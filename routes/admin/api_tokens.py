import secrets

from flask import Blueprint, jsonify, request

from extensions import db
from models import ApiToken

api_tokens_bp = Blueprint("api_tokens", __name__)


@api_tokens_bp.route("/api-tokens", methods=["GET"])
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
        name=name,
    )

    if expires_in:
        from datetime import datetime, timedelta
        api_token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

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
def delete_token(token_id):
    """Delete an API token."""
    api_token = ApiToken.query.get_or_404(token_id)
    db.session.delete(api_token)
    db.session.commit()
    return "", 204
