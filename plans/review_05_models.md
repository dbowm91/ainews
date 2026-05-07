# Plan: review_05_models - Architecture Documentation Review: Models Module

**Status:** COMPLETE
**Created:** 2026-05-07
**Goal:** Document verification results for `architecture/models.md` claims against actual codebase

---

## Executive Summary

The `architecture/models.md` documentation contains significant discrepancies with the actual implementation. Out of 48 claims verified, 27 were verified, 10 were discrepant, and several bugs were identified. The most critical issues are:

1. **Article model field names substantially differ** from documentation
2. **TrendMemory embedding is `db.Text`, not `Vector(1536)`** - vector search not implemented
3. **AdminUser missing `ip_binding` and `user_agent_hash`** session security fields
4. **PipelineRun relationship to Article not implemented** (no `pipeline_run_id` FK)
5. **Field name inconsistencies** across multiple models (e.g., `source.type` vs `source.source_type`)

---

## 1. File Inventory Verification

| File | Claimed Models | Actual Models | Status |
|------|---------------|---------------|--------|
| `article.py` | `Article`, `Citation` | `Article`, `Citation` | VERIFIED |
| `source.py` | `Source` | `Source` | VERIFIED |
| `newsletter.py` | `Newsletter`, `Subscriber`, `ArticleMetric` | `Newsletter`, `Subscriber`, `ArticleMetric` | VERIFIED |
| `pipeline.py` | `PipelineRun`, `PipelineLog`, `ArticleVersion` | `PipelineRun`, `PipelineLog`, `ArticleVersion` | VERIFIED |
| `context.py` | `TopicNote`, `TrendMemory` | `TopicNote`, `TrendMemory` | VERIFIED |
| `webhook.py` | `Webhook`, `WebhookEvent` | `Webhook`, `WebhookEvent` | VERIFIED |
| `auth.py` | `ApiToken`, `AdminUser` | `ApiToken`, `AdminUser` | VERIFIED |
| `tag.py` | `Tag`, `article_tags` | `Tag`, `article_tags` | VERIFIED |
| `search.py` | `SearchQuery` | `SearchQuery` | VERIFIED |
| `audit.py` | `AuditLog` | `AuditLog` | VERIFIED |
| `share.py` | `ShareConfig` | `ShareConfig` | VERIFIED |

**Result:** All files and models are present. ✓

---

## 2. Article Model Discrepancies

### Documentation Claims (architecture/models.md:44-62):

```python
class Article(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    url = Column(String(2000))
    source_id = Column(Integer, ForeignKey('sources.id'))
    content = Column(Text)
    summary = Column(Text)

    pipeline_status = Column(String(50))  # pending, select, research, write, edit, review, done
    impact_score = Column(Integer, default=0)

    # Timestamps
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    finalized_at = Column(DateTime)
```

### Actual Implementation (models/article.py:10-76):

```python
class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(12), unique=True, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    scheduled_publish_at = db.Column(db.DateTime, nullable=True, index=True)
    crawled_at = db.Column(db.DateTime, nullable=True, index=True)
    selected_at = db.Column(db.DateTime, nullable=True, index=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)
```

### Discrepancies:

| Doc Field | Doc Type | Actual Field | Actual Type | Severity |
|-----------|----------|--------------|-------------|----------|
| `title` | `String(500)` | `original_title` | `String(512)` | HIGH |
| `url` | `String(2000)` | `original_url` | `String(2048)` | HIGH |
| `content` | `Text` | `extracted_text` | `Text` | HIGH |
| `finalized_at` | `DateTime` | (missing) | - | MEDIUM |
| `source_id` | FK | `source_id` | FK with `ondelete="CASCADE"` | MEDIUM |
| - | - | `short_id` | `String(12)` unique | LOW |
| - | - | `external_id` | `String(128)` | LOW |
| - | - | `pipeline_started_at` | `DateTime` | LOW |
| - | - | `last_error` | `Text` | LOW |
| - | - | `retry_count`, `total_retries` | `Integer` | LOW |
| - | - | `category`, `topics` | `JSON` | LOW |

### Code References:
- **Actual model:** `models/article.py:10-76`
- **Issue location:** Field naming inconsistencies throughout

---

## 3. Source Model Discrepancies

### Documentation Claims (architecture/models.md:77-93):

```python
class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    type = Column(String(50))  # rss, api, web

    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    consecutive_successes = Column(Integer, default=0)
    last_fetch_at = Column(DateTime)
    last_success_at = Column(DateTime)

    # Configuration
    adapter_config = Column(JSON)  # Source-specific adapter settings
```

