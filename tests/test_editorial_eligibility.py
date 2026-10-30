"""Regression coverage for the mandatory publication boundary."""

from __future__ import annotations

import hashlib
import json

import pytest

from constants import PipelineStatus
from services import auto_review


class _Query:
    def order_by(self, *_args):
        return self

    def all(self):
        return []


class _Article:
    id = 71
    pipeline_status = PipelineStatus.REVIEW
    final_article = '{"headline":"A","tldr":"B","body":"C"}'
    degradation_count = 0
    raw_metadata = {}
    last_error = None
    quality_reports = _Query()


def test_auto_approve_cannot_publish_without_quality_report(app, monkeypatch):
    calls = []
    monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
    monkeypatch.setattr(auto_review, "_post_finalize", lambda _article: calls.append("post"))

    with app.app_context():
        article = _Article()

        queued = auto_review.route_to_review(article)

        assert queued is True
        assert article.pipeline_status == PipelineStatus.REVIEW
        assert article.raw_metadata["editorial_eligibility"]["status"] == "hold"
        assert "QUALITY_REPORT_MISSING" in article.raw_metadata["editorial_eligibility"]["reason_codes"]
        assert calls == []


def test_degraded_article_is_never_eligible(app):
    from services.editorial_eligibility import evaluate_article

    with app.app_context():
        article = _Article()
        article.degradation_count = 1

        verdict = evaluate_article(article)

        assert verdict.status.value == "hold"
        assert "PIPELINE_DEGRADED" in verdict.reason_codes


@pytest.mark.parametrize(
    "case,expected_reason",
    [
        ("two_independent_reports", None),
        ("primary_document_narrow_claim", None),
        ("single_secondary_report", "MATERIAL_CLAIM_UNVERIFIED"),
        ("three_syndications_one_origin", "MATERIAL_CLAIM_UNVERIFIED"),
        ("disputed_claim", "MATERIAL_CLAIM_UNVERIFIED"),
        ("unverified_claim", "MATERIAL_CLAIM_UNVERIFIED"),
        ("snippet_only", "EVIDENCE_NOT_VERIFIED"),
        ("fabricated_evidence_handle", "MATERIAL_CLAIM_UNVERIFIED"),
        ("research_provider_timeout", "EVIDENCE_NOT_VERIFIED"),
        ("missing_quality_report", "QUALITY_REPORT_MISSING"),
        ("quality_report_failed", "QUALITY_REPORT_FAILED"),
        ("stale_content_revision", "QUALITY_REPORT_STALE"),
        ("degraded_fallback", "PIPELINE_DEGRADED"),
        ("failed_final_audit", "FINAL_ARTIFACT_AUDIT_MISSING_OR_FAILED"),
        ("missing_dossier", "EVIDENCE_DOSSIER_MISSING"),
        ("source_only_fallback", "QUALITY_REPORT_MISSING"),
    ],
)
def test_synthetic_editorial_publication_matrix(app, case, expected_reason):
    """Replay core E06 cases using synthetic metadata and exact artifact digests."""
    from types import SimpleNamespace

    from services.editorial_eligibility import evaluate_article

    final = json.dumps({
        "headline": "Synthetic verified headline",
        "tldr": "A synthetic verified summary.",
        "why_it_matters": "Synthetic context.",
        "body": "The notice states version 3.2 is available.",
        "key_points": ["Version 3.2 is available."],
        "what_to_watch": "The next update is pending.",
        "citations": [{"title": "Notice", "url": "https://example.test/notice"}],
        "original_attribution": {"source": "Test feed", "url": "https://feed.test/lead"},
        "tags": ["ai"],
    })
    digest = hashlib.sha256(final.encode()).hexdigest()
    supported = case in {"two_independent_reports", "primary_document_narrow_claim"}
    status = "verified" if supported else "unverified"
    claim_status = "primary_supported" if case == "primary_document_narrow_claim" else (
        "corroborated" if case == "two_independent_reports" else "single_source"
    )
    claim = {
        "claim": "Version 3.2 is available.",
        "status": claim_status,
        "publish_allowed": supported,
    }
    dossier = SimpleNamespace(
        revision=2,
        status=status,
        payload={"claims": [claim]},
    )
    if case == "missing_dossier":
        dossier = None
    report = SimpleNamespace(
        passed=case != "quality_report_failed",
        needs_review=False,
        meta={"content_digest": "different" if case == "stale_content_revision" else digest},
    )
    if case in {"missing_quality_report", "source_only_fallback"}:
        reports = _Query()
    else:
        reports = SimpleNamespace(order_by=lambda *_: SimpleNamespace(all=lambda: [report]))
    metadata = {"editorial_audit": {"passed": case != "failed_final_audit"}}
    article = SimpleNamespace(
        final_article=final,
        degradation_count=1 if case == "degraded_fallback" else 0,
        quality_reports=reports,
        editorial_dossier=dossier,
        raw_metadata=metadata,
    )

    verdict = evaluate_article(article)

    if expected_reason is None:
        assert verdict.eligible is True
    else:
        assert verdict.eligible is False
        assert expected_reason in verdict.reason_codes
