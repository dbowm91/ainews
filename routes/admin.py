from functools import wraps
from datetime import datetime, timezone, timedelta
import logging
import re
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    current_app,
)
from sqlalchemy import func
from extensions import limiter
from constants import (
    PER_PAGE_ADMIN_ARTICLES,
    PER_PAGE_ADMIN_SUBSCRIBERS,
    PER_PAGE_PIPELINE,
    PER_PAGE_NEWSLETTERS,
    PER_PAGE_PIPELINE_LOGS,
)
from services.article import _escape_like_pattern

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _is_password_hash(value: str) -> bool:
    """Check if a value is a Werkzeug password hash (scrypt:... or pbkdf2:...)."""
    return bool(re.match(r"^(scrypt|pbkdf2):", value))


def _verify_password(stored: str, provided: str) -> bool:
    """Verify a password against a stored hash."""
    if not stored:
        return False
    if _is_password_hash(stored):
        from werkzeug.security import check_password_hash

        return check_password_hash(stored, provided)
    logger.error(
        "ADMIN_PASSWORD is not a valid hash. "
        "Run 'python scripts/hash_password.py' and update your .env file."
    )
    return False


def _admin_categories():
    """Get category names from pipeline config, with fallback."""
    try:
        from schemas.topic import load_topics

        return list(load_topics().topics.keys())
    except Exception:
        return ["ai", "privacy", "security", "programming", "hardware"]


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)

    return decorated


# ──────────────────────────────────────────────
#  Auth
# ──────────────────────────────────────────────


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if _verify_password(current_app.config["ADMIN_PASSWORD"], password):
            # Clear session to prevent fixation, then set admin flag
            session.clear()
            session["admin"] = True
            next_url = request.args.get("next", "")
            if (
                not next_url
                or not next_url.startswith("/")
                or next_url.startswith("//")
            ):
                next_url = url_for("admin.dashboard")
            return redirect(next_url)
        error = "Invalid password"
    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    return redirect("/")


# ──────────────────────────────────────────────
#  Dashboard
# ──────────────────────────────────────────────


@admin_bp.route("/")
@require_auth
def dashboard():
    from models import Article, Source, Subscriber, PipelineRun
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

    recent = Article.query.order_by(Article.created_at.desc()).limit(15).all()

    try:
        llm_info = get_provider_info()
    except Exception:
        llm_info = {"status": "error"}

    redis_ok = False
    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        redis_ok = True
    except Exception:
        pass

    # Subscriber stats
    total_subs = Subscriber.query.filter_by(active=True).count()
    subs_by_type = dict(
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter_by(active=True)
        .group_by(Subscriber.newsletter_type)
        .all()
    )

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


# ──────────────────────────────────────────────
#  Pipelines
# ──────────────────────────────────────────────


@admin_bp.route("/pipelines")
@require_auth
def pipelines():
    from models import PipelineRun, PipelineLog
    from extensions import db

    page = max(1, request.args.get("page", 1, type=int))
    run_type = request.args.get("type", "", type=str).strip()

    q = PipelineRun.query.order_by(PipelineRun.started_at.desc())
    if run_type:
        q = q.filter_by(run_type=run_type)
    per_page = PER_PAGE_PIPELINE
    runs = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(runs) > per_page
    if has_next:
        runs = runs[:per_page]

    running = PipelineRun.query.filter_by(status="running").all()

    return render_template(
        "admin/pipelines.html",
        runs=runs,
        running=running,
        has_next=has_next,
        next_page=page + 1,
        run_type=run_type,
    )


@admin_bp.route("/pipelines/<int:run_id>/logs")
@require_auth
def pipeline_logs(run_id):
    from models import PipelineRun, PipelineLog

    run = PipelineRun.query.get_or_404(run_id)
    level = request.args.get("level", "", type=str).strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_PIPELINE_LOGS

    q = PipelineLog.query.filter_by(run_id=run_id).order_by(
        PipelineLog.created_at.asc()
    )
    if level:
        q = q.filter_by(level=level)

    logs = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(logs) > per_page
    if has_next:
        logs = logs[:per_page]

    level_filter = level

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/pipeline_logs.html",
            logs=logs,
            run=run,
            level_filter=level_filter,
            has_next=has_next,
            next_page=page + 1,
        )
    return render_template(
        "admin/pipeline_logs.html",
        logs=logs,
        run=run,
        level_filter=level_filter,
        has_next=has_next,
        next_page=page + 1,
    )


