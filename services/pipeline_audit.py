"""Pipeline audit trail: what the pipeline did, stage by stage.

The trend-memory admin page answers "what did the editor agent remember
between runs". This module answers the complementary question: "what did the
pipeline actually do to produce -- or fail to produce -- this article?".

Everything here is read-only. The pipeline's own writes stay in the
``PipelineLog`` and ``PipelineRun`` tables; this module turns those rows
into view models and adds the provenance the pipeline records on the article
row itself (selector verdict, writer model, quality gate, degradations).

The module lives in the services layer: it imports models and the database
extension, never the framework and never an adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select

from extensions import db

#: The canonical order of the pipeline's stages. Used to sort the trail and
#: to label stages the operator has not seen before.
STAGE_SEQUENCE: tuple[str, ...] = (
    "crawl",
    "extract",
    "select",
    "research",
    "write",
    "edit",
)

#: Human labels for the stages that appear in the trail.
STAGE_LABELS: dict[str, str] = {
    "crawl": "crawl",
    "extract": "extract",
    "select": "select",
    "research": "research",
    "write": "write",
    "edit": "edit",
    "selector": "selector",
    "editor": "editor",
    "publish": "publish",
    "newsletter": "newsletter",
}

#: Log levels, ordered by severity.
LEVEL_SEVERITY: tuple[str, ...] = ("info", "warning", "error")

#: How many events a single page of the activity feed shows.
DEFAULT_PAGE_SIZE = 50


def stage_label(stage: str | None) -> str:
    """Return the display label for a stage name."""
    if not stage:
        return "unknown"
    return STAGE_LABELS.get(stage, stage)


def stage_rank(stage: str | None) -> int:
    """Return the canonical sort rank of a stage.

    Unknown stages sort after the known ones, alphabetically, so a newly
    added stage still shows up in a predictable place.
    """
    if stage in STAGE_SEQUENCE:
        return STAGE_SEQUENCE.index(stage)
    return len(STAGE_SEQUENCE)


@dataclass(frozen=True)
class StageEvent:
    """One recorded pipeline event."""

    id: int
    run_id: int | None
    article_id: int | None
    stage: str
    level: str
    status: str | None
    message: str
    error: str | None
    created_at: datetime | None
    duration_ms: int | None

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    @property
    def is_warning(self) -> bool:
        return self.level == "warning"


@dataclass(frozen=True)
class StageSummary:
    """Aggregated activity for one stage."""

    stage: str
    label: str
    total: int
    warnings: int
    errors: int
    last_at: datetime | None


@dataclass(frozen=True)
class ArticleProvenance:
    """Everything the pipeline recorded about one article."""

    article_id: int
    title: str
    source_name: str | None
    pipeline_status: str
    category: str | None
    selector_score: float | None
    selector_reason: str | None
    writer_model: str | None
    impact_score: int
    quality_score: float | None
    quality_passed: bool | None
    quality_needs_review: bool | None
    degradation_count: int
    retry_count: int
    total_retries: int
    extraction_status: str | None
    last_error: str | None
    has_research_brief: bool
    has_draft: bool
    has_final: bool
    version_count: int
    crawled_at: datetime | None
    pipeline_started_at: datetime | None
    selected_at: datetime | None
    published_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class ArticleTrail:
    """The full audit trail of a single article."""

    provenance: ArticleProvenance
    events: tuple[StageEvent, ...] = ()
    stage_summaries: tuple[StageSummary, ...] = ()
    versions: tuple[tuple[int, str | None, datetime | None], ...] = ()


@dataclass(frozen=True)
class EventPage:
    """A page of the pipeline activity feed."""

    events: tuple[StageEvent, ...] = ()
    total: int = 0
    page: int = 1
    per_page: int = DEFAULT_PAGE_SIZE
    has_next: bool = False
    has_prev: bool = False
    summaries: tuple[StageSummary, ...] = field(default=())


@dataclass(frozen=True)
class AuditSummary:
    """A compact view of pipeline activity, for the admin dashboard.

    The full activity feed lives on its own page; the dashboard only needs
    enough to answer "is the pipeline healthy right now, and what is it
    doing" without a second click.
    """

    total_events: int
    error_count: int
    warning_count: int
    articles_touched: int
    recent_events: tuple[StageEvent, ...] = ()
    recent_errors: tuple[StageEvent, ...] = ()
    stage_summaries: tuple[StageSummary, ...] = ()


def _duration_ms(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    """Return the duration between two timestamps in milliseconds.

    Both timestamps come from naive ``db.DateTime`` columns, so they are
    always comparable. A missing endpoint means the duration is unknown.
    """
    if started_at is None or completed_at is None:
        return None
    try:
        delta = completed_at - started_at
    except TypeError:  # pragma: no cover - defensive
        return None
    return int(delta.total_seconds() * 1000)


def _to_event(row) -> StageEvent:  # type: ignore[no-untyped-def]
    """Build a :class:`StageEvent` from a query row."""
    return StageEvent(
        id=int(row.id),
        run_id=int(row.run_id) if row.run_id is not None else None,
        article_id=int(row.article_id) if row.article_id is not None else None,
        stage=row.stage or "unknown",
        level=row.level or "info",
        status=row.status,
        message=row.message or "",
        error=row.error,
        created_at=row.created_at,
        duration_ms=_duration_ms(row.started_at, row.completed_at),
    )


def _selector_fields(selector_result) -> tuple[float | None, str | None]:  # type: ignore[no-untyped-def]
    """Extract the score and reason from a raw ``selector_result`` value."""
    if not isinstance(selector_result, dict):
        return None, None
    score = selector_result.get("score")
    reason = selector_result.get("reason")
    parsed_score: float | None = None
    if score is not None:
        try:
            parsed_score = float(score)
        except (TypeError, ValueError):
            parsed_score = None
    parsed_reason = str(reason) if reason else None
    return parsed_score, parsed_reason


def get_article_trail(article_id: int) -> ArticleTrail | None:
    """Return the full audit trail for one article.

    Returns ``None`` when the article does not exist. The trail is assembled
    from three places: the pipeline log rows recorded against the article,
    the provenance the pipeline wrote onto the article row, and the article
    version history.
    """
    from models import Article, ArticleVersion

    article = db.session.get(Article, article_id)
    if article is None:
        return None

    from models.quality import QualityReport

    quality_row = db.session.execute(
        select(
            QualityReport.overall_score,
            QualityReport.passed,
            QualityReport.needs_review,
        )
        .where(QualityReport.article_id == article_id)
        .order_by(QualityReport.created_at.desc())
        .limit(1)
    ).first()

    version_count = (
        db.session.query(func.count(ArticleVersion.id))
        .filter(ArticleVersion.article_id == article_id)
        .scalar()
        or 0
    )

    version_rows = (
        db.session.query(
            ArticleVersion.version_number,
            ArticleVersion.change_reason,
            ArticleVersion.created_at,
        )
        .filter(ArticleVersion.article_id == article_id)
        .order_by(ArticleVersion.version_number.desc())
        .all()
    )

    source_name = None
    try:
        if article.source is not None:
            source_name = article.source.name
    except Exception:  # noqa: BLE001 - a detached source must not break the trail
        source_name = None

    selector_score, selector_reason = _selector_fields(article.selector_result)

    provenance = ArticleProvenance(
        article_id=int(article.id),
        title=article.original_title or "",
        source_name=source_name,
        pipeline_status=article.pipeline_status or "unknown",
        category=article.category,
        selector_score=selector_score,
        selector_reason=selector_reason,
        writer_model=article.writer_model,
        impact_score=int(article.impact_score or 0),
        quality_score=float(quality_row[0]) if quality_row else None,
        quality_passed=bool(quality_row[1]) if quality_row else None,
        quality_needs_review=bool(quality_row[2]) if quality_row else None,
        degradation_count=int(article.degradation_count or 0),
        retry_count=int(article.retry_count or 0),
        total_retries=int(article.total_retries or 0),
        extraction_status=article.extraction_status,
        last_error=article.last_error,
        has_research_brief=bool(article.research_brief),
        has_draft=bool(article.draft_article),
        has_final=bool(article.final_article),
        version_count=int(version_count),
        crawled_at=article.crawled_at,
        pipeline_started_at=article.pipeline_started_at,
        selected_at=article.selected_at,
        published_at=article.published_at,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )

    from models import PipelineLog

    log_rows = (
        db.session.query(PipelineLog)
        .filter(PipelineLog.article_id == article_id)
        .order_by(PipelineLog.created_at.asc(), PipelineLog.id.asc())
        .all()
    )
    events = tuple(_to_event(row) for row in log_rows)

    return ArticleTrail(
        provenance=provenance,
        events=events,
        stage_summaries=_summarise(events),
        versions=tuple(
            (int(v[0]), v[1], v[2]) for v in version_rows
        ),
    )


def _summarise(events: tuple[StageEvent, ...]) -> tuple[StageSummary, ...]:
    """Aggregate events by stage, in canonical stage order."""
    buckets: dict[str, list[StageEvent]] = {}
    for event in events:
        buckets.setdefault(event.stage, []).append(event)

    summaries: list[StageSummary] = []
    for stage, stage_events in buckets.items():
        summaries.append(
            StageSummary(
                stage=stage,
                label=stage_label(stage),
                total=len(stage_events),
                warnings=sum(1 for e in stage_events if e.is_warning),
                errors=sum(1 for e in stage_events if e.is_error),
                last_at=max(
                    (e.created_at for e in stage_events if e.created_at is not None),
                    default=None,
                ),
            )
        )

    summaries.sort(key=lambda s: (stage_rank(s.stage), s.stage))
    return tuple(summaries)


def list_stage_events(
    *,
    stage: str | None = None,
    level: str | None = None,
    article_id: int | None = None,
    run_id: int | None = None,
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
) -> EventPage:
    """Return a filtered page of the pipeline activity feed.

    The feed is the pipeline's own log, read newest first, with the same
    filters the operator would apply when chasing down a bad run.
    """
    from models import PipelineLog

    page = max(1, page)
    per_page = max(10, min(per_page, 200))

    query = db.session.query(PipelineLog)
    if stage:
        query = query.filter(PipelineLog.stage == stage)
    if level:
        query = query.filter(PipelineLog.level == level)
    if article_id is not None:
        query = query.filter(PipelineLog.article_id == article_id)
    if run_id is not None:
        query = query.filter(PipelineLog.run_id == run_id)

    total = query.count()

    rows = (
        query.order_by(PipelineLog.created_at.desc(), PipelineLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    events = tuple(_to_event(row) for row in rows)

    # The summary strip is computed over the whole filtered set, not over
    # the page, so the counts stay stable while paging.
    all_rows = query.order_by(PipelineLog.created_at.asc(), PipelineLog.id.asc()).all()
    summaries = _summarise(tuple(_to_event(row) for row in all_rows))

    return EventPage(
        events=events,
        total=total,
        page=page,
        per_page=per_page,
        has_next=page * per_page < total,
        has_prev=page > 1,
        summaries=summaries,
    )


def list_known_stages() -> tuple[str, ...]:
    """Return every stage that has ever been recorded.

    Read from the log table rather than from :data:`STAGE_SEQUENCE` so a
    stage added by a newer worker still shows up in the filter.
    """
    from models import PipelineLog

    rows = (
        db.session.query(PipelineLog.stage)
        .distinct()
        .order_by(PipelineLog.stage)
        .all()
    )
    return tuple(str(row[0]) for row in rows if row[0])


def list_operator_actions(
    *,
    page: int = 1,
    per_page: int = 25,
) -> tuple[tuple[object, ...], int]:
    """Return recent admin actions and the total number of them.

    The operator's own actions are part of the audit story: a pipeline that
    keeps failing is one thing, a pipeline that keeps being manually
    nudged is another.
    """
    from models import AuditLog

    page = max(1, page)
    per_page = max(5, min(per_page, 200))

    query = db.session.query(AuditLog).order_by(AuditLog.created_at.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return tuple(rows), total


def dashboard_summary(*, recent: int = 6) -> AuditSummary:
    """Return a compact summary of pipeline activity for the admin dashboard.

    Everything is counted in one pass over the log table rather than with
    separate COUNT queries per severity: the log grows without bound, and a
    dashboard that issues six aggregate queries every three minutes is a
    dashboard that eventually times out.

    The counts are over the whole log. The dashboard is about the state of
    the pipeline, not about a window; the audit page has the filters for
    narrowing down to a time window.
    """
    from models import PipelineLog

    recent = max(1, min(recent, 50))

    rows = (
        db.session.query(
            PipelineLog.id,
            PipelineLog.run_id,
            PipelineLog.article_id,
            PipelineLog.stage,
            PipelineLog.level,
            PipelineLog.status,
            PipelineLog.message,
            PipelineLog.error,
            PipelineLog.created_at,
            PipelineLog.started_at,
            PipelineLog.completed_at,
        )
        .order_by(PipelineLog.created_at.desc(), PipelineLog.id.desc())
        .all()
    )

    events = tuple(_to_event(row) for row in rows)

    error_events = tuple(e for e in events if e.is_error)
    warning_count = sum(1 for e in events if e.is_warning)
    articles_touched = len({e.article_id for e in events if e.article_id is not None})

    return AuditSummary(
        total_events=len(events),
        error_count=len(error_events),
        warning_count=warning_count,
        articles_touched=articles_touched,
        recent_events=events[:recent],
        recent_errors=error_events[:recent],
        stage_summaries=_summarise(events),
    )
