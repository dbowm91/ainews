# Models Conventions

Contextual conventions for agents working with `models.py`.

## Database Indexes

- **Missing Indexes Added:** `Webhook.active`, `Source.active`, `Source.source_type`, `Subscriber.newsletter_type`, `PipelineRun.run_type`, composite `(run_type, status)` - all with `index=True` in models.py.
- **Source Health Indexes:** Source class has `index=True` on `consecutive_failures` and `disabled_at` columns. Migration `029_sources_health_indexes.py` creates these indexes for admin health endpoint optimization.
- **Token Prefix Index:** `ApiToken.token_prefix` is indexed to allow for efficient token lookups without exposing the full token hash in the query.
- **Semantic Search Embeddings:** `Article.embedding` and `TrendMemory.embedding` columns (using pgvector or similar) are implemented to support semantic search and high-performance related content discovery.