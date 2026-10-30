"""Email outbox workers. Every task addresses one durable recipient intent."""
from celery import shared_task


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, max_retries=3)
def deliver_newsletter_intent(self, intent_id: int) -> dict:
    from services.distribution.dispatch import deliver_intent
    state = deliver_intent(int(intent_id))
    return {"intent_id": int(intent_id), "state": state}


@shared_task(bind=True, acks_late=True)
def reconcile_newsletter_deliveries(self) -> dict:
    from services.distribution.dispatch import reconcile_requested_editions, reconcile_stale_claims
    from extensions import db
    from models import DeliveryIntent
    from sqlalchemy import select
    planned = reconcile_requested_editions()
    intent_ids = db.session.scalars(select(DeliveryIntent.id).where(DeliveryIntent.state == "pending").order_by(DeliveryIntent.id).limit(5000)).all()
    for intent_id in intent_ids:
        deliver_newsletter_intent.apply_async(args=[intent_id])
    return {"planned": planned, "dispatched": len(intent_ids), "unknown": reconcile_stale_claims()}
