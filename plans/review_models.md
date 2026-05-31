# Review: architecture/models.md

**Reviewed:** 2026-05-31
**Source:** `architecture/models.md`
**Reviewer:** Subagent 1 (Data Layer)
**Status:** COMPLETE

---

## Verified Claims

### File Inventory (Lines 7-21)
- All 12 model files exist in `models/`: `article.py`, `source.py`, `newsletter.py`, `pipeline.py`, `context.py`, `webhook.py`, `auth.py`, `tag.py`, `search.py`, `audit.py`, `quality.py`, `share.py`
- `utils.py` exists (not listed in doc, acceptable omission — utility functions, not models)
- All model classes exist with correct names: Article, Citation, Source, Newsletter, Subscriber, ArticleMetric, PipelineRun, PipelineLog, ArticleVersion, TopicNote, TrendMemory, Webhook, WebhookEvent, ApiToken, AdminUser, Tag, SearchQuery, AuditLog, QualityReport, ShareConfig

### Article Model (Lines 41-104)
- `pipeline_status` default="pending" — VERIFIED (`models/article.py:25`)
- All 30+ fields verified: id, short_id, source_id, external_id, original_url, original_title, original_author, original_published_at, extracted_text, pipeline_status, selector_result, research_brief, draft_article, final_article, original_ai_article, writer_model, impact_score, summary, category, topics, raw_metadata, extraction_status, retry_count, total_retries, degradation_count, pipeline_started_at, last_error, created_at, updated_at, scheduled_publish_at, crawled_at, selected_at, published_at, experiment_group, embedding
- All index definitions match (`models/article.py:66-75`)
- `__table_args__` unique constraint `uq_source_external_id` on `(source_id, external_id)` — VERIFIED

### Source Model (Lines 130-160)
- `source_type` (not `type`) — VERIFIED (`models/source.py:16`)
- `last_crawled` (not `last_fetch_at`) — VERIFIED (`models/source.py:18`)
- All fields match: id, source_key, name, url, feed_url, source_type, active, last_crawled, created_at, consecutive_failures, consecutive_successes, last_success_at, last_error, disabled_at
- Indexes on `consecutive_failures` and `disabled_at` — VERIFIED (`models/source.py:21,25`)

### TrendMemory Model (Lines 387-407)
- `signal` (not `observation`) — VERIFIED (`models/context.py:32`)
- `embedding` as `db.Text` (not vector type) — VERIFIED (`models/context.py:46`)
- `topic` is `String(128)` — VERIFIED (`models/context.py:31`)

### AdminUser Model (Lines 364-385)
- `backup_codes` as JSON — VERIFIED (`models/auth.py:39`)
- No `ip_binding`/`user_agent_hash` fields — VERIFIED (only id, username, password_hash, totp_secret, totp_enabled, backup_codes, created_at, updated_at)

### Newsletter Association Tables (Lines 274-303)
- `newsletter_articles` table with correct columns (newsletter_id, article_id, position, created_at) — VERIFIED (`models/newsletter.py:8-14`)
- `newsletter_subscribers` table with correct columns (newsletter_id, subscriber_id, sent_at, opened_at, clicked_at) — VERIFIED (`models/newsletter.py:16-23`)

### Article-Tag Association (Lines 305-317)
- `article_tags` table with correct columns and indexes — VERIFIED (`models/tag.py:6-21`)
- `Tag` model has `slug` field — VERIFIED (`models/tag.py:29`)

### QualityReport Model (Lines 429-469)
- All fields match: id, article_id, article_version_id, stage, overall_score, groundedness, coherence, completeness, safety, citation_score, claim_score, passed, needs_review, findings, meta, created_at
- Composite indexes `ix_quality_reports_article_stage` and `ix_quality_reports_created` — VERIFIED (`models/quality.py:45-47`)
- Relationships with correct cascade — VERIFIED (`models/quality.py:36-42`)

