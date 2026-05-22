# Models Module Architecture Review

## Summary of Verified Claims

### File Inventory: VERIFIED ✓
All files exist and contain documented models:

| File | Models | Status |
|------|--------|--------|
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

### Relationships: VERIFIED ✓
Documented relationships are correct.

### Article Model: MOSTLY CORRECT
- Field inventory is accurate
- `pipeline_status` default is "pending" ✓
- `selector_result` is JSON ✓
- `research_brief` and `draft_article` are Text ✓
- `final_article` and `original_ai_article` are Text ✓
- `writer_model` exists ✓
- `embedding` is Text ✓

### Source Model: VERIFIED ✓
All fields match including health tracking fields.

### AdminUser Security: VERIFIED ✓
2FA fields present: `totp_secret`, `totp_enabled`, `backup_codes` as JSON.

## Discrepancies and Issues

### CRIT

1. **Article.updated_at missing index**
   - Document claims: `updated_at` has index (line 194)
   - Actual: No index exists on `updated_at` column in `models/article.py:45-49`
   - Impact: Queries filtering/sorting by `updated_at` may be slow

### HIGH

2. **TrendMemory.topic wrong size**
   - Document claims: `topic = Column(String(200))` (line 169)
   - Actual: `topic = db.Column(db.String(128), nullable=False, index=True)` in `models/context.py:31`
   - Impact: Truncated topic storage for topics > 128 chars

3. **TrendMemory.importance/expires_at undocumented**
   - Document does not mention `importance` (Integer, default=1) and `expires_at` fields
   - Actual: Both exist in `models/context.py:33,37`
   - Impact: Documentation incomplete, but code functions correctly

4. **Source.created_at missing index**
   - Document claims indexes on `disabled_at` (line 195)
   - Actual: No index on `created_at` in `models/source.py:19`
   - Impact: Minor - created_at queries may be slower

### MED

5. **Article.created_at index discrepancy**
   - Document claims individual index on `created_at` (line 194)
   - Actual: Only composite index `ix_articles_status_created` exists (article.py:68)
   - Impact: Queries on `created_at` alone use full scan unless composite helps

6. **TrendMemory.last_consolidated_at undocumented**
   - Field exists in `models/context.py:38` but not documented
   - Impact: Documentation incomplete

### LOW

7. **PipelineRun.started_at missing index**
   - Document claims indexes on `run_type`, composite on `(run_type, status)` (line 196)
   - Actual: No index on `started_at` in `models/pipeline.py:20`
   - Impact: Minor - sorting by start time may be slower

8. **TrendMemory.embedding nullable discrepancy**
   - Document says "Stored as text, not vector type" but doesn't specify nullable
   - Actual: `embedding = db.Column(db.Text, nullable=True)` in `models/context.py:46`
   - Impact: Minor - embedding can be null which may need handling

## Specific Bugs

| File:Line | Issue | Severity |
|-----------|-------|----------|
| `models/article.py:45-49` | `updated_at` has `index=True` but no separate index defined in `__table_args__` | CRIT |
| `models/context.py:31` | `topic` is String(128), document says String(200) | HIGH |
| `models/source.py:19` | `created_at` lacks index | MED |

## Recommendations

### CRIT
- **Add index on Article.updated_at**: Add `db.Index("ix_articles_updated_at", "updated_at")` to `Article.__table_args__` in `models/article.py:66-75`

### HIGH
- **Fix TrendMemory.topic size**: Change `String(128)` to `String(200)` in `models/context.py:31` to match documentation, OR update documentation to reflect actual 128 char limit
- **Update architecture document**: Add `importance`, `expires_at`, `last_consolidated_at` fields to TrendMemory section

### MED
- **Add Source.created_at index**: Add `db.Index("ix_sources_created_at", "created_at")` to Source table args (optional, low impact)
- **Update document**: Note that Article.created_at only has composite index, not individual

### LOW
- **Consider adding PipelineRun.started_at index**: If often sorted by start time
- **Document TrendMemory.embedding nullable**: Update docs to clarify embedding can be NULL

## Layering Violations
None found in models layer. Models correctly use `extensions.db` and do not import from `services` or `adapters`.

## Security Concerns
None found. AdminUser properly stores hashed passwords, uses JSON for backup codes, and TOTP secrets are appropriately sized.

## Performance Concerns
Missing indexes documented above. The `updated_at` index is the most impactful since articles are frequently sorted/filtered by update time.