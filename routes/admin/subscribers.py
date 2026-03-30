from flask import render_template, request, Response
from routes.admin import admin_bp, require_auth
from constants import PER_PAGE_ADMIN_SUBSCRIBERS


@admin_bp.route("/subscribers")
@require_auth
def subscribers():
    from models import Subscriber
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    newsletter_type = request.args.get("type", "", type=str).strip()
    active_filter = request.args.get("active", "", type=str).strip()

    q = Subscriber.query.filter(Subscriber.deleted_at.is_(None)).order_by(
        Subscriber.subscribed_at.desc()
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
def export_subscribers():
    from models import Subscriber
    import csv
    import io

    subs = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .order_by(Subscriber.subscribed_at.desc())
        .all()
    )

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

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=subscribers.csv"},
    )
