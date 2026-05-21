# Models Module Architecture Review

## Summary of Verified Claims

| Claim | Status | Notes |
|-------|--------|-------|
| File inventory (10 files) | VERIFIED | All 10 model files exist with correct models |
| Article model fields (30+ fields) | VERIFIED | All fields present and accurate |
| Source model health tracking fields | VERIFIED | `consecutive_failures/successes`, `last_crawled` present |
| TrendMemory `signal` field name | VERIFIED | Actual field is `signal` (not `observation`) |
| TrendMemory `embedding` as Text | VERIFIED | `db.Column(db.Text, nullable=True)` |
| AdminUser 2FA + backup codes | VERIFIED | `totp_secret`, `totp_enabled`, `backup_codes` present |
| SourceConfig NOT in Source model | VERIFIED | Adapter config is in `schemas/source.py`, not model |
| Newsletter→Article m2m via `newsletter_articles` | VERIFIED | Association table exists |
| PipelineLog `meta` field (not `metadata`) | VERIFIED | `db.Column(db.JSON, nullable=True)` at line 57 |
| Article unique constraint `(source_id, external_id)` | VERIFIED | `uq_source_external_id` at line 67 |

## Discrepancies & Issues

### CRIT-1: Incorrect Relationship in Architecture Document

**Issue**: `architecture/models.md` line 33 claims:
```
Article (one-to-many) - via pipeline_run_id
```

**Reality**: The `Article` model has **no `pipeline_run_id` foreign key**. The relationship between `Article` and `PipelineRun` is **indirect** via `PipelineLog`:
- `PipelineLog.run_id` → `PipelineRun.id`
- `PipelineLog.article_id` → `Article.id`

There is no direct foreign key from `Article` to `PipelineRun`.

**Impact**: Documentation is misleading. Consumers expecting `article.pipeline_run_id` will fail.

**Fix**: Update architecture document to reflect actual relationship:
```
PipelineRun
├── PipelineLog (one-to-many)
└── Article (via PipelineLog.article_id - indirect many-to-many)
```

---

### CRIT-2: TrendMemory `source_articles` Field Does Not Exist

**Issue**: `architecture/models.md` line 176 claims:
```python
source_articles = Column(JSON)  # Related article IDs
```

**Reality**: The `TrendMemory` model has **no `source_articles` field**. The actual model (`models/context.py` lines 27-54) has:
- `source_article_id` (single FK to Article)
- `topic`
- `signal`
- `importance`
- `expires_at`
- `embedding`
- `created_at`
- `last_accessed_at`
- `last_consolidated_at`

**Impact**: Any code expecting `trend_memory.source_articles` will fail with `AttributeError`.

---

### MED-1: Missing `updated_at` Index Documentation

**Issue**: `architecture/models.md` line 194 lists indexes but states:
> "Plus individual indexes on: ... `updated_at` ..."

**Reality**: The `updated_at` column does have `index=True` at `models/article.py:48`, but:
1. The index is declared inline in the column definition, not as a separate `db.Index()` in `__table_args__`
2. The document incorrectly lists individual indexes without noting this distinction

**Impact**: Low - documentation is technically accurate but presentation is confusing.

---

### MED-2: TrendMemory Index `(topic, importance)` Documentation Incomplete

**Issue**: `architecture/models.md` line 197 says:
> "TrendMemory: indexes on `(topic, importance)`, `expires_at`, `last_accessed_at`"

**Reality**: All three indexes exist at `models/context.py:48-51`:
```python
db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
db.Index("ix_trend_memory_expires_at", "expires_at"),
```

**Verification**: Verified correct. However, the index name `ix_trend_memory_topic_importance` is not documented.

---

### LOW-1: Source Model `source_key` Not Documented as Unique

**Issue**: `architecture/models.md` line 118 documents `source_key` but does not note it has a unique constraint.

**Reality**: `models/source.py:10` shows:
```python
source_key = db.Column(db.String(64), unique=True, nullable=False)
```

**Impact**: Minor - unique constraint exists but isn't documented.

---

## Security & Performance Concerns

### Security: None Identified
- No security issues found in models layer
- Password hashing is external (werkzeug)
- TOTP handling is in services layer
- No SQL injection vectors

### Performance: Minor Concerns

**Issue**: `TrendMemory.last_accessed_at` uses `onupdate=datetime.utcnow` at `models/context.py:44`
- `datetime.utcnow` is deprecated in Python 3.12+
- Should use `datetime.now(timezone.utc)` for consistency with other models

**Issue**: `Source.created_at` uses complex lambda at `models/source.py:17`:
```python
default=lambda: __import__('datetime', fromlist=['datetime']).datetime.now(...)
```
- This pattern is harder to maintain than a direct import
- Inconsistent with other models using `from datetime import datetime, timezone`

---

## Recommendations

| Priority | Issue | Recommendation | File:Line |
|----------|-------|----------------|-----------|
| CRIT | pipeline_run_id relationship wrong | Fix architecture doc to show indirect relationship via PipelineLog | architecture/models.md:33 |
| CRIT | TrendMemory.source_articles doesn't exist | Fix architecture doc - field is `source_article_id` | architecture/models.md:176 |
| MED | `updated_at` index presentation | Clarify in doc that index is inline, not in __table_args__ | architecture/models.md:194 |
| MED | TrendMemory index name not documented | Add index name `ix_trend_memory_topic_importance` to doc | architecture/models.md:197 |
| LOW | `source_key` unique constraint | Document unique constraint in Source model description | architecture/models.md:118 |
| LOW | Deprecated datetime.utcnow | Replace with `datetime.now(timezone.utc)` | models/context.py:44 |
| LOW | Complex import in Source.created_at | Simplify lambda using direct import | models/source.py:17 |

---

## Bug Summary

| Bug | File | Line | Description |
|-----|------|------|-------------|
| BUG-1 | architecture/models.md | 33 | Wrong relationship - Article has no `pipeline_run_id` FK |
| BUG-2 | architecture/models.md | 176 | `TrendMemory.source_articles` field does not exist in model |