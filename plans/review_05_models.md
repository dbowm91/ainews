# Architecture Review: models.md

**Date:** 2026-05-08  
**Reviewer:** Architecture Review Agent  
**Document:** `/Users/davidbowman/projects/ainews/architecture/models.md`

---

## Summary

| Category | Status |
|----------|--------|
| File Inventory | Mostly accurate |
| Key Relationships | Partially accurate (ArticleVersion missing) |
| Article Model | Partially accurate (many extra fields) |
| Source Model | Missing adapter_config field |
| AdminUser Security | Mostly accurate (documented correctly) |
| TrendMemory | Correct (signal field verified) |
| Indexes | Partially accurate (missing undocumented indexes) |

---

## 1. Verified Items (Correct)

### File Inventory (Correct)
All documented files exist in `models/`:
- `article.py` - Article, Citation
- `source.py` - Source
- `newsletter.py` - Newsletter, Subscriber, ArticleMetric
- `pipeline.py` - PipelineRun, PipelineLog, ArticleVersion
- `context.py` - TopicNote, TrendMemory
- `webhook.py` - Webhook, WebhookEvent
- `auth.py` - ApiToken, AdminUser
- `tag.py` - Tag, article_tags
- `search.py` - SearchQuery
- `audit.py` - AuditLog
- `share.py` - ShareConfig

### Key Relationships (Partially Correct)

**Documented:**
```
Article
├── Source (many-to-one) - source_id foreign key
├── Tag (many-to-many via article_tags)
├── Citation (one-to-many)
├── ArticleMetric (one-to-one)
└── ArticleVersion (one-to-many) - edit history

PipelineRun
├── PipelineLog (one-to-many)
└── Article (one-to-many) - via pipeline_run_id

Newsletter
├── Subscriber (many-to-many via newsletter_subscribers)
└── Article (many-to-many via newsletter_articles)
```

**Verification Results:**
| Relationship | Status | Notes |
|-------------|--------|-------|
| Article -> Source (source_id FK) | VERIFIED | `article.py:15-17` |
| Article -> Tag (many-to-many) | VERIFIED | `article.py:61` with article_tags table |
| Article -> Citation (one-to-many) | VERIFIED | `article.py:56-58` |
| Article -> ArticleMetric (one-to-one) | VERIFIED | `article.py:62-64` with uselist=False |
| Article -> ArticleVersion | VERIFIED | `pipeline.py:81-84` |
| PipelineRun -> PipelineLog | VERIFIED | `pipeline.py:23-25` |
| Newsletter -> Subscriber (many-to-many) | VERIFIED | `newsletter.py:16-23` newsletter_subscribers table |
| Newsletter -> Article (many-to-many) | VERIFIED | `newsletter.py:8-14` newsletter_articles table |
| **PipelineRun -> Article** | NOT FOUND | No direct relationship; PipelineRun tracks articles via PipelineLog.article_id |
| Article -> PipelineRun | NOT FOUND | No direct relationship |

**Finding:** The documentation claims `PipelineRun` has a direct "one-to-many" relationship with `Article` via `pipeline_run_id`, but there is no such relationship in the code. Articles are associated with pipeline runs through `PipelineLog.article_id`.

### Field Naming Conventions (Correct)

The document correctly notes these known field naming discrepancies:
| Document Field | Actual Field | Verified |
|---------------|--------------|----------|
| `Source.type` | `source_type` | VERIFIED (`source.py:14`) |
| `Source.last_fetch_at` | `last_crawled` | VERIFIED (`source.py:16`) |
| `TrendMemory.observation` | `signal` | VERIFIED (`context.py:32`) |
| Article `finalized_at` | `published_at` | VERIFIED (`article.py:54` is the actual published timestamp) |
| `embedding = Column(Vector(1536))` | `embedding = db.Text` | VERIFIED (`context.py:40`) |

### AdminUser Security (Correct)

| Feature | Documented | Actual | Status |
|---------|------------|--------|--------|
| TOTP 2FA | `totp_secret` field | `totp_secret` + `totp_enabled` boolean | VERIFIED |
| Backup codes | 8 backup codes as JSON | `backup_codes` JSON field | VERIFIED |
| Session security fields | `ip_binding`, `user_agent_hash` NOT IMPLEMENTED | Correctly documented as not implemented | VERIFIED |

### Pipeline Status Flow (Correct)

**Document says:**
```
pending → select → research → writing → editing → done
                     ↓          ↓         ↓
                   review ←──────┴─────────┘
                   (impact_score < threshold)
```