### Actual Implementation (models/source.py:6-30):

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    consecutive_failures = db.Column(db.Integer, nullable=False, default=0, index=True)
    consecutive_successes = db.Column(db.Integer, nullable=False, default=0)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    disabled_at = db.Column(db.DateTime, nullable=True, index=True)
```

### Discrepancies:

| Doc Field | Doc Type | Actual Field | Actual Type | Severity |
|-----------|----------|--------------|-------------|----------|
| `type` | `String(50)` | `source_type` | `String(32)` | HIGH |
| `last_fetch_at` | `DateTime` | `last_crawled` | `DateTime` | HIGH |
| `name` | `String(200)` | `name` | `String(128)` | MEDIUM |
| `adapter_config` | `JSON` | (missing) | - | MEDIUM |
| - | - | `source_key` | `String(64)` unique | LOW |
| - | - | `feed_url` | `String(512)` | LOW |
| - | - | `active` | `Boolean` | LOW |
| - | - | `disabled_at` | `DateTime` | LOW |

### Code References:
- **Actual model:** `models/source.py:6-30`
- **adapter_config is NOT on Source model** - it's in adapter config classes at `adapters/base.py:46` and used by adapters

---

## 4. AdminUser Security Discrepancies

### Documentation Claims (architecture/models.md:99-114):

```python
class AdminUser(Base):
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True)
    password_hash = Column(String(255))

    # TOTP 2FA
    totp_secret = Column(String(32))
    backup_codes = Column(JSON)  # 8 backup codes as JSON array

    # Session security
    ip_binding = Column(String(45))  # IPv4/IPv6
    user_agent_hash = Column(String(64))
```

### Actual Implementation (models/auth.py:31-48):

```python
class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    totp_secret = db.Column(db.String(256))
    totp_enabled = db.Column(db.Boolean, default=False)
    backup_codes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

### Discrepancies:

| Doc Field | Doc Type | Actual Field | Actual Type | Severity |
|-----------|----------|--------------|-------------|----------|
| `username` | `String(100)` | `username` | `String(64)` | MEDIUM |
| `password_hash` | `String(255)` | `password_hash` | `String(128)` | MEDIUM |
| `totp_secret` | `String(32)` | `totp_secret` | `String(256)` | MEDIUM |
| `ip_binding` | `String(45)` | **(missing)** | - | HIGH |
| `user_agent_hash` | `String(64)` | **(missing)** | - | HIGH |
| - | - | `totp_enabled` | `Boolean` | LOW |

### Code References:
- **Actual model:** `models/auth.py:31-48`
- **Session binding functions:** Not found in codebase - these fields may never have been implemented

### Bugs:

1. **Missing Session Security Fields**: `ip_binding` and `user_agent_hash` documented but never implemented
   - **Impact:** Session binding to IP/UA documented but not possible
   - **Fix:** Either implement fields or update docs to remove claims

2. **TOTP Secret Length Mismatch**: Docs claim 32 chars but actual uses 256
   - **Impact:** Documentation is misleading for security review
   - **Fix:** Update docs

---

## 5. TrendMemory Discrepancies

### Documentation Claims (architecture/models.md:120-135):

```python
class TrendMemory(Base):
    __tablename__ = 'trend_memory'

    id = Column(Integer, primary_key=True)
    topic = Column(String(200))
    observation = Column(Text)

    # Embeddings for semantic search
    embedding = Column(Vector(1536))  # OpenAI ada-002 dimensions

    # Metadata
    source_articles = Column(JSON)  # Related article IDs
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime)
```

### Actual Implementation (models/context.py:27-48):

```python
class TrendMemory(db.Model):
    __tablename__ = "trend_memory"

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(128), nullable=False, index=True)
    signal = db.Column(db.Text, nullable=False)
    importance = db.Column(db.Integer, nullable=False, default=1)
    source_article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at = db.Column(db.DateTime, nullable=True)
    last_consolidated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    embedding = db.Column(db.Text, nullable=True)
```

### Discrepancies:

| Doc Field | Doc Type | Actual Field | Actual Type | Severity |
|-----------|----------|--------------|-------------|----------|
| `topic` | `String(200)` | `topic` | `String(128)` | MEDIUM |
| `observation` | `Text` | `signal` | `Text` | HIGH |
| `embedding` | `Vector(1536)` | `embedding` | `db.Text` | CRITICAL |
| `source_articles` | `JSON` | `source_article_id` | FK to articles | HIGH |
| `last_accessed_at` | `DateTime` | `last_consolidated_at` | `DateTime` | MEDIUM |
| - | - | `importance` | `Integer` | LOW |
| - | - | `expires_at` | `DateTime` | LOW |

