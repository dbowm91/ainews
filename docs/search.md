# Search

The platform provides multiple search backends: SQLite FTS5 for full-text search, and a hybrid provider combining FTS with vector similarity.

## Search Providers

| Provider | Type | Description |
|----------|------|-------------|
| `sqlite_fts` | FTS only | SQLite FTS5 with BM25 ranking |
| `hybrid` | FTS + vector | SQLite FTS5 + sentence transformer embeddings (default) |

## SQLite FTS

`SQLiteFTSProvider` (`services/search/sqlite_fts.py`) provides full-text search using SQLite's FTS5 extension.

### Query Construction

FTS queries are constructed in `_build_fts_query()`:
- Exact phrase matches: `"exact phrase"`
- Boolean operators: `term1 AND term2`, `term1 OR term2`
- Negation: `term1 NOT term2`
- Prefix matching: `term*`

### Public Search

Public search at `GET /search` uses `sqlite_fts` provider (not hybrid) and logs queries to `SearchQuery` model for analytics.

### Admin Search

Admin search at `/admin/api/search` uses the configured provider (typically `hybrid`). Supports:
- `q`: query string
- `category`: filter by topic
- `page`, `per_page`: pagination
- `vector_weight`: for hybrid provider (0-1, default 0.5)

## Hybrid Search

`HybridSearchProvider` (`services/search/hybrid.py`) combines FTS5 results with vector similarity using Reciprocal Rank Fusion (RRF).

### Scoring

```python
combined_score = (1 - vector_weight) * fts_rank + vector_weight * vector_score
```

For RRF fusion across multiple result lists:
```python
rrf_score = sum(1.0 / (k + rank) for each source)
```

### Vector Availability

Vector search requires `sentence_transformers` package. If unavailable, falls back to FTS-only search. `SearchPage.vector_available` indicates whether vector search is active.

## Embeddings

### Generation

Embeddings are generated via `services/embeddings.py` using sentence-transformers (`all-MiniLM-L6-v2` by default). The `generate_embedding()` function:

1. Produces a 384-dimension vector per article
2. Embeddings stored as base64-encoded JSON in `article.embedding`
3. Generated on article finalization (within `tasks/edit.py` post-finalize hook)

### Backfill

`backfill_embeddings` Celery task (`tasks/embeddings.py`) generates embeddings for articles missing them:

```bash
# Via API (HMAC-signed)
curl -X POST http://localhost:5000/admin/api/embeddings/backfill \
  -H "X-Task-Signature: ..." \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 50, "delay_seconds": 0.1}'
```

Runs daily at 2 AM via Celery Beat schedule.

## Redis DB Allocation

| DB | Purpose |
|----|---------|
| 0 | Celery broker |
| 1 | Config cache |
| 15 | Flask-Limiter storage |