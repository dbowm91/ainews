import logging
import redis.exceptions
from flask import render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


@admin_bp.route("/")
@require_auth
def dashboard():
    from models import Article, Source, PipelineRun
    from extensions import db
    from services.llm import get_provider_info

    pipeline_stats = dict(
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all()
    )

    sources = Source.query.all()
    article_counts = dict(
        db.session.query(Article.source_id, func.count(Article.id))
        .group_by(Article.source_id)
        .all()
    )

    recent = (
        Article.query.options(joinedload(Article.source))
        .order_by(Article.created_at.desc())
        .limit(15)
        .all()
    )

    try:
        llm_info = get_provider_info()
    except Exception as e:
        logger.warning("Provider info failed: %s", e)
        llm_info = {"status": "error", "error": str(e)}

    redis_ok = False
    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        redis_ok = True
    except redis.exceptions.RedisError as e:
        logger.warning("Redis ping failed: %s", e)

    # Subscriber stats
    from services.subscribers import get_subscriber_stats

    total_subs, subs_by_type, _ = get_subscriber_stats(db)

    # Recent pipeline runs
    recent_runs = (
        PipelineRun.query.order_by(PipelineRun.started_at.desc()).limit(5).all()
    )

    # Running pipelines
    running_count = PipelineRun.query.filter_by(status="running").count()

    return render_template(
        "admin/dashboard.html",
        pipeline_stats=pipeline_stats,
        sources=sources,
        article_counts=article_counts,
        recent=recent,
        llm_info=llm_info,
        redis_ok=redis_ok,
        total_subs=total_subs,
        subs_by_type=subs_by_type,
        recent_runs=recent_runs,
        running_count=running_count,
    )