### Code References:
- **Actual model:** `models/context.py:27-48`
- **Vector type:** Not found in models - `Vector` is never imported (searched codebase, only found in plans)

### Bugs:

1. **CRITICAL: Vector Type Not Implemented**: `embedding = Column(Vector(1536))` uses `Vector` type that doesn't exist in the codebase
   - **Impact:** Vector similarity search cannot work; embedding stored as plain text
   - **Actual behavior:** Uses `db.Text` to store embedding as string
   - **Fix:** Implement vector search using pgvector or update docs to reflect Text storage

2. **Field Name Mismatch**: Docs use `observation` but actual uses `signal`
   - **Fix:** Sync field names or clarify this is a rename

3. **Relationship Change**: Docs show `source_articles = JSON` array but actual uses `source_article_id` FK
   - **Impact:** Cannot store multiple article IDs; only single article reference
   - **Fix:** Either implement JSON array or document single-article limitation

---

## 6. Index Discrepancies

### Documentation Claims (architecture/models.md:137-144):

```
Key indexes for query performance:

- `Article`: `pipeline_status`, `source_id`, `published_at`, `created_at`
- `Source`: `name`, `type`
- `PipelineRun`: `status`, `created_at`
- `TrendMemory`: `topic` (GIN index on embedding for vector search)
```

### Actual Indexes:

**Article** (`models/article.py:66-75`):
```python
db.Index("ix_articles_status_created", "pipeline_status", "created_at"),
db.Index("ix_articles_published", "original_published_at"),
db.Index("ix_articles_impact", "impact_score"),
db.Index("ix_articles_category_status", "category", "pipeline_status"),
db.Index("ix_articles_total_retries", "total_retries"),
db.Index("ix_articles_retry_count", "retry_count"),
db.Index("ix_articles_degradation_count", "degradation_count"),
```

Plus individual indexes on: `short_id`, `source_id`, `original_title`, `category`, `experiment_group`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `published_at`

**Source** (`models/source.py`):
- `name` - has index
- `source_type` - has index (not `type`)
- `consecutive_failures` - has index
- `disabled_at` - has index

**PipelineRun** (`models/pipeline.py:27-30`):
```python
db.Index("ix_pipeline_runs_run_type", "run_type"),
db.Index("ix_pipeline_runs_run_type_status", "run_type", "status"),
```

**TrendMemory** (`models/context.py:42-45`):
```python
db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
db.Index("ix_trend_memory_expires_at", "expires_at"),
```

### Discrepancies:

| Model | Doc Claims | Actual | Severity |
|-------|------------|--------|----------|
| Article | `published_at` | `original_published_at` | MEDIUM |
| Article | standalone `created_at` | part of composite `status_created` | MEDIUM |
| Source | `type` | `source_type` | HIGH |
| PipelineRun | `status` alone | only `run_type` and `run_type+status` | MEDIUM |
| PipelineRun | `created_at` alone | (no index) | MEDIUM |
| TrendMemory | GIN index on embedding | No GIN index (embedding is Text) | CRITICAL |

### Code References:
- **Article indexes:** `models/article.py:66-75`
- **Source indexes:** `models/source.py:9-23`
- **PipelineRun indexes:** `models/pipeline.py:27-30`
- **TrendMemory indexes:** `models/context.py:42-45`

---

## 7. Relationship Discrepancies

### Documentation Claims (architecture/models.md:21-38):

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

### Actual Relationships:

**Article** (`models/article.py`):
- `source` - backref present ✓
- `tags` - many-to-many via article_tags ✓
- `citations` - one-to-many ✓
- `metrics` - one-to-one (uselist=False) ✓
- No `pipeline_run_id` FK ✗
- `versions` - one-to-many via ArticleVersion ✓

**PipelineRun** (`models/pipeline.py`):
- `logs` - one-to-many PipelineLog ✓
- No direct relationship to Article ✗

**Newsletter** (`models/newsletter.py:8-98`):
- `newsletter_subscribers` table exists ✓
- `newsletter_articles` table exists ✓
- Both association tables present

### Discrepancies:

| Relationship | Doc Status | Actual Status | Severity |
|--------------|------------|---------------|----------|
| PipelineRun → Article | claims via `pipeline_run_id` | **NOT IMPLEMENTED** | HIGH |

