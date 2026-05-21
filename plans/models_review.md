# Models Module Architecture Review

## Summary

The `architecture/models.md` document makes several claims that are **inaccurate** or **outdated**. This review verified all claims against the actual codebase in `models/` directory.

---

## Verified Claims

### File Inventory (Lines 6-19)
| Documented | Actual | Status |
|------------|--------|--------|
| `article.py` → `Article`, `Citation` | `Article`, `Citation` | ✅ VERIFIED |
| `source.py` → `Source` | `Source` | ✅ VERIFIED |
| `newsletter.py` → `Newsletter`, `Subscriber`, `ArticleMetric` | `Newsletter`, `Subscriber`, `ArticleMetric` | ✅ VERIFIED |
| `pipeline.py` → `PipelineRun`, `PipelineLog`, `ArticleVersion` | `PipelineRun`, `PipelineLog`, `ArticleVersion` | ✅ VERIFIED |
| `context.py` → `TopicNote`, `TrendMemory` | `TopicNote`, `TrendMemory` | ✅ VERIFIED |
| `webhook.py` → `Webhook`, `WebhookEvent` | `Webhook`, `WebhookEvent` | ✅ VERIFIED |
| `auth.py` → `ApiToken`, `AdminUser` | `ApiToken`, `AdminUser` | ✅ VERIFIED |
| `tag.py` → `Tag`, `article_tags` | `Tag`, `article_tags` | ✅ VERIFIED |
| `search.py` → `SearchQuery` | `SearchQuery` | ✅ VERIFIED |
| `audit.py` → `AuditLog` | `AuditLog` | ✅ VERIFIED |
| `share.py` → `ShareConfig` | `ShareConfig` | ✅ VERIFIED |

### Key Relationships Diagram (Lines 21-38)
All relationships documented are accurate. ✅

### TrendMemory.embedding (Line 127)
Document states: `embedding = Column(Text)  # Stored as text, not vector type`
Actual code (`models/context.py:46`): `embedding = db.Column(db.Text, nullable=True)`
**✅ VERIFIED** - Correctly documented as Text.

### TrendMemory.last_accessed_at (Line 132)
Document states: `last_accessed_at = Column(DateTime)`
Actual code (`models/context.py:40-45`):
```python
last_accessed_at = db.Column(
    db.DateTime,
    nullable=True,
    index=True,
    onupdate=datetime.utcnow
)
```
**✅ VERIFIED** - Field exists with index.

---

## Discrepancies and Issues

### CRIT-1: Source.adapter_config Does Not Exist (Line 91)

**Document claims:**
```python
adapter_config = Column(JSON)  # Source-specific adapter settings
```

**Actual code (`models/source.py`):**
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
    consecutive_failures = db.Column(db.Integer, ...)
    consecutive_successes = db.Column(db.Integer, ...)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    disabled_at = db.Column(db.DateTime, nullable=True, index=True)
    # NO adapter_config field
```

**Reality:** Adapter configuration is stored externally in `schemas/source.py` as `SourceConfig.config` (JSON), validated against adapter schemas (RSSConfig, APIConfig, WebConfig). Adapters access it via `source_config.config` at runtime.

**Reference:** `adapters/base.py:46` loads config from source's config dict.

---

### CRIT-2: AdminUser Missing ip_binding and user_agent_hash (Line 111)

**Document states:** `# Note: ip_binding and user_agent_hash not implemented`

**Actual code (`models/auth.py:31-48`):**
```python
class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    totp_secret = db.Column(db.String(256))
    totp_enabled = db.Column(db.Boolean, default=False)
    backup_codes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, ...)
    updated_at = db.Column(db.DateTime, ...)
```

**Status:** No `ip_binding` or `user_agent_hash` fields exist. This is correctly noted as "not implemented" in the document, but the comment should be clarified to indicate these fields **do not exist** rather than just "not implemented" (which implies a TODO).

---

### MED-1: Article Model Documented Inaccurately (Lines 40-70)