### PipelineStatus Enum (Lines 106-128)
- All 11 statuses exist in `constants.py:30-43`: PENDING, SELECTING, SELECTED, RESEARCHING, WRITING, WRITTEN, EDITING, REVIEW, DONE, SKIPPED, FAILED
- `VALID_TRANSITIONS` map in `constants.py:52-64` matches documented transitions

### Key Relationships (Lines 22-39)
- Article→Source many-to-one via source_id — VERIFIED
- Article→Tag many-to-many via article_tags — VERIFIED
- Article→Citation one-to-many — VERIFIED
- Article→ArticleMetric one-to-one — VERIFIED
- Article→ArticleVersion one-to-many (via backref in pipeline.py:81-83) — VERIFIED
- PipelineRun→PipelineLog one-to-many — VERIFIED
- Newsletter→Subscriber many-to-many via newsletter_subscribers — VERIFIED
- Newsletter→Article many-to-many via newsletter_articles — VERIFIED
- Article has `newsletters` dynamic backref — VERIFIED (`models/newsletter.py:43`)

### PipelineLog Model (Lines 209-231)
- All fields match: id, run_id, article_id, stage, level, message, created_at, started_at, completed_at, status, error, meta — VERIFIED

### SearchQuery Model (Lines 233-249)
- All fields match: id, query, results_count, clicked_article_id, created_at — VERIFIED
- `clicked_article` relationship with explicit `foreign_keys` — VERIFIED (`models/search.py:19`)

### ArticleMetric Model (Lines 253-270)
- All fields match: id, article_id, page_loads, newsletter_clicks, share_button_clicks, share_link_views, updated_at — VERIFIED
- `before_update` event listener — VERIFIED (`models/newsletter.py:122-123`)

### Newsletter & Subscriber Models (Lines 321-362)
- Newsletter fields match: id, newsletter_type, subject, html_content, article_count, recipients, delivered_count, error_message, generated_at, sent_at — VERIFIED
- Subscriber fields match all documented fields — VERIFIED
- `__table_args__` unique constraint `uq_email_newsletter` — VERIFIED (`models/newsletter.py:78-80`)

### Webhook & WebhookEvent Models (Lines 162-207)
- All Webhook fields match — VERIFIED
- All WebhookEvent fields match: id, webhook_id, event_type, status_code, response_body, error_message, delivered_at, attempt_number, idempotency_key, payload — VERIFIED

