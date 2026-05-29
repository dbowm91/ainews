# Architecture Models Review

**Review date:** 2026-05-29
**Reviewed files:** `models/*.py`, `constants.py`

---

## Verified Claims

### File Inventory (models.md lines 7-21)
All models exist and are correctly mapped:
| File | Models | Verified |
|------|--------|----------|
| `article.py` | `Article`, `Citation` | ✓ |
| `source.py` | `Source` | ✓ |
| `newsletter.py` | `Newsletter`, `Subscriber`, `ArticleMetric` | ✓ |
| `pipeline.py` | `PipelineRun`, `PipelineLog`, `ArticleVersion` | ✓ |
| `context.py` | `TopicNote`, `TrendMemory` | ✓ |
| `webhook.py` | `Webhook`, `WebhookEvent` | ✓ |
| `auth.py` | `ApiToken`, `AdminUser` | ✓ |
| `tag.py` | `Tag`, `article_tags` | ✓ |
| `search.py` | `SearchQuery` | ✓ |
| `audit.py` | `AuditLog` | ✓ |
| `quality.py` | `QualityReport` | ✓ |
| `share.py` | `ShareConfig` | ✓ |

### Article Model (models.md lines 43-104)
- 38 fields total (exceeds 30+) ✓
- Field names, types, defaults all match `models/article.py` ✓
- `selector_result` as JSON column ✓
- `research_brief` as Text ✓
- Relationships: `citations`, `tags` (via article_tags), `metrics` ✓
- All indexes present: `ix_articles_status_created`, `ix_articles_published`, `ix_articles_impact`, `ix_articles_category_status`, `ix_articles_total_retries`, `ix_articles_retry_count`, `ix_articles_degradation_count` ✓
- Unique constraint `uq_source_external_id` on `(source_id, external_id)` ✓

### PipelineStatus Enum (constants.py lines 30-43)
- All values match: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`, `done`, `skipped`, `failed` ✓
- VALID_TRANSITIONS map matches documentation (models.md lines 108-123) ✓

### Source Model (models.md lines 130-156)
- `source_type` (not `type`) ✓
- `last_crawled` (not `last_fetch_at`) ✓
- Health tracking fields: `consecutive_failures`, `consecutive_successes`, `last_success_at`, `last_error`, `disabled_at` ✓
- Adapter config note correctly states it lives in `SourceConfig.config` (schemas/source.py), not in this model ✓

### Newsletter Association Tables (models.md lines 158-187)
- `newsletter_articles`: `newsletter_id`, `article_id`, `position`, `created_at` ✓
- `newsletter_subscribers`: `newsletter_id`, `subscriber_id`, `sent_at`, `opened_at`, `clicked_at` ✓

### Newsletter & Subscriber (models.md lines 189-230)
- `Newsletter`: all fields match (`newsletter_type`, `subject`, `html_content`, `article_count`, `recipients`, `delivered_count`, `error_message`, `generated_at`, `sent_at`) ✓
- `Subscriber`: all fields match (`email`, `newsletter_type`, `unsubscribe_token`, `verification_token`, `subscribed_at`, `confirmed_at`, `active`, `deleted_at`, `preferences`, `bounce_count`, `last_bounce_at`, `last_active_at`) ✓
- Unique constraint `uq_email_newsletter` on `(email, newsletter_type)` ✓

### AdminUser (models.md lines 232-253)
- `backup_codes` as JSON ✓ (models/auth.py:39)
- Note about no session security fields on model is accurate ✓

### TrendMemory (models.md lines 255-275)
- `topic` as String(128) ✓
- `signal` (not `observation`) ✓
- `source_article_id` as single FK to articles.id, not JSON ✓
- `embedding` as Text (not vector type) ✓
- `importance` default 1 ✓
- `expires_at`, `last_consolidated_at`, `created_at`, `last_accessed_at` ✓

### TopicNote (models.md lines 277-294)
- `topic` String(128), `note` Text, `source` String(256) ✓
- Unique constraint `uq_topic_source` on `(topic, source)` ✓

### QualityReport (models.md lines 296-337)
- All fields present: `article_id`, `article_version_id`, `stage`, `overall_score`, `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings`, `meta`, `created_at` ✓
- Relationships to `Article` and `ArticleVersion` ✓
- Composite indexes: `ix_quality_reports_article_stage`, `ix_quality_reports_created` ✓
- Quality gate routing note accurate (services/quality_report.py, tasks/edit.py) ✓

### Indexes (models.md lines 341-358)
- All Article indexes verified present ✓
- Source unique constraint on `source_key`, indexes on `active`, `consecutive_failures`, `disabled_at` ✓
- PipelineRun indexes on `run_type`, `(run_type, status)`, `started_at` ✓
- TrendMemory indexes on `(topic, importance)`, `expires_at`, `last_accessed_at` ✓

---

## Incorrect Claims

**None identified.** All field names, types, defaults, and relationships match actual code.

---

## Bugs Found

**None.** No bugs in documentation.

---

## Improvement Opportunities

### 1. Minor: `article_tags` table not shown separately (MEDIUM)
**Location:** models.md - Key Relationships section (lines 24-39)

The relationship diagram shows `Tag (many-to-many via article_tags)` but doesn't show the `article_tags` table definition separately in the document. The table is defined in `models/tag.py` and used as a secondary join table. While the diagram is not incorrect, showing the `article_tags` table definition explicitly would improve clarity, similar to how `newsletter_articles` and `newsletter_subscribers` are shown.

**Recommendation:** Add a section similar to "Newsletter Association Tables" showing:
```python
article_tags = db.Table(
    "article_tags",
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
)
```

### 2. Minor: Relationship backref not shown in diagram (LOW)
**Location:** models.md - Key Relationships / Newsletter (line 37)

The diagram shows `Newsletter → Article (many-to-many)` but doesn't show that `Article` gets a dynamic backref relationship `newsletters` from this. The code in `models/newsletter.py:43` sets `backref=db.backref("newsletters", lazy="dynamic")` on the relationship.

**Recommendation:** Update diagram to show bidirectional relationship or add note about `Article.newsletters` backref.

---

## Stale Content

**None identified.** All content is current with codebase.

---

## Priority Summary

| Finding | Severity | Type | Effort |
|---------|----------|------|--------|
| Add article_tags table definition | MEDIUM | Improvement | Low |
| Document Article.newsletters backref | LOW | Improvement | Low |

All claims verified correct; no bugs or stale content found.