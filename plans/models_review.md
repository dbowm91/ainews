# Models Architecture Review

**Date:** 2026-05-21  
**Reviewer:** Architecture Verification Agent  
**Document Reviewed:** `architecture/models.md`

---

## Executive Summary

The architecture document `architecture/models.md` provides a high-level overview of the models package but contains several discrepancies with the actual implementation. Most critically, the pipeline status values, field names, and some relationship definitions do not match the actual code.

---

## Verified Correct

### File Inventory (lines 7-19)
All files listed exist and contain the expected models:
- `article.py`: Article, Citation - VERIFIED
- `source.py`: Source - VERIFIED
- `newsletter.py`: Newsletter, Subscriber, ArticleMetric - VERIFIED
- `pipeline.py`: PipelineRun, PipelineLog, ArticleVersion - VERIFIED
- `context.py`: TopicNote, TrendMemory - VERIFIED
- `webhook.py`: Webhook, WebhookEvent - VERIFIED
- `auth.py`: ApiToken, AdminUser - VERIFIED
- `tag.py`: Tag, article_tags - VERIFIED
- `search.py`: SearchQuery - VERIFIED
- `audit.py`: AuditLog - VERIFIED
- `share.py`: ShareConfig - VERIFIED

### Source Model Core Fields (lines 74-92)
- `source_type` field exists as `db.Column(db.String(32), nullable=False, index=True)` - VERIFIED (matches AGENTS.md note that type is actually source_type)
- `consecutive_failures` and `consecutive_successes` exist - VERIFIED
- `last_crawled` exists - VERIFIED (matches AGENTS.md note that last_fetch_at is actually last_crawled)
- `last_success_at` exists - VERIFIED

### AdminUser TOTP Fields (lines 94-112)
- `totp_secret` exists as `db.Column(db.String(256))` - VERIFIED
- `backup_codes` exists as `db.Column(db.JSON, nullable=True)` - VERIFIED

### TrendMemory Embedding Storage (lines 114-133)
- `embedding` is `db.Column(db.Text, nullable=True)` - VERIFIED (matches AGENTS.md note that embedding is db.Text, not vector type)

### Key Relationships (lines 21-38)
- Article -> Source (many-to-one) via `source_id` - VERIFIED
- Article -> Tag (many-to-many via article_tags) - VERIFIED
- Article -> Citation (one-to-many) - VERIFIED
- Article -> ArticleMetric (one-to-one via `uselist=False`) - VERIFIED
- Article -> ArticleVersion (one-to-many via `versions` backref) - VERIFIED
- PipelineRun -> PipelineLog (one-to-many) - VERIFIED
- Newsletter -> Article (many-to-many) - VERIFIED
- Newsletter -> Subscriber (many-to-many) - VERIFIED

### Newsletter Association Tables
- `newsletter_articles` table exists with proper FKs - VERIFIED
- `newsletter_subscribers` table exists with proper FKs - VERIFIED

---

## Discrepancies Found

### 1. Article Model Field Names (lines 44-61)

**Documentation shows:**
```python
title = Column(String(500))
url = Column(String(2000))
content = Column(Text)
```

**Actual Implementation (`models/article.py` lines 13-60):**
- `title` field does NOT exist; uses `original_title` instead
- `url` field does NOT exist; uses `original_url` instead  
- `content` field does NOT exist; uses `extracted_text`, `final_article`, `draft_article` instead
- `summary` field does NOT exist as a standalone column

**Impact:** Low - The documentation is simplified but the actual fields provide more granular data.

---

### 2. Article Pipeline Status Values (lines 55, 63-70)

**Documentation claims (line 55):**
```
pipeline_status = Column(String(50))  # pending, select, research, write, edit, review, done
```

**Status flow diagram (lines 65-69):**
```
pending → select → research → writing → editing → done
                    ↓          ↓         ↓
                  review ←──────┴─────────┘
```

**Actual Implementation (`services/pipeline_utils.py` lines 10-19):**
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

**Discrepancies:**
| Documentation | Actual Implementation |
|---------------|----------------------|
| `select` | `selecting`, `selected` |
| `research` | `researching` |
| `write` | `writing` |
| `edit` | `editing`, `written` |
| No `failed` status | `failed` used in tests |
| No `skipped` status | `skipped` used in tests |
| No `published` status | `published` used in tests |

**Impact:** Medium - Documentation is significantly simplified and doesn't reflect actual status values used in the pipeline.

---

### 3. Source Model Missing `adapter_config` (line 91)

**Documentation claims:**
```python
adapter_config = Column(JSON)  # Source-specific adapter settings
```

**Actual Implementation (`models/source.py`):**
- `adapter_config` field does NOT exist
- The `Source` model has: `source_key`, `name`, `url`, `feed_url`, `source_type`, `active`, `last_crawled`, `created_at`, `consecutive_failures`, `consecutive_successes`, `last_success_at`, `last_error`, `disabled_at`

**Impact:** Medium - Documentation shows a field that was never implemented (per AGENTS.md: "Source.adapter_config doesn't exist (documented but never implemented)").

