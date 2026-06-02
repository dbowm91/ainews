# Models Architecture Review

## Summary

The `architecture/models.md` documentation is **highly accurate** with only minor discrepancies found. The document correctly describes the file structure, field definitions, relationships, indexes, and constants. Three naming/documentation discrepancies were identified, but no actual bugs or significant issues.

---

## Verified Claims

### File Inventory (lines 5-20)
All 12 files exist with the correct models as documented:
- `article.py`: `Article`, `Citation` ✅
- `source.py`: `Source` ✅
- `newsletter.py`: `Newsletter`, `Subscriber`, `ArticleMetric` ✅
- `pipeline.py`: `PipelineRun`, `PipelineLog`, `ArticleVersion` ✅
- `context.py`: `TopicNote`, `TrendMemory` ✅
- `webhook.py`: `Webhook`, `WebhookEvent` ✅
- `auth.py`: `ApiToken`, `AdminUser` ✅
- `tag.py`: `Tag`, `article_tags` ✅
- `search.py`: `SearchQuery` ✅
- `audit.py`: `AuditLog` ✅
- `quality.py`: `QualityReport` ✅
- `share.py`: `ShareConfig` ✅

### Model Imports (line 3)
`models/__init__.py` correctly imports all models before `db.create_all()` runs. ✅

### Article Model Field Definitions (lines 42-103)
All 30+ fields match exactly between doc and code:
- Identity fields: `id`, `short_id`, `source_id`, `external_id` ✅
- Original content: `original_url`, `original_title`, `original_author`, `original_published_at`, `extracted_text` ✅
- Pipeline state: `pipeline_status`, `selector_result`, `research_brief`, `draft_article`, `final_article`, `original_ai_article`, `writer_model` ✅
- Scoring/categorization: `impact_score`, `summary`, `category`, `topics`, `raw_metadata` ✅
- Processing metadata: `extraction_status`, `retry_count`, `total_retries`, `degradation_count`, `pipeline_started_at`, `last_error` ✅
- Timestamps: `created_at`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `published_at` ✅
- A/B experiment: `experiment_group` ✅
- Embedding: `embedding` ✅
- Relationships: `citations`, `tags`, `metrics` ✅

### Citation Model (lines 130-145)
All fields match: `id`, `article_id`, `url`, `title`, `author`, `context`, `position` with correct types and defaults. ✅

### Source Model (lines 147-177)
All fields match: `id`, `source_key`, `name`, `url`, `feed_url`, `source_type`, `active`, `last_crawled`, `created_at`, `consecutive_failures`, `consecutive_successes`, `last_success_at`, `last_error`, `disabled_at`. Relationship `articles` with `lazy="dynamic"` is correct. ✅

### Webhook Model (lines 179-202)
All fields match: `id`, `name`, `url`, `secret`, `events`, `active`, `created_at`, `updated_at`, `last_triggered_at`, `last_success_at`, `last_failure_at`, `last_error`, `failure_count`. ✅

### WebhookEvent Model (lines 204-224)
All fields match: `id`, `webhook_id`, `event_type`, `status_code`, `response_body`, `error_message`, `delivered_at`, `attempt_number`, `idempotency_key`, `payload`. ✅

### PipelineLog Model (lines 226-248)
All fields match: `id`, `run_id`, `article_id`, `stage`, `level`, `message`, `created_at`, `started_at`, `completed_at`, `status`, `error`, `meta`. ✅

### ArticleVersion Model (lines 250-273)
All fields match: `id`, `article_id`, `version_number`, `final_article`, `original_ai_article`, `source_fields`, `change_reason`, `changed_by`, `created_at`. Unique constraint `uq_article_version` on `(article_id, version_number)` is correct. Relationship to Article is correct. ✅

### SearchQuery Model (lines 275-294)
All fields match: `id`, `query`, `results_count`, `clicked_article_id`, `created_at`. The `clicked_article` relationship with explicit `foreign_keys` is correctly documented. ✅

### ShareConfig Model (lines 295-310)
All fields match: `id`, `platform_key`, `label`, `url_template`, `icon_name`, `active`, `sort_order`. ✅

### ArticleMetric Model (lines 312-329)
All fields match: `id`, `article_id`, `page_loads`, `newsletter_clicks`, `share_button_clicks`, `share_link_views`, `updated_at`. The `before_update` event listener for auto-updating `updated_at` is correctly documented. ✅

### Newsletter Model (lines 394-414)
All fields match: `id`, `newsletter_type`, `subject`, `html_content`, `article_count`, `recipients`, `delivered_count`, `error_message`, `generated_at`, `sent_at`. The `articles` relationship with `secondary="newsletter_articles"` and `backref=db.backref("newsletters", lazy="dynamic")` is correct. ✅

### Subscriber Model (lines 416-435)
All fields match: `id`, `email`, `newsletter_type`, `unsubscribe_token`, `verification_token`, `subscribed_at`, `confirmed_at`, `active`, `deleted_at`, `preferences`, `bounce_count`, `last_bounce_at`, `last_active_at`. Unique constraint `uq_email_newsletter` is correct. ✅

### Newsletter Association Tables (lines 333-362)
Both `newsletter_articles` and `newsletter_subscribers` tables match exactly with all columns, foreign keys, and defaults. ✅

