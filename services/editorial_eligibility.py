"""Publication readiness and non-blocking editorial diagnostics."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


POLICY_VERSION = "editorial-diagnostics-v2"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    HOLD = "hold"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class EligibilityVerdict:
    status: EligibilityStatus
    reason_codes: tuple[str, ...]
    diagnostic_codes: tuple[str, ...]
    policy_version: str
    content_digest: str
    evidence_revision: str

    @property
    def eligible(self) -> bool:
        return self.status is EligibilityStatus.ELIGIBLE


def _digest(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def evaluate_article(article: Any) -> EligibilityVerdict:  # noqa: C901
    """Check that a publishable artifact exists and collect editorial diagnostics.

    Evidence, quality, degradation, and originality findings are recorded for
    operators but do not veto publication. Only absent, invalid, or incomplete
    final content remains blocking because there is no usable article to publish.
    """
    from schemas.llm_responses import CondensedArticle

    blocking: list[str] = []
    diagnostics: list[str] = []
    candidate = getattr(article, "final_article", None)
    parsed = None
    if not candidate:
        blocking.append("FINAL_ARTICLE_MISSING")
    else:
        try:
            parsed = CondensedArticle.model_validate_json(candidate)
        except (ValueError, TypeError):
            blocking.append("FINAL_ARTICLE_INVALID")

    if parsed is not None:
        if not parsed.headline.strip() or not parsed.tldr.strip() or not parsed.body.strip():
            blocking.append("FINAL_ARTICLE_INCOMPLETE")

    if int(getattr(article, "degradation_count", 0) or 0) > 0:
        diagnostics.append("PIPELINE_DEGRADED")

    metadata = getattr(article, "raw_metadata", None)
    # Quality and final-audit artifacts are downstream of a valid final
    # article. Research/write holds have not reached those stages yet, so
    # reporting their absence as additional failures obscures the actionable
    # hold reason.
    if parsed is not None:
        audit = metadata.get("editorial_audit") if isinstance(metadata, dict) else None
        audit_passed = isinstance(audit, dict) and audit.get("passed") is True
        if not audit_passed:
            diagnostics.append("FINAL_ARTIFACT_AUDIT_MISSING_OR_FAILED")
        report = _latest_quality_report(article)
        if report is None:
            diagnostics.append("QUALITY_REPORT_MISSING")
        elif not report.passed or report.needs_review:
            diagnostics.append("QUALITY_REPORT_FAILED")
        else:
            expected = report.meta.get("content_digest") if isinstance(report.meta, dict) else None
            if expected != _digest(candidate):
                diagnostics.append("QUALITY_REPORT_STALE")

    evidence_revision = "none"
    dossier_row = getattr(article, "editorial_dossier", None)
    if dossier_row is None:
        diagnostics.append("EVIDENCE_DOSSIER_MISSING")
    else:
        evidence_revision = str(dossier_row.revision)
        if dossier_row.status != "verified":
            diagnostics.append("EVIDENCE_NOT_VERIFIED")
        if not (dossier_row.payload or {}).get("claims"):
            diagnostics.append("CLAIM_LEDGER_MISSING")
        allowed_claim_statuses = {"corroborated", "primary_supported"}
        try:
            from schemas.pipeline import load_pipeline_config

            if load_pipeline_config().evidence.allow_single_source_attributed:
                allowed_claim_statuses.add("single_source_supported")
        except Exception:  # noqa: BLE001 - malformed policy must fail closed
            pass
        if any(
            claim.get("is_material", True)
            and claim.get("status") not in allowed_claim_statuses
            for claim in (dossier_row.payload or {}).get("claims", [])
        ):
            diagnostics.append("MATERIAL_CLAIM_UNVERIFIED")
    if dossier_row is None and isinstance(metadata, dict):
        dossier = metadata.get("editorial_dossier")
        if isinstance(dossier, dict):
            evidence_revision = str(dossier.get("revision") or "none")
            if dossier.get("status") != "verified":
                diagnostics.append("EVIDENCE_NOT_VERIFIED")

    blocking_codes = tuple(dict.fromkeys(blocking))
    diagnostic_codes = tuple(dict.fromkeys(diagnostics))
    verdict_status = EligibilityStatus.HOLD if blocking_codes else EligibilityStatus.ELIGIBLE
    _record_metric(
        verdict_status.value,
        blocking_codes[0] if blocking_codes else (
            diagnostic_codes[0] if diagnostic_codes else "none"
        ),
    )
    return EligibilityVerdict(
        status=verdict_status,
        reason_codes=blocking_codes,
        diagnostic_codes=diagnostic_codes,
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
    metadata["editorial_eligibility"]["diagnostic_codes"] = list(verdict.diagnostic_codes)
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