**Actual `_STAGE_TASKS` from `services/pipeline_utils.py:10-19`:**
```python
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),
    "editing": ("tasks.edit", "edit_article"),
    "review": ("tasks.edit", "edit_article"),
}
```

**Finding:** The documented flow uses simplified stage names (`select`, `research`, `writing`, `editing`) while the actual implementation uses more granular statuses (`pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`). The actual flow is more detailed and matches what AGENTS.md describes.

---

## 2. Discrepancies

### 2.1 Source Model Missing `adapter_config`

**Document says** (`source.py` model, line 92-93):
```python
# Configuration
adapter_config = Column(JSON)  # Source-specific adapter settings
```

**Actual implementation** (`source.py` lines 6-29):
```python
class Source(db.Model):
    __tablename__ = "sources"

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    url = db.Column(db.String(512))
    feed_url = db.Column(db.String(512))
    source_type = db.Column(db.String(32), nullable=False, index=True)
    active = db.Column(db.Boolean, default=True, index=True)
    last_crawled = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, ...)

    consecutive_failures = db.Column(db.Integer, nullable=False, default=0, index=True)
    consecutive_successes = db.Column(db.Integer, nullable=False, default=0)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    disabled_at = db.Column(db.DateTime, nullable=True, index=True)

    articles = db.relationship(...)
```

**Discrepancy:** The `adapter_config` field is NOT present in the actual Source model. This is a missing feature or documentation error.

### 2.2 Article Model Has Many Extra Fields

**Document shows 12 fields** for Article, but actual implementation has **30+ fields**.

**Document says:**
```python
class Article(Base):
    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    url = Column(String(2000))
    source_id = Column(Integer, ForeignKey('sources.id'))
    content = Column(Text)
    summary = Column(Text)
    pipeline_status = Column(String(50))
    impact_score = Column(Integer, default=0)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    finalized_at = Column(DateTime)
```

**Actual implementation** (`article.py:10-75`):
```python
class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(12), unique=True, index=True)
    source_id = db.Column(...)
    external_id = db.Column(db.String(128), index=True)
    original_url = db.Column(db.String(2048))
    original_title = db.Column(db.String(512), index=True)
    original_author = db.Column(db.String(128))
    original_published_at = db.Column(db.DateTime)
    extracted_text = db.Column(db.Text)
    pipeline_status = db.Column(db.String(32), default="pending")
    selector_result = db.Column(db.JSON)
    research_brief = db.Column(db.Text)
    draft_article = db.Column(db.Text)
    final_article = db.Column(db.Text)
    original_ai_article = db.Column(db.Text)
    writer_model = db.Column(db.String(128))
    impact_score = db.Column(db.Integer, default=0)
    summary = db.Column(db.Text)
    category = db.Column(db.String(32), index=True)
    topics = db.Column(db.JSON)
    raw_metadata = db.Column(db.JSON)
    extraction_status = db.Column(db.String(32), default="pending")
    retry_count = db.Column(db.Integer, default=0)
    total_retries = db.Column(db.Integer, nullable=False, default=0)
    degradation_count = db.Column(db.Integer, nullable=False, default=0)
    pipeline_started_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, ...)
    updated_at = db.Column(db.DateTime, ...)
    scheduled_publish_at = db.Column(db.DateTime, nullable=True, index=True)
    crawled_at = db.Column(db.DateTime, nullable=True, index=True)
    selected_at = db.Column(db.DateTime, nullable=True, index=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)
    citations = db.relationship(...)
    experiment_group = db.Column(db.String(32), nullable=True, index=True)
    embedding = db.Column(db.Text)
    tags = db.relationship(...)
    metrics = db.relationship(...)
```

**Discrepancy:** The document shows a simplified Article model. The actual implementation has many more fields for supporting the full pipeline (research_brief, draft_article, final_article, etc.).

### 2.3 Indexes Documentation is Incomplete

**Document says:**
```
- Article: pipeline_status, source_id, published_at, created_at
- Source: name, type
- PipelineRun: status, created_at
- TrendMemory: topic (GIN index on embedding for vector search)
```

**Actual indexes found:**

| Model | Actual Indexes |
|-------|----------------|
| Article | `short_id`, `source_id`, `external_id`, `original_title`, `category`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `published_at`, `experiment_group`; composite indexes on `(pipeline_status, created_at)`, `(original_published_at)`, `(impact_score)`, `(category, pipeline_status)`, `(total_retries)`, `(retry_count)`, `(degradation_count)` |
| Source | `name`, `source_type`, `active`, `consecutive_failures`, `disabled_at` |
| PipelineRun | `finished_at`; composite indexes on `(run_type)`, `(run_type, status)` |
| TrendMemory | `topic` (B-tree), `source_article_id`; composite indexes on `(topic, importance)`, `(expires_at)` |

