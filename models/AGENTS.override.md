# Models Conventions

Contextual conventions for agents working with `models.py`.

## Database Indexes

- **Missing Indexes Added:** `Webhook.active`, `Source.active`, `Source.source_type`, `Subscriber.newsletter_type`, `PipelineRun.run_type`, composite `(run_type, status)` - all with `index=True` in models.py.
- **Source Health Indexes:** Source class has `index=True` on `consecutive_failures` and `disabled_at` columns. Migration `029_sources_health_indexes.py` creates these indexes for admin health endpoint optimization.