"""Admin API coverage for the editor memory operator surface."""

from datetime import datetime, timezone
import hashlib
import os
from unittest.mock import patch


def _create_item(app, *, status="active"):
    from extensions import db
    from models import MemoryEvidence, MemoryItem, MemoryScope

    with app.app_context():
        item = MemoryItem(
            owner_category="ai",
            item_type="observation",
            text="AI policy changed after a new regulator announcement.",
            importance=3,
            status=status,
            fingerprint=f"admin-{status}-{datetime.now(timezone.utc).timestamp()}",
        )
        db.session.add(item)
        db.session.flush()
        db.session.add(MemoryScope(memory_id=item.id, scope_type="category", scope_id="ai"))
        db.session.add(MemoryEvidence(
            memory_id=item.id,
            source_reference="fixture:policy-report",
            claim_id="claim-1",
            evidence_text="A regulator announced a policy change.",
            relation="supports",
        ))
        db.session.commit()
        return item.id


def test_memory_detail_requires_auth(client, app):
    item_id = _create_item(app)

    response = client.get(f"/api/v1/memory/items/{item_id}")

    assert response.status_code in (302, 401)


def test_memory_detail_includes_historical_evidence_and_lineage(auth_client, app):
    from extensions import db
    from models import MemoryItem, MemoryLineage

    item_id = _create_item(app, status="archived")
    with app.app_context():
        source = MemoryItem(
            owner_category="ai",
            item_type="observation",
            text="Earlier source observation.",
            importance=2,
            fingerprint="admin-lineage-source",
        )
        db.session.add(source)
        db.session.flush()
        db.session.add(MemoryLineage(
            source_memory_id=source.id,
            target_memory_id=item_id,
            relation="supports",
            actor="test",
        ))
        db.session.commit()

    response = auth_client.get(f"/api/v1/memory/items/{item_id}")

    assert response.status_code == 200
    result = response.get_json()
    assert result["id"] == item_id
    assert result["status"] == "archived"
    assert result["evidence_count"] == 1
    assert result["evidence"][0]["claim_id"] == "claim-1"
    assert result["lineage"]


def test_archive_requires_reason_and_valid_action_is_audited(auth_client, app):
    from extensions import db
    from models import MemoryItem

    item_id = _create_item(app)
    response = auth_client.post(
        f"/api/v1/memory/items/{item_id}/action", json={"action": "archive"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "reason_required"

    with patch("routes.admin.trend_memory.log_admin_action") as audit:
        response = auth_client.post(
            f"/api/v1/memory/items/{item_id}/action",
            json={"action": "archive", "reason": "No longer current after correction."},
        )

    assert response.status_code == 200
    assert response.get_json()["status"] == "archived"
    audit.assert_called_once()
    assert audit.call_args.args[0] == "editor_memory_archive"
    assert audit.call_args.kwargs["details"]["reason"] == "No longer current after correction."
    with app.app_context():
        assert db.session.get(MemoryItem, item_id).status == "archived"


def test_supersede_requires_reason(auth_client, app):
    item_id = _create_item(app)

    response = auth_client.post(
        f"/api/v1/memory/items/{item_id}/action",
        json={"action": "supersede", "reason": "old"},
    )

    assert response.status_code == 400
    assert response.get_json()["minimum_length"] == 10


def test_memory_overview_exposes_bounded_retrieval_metrics(auth_client):
    from services.metrics import get_metrics

    get_metrics().counter_inc("memory.category_hits", labels={"category": "ai", "stage": "edit"})

    response = auth_client.get("/api/v1/memory/overview")

    assert response.status_code == 200
    metrics = response.get_json()["retrieval_metrics"]
    assert metrics["counters"]["memory.category_hits{category=ai,stage=edit}"] >= 1


def test_memory_actions_enforce_csrf_when_enabled(auth_client, app):
    from itsdangerous import URLSafeTimedSerializer

    from extensions import db
    from models import MemoryItem

    item_id = _create_item(app)
    app.config["WTF_CSRF_ENABLED"] = True
    raw = hashlib.sha1(os.urandom(64)).hexdigest()
    signed = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token").dumps(raw)
    with auth_client.session_transaction() as session:
        session["csrf_token"] = raw

    rejected = auth_client.post(
        f"/api/v1/memory/items/{item_id}/action", json={"action": "pin"},
    )
    assert rejected.status_code == 400

    accepted = auth_client.post(
        f"/api/v1/memory/items/{item_id}/action",
        json={"action": "pin"},
        headers={"X-CSRFToken": signed},
    )
    assert accepted.status_code == 200
    with app.app_context():
        assert db.session.get(MemoryItem, item_id).is_pinned is True