---

### 4. TrendMemory `source_articles` Field (line 130)

**Documentation claims:**
```python
source_articles = Column(JSON)  # Related article IDs
```

**Actual Implementation (`models/context.py` lines 27-48):**
- `source_articles` field does NOT exist
- Instead has: `source_article_id = db.Column(db.Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)`

**Impact:** Medium - The relationship is inverted (single FK vs JSON array of IDs).

---

### 5. TrendMemory `last_accessed_at` Field (line 132)

**Documentation claims:**
```python
last_accessed_at = Column(DateTime)
```

**Actual Implementation:**
- `last_accessed_at` field does NOT exist
- Has `last_consolidated_at` instead (not documented)

**Impact:** Low - Field not used/incomplete documentation.

---

### 6. Source Index `type` vs `source_type` (line 140)

**Documentation claims:**
```markdown
Source: `name`, `type`
```

**Actual Implementation (`models/source.py`):**
- `name` has `index=True`
- `source_type` has `index=True`
- No field called simply `type`

**Impact:** Low - Minor naming clarification issue (likely meant `source_type`).

---

### 7. PipelineRun Index `status` (line 141)

**Documentation claims:**
```markdown
PipelineRun: `status`, `created_at`
```

**Actual Implementation (`models/pipeline.py`):**
- `status` does NOT have an index
- `finished_at` has `index=True`
- `run_type` has index via `ix_pipeline_runs_run_type`
- Composite index `ix_pipeline_runs_run_type_status` exists

**Impact:** Low - Documentation lists indexes that don't match implementation.

---

## Bugs Identified

### 1. TrendMemory Missing `last_accessed_at` Field

The `TrendMemory` model has `created_at` but no `last_accessed_at` field as documented. If this field is needed for cache invalidation or access tracking, it should be added.

**Location:** `models/context.py`  
**Suggested Fix:** Add `last_accessed_at = db.Column(db.DateTime, nullable=True)` to TrendMemory model.

---

## Improvement Suggestions

### 1. Update Pipeline Status Documentation

The architecture document's pipeline status section should be updated to reflect actual values:

**Current (incorrect):**
```
pending → select → research → writing → editing → done
```

**Should be:**
```
pending → selecting → selected → researching → writing → written → editing → review → done
                                        ↓           ↓
                                      review ←──────┴── (quality gate failure)
```

Additionally, these statuses exist but aren't documented: `failed`, `skipped`, `published`.

---

### 2. Document All Article Fields

The Article model has many more fields than documented. Consider adding a complete field listing or referring to the actual model definition.

---

### 3. Remove `adapter_config` from Documentation

Since `Source.adapter_config` was never implemented (per AGENTS.md), remove it from the architecture document or mark it as "not implemented".

---

### 4. Document ArticleMetric Relationship Direction

The documentation says "ArticleMetric (one-to-one)" but should clarify: **Article has one-to-one with ArticleMetric** (via `metrics` relationship with `uselist=False`).

---

### 5. Document Association Table Extra Fields

The `newsletter_subscribers` association table has additional fields beyond simple FKs:
- `sent_at`, `opened_at`, `clicked_at`

These should be documented.

---

## Questions for Architecture

### Q1: What is the intended future of `adapter_config`?

The `Source.adapter_config` field is documented but never implemented. Should it be:
- (a) Removed from documentation
- (b) Implemented in a future iteration
- (c) Replaced with a different configuration mechanism

### Q2: What is the relationship between `source_articles` and `source_article_id`?

The documentation shows `TrendMemory.source_articles` as a JSON array, but the implementation uses `source_article_id` as a single FK. Should TrendMemory track:
- (a) A single related article (current implementation)
- (b) Multiple related articles (documentation suggests)

### Q3: Is `last_accessed_at` on TrendMemory still needed?

If TrendMemory is used for semantic search caching, `last_accessed_at` could be valuable for cache invalidation. Is this field still needed or should it be removed from documentation?

### Q4: Pipeline Status Simplification

The actual pipeline has many more status values than documented. Should the architecture document:
- (a) Be updated to match actual implementation exactly
- (b) Continue showing simplified overview
- (c) Show the full state machine diagram

---

## Summary Table

| Item | Documentation | Actual | Status |
|------|--------------|--------|--------|
| Article.title | exists | `original_title` | DISCREPANCY |
| Article.url | exists | `original_url` | DISCREPANCY |
| Article.content | exists | `extracted_text` etc | DISCREPANCY |
| Article.pipeline_status values | select, research, write, edit | selecting, selected, researching, writing, written, editing | DISCREPANCY |
| Source.adapter_config | JSON field | doesn't exist | BUG/DOC |
| TrendMemory.source_articles | JSON field | `source_article_id` FK | DISCREPANCY |
| TrendMemory.last_accessed_at | exists | doesn't exist | MISSING |
| Source index `type` | exists | `source_type` index | DISCREPANCY |
| PipelineRun index `status` | exists | doesn't exist | DISCREPANCY |

---

*End of Review*
