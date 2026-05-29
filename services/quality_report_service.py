"""Quality report retrieval service for subagent tools.

Provides read-only access to persisted quality reports for articles.
This is separate from build_quality_report which generates new reports.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Article, QualityReport

logger = logging.getLogger(__name__)


def get_quality_report(article_id: int) -> Optional[dict]:
    """Get the latest quality report for an article.

    Args:
        article_id: The article ID to fetch the report for.

    Returns:
        Dict with report data or None if no report exists.
    """
    try:
        article = db.session.get(Article, article_id)
        if not article:
            return None

        report = (
            QualityReport.query.filter_by(article_id=article_id)
            .order_by(QualityReport.created_at.desc())
            .first()
        )
        if not report:
            return None

        findings_by_severity = {"error": [], "warning": [], "info": []}
        for f in report.findings:
            severity = f.get("severity", "info")
            if severity in findings_by_severity:
                findings_by_severity[severity].append(f)

        return {
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
        }
    except SQLAlchemyError as e:
        logger.error("Error fetching quality report for article %d: %s", article_id, e)
        return None