**Key Issues:**
1. **Document claims GIN index on embedding for vector search** - NO GIN index exists. The `embedding` field is `db.Text` (plain text storage), not a vector type. No GIN index is present.

2. **PipelineRun: Document claims `status`, `created_at` indexes** - Actual has `finished_at` and composite indexes on `(run_type)` and `(run_type, status)`, but no explicit `status` or `created_at` single-column indexes.

3. **Source: Document claims `type` index** - Actual has `source_type` index (correctly named), but document says `type`.

### 2.4 Pipeline Status Constants Incomplete

**Document shows:** `pending`, `select`, `research`, `write`, `edit`, `review`, `done`

**Actual `PipelineStatus` class** (`constants.py:30-41`):
```python
class PipelineStatus:
    PENDING = "pending"
    RESEARCHING = "researching"
    WRITING = "writing"
    EDITING = "editing"
    REVIEW = "review"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
```

**Discrepancy:** The document shows simplified stage names that don't match the actual constants. The constants include `SKIPPED` and `FAILED` which are not in the documented flow.

---

## 3. Issues Found

### 3.1 Missing `adapter_config` on Source Model

**Severity:** Medium  
**Type:** Missing Feature / Documentation Error

The documentation shows `adapter_config = Column(JSON)` on the Source model, but this field does not exist in the actual implementation. This could be:
- A planned but unimplemented feature
- A documentation error

If source-specific adapter settings are needed, this field should be added to the model.

### 3.2 No Vector/GIN Index for TrendMemory Embedding

**Severity:** Medium  
**Type:** Missing Feature

The documentation claims there is a "GIN index on embedding for vector search" on the TrendMemory model, but:
1. The `embedding` field is `db.Text` (plain text storage)
2. No GIN index exists on this field
3. No vector search capability is implemented

If vector search is needed, the model should use a proper vector type (e.g., `pgvector` extension) with a GIN or HNSW index.

### 3.3 Article->PipelineRun Relationship Missing

**Severity:** Low  
**Type:** Documentation Error

The documentation shows `PipelineRun -> Article (one-to-many)` as a relationship, but there is no such direct relationship. Articles are associated with pipeline runs through `PipelineLog.article_id` (via the pipeline_logs table). This is a conceptual modeling error in the documentation.

### 3.4 Source Model Has `source_key` (Not Documented)

**Severity:** Low  
**Type:** Undocumented Field

The Source model has a `source_key = db.Column(db.String(64), unique=True, nullable=False)` field that is not mentioned in the documentation. This appears to be a unique identifier for the source (e.g., "hackernews", "techcrunch") separate from `name`.

---

## 4. Architecture Principle Violations

### 4.1 No Architecture Violations Found

The models layer appears to follow proper SQLAlchemy patterns:
- Relationships are correctly defined
- Foreign keys use `ondelete="CASCADE"` appropriately
- Indexes are created for query performance
- JSON fields are used for flexible data storage
- Default values and timestamps are properly implemented

---

## 5. Recommendations

### High Priority

1. **Fix `adapter_config` discrepancy**
   - If the field is needed: Add it to `models/source.py`
   - If it's not needed: Remove from documentation

2. **Update Indexes section in documentation**
   - Remove claim of GIN index on embedding (not implemented)
   - Document actual composite indexes
   - Document all indexes, not just a subset

### Medium Priority

3. **Update Article model documentation**
   - Document all actual fields or create a simplified version noting "many additional pipeline fields"
   - Clarify the relationship between Article and pipeline stages

4. **Fix PipelineRun -> Article relationship**
   - Remove the direct relationship claim
   - Document that articles are tracked via PipelineLog

5. **Update pipeline status flow**
   - Use actual status constants or document the simplified stage mapping

### Low Priority

6. **Document `source_key` field**
   - Explain the difference between `source_key` (unique identifier) and `name` (display name)

7. **Consider adding vector search support**
   - If semantic search on TrendMemory is needed, implement proper vector type with pgvector or similar

---

## 6. Summary

The models documentation has several discrepancies with the actual implementation:

| Category | Discrepancy Count | Severity |
|----------|-------------------|----------|
| Missing fields | 1 (adapter_config) | Medium |
| Extra fields | 1 (source_key) | Low |
| Index inaccuracies | 3 | Medium |
| Relationship errors | 1 | Low |
| Status constants | 1 | Low |

**Overall Assessment:** The documentation captures the general structure of the models but has significant inaccuracies in field definitions, indexes, and relationships. The code is internally consistent and well-structured; the documentation needs updating to match.

---

*End of Review*