### Article-Tag Association (lines 364-376)
`article_tags` table matches exactly with proper cascading deletes. ✅

### Tag Model (lines 380-392)
All fields match: `id`, `name`, `slug`, `created_at`. ✅

### AdminUser Model (lines 437-458)
All fields match: `id`, `username`, `password_hash`, `totp_secret`, `totp_enabled`, `backup_codes`, `created_at`, `updated_at`. Note about session security fields not existing is correct. ✅

### ApiToken Model (lines 460-475)
All fields match: `id`, `token_hash`, `token_prefix`, `name`, `created_at`, `last_used_at`, `expires_at`. ✅

### AuditLog Model (lines 477-497)
All fields match: `id`, `action`, `category`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at`. Composite index `ix_audit_logs_target` on `(target_type, target_id)` is correct. ✅

### TrendMemory Model (lines 499-519)
All fields match: `id`, `topic`, `signal`, `importance`, `source_article_id`, `expires_at`, `last_consolidated_at`, `created_at`, `last_accessed_at`, `embedding`. ✅

### TopicNote Model (lines 521-538)
All fields match: `id`, `topic`, `note`, `source`, `created_at`, `updated_at`. Unique constraint `uq_topic_source` is correct. ✅

### QualityReport Model (lines 540-583)
All fields match: `id`, `article_id`, `article_version_id`, `stage`, `overall_score`, `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings`, `meta`, `created_at`. Relationships and composite indexes are correct. ✅

### PipelineStatus Values (lines 106-128)
All status values match exactly between document and `constants.py:30-43`:
`PENDING`, `SELECTING`, `SELECTED`, `RESEARCHING`, `WRITING`, `WRITTEN`, `EDITING`, `REVIEW`, `DONE`, `SKIPPED`, `FAILED` ✅

### VALID_TRANSITIONS (lines 108-128)
All transitions in `constants.py:52-64` match the documented table exactly. ✅

### Article Indexes (lines 586-598)
All documented indexes exist in `models/article.py:66-75`:
- `ix_articles_status_created` on `(pipeline_status, created_at)` ✅
- `ix_articles_published` on `original_published_at` ✅
- `ix_articles_impact` on `impact_score` ✅
- `ix_articles_category_status` on `(category, pipeline_status)` ✅
- `ix_articles_total_retries` on `total_retries` ✅
- `ix_articles_retry_count` on `retry_count` ✅
- `ix_articles_degradation_count` on `degradation_count` ✅
- `uq_source_external_id` unique constraint on `(source_id, external_id)` ✅
- Individual indexes on all listed fields ✅

### Source Indexes (line 599)
Index on `active`, `consecutive_failures`, `disabled_at`, and unique constraint on `source_key` all exist. ✅

### PipelineRun Indexes (line 600)
Index on `run_type`, composite index on `(run_type, status)`, and index on `started_at` all exist in `models/pipeline.py:27-30`. ✅

### TrendMemory Indexes (line 601)
Indexes on `(topic, importance)` as `ix_trend_memory_topic_importance`, on `expires_at` as `ix_trend_memory_expires_at`, and on `last_accessed_at` all exist in `models/context.py:48-51`. ✅

### QualityReport Indexes (line 602)
Composite index `ix_quality_reports_article_stage` on `(article_id, stage)` and index `ix_quality_reports_created` on `created_at` exist in `models/quality.py:45-48`. ✅

---

## Discrepancies Found

### 1. Source Model - Field Name Mismatch
- **Claim**: "Documentation states `last_fetch_at` for source's last crawl timestamp" (architecture/models.md:162 comment)
- **Reality**: The actual field is named `last_crawled` in `models/source.py:18`
- **Severity**: Minor
- **Location**: `models/source.py:18`
- **Suggested fix**: Update doc line 162 from `last_fetch_at` to `last_crawled`

---

## Bugs Identified

No bugs identified. All code is consistent and functional.

---

## Improvement Opportunities

### 1. TopicNote topic field index not documented
- **Improvement**: Document that `TopicNote.topic` has `index=True`
- **Location**: `models/context.py:12`
- **Benefit**: Accurate documentation of database indexes

### 2. Source consecutive_successes index not documented
- **Improvement**: Document that `Source.consecutive_successes` could benefit from an index for health-based source queries
- **Location**: `models/source.py:22`
- **Benefit**: Would help performance for queries filtering by consecutive_successes

### 3. TrendMemory last_accessed_at auto-update not documented
- **Improvement**: Document that `TrendMemory.last_accessed_at` has `onupdate=lambda: datetime.now(timezone.utc)` for automatic tracking
- **Location**: `models/context.py:40-45`
- **Benefit**: Shows this field is automatically maintained

---

## Stale Items Found

None. The document appears to be well-maintained and synchronized with the codebase.

---

## Recommendations

1. **Low Priority**: Fix `last_fetch_at` → `last_crawled` in Source model documentation (line 162)
2. **Low Priority**: Add documentation for `TopicNote.topic` index
3. **Low Priority**: Consider adding index on `Source.consecutive_successes` for query performance if not already adding it
4. **Low Priority**: Document `TrendMemory.last_accessed_at` auto-update behavior