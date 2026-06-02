"""Admin API routes for quality report retrieval and querying."""

from flask import Response, request

from extensions import db
from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response


@admin_api_bp.route("/articles/<int:article_id>/quality", methods=["GET"])
@require_auth
def get_article_quality_report(article_id: int) -> tuple[Response, int] | Response:
    """Get the latest quality report for an article.

    Returns 404 if no quality report exists for the article.
    """
    from models import Article, QualityReport

    article = db.get_or_404(Article, article_id)

    report = (
        QualityReport.query.filter_by(article_id=article_id)
        .order_by(QualityReport.created_at.desc())
        .first()
    )

    if not report:
        return api_response(error="No quality report found for this article", status=404)

    findings_by_severity: dict[str, list[dict]] = {"error": [], "warning": [], "info": []}
    for f in report.findings:
        severity = f.get("severity", "info")
        if severity in findings_by_severity:
            findings_by_severity[severity].append(f)

    return api_response(
        data={
            "id": report.id,
            "article_id": report.article_id,
            "article_version_id": report.article_version_id,
            "stage": report.stage,
            "overall_score": report.overall_score,
            "groundedness": report.groundedness,
            "coherence": report.coherence,
            "completeness": report.completeness,
            "safety": report.safety,
            "citation_score": report.citation_score,
            "claim_score": report.claim_score,
            "passed": report.passed,
            "needs_review": report.needs_review,
            "findings_total": len(report.findings),
            "findings_by_severity": findings_by_severity,
            "meta": report.meta,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        },
    )


@admin_api_bp.route("/quality/recent", methods=["GET"])
@require_auth
def get_recent_quality_reports() -> tuple[Response, int]:
    """Get recent quality reports with optional filtering.

    Query params:
        passed: If "false", return only reports that did not pass quality (default: all)
        needs_review: If "true", return only reports needing review
        limit: Max number of reports to return (default 50, max 200)
    """
    from models import QualityReport

    passed_filter = request.args.get("passed", "", type=str).strip().lower()
    needs_review_filter = request.args.get("needs_review", "", type=str).strip().lower()
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))

    q = QualityReport.query.order_by(QualityReport.created_at.desc())

    if passed_filter == "false":
        q = q.filter_by(passed=False)
    elif passed_filter == "true":
        q = q.filter_by(passed=True)

    if needs_review_filter == "true":
        q = q.filter_by(needs_review=True)

    q = q.limit(limit)

    reports = q.all()

    return api_response(
        data={
            "count": len(reports),
            "reports": [
                {
                    "id": r.id,
                    "article_id": r.article_id,
                    "stage": r.stage,
                    "overall_score": r.overall_score,
                    "citation_score": r.citation_score,
                    "claim_score": r.claim_score,
                    "passed": r.passed,
                    "needs_review": r.needs_review,
                    "findings_count": len(r.findings),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reports
            ],
        },
    )
