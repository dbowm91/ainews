from flask import Response, render_template, request, stream_with_context

from constants import PER_PAGE_ADMIN_SUBSCRIBERS
from routes.admin import admin_bp, require_auth


@admin_bp.route("/subscribers")
@require_auth
def subscribers() -> str:
    from models import Subscriber
    from services.pagination import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    newsletter_type = request.args.get("type", "", type=str).strip()
    active_filter = request.args.get("active", "", type=str).strip()

    q = Subscriber.query.filter(Subscriber.deleted_at.is_(None)).order_by(
        Subscriber.subscribed_at.desc(),
    )
    if newsletter_type:
        q = q.filter_by(newsletter_type=newsletter_type)
    if active_filter == "active":
        q = q.filter_by(active=True)
    elif active_filter == "inactive":
        q = q.filter_by(active=False)

    per_page = PER_PAGE_ADMIN_SUBSCRIBERS
    subs, has_next, next_page = paginate_query(q, page, per_page)

    # Get distinct newsletter types for filter
    types = [
        r[0]
        for r in Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .with_entities(Subscriber.newsletter_type)
        .distinct()
        .all()
    ]

    return render_template(
        "admin/subscribers.html",
        subscribers=subs,
        has_next=has_next,
        next_page=next_page,
        page=page,
        newsletter_type=newsletter_type,
        active_filter=active_filter,
        types=types,
    )


@admin_bp.route("/subscribers/export")
@require_auth
def export_subscribers() -> Response:
    import csv
    import io
    import logging

    from models import Subscriber
    from services.audit import log_admin_action

    logger = logging.getLogger(__name__)

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "newsletter_type", "subscribed_at", "active"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        count = 0
        try:
            query = (
                Subscriber.query.filter(Subscriber.deleted_at.is_(None))
                .order_by(Subscriber.subscribed_at.desc())
                .yield_per(500)
            )
            for sub in query:
                writer.writerow(
                    [
                        sub.email,
                        sub.newsletter_type,
                        sub.subscribed_at.isoformat() if sub.subscribed_at else "",
                        sub.active,
                    ],
                )
                count += 1
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

            try:
                log_admin_action(
                    "subscriber_export",
                    category="subscriber",
                    details={"count": count},
                )
            except Exception:
                logger.warning("Audit logging failed for subscriber_export")
        except Exception as e:
            logger.error("CSV export failed: %s", e)
            yield f"# ERROR: {e}\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscribers.csv"},
    )
