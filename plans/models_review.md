# Models Architecture Review

Review Date: 2026-05-12
Reference: `/Users/davidbowman/projects/ainews/architecture/models.md`

---

## Verified Claims

### Field Naming Conventions (Correct)
| Claim | Actual | Status |
|-------|--------|--------|
| `Source.type` is actually `source_type` | Confirmed: `source.py` line 14 uses `source_type` | VERIFIED |
| `Source.last_fetch_at` is actually `last_crawled` | Confirmed: `source.py` line 16 uses `last_crawled` | VERIFIED |
| `TrendMemory.observation` is actually `signal` | Confirmed: `context.py` line 32 uses `signal` | VERIFIED |
| `TrendMemory.embedding` is `db.Text` | Confirmed: `context.py` line 40 uses `db.Text` (not vector type) | VERIFIED |
| `Article.finalized_at` doesn't exist | Confirmed: No `finalized_at` field; `article.py` uses `published_at` (line 54) | VERIFIED |

### Model Relationships (Correct)
| Claim | Evidence | Status |
|-------|----------|--------|
| Article → Source (many-to-one) | `article.py` line 15-17: `source_id` FK to `sources.id` | VERIFIED |
| Article → Citation (one-to-many) | `article.py` line 56-58 | VERIFIED |
| Article → Tag (many-to-many via article_tags) | `article.py` line 61 with `article_tags` table from `tag.py` | VERIFIED |
| Article → ArticleMetric (one-to-one) | `article.py` line 62-64 with `uselist=False` | VERIFIED |
| Article → ArticleVersion (one-to-many) | `pipeline.py` line 81-84 via backref `versions` | VERIFIED |
| PipelineRun → PipelineLog (one-to-many) | `pipeline.py` line 23-25 | VERIFIED |
| PipelineRun → Article (one-to-many via pipeline_run_id) | Not implemented - no `pipeline_run_id` FK on Article | VERIFIED |
| Newsletter → Subscriber (many-to-many via newsletter_subscribers) | `newsletter.py` line 16-23 table definition | VERIFIED |
| Newsletter → Article (many-to-many via newsletter_articles) | `newsletter.py` line 8-14 table definition | VERIFIED |
| TrendMemory → Article (many-to-one via source_article_id) | `context.py` line 34-36 FK to articles | VERIFIED |

### File Inventory (Correct)
All files listed in the architecture document exist and contain the documented models:
- `article.py`: Article, Citation
- `source.py`: Source
- `newsletter.py`: Newsletter, Subscriber, ArticleMetric (with association tables)
- `pipeline.py`: PipelineRun, PipelineLog, ArticleVersion
- `context.py`: TopicNote, TrendMemory
- `webhook.py`: Webhook, WebhookEvent
- `auth.py`: ApiToken, AdminUser
- `tag.py`: Tag, article_tags
- `search.py`: SearchQuery
- `audit.py`: AuditLog

### Index Definitions
| Model | Indexes Listed | Actual Indexes | Status |
|-------|----------------|----------------|--------|
| Article | `pipeline_status`, `source_id`, `published_at`, `created_at` | Additional: `short_id`, `external_id`, `original_title`, `category`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `experiment_group` + composite indexes | VERIFIED with additions |
| Source | `name`, `type` | Additional: `source_key` (unique), `active`, `consecutive_failures`, `disabled_at` | VERIFIED with additions |
| PipelineRun | `status`, `created_at` | `finished_at` index, plus composite indexes on `run_type`, `run_type+status` | VERIFIED with additions |
| TrendMemory | `topic` | `topic` index exists, plus composite `topic_importance`, `expires_at` | VERIFIED with additions |

---

## Discrepancies

### 1. PipelineRun → Article Relationship Not Implemented
**Severity:** Medium
**Location:** `architecture/models.md` line 33

The architecture document claims:
```
PipelineRun
├── Article (one-to-many) - via pipeline_run_id
```

However, the `Article` model has **no `pipeline_run_id` field** or any FK relationship to `PipelineRun`. The `PipelineRun` model has no `articles` relationship either.

**Impact:** Cannot query "all articles processed by a given pipeline run" directly from the database. The relationship is logical, not enforced.

---

### 2. AdminUser Missing Fields (Documented but Not Implemented)
**Severity:** Low (documented as not implemented)
**Location:** `architecture/models.md` line 111

The document explicitly states:
```
# Note: ip_binding and user_agent_hash not implemented
```

This is correctly documented as not implemented. However, the architecture doc does not mention that `totp_enabled` field exists (line 38 of `auth.py`).