@admin_bp.route("/trigger-crawl", methods=["POST"])
@require_auth
def trigger_crawl():
    from tasks import run_all_sources
    from models import PipelineRun
    from extensions import db

    try:
        run = PipelineRun(
            run_type="crawl",
            status="running",
            triggered_by="manual",
        )
        db.session.add(run)
        db.session.commit()

        result = run_all_sources.delay(run_id=run.id)
        run.task_id = result.id
        db.session.commit()
        return jsonify(
            {"message": "Crawl started", "task_id": result.id, "run_id": run.id}
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger crawl")
        return jsonify({"message": "Failed to start crawl"}), 503


# ──────────────────────────────────────────────
#  Articles Management
# ──────────────────────────────────────────────


@admin_bp.route("/articles")
@require_auth
def articles():
    from models import Article

    page = max(1, request.args.get("page", 1, type=int))
    query = request.args.get("q", "", type=str).strip()
    status = request.args.get("status", "", type=str).strip()
    category = request.args.get("category", "", type=str).strip()

    q = Article.query.order_by(Article.created_at.desc())

    if query:
        escaped_query = _escape_like_pattern(query)
        q = q.filter(Article.original_title.ilike(f"%{escaped_query}%", escape="\\"))
    if status:
        q = q.filter_by(pipeline_status=status)
    if category:
        q = q.filter_by(category=category)

    per_page = PER_PAGE_ADMIN_ARTICLES
    articles = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(articles) > per_page
    if has_next:
        articles = articles[:per_page]

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/articles_table.html",
            articles=articles,
            has_next=has_next,
            next_page=page + 1,
            page=page,
            query=query,
            status=status,
            category=category,
            categories=_admin_categories(),
        )

    categories = _admin_categories()

    return render_template(
        "admin/articles.html",
        articles=articles,
        has_next=has_next,
        next_page=page + 1,
        page=page,
        query=query,
        status=status,
        category=category,
        categories=categories,
    )


@admin_bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@require_auth
def edit_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)

    if request.method == "POST":
        import json
        from constants import (
            VALID_PIPELINE_STATUSES,
            IMPACT_SCORE_MIN,
            IMPACT_SCORE_MAX,
        )

        # Parse final_article JSON and update fields
        fa = {}
        if article.final_article:
            try:
                fa = json.loads(article.final_article)
            except (json.JSONDecodeError, TypeError):
                fa = {}
        original_fa = dict(fa)  # snapshot before overwriting

        fa["headline"] = request.form.get("headline", "").strip()
        fa["tldr"] = request.form.get("tldr", "").strip()
        fa["why_it_matters"] = request.form.get("why_it_matters", "").strip()
        fa["body"] = request.form.get("body", "").strip()
        fa["what_to_watch"] = request.form.get("what_to_watch", "").strip()

        key_points_raw = request.form.get("key_points", "").strip()
        if key_points_raw:
            fa["key_points"] = [
                kp.strip() for kp in key_points_raw.split("\n") if kp.strip()
            ]
        else:
            fa["key_points"] = []

        tags_raw = request.form.get("tags", "").strip()
        if tags_raw:
            fa["tags"] = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
        else:
            fa["tags"] = []

        # Preserve structured fields not editable in the form
        for preserve_key in ("citations", "original_attribution"):
            if original_fa.get(preserve_key):
                fa[preserve_key] = original_fa[preserve_key]

        article.final_article = json.dumps(fa)

        # Create version snapshot before saving
        from services.article import create_article_version

        create_article_version(article, change_reason="admin_edit", changed_by="admin")

        # Validate category
        new_category = request.form.get("category", article.category).strip()
        valid_categories = set(_admin_categories())
        if new_category in valid_categories:
            article.category = new_category

        # Validate pipeline_status
        new_status = request.form.get(
            "pipeline_status", article.pipeline_status
        ).strip()
        if new_status in VALID_PIPELINE_STATUSES:
            article.pipeline_status = new_status

        # Validate impact_score
        impact_raw = request.form.get("impact_score", "")
        if impact_raw.strip():
            try:
                article.impact_score = max(
                    IMPACT_SCORE_MIN, min(IMPACT_SCORE_MAX, int(impact_raw))
                )
            except ValueError:
                pass

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to save article %s", article_id)
            return render_template(
                "admin/article_edit.html",
                article=article,
                fa=fa,
                categories=_admin_categories(),
                error="Failed to save changes. Please try again.",
            ), 500
        return redirect(url_for("admin.articles"))

    # Parse current final_article for form
    import json

    fa = {}
    if article.final_article:
        try:
            fa = json.loads(article.final_article)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template(
        "admin/article_edit.html",
        article=article,
        fa=fa,
        categories=_admin_categories(),
    )


