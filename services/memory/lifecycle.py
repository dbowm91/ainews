from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from extensions import db
from models import Article, MemoryEvidence, MemoryItem, MemoryMaintenanceState, MemoryScope, TrendMemory
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
) -> MemoryItem | None:
    owner = normalize_category(owner_category)
    signal = " ".join(text.split())[:1200]
    if not signal:
        return None
    fingerprint = _fingerprint(owner, signal, article_version)
    item = db.session.execute(select(MemoryItem).where(MemoryItem.fingerprint == fingerprint)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    importance = max(1, min(int(importance), 3))
    ttl_days = {1: 7, 2: 30}.get(importance)
    expiry = now + timedelta(days=ttl_days) if ttl_days else None
    review = now + timedelta(days={1: 7, 2: 30, 3: 90}[importance])
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
        )
        db.session.add(item)
        db.session.flush()
        db.session.add(MemoryScope(memory_id=item.id, scope_type="category", scope_id=owner))
    if article_id is not None:
        exists = db.session.execute(select(MemoryEvidence.id).where(
            MemoryEvidence.memory_id == item.id,
            MemoryEvidence.source_article_id == article_id,
            MemoryEvidence.source_article_version == article_version,
        ).limit(1)).scalar_one_or_none()
        if not exists:
            db.session.add(MemoryEvidence(
                memory_id=item.id,
                source_article_id=article_id,
                source_article_version=article_version,
                source_url=source_url,
                source_reference=f"article:{article_id}",
                evidence_text=signal[:500],
                relation="supports",
                first_seen_at=now,
                last_seen_at=now,
            ))
            item.last_evidence_at = now
    return item


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
    now = datetime.now(timezone.utc)
    limit = max(1, min(int(limit), 5000))
    expired = db.session.execute(select(MemoryItem).where(
        MemoryItem.status == "active",
        MemoryItem.is_pinned.is_(False),
        MemoryItem.expires_at.is_not(None),
        MemoryItem.expires_at <= now,
    ).order_by(MemoryItem.expires_at, MemoryItem.id).limit(limit)).scalars().all()
    due_high = db.session.execute(select(MemoryItem.id).where(
        MemoryItem.status == "active",
        MemoryItem.importance == 3,
        MemoryItem.review_due_at.is_not(None),
        MemoryItem.review_due_at <= now,
    ).order_by(MemoryItem.review_due_at, MemoryItem.id).limit(limit)).scalars().all()
    if not dry_run:
        for item in expired:
            item.status = "archived"
            item.updated_at = now
        state = db.session.get(MemoryMaintenanceState, 1)
        stats = {"archived_expired": len(expired), "high_review_due": len(due_high), "llm_calls": 0}
        if state is None:
            state = MemoryMaintenanceState(id=1, last_run_at=now, stats=stats)
            db.session.add(state)
        else:
            state.last_run_at = now
            state.stats = stats
        db.session.commit()
    return {"archived_expired": len(expired), "high_review_due": len(due_high), "llm_calls": 0}


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