---

### 3. TrendMemory Missing `source_articles` JSON Field
**Severity:** Low
**Location:** `architecture/models.md` line 130

The architecture document shows:
```python
source_articles = Column(JSON)  # Related article IDs
```

But `context.py` line 34-36 shows:
```python
source_article_id = db.Column(
    db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
)
```

The actual implementation uses a single FK (`source_article_id`) rather than a JSON array of article IDs.

---

### 4. Source Missing `adapter_config` Field
**Severity:** Medium
**Location:** `architecture/models.md` line 91

The architecture document shows:
```python
adapter_config = Column(JSON)  # Source-specific adapter settings
```

But `source.py` does **not** have an `adapter_config` field. The Source model only has:
- `source_key`, `name`, `url`, `feed_url`, `source_type`, `active`
- Health tracking: `last_crawled`, `consecutive_failures`, `consecutive_successes`, `last_success_at`, `last_error`, `disabled_at`

The `adapter_config` documented field is not implemented.

---

### 5. Article Model Has Significant Additional Fields
**Severity:** Informational
**Location:** `models/article.py`

The actual Article model is much more complex than the architecture document suggests:

**Additional fields not documented:**
- `short_id`, `external_id`, `original_url`, `original_title`, `original_author`, `original_published_at`
- `extracted_text`, `selector_result`, `research_brief`, `draft_article`, `final_article`, `original_ai_article`
- `writer_model`, `summary`, `category`, `topics`, `raw_metadata`, `extraction_status`
- `retry_count`, `total_retries`, `degradation_count`, `pipeline_started_at`, `last_error`
- `crawled_at`, `selected_at`, `scheduled_publish_at`, `experiment_group`, `embedding`

This suggests the architecture document is significantly outdated relative to the actual model.

---

### 6. Newsletter Model Missing `recipients` Implementation Detail
**Severity:** Informational
**Location:** `architecture/models.md` vs `newsletter.py`

The document shows Newsletter with `recipients` field but the actual `Newsletter` model has `recipients = db.Column(db.Integer, default=0)` at line 34, which appears to store a count rather than being a relationship.

---

## Improvement Recommendations

### 1. Update Architecture Document
The architecture document is significantly outdated.
- Document all actual Article fields
- Remove `adapter_config` from Source documentation or implement it
- Update TrendMemory to reflect single FK (`source_article_id`) instead of JSON array
- Document composite indexes explicitly

### 2. Add PipelineRun → Article Relationship
If articles should track which pipeline run fetched/processed them:

```python
# In Article model, add:
pipeline_run_id = db.Column(
    db.Integer, db.ForeignKey("pipeline_runs.id", ondelete="SET NULL"), 
    nullable=True, index=True
)
```

### 3. Consider Adding `adapter_config` to Source
If source-specific adapter settings are needed, add to `source.py`:
```python
adapter_config = db.Column(db.JSON, nullable=True)
```

### 4. Standardize Index Naming
Currently indexes mix implicit (`index=True`) and explicit (`db.Index("ix_...")`) naming. Consider:
- Use explicit `ix_table_column` naming for all
- Document composite indexes in architecture

### 5. Source Model Missing `url` Index
The `Source.url` field (line 12) lacks an index but may be queried by URL.

---

## Bugs Found

### 1. TrendMemory Missing `source_articles` JSON Array (Not a Bug, but Misleading Docs)
**File:** `architecture/models.md` line 130
**Issue:** The documentation claims `source_articles = Column(JSON)` but the actual field is `source_article_id` FK.
**Recommendation:** Update documentation to match implementation.

### 2. Source.adapter_config Not Implemented
**File:** `source.py` / `architecture/models.md` line 91
**Issue:** `adapter_config` is documented but not present in the model.
**Impact:** Sources cannot store adapter-specific configuration.

---

## Layer Violations

### None Found

The models layer is a standalone SQLAlchemy layer with no imports from `services`, `adapters`, or other higher-level modules. This is correct.

**Verification:**
- `models/__init__.py` only imports from local model files
- No model files import from `services/` or `adapters/`
- Extensions are imported from `extensions` (db instance)

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 14 |
| Discrepancies | 6 |
| Improvement Recommendations | 5 |
| Bugs Found | 2 |
| Layer Violations | 0 |

**Overall Assessment:** The architecture document has significant discrepancies with actual code, particularly around the Article model complexity and missing `adapter_config` field. Field naming conventions are correctly documented. Relationships are mostly accurate except PipelineRun→Article which is documented but not implemented.