@admin_bp.route("/articles/<int:article_id>/original")
@require_auth
def view_original_article(article_id):
    from models import Article

    article = Article.query.get_or_404(article_id)

    if not article.original_ai_article:
        return jsonify({"message": "No original AI version available"}), 404

    return article.original_ai_article, 200, {"Content-Type": "application/json"}


@admin_bp.route("/articles/<int:article_id>/versions")
@require_auth
def article_versions(article_id):
    from models import Article
    from services.article import get_article_versions, parse_article_json

    article = Article.query.get_or_404(article_id)
    parse_article_json(article)
    versions = get_article_versions(article_id)

    return render_template(
        "admin/article_versions.html",
        article=article,
        versions=versions,
    )


@admin_bp.route(
    "/articles/<int:article_id>/versions/<int:version_id>/rollback", methods=["POST"]
)
@require_auth
def rollback_article(article_id, version_id):
    from models import Article, ArticleVersion
    from extensions import db
    from services.article import create_article_version

    article = Article.query.get_or_404(article_id)
    version = ArticleVersion.query.get_or_404(version_id)

    if version.article_id != article_id:
        return jsonify({"message": "Version does not belong to this article"}), 400

    # Create a version snapshot of current state before rollback
    create_article_version(article, change_reason="pre_rollback", changed_by="admin")

    # Restore from version
    article.final_article = version.final_article
    article.original_ai_article = version.original_ai_article

    # Create version record for the rollback itself
    create_article_version(article, change_reason="rollback", changed_by="admin")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception(
            "Failed to rollback article %s to version %s", article_id, version_id
        )
        return jsonify({"message": "Rollback failed"}), 500

    logger.info(f"Rolled back article {article_id} to version {version.version_number}")
    return redirect(url_for("admin.article_versions", article_id=article_id))


@admin_bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@require_auth
def delete_article(article_id):
    from models import Article, Citation, ArticleMetric, article_tags
    from extensions import db

    article = Article.query.get_or_404(article_id)

    Citation.query.filter_by(article_id=article_id).delete()
    ArticleMetric.query.filter_by(article_id=article_id).delete()
    db.session.execute(
        article_tags.delete().where(article_tags.c.article_id == article_id)
    )
    db.session.delete(article)
    db.session.commit()

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/reprocess", methods=["POST"])
@require_auth
def reprocess_article(article_id):
    from models import Article
    from extensions import db
    from tasks import select_article

    article = Article.query.get_or_404(article_id)
    stage = request.form.get("from_stage", "select")

    if stage == "select":
        article.pipeline_status = "pending"
        article.selector_result = None
        article.research_brief = None
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        select_article.delay(article.id)
    elif stage == "research":
        from tasks import research_article

        article.pipeline_status = "researching"
        article.research_brief = None
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        research_article.delay(article.id)
    elif stage == "write":
        from tasks import write_article

        article.pipeline_status = "writing"
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        write_article.delay(article.id)

    return redirect(url_for("admin.articles"))


# ──────────────────────────────────────────────
#  Metrics
# ──────────────────────────────────────────────