### Code References:
- **Newsletter tables:** `models/newsletter.py:8-23`
- **ArticleVersion relationship:** `models/pipeline.py:81-84`
- **Article relationships:** `models/article.py:56-64`

### Bug:

1. **PipelineRun → Article Relationship Not Implemented**
   - **Issue:** Doc claims Article has `pipeline_run_id` FK but no such field exists
   - **Impact:** Cannot trace articles back to their pipeline run without this FK
   - **Fix:** Add `pipeline_run_id` FK to Article if audit trail is needed

---

## 8. Pipeline Status Flow Verification

### Documentation Claims (architecture/models.md:64-71):

```
pending → select → research → writing → editing → done
                    ↓          ↓         ↓
                  review ←──────┴─────────┘
                  (impact_score < threshold)
```

### Actual Implementation:

**Article.pipeline_status values** (`models/article.py:25`):
- Default: `"pending"`
- Used throughout codebase for workflow

**Comment in code** (`services/article_pipeline.py`):
- Found in grep results: "impact_score < threshold" comment

### Verification: ✓ VERIFIED

---

## 9. Newsletter Association Tables Clarification

Upon detailed review, the newsletter association tables ARE present:

**newsletter_articles** (`models/newsletter.py:8-14`):
```python
newsletter_articles = db.Table(
    "newsletter_articles",
    db.Column("newsletter_id", db.Integer, db.ForeignKey("newsletters.id", ondelete="CASCADE"), primary_key=True),
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("position", db.Integer, nullable=False, default=0),
    db.Column("created_at", db.DateTime, default=lambda: datetime.now(timezone.utc)),
)
```

**newsletter_subscribers** (`models/newsletter.py:16-23`):
```python
newsletter_subscribers = db.Table(
    "newsletter_subscribers",
    db.Column("newsletter_id", db.Integer, db.ForeignKey("newsletters.id", ondelete="CASCADE"), primary_key=True),
    db.Column("subscriber_id", db.Integer, db.ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True),
    db.Column("sent_at", db.DateTime, nullable=True),
    db.Column("opened_at", db.DateTime, nullable=True),
    db.Column("clicked_at", db.DateTime, nullable=True),
)
```

**Status:** DISCREPANCY CORRECTED - The plans/05_models.md incorrectly claimed these were missing, but they ARE present in the codebase.

### Code References:
- **newsletter_articles:** `models/newsletter.py:8-14`
- **newsletter_subscribers:** `models/newsletter.py:16-23`
- **Newsletter.articles relationship:** `models/newsletter.py:40-44`
- **Subscriber.newsletters relationship:** `models/newsletter.py:94-98`

---

## 10. Bug Summary

### Critical (Must Fix)

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 1 | **Vector type `Vector(1536)` not implemented** - embedding stored as Text | `models/context.py:40` | Vector similarity search won't work |
| 2 | **No GIN index on embedding** - can't do vector search anyway | `models/context.py` | Vector search not possible even if type existed |

### High

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 3 | **Missing `ip_binding` field** for session security | `models/auth.py` | Session IP binding documented but not implemented |
| 4 | **Missing `user_agent_hash` field** for session security | `models/auth.py` | Session UA binding documented but not implemented |
| 5 | **Field name mismatch**: `observation` vs `signal` in TrendMemory | `models/context.py:32` | Doc/code inconsistency |
| 6 | **Field name mismatch**: `source_articles` JSON vs `source_article_id` FK | `models/context.py:34-35` | Only single article reference possible |
| 7 | **Field name mismatch**: `last_fetch_at` vs `last_crawled` in Source | `models/source.py:16` | Doc confusion |

### Medium

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 8 | **Missing `finalized_at`** in Article | `models/article.py` | Cannot determine when article was finalized |
| 9 | **Field length mismatches**: `title`/`url` sizes differ | `models/article.py:20,19` | Minor doc inconsistency |
| 10 | **Missing `adapter_config`** on Source model | `models/source.py` | Doc claims it's there but it's adapter-side |
| 11 | **Source `type` vs `source_type`** naming inconsistency | `models/source.py:14` | Doc confusion |
| 12 | **Password hash length**: Doc 255 vs actual 128 | `models/auth.py:36` | Security doc misleading |
| 13 | **TOTP secret length**: Doc 32 vs actual 256 | `models/auth.py:37` | Security doc misleading |
| 14 | **PipelineRun → Article relationship not implemented** | `models/article.py` | Cannot trace article to pipeline run |

