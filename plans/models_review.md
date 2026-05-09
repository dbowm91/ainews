# Models Architecture Review Plan

## Verified Claims
- Article model has `pipeline_status` field (line 25 in article.py)
- Article model has `published_at` field (line 54 in article.py)
- Article model does NOT have `finalized_at` field
- Source model uses `source_type` (line 14 in source.py)
- Source model uses `last_crawled` (line 16 in source.py), NOT `last_fetch_at`
- TrendMemory uses `signal` (line 32 in context.py), NOT `observation`
- TrendMemory `embedding` is `db.Text` (line 40 in context.py), not a vector type
- AdminUser has `totp_secret`, `backup_codes`, `totp_enabled` fields (lines 37-39 in auth.py)
- AdminUser backup_codes stored as JSON array (line 39 in auth.py)
- Newsletter has many-to-many with Article via `newsletter_articles` association table (lines 8-14 in newsletter.py)
- Newsletter has many-to-many with Subscriber via `newsletter_subscribers` association table (lines 16-23 in newsletter.py)
- Article has many-to-many with Tag via `article_tags` table (line 7 in article.py references tag.py line 6)
- PipelineLog uses `meta` field, not `metadata` (line 57 in pipeline.py)
- All models in `models/__init__.py` are properly exported
- Adapters correctly import from `utils/url.py` (rss.py:12, api.py:11, web.py:15) - clean layering verified

## Discrepancies

### 1. Source Model Missing `adapter_config`
**Architecture doc states**: Source model has `adapter_config = Column(JSON)` for source-specific adapter settings (line 91 in models.md)

**Actual code**: `Source` model (source.py) does NOT have an `adapter_config` field. The model only has: id, source_key, name, url, feed_url, source_type, active, last_crawled, created_at, consecutive_failures, consecutive_successes, last_success_at, last_error, disabled_at, and the articles relationship.

This is a documented-but-never-implemented field noted in AGENTS.md.

### 2. TrendMemory GIN Index on Embedding
**Architecture doc states**: "TrendMemory: topic (GIN index on embedding for vector search)" (line 142 in models.md)

**Actual code**: The `TrendMemory` model has a regular index on `topic` and `importance` (line 43), and on `expires_at` (line 44). There is NO GIN index on the `embedding` column. The embedding is stored as plain `db.Text`, and no vector index exists.

### 3. AdminUser Session Security Not Implemented
**Architecture doc states**: "Note: ip_binding and user_agent_hash not implemented" (line 111 in models.md)

**Actual code**: The AdminUser model does not have `ip_binding` or `user_agent_hash` fields. The model only has: id, username, password_hash, totp_secret, totp_enabled, backup_codes, created_at, updated_at.

### 4. Article Model Additional Fields Not Documented
**Architecture doc shows**: id, title, url, source_id, content, summary, pipeline_status, impact_score, published_at, created_at (lines 44-61 in models.md)

**Actual code**: The Article model has many additional fields not shown in the architecture diagram:
- short_id, external_id, original_url, original_title, original_author, original_published_at
- extracted_text, selector_result, research_brief, draft_article, final_article, original_ai_article
- writer_model, category, topics, raw_metadata, extraction_status, retry_count, total_retries, degradation_count
- pipeline_started_at, last_error, updated_at, scheduled_publish_at, crawled_at, selected_at
- experiment_group, embedding, metrics relationship, citations relationship, tags relationship

### 5. Pipeline Status Values Don't Match Documentation
**Architecture doc states**: "pending, select, research, write, edit, review, done" (line 55 in models.md)

**Actual code**: The architecture doc shows a flow "pending → select → research → writing → editing → done" with "review" as an alternative path (lines 63-69). However, the actual status values used in the codebase (as noted in AGENTS.md) are: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`. The document shows simplified names without "-ing" suffixes.

## Improvement Recommendations

1. [HIGH] **Source Model**: Either implement `adapter_config` field or remove from architecture documentation. If adapter-specific configuration is needed, it should be added as a JSON column.

2. [HIGH] **TrendMemory Vector Search**: Either implement GIN index on embedding for vector search capabilities, or update the architecture to remove this claim. Currently the embedding is just stored as text with no vector index.

3. [MEDIUM] **AdminUser Session Binding**: If IP/user-agent binding is needed for security, implement it. Otherwise remove the "not implemented" note from documentation since it implies it should exist.

4. [MEDIUM] **Article Model Documentation**: The Article model is the central entity but the architecture doc only shows a subset of fields. Consider documenting the full field set or noting that additional fields exist for internal processing.

5. [MEDIUM] **Pipeline Status Documentation**: Update the status values to match actual implementation: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`.

6. [LOW] **Architecture Consistency**: Consider adding a note about which fields are intended for external API exposure vs. internal processing.

## Bugs Found

1. **No bugs found** - The models compile and work as implemented. Discrepancies are documentation vs. implementation issues, not code bugs.

## Layer Violations

1. **None found** - Verified that adapters (rss.py, api.py, web.py) correctly import from `utils/url.py` rather than `services/url.py`, maintaining clean layering as documented.

2. **Duplicate URL implementations**: Both `services/url.py` and `utils/url.py` contain similar URL validation and DNS resolution logic. This is noted in AGENTS.md that `services/url.py` has "duplicate implementations". While not a layering violation per se, it creates maintenance burden. Services should use `utils/url.py` functions and not duplicate the logic.

## Summary

The models are generally well-structured and match the architecture document for the core fields. The main issues are:
- Missing `adapter_config` on Source (documented but never implemented)
- Missing GIN index on TrendMemory.embedding for vector search
- Incomplete documentation of Article model fields
- Pipeline status names in docs don't match actual values used
- Duplicate URL utilities between services and utils

The clean layering is maintained - adapters import from utils, not services.
