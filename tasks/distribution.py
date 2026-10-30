"""Email outbox workers. Every task addresses one durable recipient intent."""
from celery import shared_task


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, max_retries=3)
def deliver_newsletter_intent(self, intent_id: int) -> dict:
    from services.distribution.dispatch import deliver_intent
    state = deliver_intent(int(intent_id))
    return {"intent_id": int(intent_id), "state": state}


@shared_task(bind=True, acks_late=True)
def reconcile_newsletter_deliveries(self) -> dict:
    from services.distribution.dispatch import reconcile_stale_claims
    return {"unknown": reconcile_stale_claims()}
