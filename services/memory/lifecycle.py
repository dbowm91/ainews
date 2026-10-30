from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from extensions import db
from models import (
    Article,
    MemoryCategorySummary,
    MemoryEvidence,
    MemoryItem,
    MemoryLineage,
    MemoryMaintenanceState,
    MemoryScope,
    TrendMemory,
)
from services.memory.repository import normalize_category


def _fingerprint(owner: str, text: str, article_version: str = "") -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return hashlib.sha256(f"{owner}\0{normalized}".encode()).hexdigest()


def add_observation(
    *,
    owner_category: str,
    text: str,
    importance: int,
    article_id: int | None,
    article_version: str,
    source_url: str | None = None,
    confidence: str | None = "medium",
    valid_as_of: datetime | None = None,
    claim_id: str | None = None,
    decision_reason: str | None = None,
    relation: str = "supports",
    supersedes_claim_id: str | None = None,
) -> MemoryItem | None:
    owner = normalize_category(owner_category)
    signal = " ".join(text.split())[:1200]
    if not signal:
        return None
    fingerprint = _fingerprint(owner, signal, article_version)
    item = db.session.execute(select(MemoryItem).where(MemoryItem.fingerprint == fingerprint)).scalar_one_or_none()
    prior = None
    if relation == "corrects":
        if not supersedes_claim_id:
            return None
        prior = db.session.execute(
            select(MemoryItem)
            .join(MemoryEvidence, MemoryEvidence.memory_id == MemoryItem.id)
            .where(
                MemoryItem.owner_category == owner,
                MemoryItem.id != (item.id if item else -1),
                MemoryEvidence.claim_id == supersedes_claim_id,
                MemoryItem.status.in_(("active", "synthesized")),
            )
            .order_by(MemoryItem.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is None:
            return None
    now = datetime.now(timezone.utc)
    importance = max(1, min(int(importance), 3))
    ttl_days = {1: 7, 2: 30}.get(importance)
    expiry = now + timedelta(days=ttl_days) if ttl_days else None
    from schemas.pipeline import load_pipeline_config

    memory_config = load_pipeline_config().memory
    review = now + timedelta(days={1: 7, 2: 30, 3: memory_config.max_high_age_days}[importance])
    if item is None:
        item = MemoryItem(
            owner_category=owner,
            item_type="observation",
            text=signal,
            importance=importance,
            confidence=confidence,
            valid_as_of=valid_as_of,
            qualifier="Source-backed editorial observation; historical context, not independent verification.",
            status="active",
            review_due_at=review,
            expires_at=expiry,
            first_seen_at=now,
            last_evidence_at=now,
            fingerprint=fingerprint,
            evidence_digest=hashlib.sha256(f"{article_id}:{article_version}".encode()).hexdigest(),
            decision_metadata={
                "policy_version": "editor-memory-candidate-v1",
                "importance_reason": decision_reason or "importance supplied by proposal; confidence is stored separately",
            },
        )
        db.session.add(item)
        db.session.flush()
        db.session.add(MemoryScope(memory_id=item.id, scope_type="category", scope_id=owner))
    if article_id is not None:
        exists = db.session.execute(select(MemoryEvidence.id).where(
            MemoryEvidence.memory_id == item.id,
            MemoryEvidence.source_article_id == article_id,
            MemoryEvidence.source_article_version == article_version,
            MemoryEvidence.claim_id == claim_id,
        ).limit(1)).scalar_one_or_none()
        if not exists:
            db.session.add(MemoryEvidence(
                memory_id=item.id,
                source_article_id=article_id,
                source_article_version=article_version,
                source_url=source_url,
                source_reference=f"article:{article_id}" + (f":claim:{claim_id}" if claim_id else ""),
                claim_id=claim_id,
                evidence_text=signal[:500],
                relation=relation,
                first_seen_at=now,
                last_seen_at=now,
            ))
            item.last_evidence_at = now
    if prior is not None:
        prior.status = "superseded"
        prior.review_status = "superseded"
        prior.review_reason = "corrected_by_source_backed_memory"
        prior.updated_at = now
        db.session.add(MemoryLineage(
            source_memory_id=prior.id,
            target_memory_id=item.id,
            relation="supersedes",
            actor="trend-memory-proposal",
        ))
        projection = db.session.get(MemoryCategorySummary, owner)
        if projection is not None and prior.id in (projection.evidence_ids or []):
            current = db.session.get(MemoryItem, projection.current_memory_id) if projection.current_memory_id else None
            if current is not None and current.status == "active":
                current.status = "superseded"
                current.review_status = "superseded"
                current.review_reason = "underlying_evidence_corrected"
                current.updated_at = now
                for scope_row in db.session.execute(select(MemoryScope).where(
                    MemoryScope.memory_id == current.id,
                    MemoryScope.scope_type == "shared",
                    MemoryScope.scope_id == "global",
                )).scalars().all():
                    db.session.delete(scope_row)
            projection.current_memory_id = None
            projection.content = ""
            projection.evidence_ids = []
            projection.evidence_digest = None
            projection.revision += 1
            projection.updated_at = now
    return item


def has_claim_memory(owner_category: str, claim_id: str) -> bool:
    """Return whether an active source-backed V2 observation has this claim ID."""
    owner = normalize_category(owner_category)
    return db.session.execute(
        select(MemoryItem.id)
        .join(MemoryEvidence, MemoryEvidence.memory_id == MemoryItem.id)
        .where(
            MemoryItem.owner_category == owner,
            MemoryItem.status.in_(("active", "synthesized")),
            MemoryEvidence.claim_id == claim_id,
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def backfill_legacy_memories(*, batch_size: int = 250, dry_run: bool = True, offset: int = 0) -> dict[str, int]:
    """Restartable deterministic importer; never alters or deletes legacy rows."""
    batch_size = max(1, min(int(batch_size), 1000))
    rows = db.session.execute(
        select(TrendMemory).order_by(TrendMemory.id).offset(max(0, offset)).limit(batch_size)
    ).scalars().all()
    imported = 0
    skipped = 0
    seen_items: dict[str, MemoryItem] = {}
    for legacy in rows:
        article = db.session.get(Article, legacy.source_article_id) if legacy.source_article_id else None
        category = normalize_category(article.category if article else legacy.topic)
        fingerprint = _fingerprint(category, legacy.signal)
        item = db.session.execute(select(MemoryItem).where(MemoryItem.fingerprint == fingerprint)).scalar_one_or_none()
        if item is None:
            item = seen_items.get(fingerprint)
        if item is not None:
            skipped += 1
            if not dry_run and legacy.source_article_id:
                evidence_exists = db.session.execute(select(MemoryEvidence.id).where(
                    MemoryEvidence.memory_id == item.id,
                    MemoryEvidence.source_article_id == legacy.source_article_id,
                    MemoryEvidence.source_reference == f"legacy-trend-memory:{legacy.id}",
                ).limit(1)).scalar_one_or_none()
                if not evidence_exists:
                    created_at = legacy.created_at or datetime.now(timezone.utc)
                    db.session.add(MemoryEvidence(
                        memory_id=item.id,
                        source_article_id=legacy.source_article_id,
                        source_reference=f"legacy-trend-memory:{legacy.id}",
                        evidence_text=legacy.signal[:500],
                        relation="supports",
                        first_seen_at=created_at,
                        last_seen_at=created_at,
                    ))
            continue
        if dry_run:
            imported += 1
            continue
        created_at = legacy.created_at or datetime.now(timezone.utc)
        valid_expiry = legacy.expires_at
        if valid_expiry and valid_expiry.tzinfo is None:
            valid_expiry = valid_expiry.replace(tzinfo=timezone.utc)
        item = MemoryItem(
            owner_category=category,
            item_type="observation",
            text=legacy.signal,
            importance=max(1, min(int(legacy.importance), 3)),
            confidence="unknown",
            qualifier=f"Migrated legacy topic {legacy.topic!r}; validity and precision unknown.",
            valid_as_of=article.original_published_at if article else None,
            status="active",
            expires_at=valid_expiry,
            review_due_at=created_at + timedelta(days=90 if legacy.importance == 3 else 30 if legacy.importance == 2 else 7),
            first_seen_at=created_at,
            last_evidence_at=created_at,
            fingerprint=fingerprint,
        )
        db.session.add(item)
        db.session.flush()
        seen_items[fingerprint] = item
        db.session.add(MemoryScope(memory_id=item.id, scope_type="category", scope_id=category))
        if legacy.source_article_id:
            db.session.add(MemoryEvidence(
                memory_id=item.id,
                source_article_id=legacy.source_article_id,
                source_reference=f"legacy-trend-memory:{legacy.id}",
                evidence_text=legacy.signal[:500],
                relation="supports",
                first_seen_at=created_at,
                last_seen_at=created_at,
            ))
        imported += 1
    if not dry_run:
        db.session.commit()
    return {"scanned": len(rows), "imported": imported, "skipped": skipped, "next_offset": max(0, offset) + len(rows)}


def maintain_memory(*, limit: int = 500, dry_run: bool = False) -> dict[str, int]:
    """Deterministic bounded lifecycle pass; it never invokes an LLM."""
    from services.memory.preflight import ensure_memory_schema

    ensure_memory_schema()
    now = datetime.now(timezone.utc)
    limit = max(1, min(int(limit), 5000))
    from schemas.pipeline import load_pipeline_config

    memory_config = load_pipeline_config().memory
    grace_days = memory_config.high_review_grace_days
    fallback_review_date = now - timedelta(days=memory_config.max_high_age_days)
    fallback_retirement_date = fallback_review_date - timedelta(days=grace_days)
    expired = db.session.execute(select(MemoryItem).where(
        MemoryItem.status == "active",
        MemoryItem.is_pinned.is_(False),
        MemoryItem.expires_at.is_not(None),
        MemoryItem.expires_at <= now,
    ).order_by(MemoryItem.expires_at, MemoryItem.id).limit(limit)).scalars().all()
    due_high = db.session.execute(select(MemoryItem.id).where(
        MemoryItem.status == "active",
        MemoryItem.importance == 3,
        or_(
            MemoryItem.review_due_at <= now,
            and_(MemoryItem.review_due_at.is_(None), MemoryItem.created_at <= fallback_review_date),
        ),
    ).order_by(MemoryItem.review_due_at, MemoryItem.id).limit(limit)).scalars().all()
    retirement_cutoff = now - timedelta(days=grace_days)
    retired_high = db.session.execute(select(MemoryItem).where(
        MemoryItem.status == "active",
        MemoryItem.importance == 3,
        MemoryItem.is_pinned.is_(False),
        or_(
            MemoryItem.review_due_at <= retirement_cutoff,
            and_(MemoryItem.review_due_at.is_(None), MemoryItem.created_at <= fallback_retirement_date),
        ),
    ).order_by(MemoryItem.review_due_at, MemoryItem.id).limit(limit)).scalars().all()
    if not dry_run:
        for item in expired:
            item.status = "archived"
            item.review_status = "archived"
            item.review_reason = "retention_expired"
            item.updated_at = now
        for item in retired_high:
            item.status = "archived"
            item.review_status = "overdue_archived"
            item.review_reason = "high_review_grace_elapsed"
            item.review_attempted_at = now
            item.review_count = int(item.review_count or 0) + 1
            item.updated_at = now
        state = db.session.get(MemoryMaintenanceState, 1)
        stats = {
            "archived_expired": len(expired),
            "high_review_due": len(due_high),
            "high_retired": len(retired_high),
            "llm_calls": 0,
        }
        if state is None:
            state = MemoryMaintenanceState(id=1, last_run_at=now, stats=stats)
            db.session.add(state)
        else:
            state.last_run_at = now
            state.stats = stats
        db.session.commit()
    return {
        "archived_expired": len(expired),
        "high_review_due": len(due_high),
        "high_retired": len(retired_high),
        "llm_calls": 0,
    }


def renew_high_memory(memory_id: int, *, reason: str) -> bool:
    """Record an explicit operator review and renew finite HIGH eligibility."""
    item = db.session.get(MemoryItem, memory_id)
    clean_reason = " ".join(reason.split())[:256]
    if item is None or item.importance != 3 or len(clean_reason) < 10:
        return False
    now = datetime.now(timezone.utc)
    from schemas.pipeline import load_pipeline_config

    item.status = "active"
    item.review_status = "renewed"
    item.review_reason = clean_reason
    item.last_reviewed_at = now
    item.review_attempted_at = now
    item.review_due_at = now + timedelta(days=load_pipeline_config().memory.max_high_age_days)
    item.expires_at = None
    item.review_count = int(item.review_count or 0) + 1
    item.updated_at = now
    return True


def promote_shared(memory_id: int, *, approved_by: str) -> bool:
    """Add a single shared reference after provenance has been confirmed."""
    item = db.session.get(MemoryItem, memory_id)
    if item is None or item.status != "active" or not approved_by.strip():
        return False
    evidence_count = db.session.execute(select(MemoryEvidence.id).where(
        MemoryEvidence.memory_id == memory_id,
        MemoryEvidence.source_article_id.is_not(None),
    ).limit(1)).scalar_one_or_none()
    if evidence_count is None or not item.valid_as_of:
        return False
    existing = db.session.execute(select(MemoryScope.id).where(
        MemoryScope.memory_id == memory_id,
        MemoryScope.scope_type == "shared",
        MemoryScope.scope_id == "global",
    ).limit(1)).scalar_one_or_none()
    if existing:
        return True
    db.session.add(MemoryScope(
        memory_id=memory_id,
        scope_type="shared",
        scope_id="global",
        approved_by=approved_by[:128],
    ))
    db.session.commit()
    return True


def demote_shared(memory_id: int) -> bool:
    deleted = db.session.execute(select(MemoryScope).where(
        MemoryScope.memory_id == memory_id,
        MemoryScope.scope_type == "shared",
        MemoryScope.scope_id == "global",
    )).scalars().all()
    for row in deleted:
        db.session.delete(row)
    db.session.commit()
    return bool(deleted)