**Document shows:**
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
```

**Actual code (`models/article.py:10-75`):**
The actual Article model is significantly different:

| Documented Field | Actual Field | Status |
|------------------|--------------|--------|
| `title` | `original_title` | ❌ DIFFERENT |
| `url` | `original_url` | ❌ DIFFERENT |
| `content` | `extracted_text` | ❌ DIFFERENT |
| (not documented) | `short_id` | ❌ MISSING |
| (not documented) | `external_id` | ❌ MISSING |
| (not documented) | `pipeline_status` exists | ✅ |
| (not documented) | `selector_result` | ❌ MISSING |
| (not documented) | `research_brief` | ❌ MISSING |
| (not documented) | `draft_article` | ❌ MISSING |
| (not documented) | `final_article` | ❌ MISSING |
| (not documented) | `original_ai_article` | ❌ MISSING |
| (not documented) | `writer_model` | ❌ MISSING |
| (not documented) | `category` | ❌ MISSING |
| (not documented) | `topics` | ❌ MISSING |
| (not documented) | `raw_metadata` | ❌ MISSING |
| (not documented) | `extraction_status` | ❌ MISSING |
| (not documented) | `retry_count`, `total_retries`, `degradation_count` | ❌ MISSING |
| (not documented) | `pipeline_started_at` | ❌ MISSING |
| (not documented) | `last_error` | ❌ MISSING |
| (not documented) | `updated_at` | ❌ MISSING |
| (not documented) | `scheduled_publish_at` | ❌ MISSING |
| (not documented) | `crawled_at`, `selected_at` | ❌ MISSING |
| (not documented) | `experiment_group` | ❌ MISSING |
| (not documented) | `embedding` (article-level) | ❌ MISSING |
| `published_at` | `published_at` (nullable) | ✅ EXISTS |

**Issue:** The Article model in the architecture document is a **stub/oversimplification** and does not reflect the actual implementation.

---

### MED-2: Source Model Has source_key Instead of adapter_config

**Document shows:**
```python
class Source(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    source_type = Column(String(50))  # rss, api, web
    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    consecutive_successes = Column(Integer, default=0)
    last_crawled = Column(DateTime)
    last_success_at = Column(DateTime)
    # Configuration
    adapter_config = Column(JSON)  # Source-specific adapter settings
```

**Actual (`models/source.py:6-30`):**
- `source_key` (Line 10) exists but is NOT documented
- `adapter_config` does NOT exist
- `url` and `feed_url` are NOT documented
- `active` is NOT documented
- `last_error` is NOT documented
- `disabled_at` is NOT documented

---

### MED-3: Index Documentation Incomplete (Lines 136-142)

**Document claims:**
```
- `Article`: `pipeline_status`, `source_id`, `published_at`, `created_at`
- `Source`: `name`, `type`
- `PipelineRun`: `status`, `created_at`
- `TrendMemory`: `topic` (no GIN index)
```

**Actual Indexes:**

**Article (`models/article.py:66-75`):**
```python
__table_args__ = (
    db.UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
    db.Index("ix_articles_status_created", "pipeline_status", "created_at"),
    db.Index("ix_articles_published", "original_published_at"),
    db.Index("ix_articles_impact", "impact_score"),
    db.Index("ix_articles_category_status", "category", "pipeline_status"),
    db.Index("ix_articles_total_retries", "total_retries"),
    db.Index("ix_articles_retry_count", "retry_count"),
    db.Index("ix_articles_degradation_count", "degradation_count"),
)
```

Actual: `pipeline_status`, `source_id` (FK), `published_at` (as `original_published_at`), `created_at`, plus many more.

**Source (`models/source.py`):**
- Indexes on `name` (line 11)
- Indexes on `source_type` (line 14)
- Index on `consecutive_failures` (line 19)
- Index on `disabled_at` (line 23)
- Unique constraint on `source_key` (line 10)

**PipelineRun (`models/pipeline.py:27-30`):**
```python
__table_args__ = (
    db.Index("ix_pipeline_runs_run_type", "run_type"),
    db.Index("ix_pipeline_runs_run_type_status", "run_type", "status"),
)
```
No index on `created_at`.

**TrendMemory (`models/context.py:48-51`):**
```python
__table_args__ = (
    db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
    db.Index("ix_trend_memory_expires_at", "expires_at"),
)
```
`last_accessed_at` has an index (line 43) but is not documented.

---

### MED-4: Pipeline Status Flow Outdated (Lines 63-70)

**Document shows:**
```
pending → select → research → writing → editing → done
```

**Actual Statuses (from `models/article.py:25`):**
```python
pipeline_status = db.Column(db.String(32), default="pending")
```

The documented flow `pending → select → research → writing → editing → done` does not match the actual pipeline implementation. Actual stages (from `tasks/` and `services/pipeline/`) include:
- `pending`
- `select` / `selecting` / `selected`
- `research` / `researching`
- `write` / `writing` / `written`
- `edit` / `editing`
- `review`
- `done`

The architecture doc shows "writing" and "editing" but actual models use `write` and `edit` as base statuses.

---

### MED-5: Newsletter Relationship Missing `newsletter_articles` and `newsletter_subscribers` Tables

**Document shows:**
```
Newsletter
├── Subscriber (many-to-many via newsletter_subscribers)
└── Article (many-to-many via newsletter_articles)
```

**Actual (`models/newsletter.py:8-23`):**
Tables exist and are correctly documented, but the document does not explicitly show these as association tables.

---

## Recommendations

1. **Update Article Model Documentation**
   - Replace the stub example with accurate field list
   - Document all JSON columns (`topics`, `raw_metadata`, `selector_result`)
   - Document `short_id` as the public-facing identifier
   - Document `experiment_group` for A/B testing

2. **Remove `adapter_config` from Source Model**
   - Document that adapter configuration is stored in `schemas/source.py` as `SourceConfig.config`
   - Reference where adapters access it (`adapters/base.py`)

3. **Clarify AdminUser Session Security**
   - Change "not implemented" comment to clearly state these fields do not exist

4. **Update Index Documentation**
   - Document actual index names and column sets
   - Add `last_accessed_at` index for TrendMemory

5. **Fix Pipeline Status Flow**
   - Update to reflect actual statuses used in code

6. **Document Association Tables**
   - Add explicit entries for `newsletter_articles` and `newsletter_subscribers` in file inventory

---

## Bugs Identified

| ID | Severity | Location | Issue |
|----|----------|----------|-------|
| CRIT-1 | Critical | `architecture/models.md:91` | `adapter_config` documented but does not exist in Source model |
| MED-1 | Medium | `architecture/models.md:40-61` | Article model example is a stub, missing most fields |
| MED-2 | Medium | `architecture/models.md:73-92` | Source model missing `source_key`, `url`, `feed_url`, `active`, `last_error`, `disabled_at` |
| MED-3 | Medium | `architecture/models.md:136-142` | Index documentation incomplete and inaccurate |
| MED-4 | Medium | `architecture/models.md:63-70` | Pipeline status flow outdated |
| MED-5 | Medium | `architecture/models.md:21-38` | Association tables not explicitly documented |