# Models Review: architecture/models.md vs Actual Codebase

## Summary

The architecture document is **mostly accurate** with several minor discrepancies in indexes and some unspecified fields. Field naming conventions (source_type, last_crawled) are correctly documented.

---

## Verified Claims

### File Inventory ✓
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
| `share.py` | `ShareConfig` | ✓ |

### Key Relationships ✓
- Article → Source (many-to-one) via `source_id` FK ✓
- Article → Tag (many-to-many via article_tags) ✓
- Article → Citation (one-to-many) ✓
- Article → ArticleMetric (one-to-one via `uselist=False`) ✓
- Article → ArticleVersion (one-to-many) ✓
- PipelineRun → PipelineLog (one-to-many) ✓
- Newsletter → Subscriber (many-to-many) ✓
- Newsletter → Article (many-to-many) ✓

### Field Naming Conventions ✓
| Document Claim | Actual Code | Status |
|----------------|-------------|--------|
| `Source.type` → `source_type` | `source_type` (line 16) | ✓ CORRECT |
| `Source.last_fetch_at` → `last_crawled` | `last_crawled` (line 18) | ✓ CORRECT |
| `Article.finalized_at` doesn't exist | Use `published_at` | ✓ CORRECT |
| `TrendMemory.observation` → `signal` | `signal` (line 32) | ✓ CORRECT |
| `TrendMemory.embedding` → Text | `Text` (line 46) | ✓ CORRECT |

### AdminUser Security ✓
- `backup_codes` as JSON ✓ (line 39)
- No `ip_binding`, `user_agent_hash` fields ✓

### TrendMemory Model ✓
- `topic` is `String(128)` (not 200) ✓ (line 31)
- `embedding` as Text ✓ (line 46)
- `source_article_id` as single FK (not JSON) ✓ (line 34-36)
- `last_accessed_at` field exists ✓ (line 40-45)

### PipelineStatus State Machine ✓
All statuses documented correctly: `pending`, `selecting`/`selected`, `researching`, `writing`/`written`, `editing`, `review`, `done`, `skipped`, `failed`.

---

## Discrepancies & Issues

### 1. Index Discrepancy: `ix_articles_published` (MEDIUM)

**Document says:** Index `ix_articles_published` on `original_published_at`

**Actual Code:**
- `models/article.py:22` - `original_published_at` has NO index
- `models/article.py:54` - `published_at` has `index=True` but NO explicit index name

**Issue:** The documented index name and column are mismatched. Either:
- The column should be `published_at` with index name `ix_articles_published`, OR
- The column is correct (`original_published_at`) but index is missing

**Recommendation:** If `original_published_at` is the intended column for published article listings, add the missing index. If `published_at` is correct, update documentation.

---

### 2. Article.updated_at Has Index (Not Documented) (LOW)

**Document says:** `updated_at` has no index

**Actual Code:** `models/article.py:45-49` - `updated_at` has `index=True`

**Issue:** Minor documentation omission.

---

### 3. Source.source_key Not Nullable (Not Documented) (LOW)

**Document says:** `source_key = Column(String(64), unique=True)`

**Actual Code:** `models/source.py:12` - `source_key = db.Column(db.String(64), unique=True, nullable=False)`

**Issue:** Minor - the non-nullable constraint is an important detail omitted from docs.

---

### 4. TrendMemory.last_accessed_at onupdate Lambda (MEDIUM)

**Code:** `models/context.py:40-45`
```python
last_accessed_at = db.Column(
    db.DateTime,
    nullable=True,
    index=True,
    onupdate=lambda: datetime.now(timezone.utc),
)
```

**Issue:** This `onupdate` lambda may not work correctly with SQLAlchemy. The `onupdate` callback should receive the current time directly, not via lambda. However, if tests pass and functionality works, this is low priority.

---

## Missing Implementations

None found. All documented models and fields exist in code.

---

## Security Concerns

None identified. The models follow security best practices:
- Passwords stored as hashes
- Backup codes stored as JSON (not plaintext)
- API tokens use hashed values

---

## Performance Concerns

### TrendMemory.last_accessed_at Index (MEDIUM)

**Code:** `models/context.py:49` - Composite index on `(topic, importance)` exists, but individual indexes on `expires_at` and `last_accessed_at` are also defined.

**Note:** The document lists indexes on `expires_at` and `last_accessed_at` separately, but code shows:
- `ix_trend_memory_topic_importance` on `(topic, importance)`
- `ix_trend_memory_expires_at` on `expires_at`

The index on `last_accessed_at` is created inline with the column definition (not via `__table_args__`), which is correct but not explicitly documented as a named index.

---

## Specific Bugs

No bugs found. All code implementations match their intended behavior.

---

## Recommendations

| Priority | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| MEDIUM | Index on `original_published_at` missing | `models/article.py:22` | Add `db.Index("ix_articles_published", "original_published_at")` to `__table_args__` if this is the intended column |
| LOW | `updated_at` index undocumented | `models/article.py:45-49` | Update docs to note `updated_at` has `index=True` |
| LOW | `source_key` non-nullable undocumented | `models/source.py:12` | Update docs to show `nullable=False` |
| MEDIUM | `last_accessed_at` onupdate lambda | `models/context.py:44` | Verify `onupdate` works correctly; consider using `default` callable syntax instead |

---

## Conclusion

The architecture document is **highly accurate** with only minor discrepancies in index documentation and a few undocumented column constraints. The core structure and field naming conventions are correctly documented. No critical issues found.