### Indexes Section (Lines 473-490)
- Article composite indexes — VERIFIED
- Source indexes — VERIFIED
- PipelineRun indexes — VERIFIED (`models/pipeline.py:27-29`)
- TrendMemory indexes — VERIFIED (`models/context.py:48-51`)
- QualityReport composite indexes — VERIFIED

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 419 | TopicNote `topic = Column(String(128), nullable=False)` (no index) | `models/context.py:12` — `topic = db.Column(db.String(128), nullable=False, index=True)` | LOW |
| 396 | TrendMemory `topic = Column(String(128))` (no index, no nullable) | `models/context.py:31` — `topic = db.Column(db.String(128), nullable=False, index=True)` | LOW |
| 374 | AdminUser `password_hash = Column(String(128))` (no nullable) | `models/auth.py:36` — `password_hash = db.Column(db.String(128), nullable=False)` | LOW |
| 379 | AdminUser `backup_codes = Column(JSON)` (no nullable) | `models/auth.py:39` — `backup_codes = db.Column(db.JSON, nullable=True)` | LOW |
| 399 | TrendMemory `source_article_id` described as "Single FK, not JSON" | Code is correct (single FK), but doc implies this was a change from JSON — misleading comment | LOW |
| 403 | TrendMemory `last_accessed_at = Column(DateTime)` (no nullable) | `models/context.py:40-44` — has `nullable=True, index=True, onupdate=...` | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | **Missing `ArticleVersion` model documentation.** The `ArticleVersion` model exists in `models/pipeline.py:63-91` with fields `article_id`, `version_number`, `final_article`, `original_ai_article`, `source_fields`, `change_reason`, `changed_by`, `created_at`. It is listed in the file inventory but has no detailed field documentation like other models. | `architecture/models.md` | MEDIUM | `models/pipeline.py:63-91` has 8 fields + unique constraint not documented |
| 2 | **Missing `Citation` model documentation.** The `Citation` model exists in `models/article.py:86-100` with fields `article_id`, `url`, `title`, `author`, `context`, `position`. It is listed in the file inventory but has no detailed field documentation. | `architecture/models.md` | LOW | `models/article.py:86-100` |
| 3 | **Missing `Tag` model documentation.** The `Tag` model exists in `models/tag.py:24-33` with fields `name`, `slug`, `created_at`. Listed but not documented. | `architecture/models.md` | LOW | `models/tag.py:24-33` |
| 4 | **Missing `AuditLog` model documentation.** The `AuditLog` model exists in `models/audit.py:8-24` with fields `action`, `category`, `target_type`, `target_id`, `user`, `details`, `ip_address`, `created_at`. Listed but not documented. | `architecture/models.md` | LOW | `models/audit.py:8-24` |
| 5 | **Missing `ApiToken` model documentation.** The `ApiToken` model exists in `models/auth.py:8-28` with fields `token_hash`, `token_prefix`, `name`, `created_at`, `last_used_at`, `expires_at`. Listed but not documented. | `architecture/models.md` | LOW | `models/auth.py:8-28` |
| 6 | **Missing `ShareConfig` model documentation.** The `ShareConfig` model exists in `models/share.py:6-18` with fields `platform_key`, `label`, `url_template`, `icon_name`, `active`, `sort_order`. Listed but not documented. | `architecture/models.md` | LOW | `models/share.py:6-18` |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Document the `ArticleVersion` model with full field list and unique constraint. | maintainability | P1 |
| 2 | Document `Citation`, `Tag`, `AuditLog`, `ApiToken`, `ShareConfig` models with field lists. | maintainability | P2 |
| 3 | Add `Subscriber.is_verified` property and `Subscriber.get_active()` classmethod to documentation. | maintainability | P3 |
| 4 | Add `models/utils.py` (`slugify`, `encode_short_url`, `decode_short_url`) to the file inventory. | maintainability | P3 |
| 5 | The doc uses `Column(...)` shorthand (no `db.` prefix) which is inconsistent with actual code using `db.Column(...)`. Consider using the actual import style for clarity. | maintainability | P3 |
| 6 | Document `Source.created_at` has no `index=True` (line 146 of doc matches code, but other timestamp fields do have indexes — worth noting the asymmetry). | maintainability | P3 |
| 7 | The `VALID_PIPELINE_STATUSES` frozenset in `constants.py:97-108` excludes `selecting`, `selected`, and `written`, but the models.md status table includes them. Consider clarifying that `VALID_PIPELINE_STATUSES` is for the admin API filter only, not all valid statuses. | maintainability | P2 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| N/A | No stale content detected | All referenced files, classes, and functions exist | None |

---

## Summary

- Verified: 42 claims
- Incorrect: 6 claims (all LOW severity — missing `index=True` or `nullable=` attributes in doc strings)
- Bugs: 6 (HIGH: 0, MEDIUM: 1, LOW: 5)
- Improvements: 7
- Stale items: 0

**Overall Assessment:** The models.md document is largely accurate and well-structured. The primary gaps are: (1) several models (ArticleVersion, Citation, Tag, AuditLog, ApiToken, ShareConfig) are listed in the inventory but lack detailed field documentation, and (2) minor attribute omissions (index=True, nullable=) in the TrendMemory, TopicNote, and AdminUser field definitions. No incorrect file paths, class names, or relationship definitions were found.