@admin_bp.route("/metrics")
@require_auth
def metrics():
    from models import Article, ArticleMetric, Subscriber
    from extensions import db

    # Date range
    days = request.args.get("days", 30, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total metrics
    totals = (
        db.session.query(
            func.coalesce(func.sum(ArticleMetric.page_loads), 0),
            func.coalesce(func.sum(ArticleMetric.share_button_clicks), 0),
            func.coalesce(func.sum(ArticleMetric.share_link_views), 0),
        )
        .filter(ArticleMetric.updated_at >= cutoff)
        .first()
    )

    # Top articles by page loads
    top_by_views = (
        db.session.query(Article, ArticleMetric.page_loads)
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.page_loads > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.page_loads.desc())
        .limit(10)
        .all()
    )

    # Top articles by share clicks
    top_by_shares = (
        db.session.query(Article, ArticleMetric.share_button_clicks)
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_button_clicks > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_button_clicks.desc())
        .limit(10)
        .all()
    )

    # Top articles by share link views
    top_by_link_views = (
        db.session.query(Article, ArticleMetric.share_link_views)
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_link_views > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_link_views.desc())
        .limit(10)
        .all()
    )

    # Subscriber metrics
    total_subs = Subscriber.query.filter_by(active=True).count()
    subs_by_type = dict(
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter_by(active=True)
        .group_by(Subscriber.newsletter_type)
        .all()
    )
    inactive_subs = Subscriber.query.filter_by(active=False).count()

    return render_template(
        "admin/metrics.html",
        totals=totals,
        top_by_views=top_by_views,
        top_by_shares=top_by_shares,
        top_by_link_views=top_by_link_views,
        days=days,
        total_subs=total_subs,
        subs_by_type=subs_by_type,
        inactive_subs=inactive_subs,
    )


# ──────────────────────────────────────────────
#  Share Config
# ──────────────────────────────────────────────


@admin_bp.route("/shares")
@require_auth
def shares():
    from models import ShareConfig

    configs = ShareConfig.query.order_by(ShareConfig.sort_order).all()
    return render_template("admin/shares.html", configs=configs)


@admin_bp.route("/shares/<int:config_id>/toggle", methods=["POST"])
@require_auth
def toggle_share(config_id):
    from models import ShareConfig
    from extensions import db

    config = ShareConfig.query.get_or_404(config_id)
    config.active = not config.active
    db.session.commit()

    if request.headers.get("HX-Request"):
        return render_template("admin/partials/share_row.html", config=config)
    return redirect(url_for("admin.shares"))


# ──────────────────────────────────────────────
#  Review Queue
# ──────────────────────────────────────────────


@admin_bp.route("/review")
@require_auth
def review_queue():
    from models import Article

    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_ADMIN_ARTICLES

    q = Article.query.filter_by(pipeline_status="review").order_by(
        Article.impact_score.desc()
    )
    articles = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(articles) > per_page
    if has_next:
        articles = articles[:per_page]

    from services.article import parse_articles

    parse_articles(articles)

    total_review = Article.query.filter_by(pipeline_status="review").count()

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/review_table.html",
            articles=articles,
            has_next=has_next,
            next_page=page + 1,
            page=page,
            total_review=total_review,
        )
    return render_template(
        "admin/review.html",
        articles=articles,
        has_next=has_next,
        next_page=page + 1,
        page=page,
        total_review=total_review,
    )


@admin_bp.route("/review/<int:article_id>/approve", methods=["POST"])
@require_auth
def approve_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)
    if article.pipeline_status != "review":
        return jsonify({"message": "Article is not in review"}), 400

    article.pipeline_status = "done"
    article.retry_count = 0
    article.last_error = None
    db.session.commit()

    logger.info(f"Approved article {article_id}: {article.original_title[:50]}")

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))


@admin_bp.route("/review/<int:article_id>/reject", methods=["POST"])
@require_auth
def reject_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)
    if article.pipeline_status != "review":
        return jsonify({"message": "Article is not in review"}), 400

    article.pipeline_status = "skipped"
    db.session.commit()

    logger.info(f"Rejected article {article_id}: {article.original_title[:50]}")

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))


# ──────────────────────────────────────────────
#  Newsletters
# ──────────────────────────────────────────────


@admin_bp.route("/newsletters")
@require_auth
def newsletters():
    from models import Newsletter

    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_NEWSLETTERS
    newsletters = (
        Newsletter.query.order_by(Newsletter.generated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page + 1)
        .all()
    )
    has_next = len(newsletters) > per_page
    if has_next:
        newsletters = newsletters[:per_page]

    return render_template(
        "admin/newsletters.html",
        newsletters=newsletters,
        has_next=has_next,
        next_page=page + 1,
    )