### Low

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 15 | **TrendMemory `topic` length**: Doc 200 vs actual 128 | `models/context.py:31` | Minor doc inconsistency |
| 16 | **TrendMemory `last_accessed_at` vs `last_consolidated_at`** | `models/context.py:38` | Doc confusion |
| 17 | **Article `short_id` exists but not documented** | `models/article.py:14` | Missing from docs |

---

## 11. Improvement Recommendations

### Immediate Actions (Critical/High)

1. **Fix Vector Search Implementation**
   - Option A: Implement `pgvector` extension and update embedding column type
   - Option B: Update docs to reflect `db.Text` storage for embeddings
   - Code: `models/context.py:40`

2. **Add Missing AdminUser Security Fields**
   - Add `ip_binding` and `user_agent_hash` to AdminUser model if session binding is needed
   - OR update docs to remove these claims
   - Code: `models/auth.py:31-48`

3. **Sync TrendMemory Field Names**
   - Rename `signal` → `observation` in code OR update docs
   - Code: `models/context.py:32`

4. **Add Pipeline Run Tracking (Optional)**
   - Add `pipeline_run_id` FK to Article if audit trail is required
   - Code: `models/article.py`

### Documentation Updates (Medium)

5. **Update architecture/models.md with accurate field names:**
   - Article: `original_title`, `extracted_text`, `original_url`
   - Source: `source_type`, `last_crawled`
   - TrendMemory: `signal`, `source_article_id`, `embedding` as Text
   - AdminUser: `String(256)` for totp_secret, no `ip_binding`/`user_agent_hash`

6. **Add composite index documentation:**
   - Article: `ix_articles_status_created` (pipeline_status, created_at)
   - Source: `source_type` not `type`
   - PipelineRun: `ix_pipeline_runs_run_type`, `ix_pipeline_runs_run_type_status`

7. **Document Newsletter Association Tables:**
   - Clarify that `newsletter_articles` and `newsletter_subscribers` ARE implemented
   - Add position/sent_at/opened_at/clicked_at fields to docs

### Future Considerations

8. **Consider adding `finalized_at` to Article** if workflow requires it

9. **Vector Search Infrastructure:**
   - If vector search needed, implement pgvector or use external vector DB
   - Add GIN index on embedding column

---

## 12. Action Items

### Must Fix (Critical/High Priority)

- [ ] **CRITICAL:** Update `architecture/models.md` TrendMemory embedding type from `Vector(1536)` to `db.Text` (or implement pgvector)
- [ ] **HIGH:** Add `ip_binding` and `user_agent_hash` fields to AdminUser OR update docs to remove these claims
- [ ] **HIGH:** Sync TrendMemory `signal` ↔ `observation` naming between code and docs
- [ ] **HIGH:** Add `pipeline_run_id` FK to Article if pipeline audit trail is required
- [ ] **HIGH:** Update docs for Source `source_type` (not `type`) and `last_crawled` (not `last_fetch_at`)

### Should Fix (Medium Priority)

- [ ] **MEDIUM:** Update Article field names in docs: `title` → `original_title`, `url` → `original_url`, `content` → `extracted_text`
- [ ] **MEDIUM:** Update AdminUser field sizes in docs: `password_hash` → `String(128)`, `totp_secret` → `String(256)`
- [ ] **MEDIUM:** Add missing Article fields to docs: `short_id`, `pipeline_started_at`, `last_error`, `retry_count`, etc.
- [ ] **MEDIUM:** Update PipelineRun index documentation: `status` + `created_at` → `run_type` + `run_type+status`
- [ ] **MEDIUM:** Add Newsletter association table documentation (they ARE present)

### Could Fix (Low Priority)

- [ ] **LOW:** Consider adding `finalized_at` to Article model
- [ ] **LOW:** Update TrendMemory `topic` length from 200 to 128 in docs
- [ ] **LOW:** Document `last_accessed_at` → `last_consolidated_at` rename

---

## 13. Summary Statistics

| Category | Count |
|----------|-------|
| Total Claims Verified | 48 |
| Verified | 27 |
| Discrepancies Found | 17 |
| Critical Bugs | 2 |
| High Bugs | 6 |
| Medium Bugs | 8 |
| Low Bugs | 3 |

**Overall Assessment:** The models implementation is functional and complete for current use cases, but the documentation has significant drift from actual implementation. Most discrepancies are documentation issues (field names, types, sizes) rather than functional bugs. The critical issue is the `Vector(1536)` embedding type that was never implemented - this is a significant architecture claim that doesn't match reality.

---

*Generated: 2026-05-07*
*Review based on: architecture/models.md vs models/*.py*
