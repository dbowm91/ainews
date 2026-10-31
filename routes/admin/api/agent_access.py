"""Admin management for isolated public reader keys."""
from datetime import datetime, timedelta, timezone

from flask import jsonify, render_template, request

from extensions import db
from models import AgentAccessConfig, AgentCredential
from routes.admin import admin_api_bp, admin_bp, require_auth
from routes.decorators import csrf_for_session_auth
from services.agent_access import create_credential


@admin_bp.route("/agent-access")
@require_auth
def agent_access_page():
    return render_template("admin/agent_access.html")


@admin_api_bp.route("/agent-access", methods=["GET"])
@require_auth
def get_agent_access():
    from services.agent_access import get_policy
    return jsonify(get_policy())


@admin_api_bp.route("/agent-access", methods=["PUT"])
@require_auth
@csrf_for_session_auth
def update_agent_access():
    data = request.get_json(silent=True) or {}
    allowed = {"public_api_enabled", "public_mcp_enabled", "anonymous_enabled"}
    limits = {"requests_per_hour": (1, 100000), "anonymous_requests_per_hour": (1, 10000)}
    if any(key in data and not isinstance(data[key], bool) for key in allowed):
        return jsonify({"error": "enable flags must be booleans"}), 400
    if data.get("public_mcp_enabled") is True:
        from importlib.util import find_spec
        if find_spec("mcp") is None:
            return jsonify({"error": "install the optional agent dependency extra before enabling MCP"}), 409
    if any(key in data and (isinstance(data[key], bool) or not isinstance(data[key], int) or not low <= data[key] <= high) for key, (low, high) in limits.items()):
        return jsonify({"error": "invalid request limit"}), 400
    policy = db.session.get(AgentAccessConfig, 1) or AgentAccessConfig(id=1)
    for key in allowed | set(limits):
        if key in data:
            setattr(policy, key, data[key])
    db.session.add(policy)
    db.session.commit()
    from services.audit import log_admin_action
    log_admin_action("agent_access_policy_update", target_type="agent_access_config", target_id=1, details=data, category="config")
    from services.agent_access import get_policy
    return jsonify(get_policy())


@admin_api_bp.route("/agent-credentials", methods=["GET"])
@require_auth
def list_agent_credentials():
    return jsonify([{"public_id": c.public_id, "label": c.label, "enabled": c.enabled,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "requests_per_hour": c.requests_per_hour, "revoked": c.revoked_at is not None} for c in AgentCredential.query.order_by(AgentCredential.created_at.desc()).all()])


@admin_api_bp.route("/agent-credentials", methods=["POST"])
@require_auth
@csrf_for_session_auth
def create_agent_credential():
    data = request.get_json(silent=True) or {}
    label = str(data.get("label", "")).strip()
    if not label or len(label) > 120:
        return jsonify({"error": "label must be 1–120 characters"}), 400
    hours = data.get("expires_in_days")
    if hours is not None and (not isinstance(hours, int) or not 1 <= hours <= 366):
        return jsonify({"error": "expires_in_days must be between 1 and 366"}), 400
    quota = data.get("requests_per_hour")
    if quota is not None and (not isinstance(quota, int) or not 1 <= quota <= 10000):
        return jsonify({"error": "requests_per_hour must be between 1 and 10000"}), 400
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=hours) if hours else None
    credential, token = create_credential(label, expires_at=expires_at, requests_per_hour=quota)
    from services.audit import log_admin_action
    log_admin_action("agent_credential_create", target_type="agent_credential", target_id=credential.id, details={"label": label}, category="config")
    return jsonify({"public_id": credential.public_id, "label": credential.label, "token": token,
        "created_at": credential.created_at.isoformat(), "expires_at": credential.expires_at.isoformat() if credential.expires_at else None}), 201


@admin_api_bp.route("/agent-credentials/<public_id>", methods=["DELETE"])
@require_auth
@csrf_for_session_auth
def revoke_agent_credential(public_id: str):
    credential = AgentCredential.query.filter_by(public_id=public_id).first_or_404()
    credential.enabled = False
    credential.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    from services.audit import log_admin_action
    log_admin_action("agent_credential_revoke", target_type="agent_credential", target_id=credential.id, details={"public_id": public_id}, category="config")
    return jsonify({"revoked": True, "public_id": public_id})