@admin_bp.route("/newsletters/<int:newsletter_id>")
@require_auth
def view_newsletter(newsletter_id):
    from models import Newsletter

    nl = Newsletter.query.get_or_404(newsletter_id)
    return nl.html_content, 200, {"Content-Type": "text/html"}


@admin_bp.route("/newsletters/generate", methods=["POST"])
@require_auth
def trigger_newsletter():
    from tasks.newsletter import generate_daily_newsletters

    try:
        result = generate_daily_newsletters.delay()
        return jsonify(
            {"message": "Newsletter generation started", "task_id": result.id}
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter")
        return jsonify({"message": "Failed to start newsletter generation"}), 503


@admin_bp.route("/newsletters/dry-run", methods=["POST"])
@require_auth
def newsletter_dry_run():
    from tasks.newsletter import generate_daily_newsletters

    test_email = request.form.get("test_email", "").strip()
    if not test_email or "@" not in test_email:
        return jsonify({"message": "Invalid email address"}), 400

    try:
        result = generate_daily_newsletters.delay(dry_run_email=test_email)
        return jsonify(
            {
                "message": f"Dry run started — will send to {test_email}",
                "task_id": result.id,
            }
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter dry run")
        return jsonify({"message": "Failed to start dry run"}), 503


# ──────────────────────────────────────────────
#  Subscribers
# ──────────────────────────────────────────────


@admin_bp.route("/subscribers")
@require_auth
def subscribers():
    from models import Subscriber

    page = max(1, request.args.get("page", 1, type=int))
    newsletter_type = request.args.get("type", "", type=str).strip()
    active_filter = request.args.get("active", "", type=str).strip()

    q = Subscriber.query.order_by(Subscriber.subscribed_at.desc())
    if newsletter_type:
        q = q.filter_by(newsletter_type=newsletter_type)
    if active_filter == "active":
        q = q.filter_by(active=True)
    elif active_filter == "inactive":
        q = q.filter_by(active=False)

    per_page = PER_PAGE_ADMIN_SUBSCRIBERS
    subs = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(subs) > per_page
    if has_next:
        subs = subs[:per_page]

    # Get distinct newsletter types for filter
    types = [
        r[0]
        for r in Subscriber.query.with_entities(Subscriber.newsletter_type)
        .distinct()
        .all()
    ]

    return render_template(
        "admin/subscribers.html",
        subscribers=subs,
        has_next=has_next,
        next_page=page + 1,
        page=page,
        newsletter_type=newsletter_type,
        active_filter=active_filter,
        types=types,
    )


@admin_bp.route("/subscribers/export")
@require_auth
@limiter.limit("5 per hour")
def export_subscribers():
    from models import Subscriber
    import csv
    import io

    subs = Subscriber.query.order_by(Subscriber.subscribed_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "newsletter_type", "subscribed_at", "active"])
    for sub in subs:
        writer.writerow(
            [
                sub.email,
                sub.newsletter_type,
                sub.subscribed_at.isoformat() if sub.subscribed_at else "",
                sub.active,
            ]
        )

    from flask import Response

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=subscribers.csv"},
    )


# ──────────────────────────────────────────────
#  API / Health
# ──────────────────────────────────────────────


@admin_bp.route("/api/health")
@require_auth
def health():
    from extensions import db
    from sqlalchemy import text
    from services.circuit_breaker import get_all_breaker_status

    status = {"flask": "ok", "database": "unknown", "llm": "unknown"}

    try:
        db.session.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception:
        status["database"] = "error"

    try:
        from services.llm import get_provider_info

        status["llm"] = get_provider_info()
    except Exception:
        status["llm"] = "error"

    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "error"

    status["circuit_breakers"] = get_all_breaker_status()

    return jsonify(status)


@admin_bp.route("/api/task/<task_id>")
@require_auth
def task_status(task_id):
    from celery.result import AsyncResult
    from celery_app import celery_app

    task = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "status": task.status,
        "result": None,
    }
    if task.ready():
        response["result"] = task.result
    elif task.info:
        response["result"] = task.info
    return jsonify(response)


@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
def reload_config():
    from services.config_cache import get_config_cache
    from services.llm import clear_provider_cache

    get_config_cache().invalidate_all()
    clear_provider_cache()
    return jsonify({"message": "Config cache cleared"}), 200
