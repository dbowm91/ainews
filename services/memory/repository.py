from __future__ import annotations

import re
import math
import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import and_, case, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import MemoryEvidence, MemoryItem, MemoryLineage, MemoryScope

_TOKEN_RE = re.compile(r"[\w-]{2,}", re.UNICODE)
logger = logging.getLogger(__name__)


def normalize_category(category: str | None) -> str:
    """Resolve known category display names to stable topic keys."""
    if not category or not category.strip():
        return "uncategorized"
    from schemas.topic import normalize_topic

    return normalize_topic(unicodedata.normalize("NFKC", category).strip()) or "uncategorized"


def tokenize(text: str) -> list[str]:
    return list(dict.fromkeys(token.casefold() for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", text))[:64]))


def _like_pattern(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _lexical_score(terms: list[str]) -> ColumnElement[int]:
    score: ColumnElement[int] = case(
        (MemoryItem.text.ilike(_like_pattern(terms[0]), escape="\\"), 1), else_=0,
    )
    for token in terms[1:]:
        score = score + case(
            (MemoryItem.text.ilike(_like_pattern(token), escape="\\"), 1), else_=0,
        )
    return score


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    owner_category: str
    item_type: str
    text: str
    importance: int
    status: str
    confidence: str | None
    qualifier: str | None
    valid_as_of: datetime | None
    source_article_ids: tuple[int, ...]
    evidence_count: int
    source_domains: tuple[str, ...]
    shared: bool
    score: float
    score_reasons: tuple[str, ...]


@dataclass(frozen=True)
class MemoryCandidate:
    """A bounded, already scope-filtered retrieval candidate."""

    memory_id: int
    shared: bool
    match_mode: str
    fts_rank: float | None = None


def _candidate_ids(  # noqa: C901 - bounded candidate generation keeps scope and caps auditable
    query: str,
    category_id: str,
    scope: str,
    historical: bool,
    limit: int,
    exclude_article_id: int | None = None,
) -> list[MemoryCandidate]:
    now = datetime.now(timezone.utc)
    from schemas.pipeline import load_pipeline_config

    high_review_cutoff = now - timedelta(
        days=load_pipeline_config().memory.high_review_grace_days
    )
    active_statuses = ("active", "synthesized", "superseded", "archived") if historical else ("active",)
    conditions = [MemoryItem.status.in_(active_statuses)]
    if not historical:
        conditions.append(or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now))
        conditions.append(or_(
            MemoryItem.importance < 3,
            and_(MemoryItem.review_due_at.is_not(None), MemoryItem.review_due_at > high_review_cutoff),
        ))
    query_tokens = tokenize(query)
    shared_ids = select(MemoryScope.memory_id).where(
        MemoryScope.scope_type == "shared", MemoryScope.scope_id == "global"
    )
    # Overfetch globally, then rank by query relevance before applying the
    # caller's top-k. Importance and recency are score features, never a
    # pre-ranking truncation policy.
    candidate_cap = min(500, max(limit * 8, 64))
    fts_matches: dict[int, float] | None = None
    source_exclusion = ""
    if exclude_article_id is not None:
        source_exclusion = (
            " AND NOT EXISTS (SELECT 1 FROM memory_evidence e "
            "WHERE e.memory_id = m.id AND e.source_article_id = :exclude_article_id)"
        )
    if query_tokens:
        quoted_tokens = [f'"{token.replace(chr(34), "")}"' for token in query_tokens[:12]]
        fts_queries = list(dict.fromkeys((" AND ".join(quoted_tokens), " OR ".join(quoted_tokens))))
        try:
            scope_terms: list[str] = []
            params: dict[str, object] = {
                "category": category_id,
                "now": now,
                "high_cutoff": high_review_cutoff,
            }
            if exclude_article_id is not None:
                params["exclude_article_id"] = exclude_article_id
            if scope in ("own", "combined"):
                scope_terms.append("m.owner_category = :category")
            if scope in ("shared", "combined"):
                scope_terms.append(
                    "EXISTS (SELECT 1 FROM memory_scopes s "
                    "WHERE s.memory_id = m.id AND s.scope_type = 'shared' "
                    "AND s.scope_id = 'global')"
                )
            status_clause = "m.status IN ('active')"
            review_clause = " AND (m.importance < 3 OR (m.review_due_at IS NOT NULL AND m.review_due_at > :high_cutoff))"
            if historical:
                status_clause = "m.status IN ('active','synthesized','superseded','archived')"
                review_clause = ""
            expiry_clause = "" if historical else " AND (m.expires_at IS NULL OR m.expires_at > :now)"
            scoped_sql = " OR ".join(scope_terms) or "0"
            ranked_matches: dict[int, float] = {}
            for fts_query in fts_queries:
                remaining = candidate_cap - len(ranked_matches)
                if remaining <= 0:
                    break
                params["query"] = fts_query
                params["limit"] = remaining
                matches = db.session.execute(
                    db.text(
                        "SELECT f.rowid, rank FROM memory_items_fts AS f "
                        "JOIN memory_items AS m ON m.id = f.rowid "
                        "WHERE memory_items_fts MATCH :query "
                        f"AND ({scoped_sql}) AND {status_clause}{expiry_clause}{review_clause} "
                        f"{source_exclusion} ORDER BY rank LIMIT :limit"
                    ),
                    params,
                ).all()
                for value in matches:
                    ranked_matches.setdefault(int(value[0]), float(value[1]))
            fts_matches = ranked_matches
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.info("Memory FTS5 unavailable; using bounded SQLite lexical fallback: %s", type(exc).__name__)

    pairs: list[MemoryCandidate] = []
    excluded_source = None
    if exclude_article_id is not None:
        excluded_source = select(MemoryEvidence.id).where(
            MemoryEvidence.memory_id == MemoryItem.id,
            MemoryEvidence.source_article_id == exclude_article_id,
        ).exists()
    if scope in ("own", "combined"):
        stmt = select(MemoryItem.id).where(MemoryItem.owner_category == category_id, *conditions)
        if excluded_source is not None:
            stmt = stmt.where(~excluded_source)
        if fts_matches is not None:
            stmt = stmt.where(MemoryItem.id.in_(fts_matches))
        elif query_tokens:
            terms = query_tokens[:12]
            stmt = stmt.where(or_(*(MemoryItem.text.ilike(_like_pattern(token), escape="\\") for token in terms)))
            # Bounded SQLite lexical fallback: sort by matching term count,
            # then stable id. Never materialize the full memory corpus.
            stmt = stmt.order_by(_lexical_score(terms).desc(), MemoryItem.id)
        else:
            stmt = stmt.order_by(MemoryItem.id)
        if fts_matches is not None:
            stmt = stmt.order_by(MemoryItem.id)
        scope_cap = candidate_cap if fts_matches is not None or scope == "own" else max(1, candidate_cap // 2)
        for value in db.session.execute(stmt.limit(scope_cap)).scalars().all():
            pairs.append(MemoryCandidate(int(value), False, "fts5" if fts_matches is not None else "lexical", fts_matches.get(int(value)) if fts_matches is not None else None))
    if scope in ("shared", "combined"):
        stmt = select(MemoryItem.id).where(MemoryItem.id.in_(shared_ids), *conditions)
        if excluded_source is not None:
            stmt = stmt.where(~excluded_source)
        if fts_matches is not None:
            stmt = stmt.where(MemoryItem.id.in_(fts_matches))
        elif query_tokens:
            terms = query_tokens[:12]
            stmt = stmt.where(or_(*(MemoryItem.text.ilike(_like_pattern(token), escape="\\") for token in terms)))
            stmt = stmt.order_by(_lexical_score(terms).desc(), MemoryItem.id)
        else:
            stmt = stmt.order_by(MemoryItem.id)
        if fts_matches is not None:
            stmt = stmt.order_by(MemoryItem.id)
        scope_cap = candidate_cap if fts_matches is not None or scope == "shared" else max(1, candidate_cap // 2)
        for value in db.session.execute(stmt.limit(scope_cap)).scalars().all():
            pairs.append(MemoryCandidate(int(value), True, "fts5" if fts_matches is not None else "lexical", fts_matches.get(int(value)) if fts_matches is not None else None))
    # An item can be both category-owned and shared. For its owner, return it
    # once as a local record; other categories receive the shared reference.
    unique: dict[int, MemoryCandidate] = {}
    for candidate in pairs:
        previous = unique.get(candidate.memory_id)
        if previous is None or (previous.shared and not candidate.shared):
            unique[candidate.memory_id] = candidate
    return list(unique.values())


def memory_search(  # noqa: C901 - bounded filtering, ranking and diversity are one auditable pass
    query: str,
    *,
    category_id: str,
    scope: str = "combined",
    limit: int = 8,
    historical: bool = False,
    exclude_article_id: int | None = None,
) -> list[MemoryRecord]:
    if len(query) > 512:
        raise ValueError("query must be at most 512 characters")
    if scope not in {"own", "shared", "combined"}:
        raise ValueError("scope must be own, shared or combined")
    limit = max(0, min(int(limit), 20))
    if limit == 0:
        return []
    if not tokenize(query):
        return []
    category = normalize_category(category_id)
    candidates = _candidate_ids(query, category, scope, historical, max(limit, 1), exclude_article_id)
    candidates.sort(key=lambda candidate: (candidate.fts_rank if candidate.fts_rank is not None else 0.0, candidate.memory_id))
    fts_scores = {
        candidate.memory_id: (len(candidates) - index) / max(len(candidates), 1)
        for index, candidate in enumerate(candidates)
        if candidate.fts_rank is not None
    }
    candidate_by_id = {candidate.memory_id: candidate for candidate in candidates}
    pairs = [(candidate.memory_id, candidate.shared) for candidate in candidates]
    if not pairs:
        return []
    ids = [item_id for item_id, _ in pairs]
    items = db.session.execute(select(MemoryItem).where(MemoryItem.id.in_(ids))).scalars().all()
    shared_by_id = dict(pairs)
    query_tokens = set(tokenize(query))
    now = datetime.now(timezone.utc)
    from schemas.pipeline import load_pipeline_config

    high_review_cutoff = now - timedelta(
        days=load_pipeline_config().memory.high_review_grace_days
    )
    evidence_rows = db.session.execute(
        select(MemoryEvidence.memory_id, MemoryEvidence.source_article_id, MemoryEvidence.source_url).where(
            MemoryEvidence.memory_id.in_(ids), MemoryEvidence.source_article_id.is_not(None)
        ).order_by(MemoryEvidence.id).limit(max(1, len(ids) * 8))
    ).all()
    evidence: dict[int, list[int]] = {}
    domains: dict[int, list[str]] = {}
    for memory_id, article_id, source_url in evidence_rows:
        evidence.setdefault(memory_id, []).append(article_id)
        try:
            host = (urlsplit(source_url).hostname or "").casefold().removeprefix("www.") if source_url else ""
        except ValueError:
            host = ""
        if host:
            domains.setdefault(memory_id, []).append(host)
    by_id = {item.id: item for item in items}
    records: list[MemoryRecord] = []
    for item_id, shared in pairs:
        item = by_id.get(item_id)
        if item is None:
            continue
        expires_at = item.expires_at
        if not historical and expires_at and (expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at) <= now:
            continue
        review_due = item.review_due_at
        if review_due and review_due.tzinfo is None:
            review_due = review_due.replace(tzinfo=timezone.utc)
        if not historical and item.importance == 3 and (review_due is None or review_due <= high_review_cutoff):
            continue
        text_tokens = set(tokenize(item.text))
        overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
        if query_tokens and overlap < 0.15:
            continue
        last_evidence = item.last_evidence_at or item.created_at
        if last_evidence and last_evidence.tzinfo is None:
            last_evidence = last_evidence.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - last_evidence).total_seconds() / 86400) if last_evidence else 3650.0
        freshness = 1 / (1 + age_days / 90)
        confidence_score = {"high": 0.2, "medium": 0.1, "qualified": 0.1, "low": 0.0}.get(item.confidence, 0.0)
        evidence_count = len(evidence.get(item.id, []))
        independent_domains = len(set(domains.get(item.id, [])))
        evidence_score = min(0.3, math.log1p(independent_domains) * 0.1)
        reasons = [
            f"lexical_overlap={overlap:.2f}",
            f"freshness={freshness:.2f}",
            f"evidence_count={evidence_count}",
            f"independent_source_domains={independent_domains}",
            f"importance={item.importance}",
            f"match_mode={candidate_by_id[item_id].match_mode}",
        ]
        if candidate_by_id[item_id].fts_rank is not None:
            reasons.append(f"fts_rank={candidate_by_id[item_id].fts_rank:.6g}")
        if item.valid_as_of:
            reasons.append("valid_as_of_present")
        fts_score = fts_scores.get(item_id, 0.0)
        score = overlap * 4 + freshness * 0.5 + confidence_score + evidence_score + item.importance * 0.1 + fts_score
        records.append(MemoryRecord(
            id=item.id,
            owner_category=item.owner_category,
            item_type=item.item_type,
            text=item.text,
            importance=item.importance,
            status=item.status,
            confidence=item.confidence,
            qualifier=item.qualifier,
            valid_as_of=item.valid_as_of,
            source_article_ids=tuple(dict.fromkeys(evidence.get(item.id, []))),
            evidence_count=evidence_count,
            source_domains=tuple(dict.fromkeys(domains.get(item.id, []))),
            shared=shared,
            score=score,
            score_reasons=tuple(reasons),
        ))
    records.sort(key=lambda record: (-record.score, -record.importance, record.id))
    selected: list[MemoryRecord] = []
    domains_seen: dict[str, int] = {}
    deferred: list[MemoryRecord] = []
    for record in records:
        if record.source_domains and any(domains_seen.get(domain, 0) >= 2 for domain in record.source_domains):
            deferred.append(record)
            continue
        selected.append(record)
        for domain in record.source_domains:
            domains_seen[domain] = domains_seen.get(domain, 0) + 1
        if len(selected) == limit:
            break
    if len(selected) < limit:
        selected.extend(deferred[: limit - len(selected)])
    return selected


def memory_get(
    ids: list[int], *, category_id: str, allow_shared: bool = True, historical: bool = False,
    max_evidence_per_item: int = 20, max_lineage_per_item: int = 20,
) -> list[dict]:
    ids = list(dict.fromkeys(int(value) for value in ids))[:20]
    if not ids:
        return []
    category = normalize_category(category_id)
    shared_ids = set()
    if allow_shared:
        shared_ids = set(db.session.execute(select(MemoryScope.memory_id).where(
            MemoryScope.memory_id.in_(ids), MemoryScope.scope_type == "shared", MemoryScope.scope_id == "global"
        )).scalars().all())
    status_filter = (
        MemoryItem.status.in_(("active", "synthesized", "superseded", "archived"))
        if historical
        else MemoryItem.status == "active"
    )
    items = db.session.execute(select(MemoryItem).where(
        MemoryItem.id.in_(ids),
        status_filter,
        or_(MemoryItem.owner_category == category, MemoryItem.id.in_(shared_ids)),
    )).scalars().all()
    output = []
    now = datetime.now(timezone.utc)
    from schemas.pipeline import load_pipeline_config

    high_review_cutoff = now - timedelta(
        days=load_pipeline_config().memory.high_review_grace_days
    )
    for item in items:
        expires_at = item.expires_at
        if not historical and expires_at and (
            expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
        ) <= now:
            continue
        review_due = item.review_due_at
        if review_due and review_due.tzinfo is None:
            review_due = review_due.replace(tzinfo=timezone.utc)
        if not historical and item.importance == 3 and (review_due is None or review_due <= high_review_cutoff):
            continue
        evidence = db.session.execute(select(MemoryEvidence).where(
            MemoryEvidence.memory_id == item.id
        ).order_by(MemoryEvidence.id).limit(max(0, min(int(max_evidence_per_item), 20)))).scalars().all()
        lineage = db.session.execute(select(MemoryLineage).where(or_(
            MemoryLineage.source_memory_id == item.id, MemoryLineage.target_memory_id == item.id
        )).order_by(MemoryLineage.id).limit(max(0, min(int(max_lineage_per_item), 20)))).scalars().all()
        output.append({
            "id": item.id,
            "owner_category": item.owner_category,
            "item_type": item.item_type,
            "text": item.text[:2000],
            "status": item.status,
            "importance": item.importance,
            "confidence": item.confidence,
            "qualifier": item.qualifier,
            "valid_as_of": item.valid_as_of.isoformat() if item.valid_as_of else None,
            "shared": item.id in shared_ids,
            "evidence": [{"article_id": e.source_article_id, "url": e.source_url, "claim_id": e.claim_id, "relation": e.relation} for e in evidence],
            "lineage": [{"source_id": e.source_memory_id, "target_id": e.target_memory_id, "relation": e.relation} for e in lineage],
        })
    return output
