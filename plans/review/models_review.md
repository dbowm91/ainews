# Models Module Review

Review of `architecture/models.md` against actual implementation in `models/` directory.

---

## Verified Claims

The following claims in the documentation match the implementation:

### File Inventory
All files and models listed in the documentation exist and match:
- `article.py`: Article, Citation
- `source.py`: Source
- `newsletter.py`: Newsletter, Subscriber, ArticleMetric
- `pipeline.py`: PipelineRun, PipelineLog, ArticleVersion
- `context.py`: TopicNote, TrendMemory
- `webhook.py`: Webhook, WebhookEvent
- `auth.py`: ApiToken, AdminUser
- `tag.py`: Tag, article_tags
- `search.py`: SearchQuery
- `audit.py`: AuditLog
- `share.py`: ShareConfig

### Article Model Core Fields
Core fields match documentation: `id`, `short_id`, `source_id`, `external_id`, `original_url`, `original_title`, `original_author`, `original_published_at`, `extracted_text`, `pipeline_status`, `selector_result`, `research_brief`, `draft_article`, `final_article`, `writer_model`, `impact_score`, `summary`, `category`, `topics`, `raw_metadata`, `extraction_status`, `retry_count`, `total_retries`, `degradation_count`, `last_error`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `published_at`, `experiment_group`, `embedding`.

### Source Model Core Fields
Fields match: `id`, `source_key`, `name`, `url`, `feed_url`, `source_type`, `active`, `consecutive_failures`, `consecutive_successes`, `last_crawled`, `last_success_at`, `last_error`, `disabled_at`.

### AdminUser Model
Fields match: `id`, `username`, `password_hash`, `totp_secret`, `totp_enabled`, `backup_codes`, `created_at`, `updated_at`. Note about session hijacking protection in routes/admin/__init__.py is accurate.

### TrendMemory Model
Fields match: `id`, `topic` (String(128)), `signal`, `importance`, `expires_at`, `last_consolidated_at`, `embedding` (Text), `source_article_id` (FK with ondelete="SET NULL"), `created_at`, `last_accessed_at`.

### Relationship Cardinalities
- Article -> Source (many-to-one) via source_id FK
- Article -> Tag (many-to-many via article_tags)
- Article -> Citation (one-to-many)
- Article -> ArticleMetric (one-to-one via unique FK)
- Article -> ArticleVersion (one-to-many)
- PipelineRun -> PipelineLog (one-to-many)
- Newsletter -> Subscriber (many-to-many via newsletter_subscribers)
- Newsletter -> Article (many-to-many via newsletter_articles)

### Indexes Verified
- `uq_source_external_id` unique constraint on Article
- `ix_articles_status_created` on (pipeline_status, created_at)
- `ix_articles_published` on original_published_at
- `ix_pipeline_runs_run_type` on run_type
- `ix_pipeline_runs_run_type_status` on (run_type, status)
- `ix_trend_memory_topic_importance` on (topic, importance)
- `ix_trend_memory_expires_at` on expires_at

---

## Discrepancies

### 1. Article Indexes Documentation Incomplete

**Documentation claims:**
> - ix_articles_impact on impact_score
> - ix_articles_category_status on (category, pipeline_status)
> - ix_articles_total_retries on total_retries
> - ix_articles_retry_count on retry_count
> - ix_articles_degradation_count on degradation_count

**Actual implementation:** All five indexes exist in `__table_args__` (lines 70-74) but are NOT mentioned in the Article model code block or Indexes section of the documentation. The documentation only lists indexes up to `ix_articles_published`.

### 2. Article `pipeline_started_at` Nullability

**Documentation shows:** `pipeline_started_at = Column(DateTime)` (line 82)

**Actual implementation:** `pipeline_started_at = db.Column(db.DateTime, nullable=True)` (line 42)

The documentation should show `nullable=True`.

### 3. TrendMemory `embedding` Nullability

**Documentation shows:** `embedding = Column(Text)` (line 176)

**Actual implementation:** `embedding = db.Column(db.Text, nullable=True)` (line 46)

The documentation should show `nullable=True`.

### 4. TrendMemory `last_accessed_at` Index Not Documented

**Documentation does not mention:** Index on `last_accessed_at`

**Actual implementation:** `last_accessed_at = db.Column(..., index=True)` (line 40-44)

The Indexes section should include: `TrendMemory`: indexes on `(topic, importance)`, `expires_at`, `last_accessed_at`, `source_article_id`

### 5. Source `active` Index Not Documented

**Documentation shows:** `active = Column(Boolean, default=True)` (line 123)

**Actual implementation:** `active = db.Column(db.Boolean, default=True, index=True)` (line 17)

The documentation should indicate `index=True` for the `active` column, and the Indexes section should mention index on `disabled_at` (line 25) and `consecutive_failures` (line 21) which are verified.

### 6. Subscriber Model Underdocumented

**Documentation shows:** Subscriber model not detailed, only listed in table

**Actual implementation:** Subscriber has additional fields not documented:
- `preferences = db.Column(db.JSON, nullable=True, default=dict)` (line 73)
- `bounce_count = db.Column(db.Integer, nullable=False, default=0)` (line 74)
- `last_bounce_at = db.Column(db.DateTime, nullable=True)` (line 75)
- `last_active_at = db.Column(db.DateTime, nullable=True, index=True)` (line 76)
- Unique constraint `uq_email_newsletter` on (email, newsletter_type) (line 79)
- `verification_token` field with unique index (lines 63-68)
- Default unsubscribe_token generation via `secrets.token_urlsafe(32)` (lines 56-62)

### 7. ArticleMetric Unique Constraint Not Documented

**Documentation says:** "ArticleMetric (one-to-one)"

**Actual implementation:** `article_id = db.Column(..., unique=True, ...)` (line 108)

The documentation should note the unique=True constraint on article_id.

### 8. Article `created_at` and `updated_at` Indexes Not Documented

**Documentation shows:**
```python
created_at = Column(DateTime, default=datetime.utcnow, index=True)
updated_at = Column(DateTime, default=datetime.utcnow, index=True)
```

The code shows `index=True` explicitly on both fields (lines 44, 45-49). The documentation text matches but the Indexes section does not call out these specific indexes.

---

## Bugs

No bugs identified. The implementation is internally consistent and functional.

---

## Improvements

### 1. Document All Indexes Completely

The Indexes section for Article should include all indexes:
- Currently documented: `ix_articles_status_created`, `ix_articles_published`, plus individual indexes on various columns
- Missing from doc but present in code: `ix_articles_impact`, `ix_articles_category_status`, `ix_articles_total_retries`, `ix_articles_retry_count`, `ix_articles_degradation_count`

### 2. Add Subscriber Model Detail

The Subscriber model has many fields not documented. Consider adding a code block for Subscriber similar to AdminUser.

### 3. Clarify Pipeline Status Flow

The pipeline status flow diagram and "Actual statuses" list are helpful. Consider adding which statuses represent errors vs. success paths (e.g., `failed`, `skipped`).

### 4. Document ArticleVersion Relationship

The relationship from Article to ArticleVersion via `versions` backref is not documented in the Key Relationships section.

### 5. Add Newsletter Model Detail

Similar to AdminUser section, add a code block for Newsletter showing articles relationship and key fields.

---

## Security Concerns

No security concerns identified. The models correctly use:
- Foreign key `ondelete` specifications for cascade/set null behavior
- Proper indexing on sensitive fields (e.g., unsubscribe_token, verification_token)
- Unique constraints for deduplication
- JSON storage for backup codes (already noted in documentation)
