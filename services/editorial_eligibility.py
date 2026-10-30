"""Single fail-closed publication eligibility policy for editorial artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


POLICY_VERSION = "evidence-first-v1"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    HOLD = "hold"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class EligibilityVerdict:
    status: EligibilityStatus
    reason_codes: tuple[str, ...]
    policy_version: str
    content_digest: str
    evidence_revision: str

    @property
    def eligible(self) -> bool:
        return self.status is EligibilityStatus.ELIGIBLE


def _digest(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def evaluate_article(article: Any) -> EligibilityVerdict:  # noqa: C901
    """Evaluate the exact candidate and latest persisted quality/evidence state.

    This policy intentionally does not infer eligibility from impact, retry
    counts, review configuration, or model-reported confidence.
    """
    from schemas.llm_responses import CondensedArticle

    reasons: list[str] = []
    candidate = getattr(article, "final_article", None)
    try:
        parsed = CondensedArticle.model_validate_json(candidate or "")
    except (ValueError, TypeError):
        parsed = None
        reasons.append("FINAL_ARTICLE_INVALID")

    if parsed is not None:
        if not parsed.headline.strip() or not parsed.tldr.strip() or not parsed.body.strip():
            reasons.append("FINAL_ARTICLE_INCOMPLETE")

    if int(getattr(article, "degradation_count", 0) or 0) > 0:
        reasons.append("PIPELINE_DEGRADED")

    report = _latest_quality_report(article)
    if report is None:
        reasons.append("QUALITY_REPORT_MISSING")
    elif not report.passed or report.needs_review:
        reasons.append("QUALITY_REPORT_FAILED")
    else:
        expected = report.meta.get("content_digest") if isinstance(report.meta, dict) else None
        if expected != _digest(candidate):
            reasons.append("QUALITY_REPORT_STALE")

    evidence_revision = "none"
    dossier_row = getattr(article, "editorial_dossier", None)
    if dossier_row is None:
        reasons.append("EVIDENCE_DOSSIER_MISSING")
    else:
        evidence_revision = str(dossier_row.revision)
        if dossier_row.status != "verified":
            reasons.append("EVIDENCE_NOT_VERIFIED")
        if not (dossier_row.payload or {}).get("claims"):
            reasons.append("CLAIM_LEDGER_MISSING")
        if any(
            claim.get("status") not in {"corroborated", "primary_supported"}
            for claim in (dossier_row.payload or {}).get("claims", [])
        ):
            reasons.append("MATERIAL_CLAIM_UNVERIFIED")
    metadata = getattr(article, "raw_metadata", None)
    if not isinstance(metadata, dict) or not (
        isinstance(metadata.get("editorial_audit"), dict)
        and metadata["editorial_audit"].get("passed") is True
    ):
        reasons.append("FINAL_ARTIFACT_AUDIT_MISSING_OR_FAILED")
    if dossier_row is None and isinstance(metadata, dict):
        dossier = metadata.get("editorial_dossier")
        if isinstance(dossier, dict):
            evidence_revision = str(dossier.get("revision") or "none")
            if dossier.get("status") != "verified":
                reasons.append("EVIDENCE_NOT_VERIFIED")

    verdict_status = EligibilityStatus.HOLD if reasons else EligibilityStatus.ELIGIBLE
    _record_metric(verdict_status.value, reasons[0] if reasons else "none")
    return EligibilityVerdict(
        status=verdict_status,
        reason_codes=tuple(dict.fromkeys(reasons)),
        policy_version=POLICY_VERSION,
        content_digest=_digest(candidate),
        evidence_revision=evidence_revision,
    )


def _record_metric(status: str, reason: str) -> None:
    """Record bounded outcome labels without article or source identifiers."""
    try:
        from services.metrics import get_metrics

        get_metrics().counter_inc(
            "editorial.eligibility",
            labels={"status": status, "reason": reason},
        )
    except Exception:  # noqa: BLE001 - metrics must never affect publication policy
        pass


def record_verdict(article: Any, verdict: EligibilityVerdict) -> None:
    metadata = getattr(article, "raw_metadata", None)
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata["editorial_eligibility"] = asdict(verdict)
    metadata["editorial_eligibility"]["status"] = verdict.status.value
    metadata["editorial_eligibility"]["reason_codes"] = list(verdict.reason_codes)
    article.raw_metadata = metadata


def _latest_quality_report(article: Any) -> Any | None:
    """Return latest quality report, matching its version to current content."""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        reports = article.quality_reports.order_by("created_at").all()
    except (AttributeError, TypeError, SQLAlchemyError):
        return None
    return reports[-1] if reports else None


def require_eligible(article: Any) -> EligibilityVerdict:
    verdict = evaluate_article(article)
    record_verdict(article, verdict)
    return verdict

