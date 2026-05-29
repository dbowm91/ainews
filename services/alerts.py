"""Alerting service for deterministic evaluation of system health alerts."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    code: str
    severity: str
    title: str
    message: str
    source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


@dataclass
class AlertThresholds:
    pipeline_backlog: int = 50
    stuck_article_count: int = 10
    source_consecutive_failures: int = 5
    crawl_zero_articles_runs: int = 3
    crawl_zero_articles_hours: float = 24.0
    quality_gate_failure_rate: float = 0.5
    newsletter_delivery_failure_rate: float = 0.1
    estimated_cost_window_hours: float = 1.0
    estimated_cost_threshold: float = 100.0


_DEFAULT_THRESHOLDS = AlertThresholds()


def _check_celery_workers() -> Alert | None:
    try:
        from celery_app import celery_app
        inspector = celery_app.control.inspect()
        ping = inspector.ping()
        if not ping or not any(ping.values()):
            return Alert(
                code="CELERY_NO_WORKERS",
                severity="critical",
                title="No Celery workers available",
                message="Pipeline cannot execute without workers.",
                source="celery",
            )
    except Exception:
        return Alert(
            code="CELERY_CHECK_FAILED",
            severity="critical",
            title="Unable to check Celery workers",
            message="Celery health check raised an exception.",
            source="celery",
        )
    return None


def _check_redis_available() -> Alert | None:
    try:
        from extensions import get_redis
        r = get_redis()
        r.ping()
    except Exception:
        return Alert(
            code="REDIS_UNAVAILABLE",
            severity="critical",
            title="Redis is unavailable",
            message="Rate limiter and cache require Redis.",
            source="redis",
        )
    return None


def _check_circuit_breaker_open(primary_provider: str = "openai") -> Alert | None:
    try:
        from services.circuit_breaker import get_breaker, State
        breaker = get_breaker(primary_provider)
        if breaker.state == State.OPEN:
            return Alert(
                code="CIRCUIT_BREAKER_OPEN",
                severity="critical",
                title=f"Circuit breaker open for {primary_provider}",
                message="LLM calls are being rejected. Check provider status.",
                source="circuit_breaker",
                metadata={"provider": primary_provider},
            )
    except Exception:
        pass
    return None


def _check_pipeline_backlog(thresholds: AlertThresholds = _DEFAULT_THRESHOLDS) -> Alert | None:
    try:
        from models import Article
        pending = Article.query.filter(
            Article.pipeline_status.in_(["pending", "selecting", "selected", "researching", "writing", "editing"])
        ).count()
        if pending > thresholds.pipeline_backlog:
            return Alert(
                code="PIPELINE_BACKLOG",
                severity="warning",
                title=f"Pipeline backlog is high ({pending} articles)",
                message=f"Pending articles ({pending}) exceed threshold ({thresholds.pipeline_backlog}).",
                source="pipeline",
                metadata={"pending_count": pending, "threshold": thresholds.pipeline_backlog},
            )
    except Exception:
        pass
    return None


def _check_stuck_articles(thresholds: AlertThresholds = _DEFAULT_THRESHOLDS) -> Alert | None:
    try:
        from models import Article
        stuck = Article.query.filter(
            Article.pipeline_status.in_(["pending", "selecting", "selected", "researching", "writing", "editing"]),
            Article.retry_count >= 3,
        ).count()
        if stuck > thresholds.stuck_article_count:
            return Alert(
                code="STUCK_ARTICLES",
                severity="warning",
                title=f"Stuck articles detected ({stuck})",
                message=f"Articles with 3+ retries ({stuck}) exceed threshold ({thresholds.stuck_article_count}).",
                source="pipeline",
                metadata={"stuck_count": stuck, "threshold": thresholds.stuck_article_count},
            )
    except Exception:
        pass
    return None


def _check_source_failures(thresholds: AlertThresholds = _DEFAULT_THRESHOLDS) -> Alert | None:
    try:
        from models import Source
        failing = Source.query.filter(
            Source.consecutive_failures >= thresholds.source_consecutive_failures,
            Source.active.is_(True),
        ).count()
        if failing > 0:
            return Alert(
                code="SOURCE_CONSECUTIVE_FAILURES",
                severity="warning",
                title=f"Sources with consecutive failures ({failing})",
                message=f"{failing} source(s) have >= {thresholds.source_consecutive_failures} consecutive failures.",
                source="sources",
                metadata={"failing_sources": failing, "threshold": thresholds.source_consecutive_failures},
            )
    except Exception:
        pass
    return None


def _check_crawl_zero_articles(
    runs: int | None = None,
    hours: float | None = None,
    thresholds: AlertThresholds = _DEFAULT_THRESHOLDS,
) -> Alert | None:
    try:
        from models import PipelineRun
        now = datetime.now(timezone.utc)
        cutoff_hours = hours if hours is not None else thresholds.crawl_zero_articles_hours
        cutoff = now - timedelta(hours=cutoff_hours)
        runs_count = runs if runs is not None else thresholds.crawl_zero_articles_runs
        recent = (
            PipelineRun.query
            .filter(PipelineRun.started_at >= cutoff)
            .filter(PipelineRun.run_type.in_(["crawl", "run-all-sources"]))
            .order_by(PipelineRun.started_at.desc())
            .limit(runs_count)
            .all()
        )
        if len(recent) < runs_count:
            return None
        all_zero = all(r.articles_fetched == 0 for r in recent)
        if all_zero:
            return Alert(
                code="CRAWL_ZERO_ARTICLES",
                severity="warning",
                title="Crawl produced zero new articles",
                message=f"Last {runs_count} crawl runs produced 0 articles over {cutoff_hours}h.",
                source="crawl",
                metadata={"runs_checked": runs_count, "hours": cutoff_hours},
            )
    except Exception:
        pass
    return None


def _check_quality_gate_failures(
    window_hours: float = 1.0,
    threshold: float | None = None,
) -> Alert | None:
    try:
        from models import QualityReport
        threshold_val = threshold if threshold is not None else _DEFAULT_THRESHOLDS.quality_gate_failure_rate
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        total = QualityReport.query.filter(QualityReport.created_at >= cutoff).count()
        if total == 0:
            return None
        failed = QualityReport.query.filter(
            QualityReport.created_at >= cutoff,
            QualityReport.passed.is_(False),
        ).count()
        rate = failed / total
        if rate > threshold_val:
            return Alert(
                code="QUALITY_GATE_FAILURE_RATE",
                severity="warning",
                title=f"Quality gate failure rate high ({rate:.0%})",
                message=f"Failed {failed}/{total} quality reports ({rate:.0%}) exceeds threshold ({threshold_val:.0%}).",
                source="quality",
                metadata={
                    "failed": failed,
                    "total": total,
                    "rate": round(rate, 4),
                    "threshold": threshold_val,
                    "window_hours": window_hours,
                },
            )
    except Exception:
        pass
    return None


def _check_newsletter_delivery_failures(
    window_hours: float = 1.0,
    threshold: float | None = None,
) -> Alert | None:
    try:
        from models import Newsletter
        threshold_val = threshold if threshold is not None else _DEFAULT_THRESHOLDS.newsletter_delivery_failure_rate
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        recent = (
            Newsletter.query
            .filter(Newsletter.generated_at >= cutoff)
            .all()
        )
        if not recent:
            return None
        total = len(recent)
        failed = sum(1 for n in recent if n.error_message is not None)
        if total == 0:
            return None
        rate = failed / total
        if rate > threshold_val:
            return Alert(
                code="NEWSLETTER_DELIVERY_FAILURES",
                severity="warning",
                title=f"Newsletter delivery failure rate high ({rate:.0%})",
                message=f"Failed {failed}/{total} newsletters ({rate:.0%}) exceeds threshold ({threshold_val:.0%}).",
                source="newsletter",
                metadata={
                    "failed": failed,
                    "total": total,
                    "rate": round(rate, 4),
                    "threshold": threshold_val,
                    "window_hours": window_hours,
                },
            )
    except Exception:
        pass
    return None


def _check_estimated_cost(
    window_hours: float | None = None,
    threshold: float | None = None,
) -> Alert | None:
    try:
        threshold_val = threshold if threshold is not None else _DEFAULT_THRESHOLDS.estimated_cost_threshold
        window = window_hours if window_hours is not None else _DEFAULT_THRESHOLDS.estimated_cost_window_hours
        from services.metrics import get_metrics
        metrics = get_metrics()
        all_metrics = metrics.get_metrics()
        cost_key = None
        for key in all_metrics.get("counters", {}):
            if "cost" in key.lower() or "spend" in key.lower():
                cost_key = key
                break
        if cost_key is None:
            return None
        total_cost = all_metrics["counters"].get(cost_key, 0)
        if total_cost > threshold_val:
            return Alert(
                code="ESTIMATED_COST_ABOVE_THRESHOLD",
                severity="info",
                title=f"Estimated cost above threshold (${total_cost:.2f})",
                message=f"Cost ${total_cost:.2f} exceeds threshold ${threshold_val:.2f} in last {window}h window.",
                source="metrics",
                metadata={
                    "cost": total_cost,
                    "threshold": threshold_val,
                    "window_hours": window,
                    "metric_key": cost_key,
                },
            )
    except Exception:
        pass
    return None


def get_active_alerts(
    thresholds: AlertThresholds | None = None,
    include_checks: list[str] | None = None,
) -> list[Alert]:
    """Evaluate all deterministic alert rules and return active alerts.

    Args:
        thresholds: Custom alert thresholds. Uses defaults if None.
        include_checks: Optional list of alert codes to include. If None, evaluates all.

    Returns:
        List of active Alert objects.
    """
    if thresholds is None:
        thresholds = _DEFAULT_THRESHOLDS

    alerts: list[Alert] = []

    checks = [
        ("celery_workers", _check_celery_workers),
        ("redis", _check_redis_available),
        ("circuit_breaker", _check_circuit_breaker_open),
        ("pipeline_backlog", _check_pipeline_backlog),
        ("stuck_articles", _check_stuck_articles),
        ("source_failures", _check_source_failures),
        ("crawl_zero", _check_crawl_zero_articles),
        ("quality_gate", _check_quality_gate_failures),
        ("newsletter_delivery", _check_newsletter_delivery_failures),
        ("cost", _check_estimated_cost),
    ]

    for name, check_fn in checks:
        if include_checks and name not in include_checks:
            continue
        try:
            alert = check_fn(thresholds)
            if alert:
                alerts.append(alert)
        except Exception:
            logger.debug("Alert check %s failed", name, exc_info=True)

    return alerts


def dispatch_alerts(alerts: list[Alert]) -> None:
    """Dispatch alerts to webhook system if any are critical.

    Args:
        alerts: List of active alerts to dispatch.
    """
    if not alerts:
        return
    critical = [a for a in alerts if a.severity == "critical"]
    if not critical:
        return
    try:
        from services.webhooks import trigger_event
        trigger_event(
            "alert.critical",
            {
                "alert_count": len(alerts),
                "critical_count": len(critical),
                "alerts": [a.to_dict() for a in alerts],
            },
            idempotency_key=f"alert-critical:{int(time.time()) // 60}",
        )
    except Exception:
        logger.debug("Failed to dispatch alerts to webhooks", exc_info=True)