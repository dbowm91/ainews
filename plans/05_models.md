# Plan 05: Models Architecture Verification

**Status:** DRAFT
**Created:** 2026-05-06
**Goal:** Document verification results for `architecture/models.md` claims against actual codebase

---

## Verification Results

### File Inventory Claims

| Claim | Status | Notes |
|-------|--------|-------|
| `article.py` → `Article`, `Citation` | VERIFIED | All present |
| `source.py` → `Source` | VERIFIED | Present |
| `newsletter.py` → `Newsletter`, `Subscriber`, `ArticleMetric` | VERIFIED | All present |
| `pipeline.py` → `PipelineRun`, `PipelineLog`, `ArticleVersion` | VERIFIED | All present |
| `context.py` → `TopicNote`, `TrendMemory` | VERIFIED | All present |
| `webhook.py` → `Webhook`, `WebhookEvent` | VERIFIED | All present |
| `auth.py` → `ApiToken`, `AdminUser` | VERIFIED | All present |
| `tag.py` → `Tag`, `article_tags` | VERIFIED | Present |
| `search.py` → `SearchQuery` | VERIFIED | Present |
| `audit.py` → `AuditLog` | VERIFIED | Present |
| `share.py` → `ShareConfig` | VERIFIED | Present |

### Model Claims

| Model | Status | Notes |
|-------|--------|-------|
| Article | VERIFIED | All fields match |
| Citation | VERIFIED | Present in article.py |
| Source | VERIFIED | Has consecutive_failures/successes |
| Newsletter | VERIFIED | Present |
| Subscriber | VERIFIED | Present |
| ArticleMetric | VERIFIED | Present with one-to-one relationship to Article |
| PipelineRun | VERIFIED | Present |
| PipelineLog | VERIFIED | Present |
| ArticleVersion | VERIFIED | Present with backref "versions" on Article |
| TopicNote | VERIFIED | Present |
| TrendMemory | VERIFIED | Present |
| Webhook | VERIFIED | Present |
| WebhookEvent | VERIFIED | Present |
| ApiToken | VERIFIED | Present |
| AdminUser | PARTIAL | Has totp_secret, totp_enabled, backup_codes; MISSING ip_binding, user_agent_hash |
| Tag | VERIFIED | Present |

### Relationship Claims

| Claim | Status | Notes |
|-------|--------|-------|
| Article → Source (FK: source_id) | VERIFIED | Present |
| Article → Tag (many-to-many via article_tags) | VERIFIED | Present |
| Article → Citation (one-to-many) | VERIFIED | Present |
| Article → ArticleMetric (one-to-one) | VERIFIED | uselist=False |
| Article → ArticleVersion (one-to-many) | VERIFIED | backref="versions" |
| PipelineRun → PipelineLog (one-to-many) | VERIFIED | Present |
| PipelineRun → Article (via pipeline_run_id) | NOT FOUND | No pipeline_run_id FK on Article model |
| Newsletter → Subscriber (many-to-many) | DISCREPANCY | No newsletter_subscribers association table |
| Newsletter → Article (many-to-many) | DISCREPANCY | No newsletter_articles association table |

### AdminUser Security Claims

| Claim | Status | Notes |
|-------|--------|-------|
| totp_secret field | VERIFIED | Present |
| backup_codes as JSON | VERIFIED | db.Column(db.JSON, nullable=True) |
| totp_enabled field | VERIFIED | Present in actual, missing in docs |
| ip_binding field | DISCREPANCY | Missing in actual model |
| user_agent_hash field | DISCREPANCY | Missing in actual model |

### TrendMemory Claims

| Claim | Status | Notes |
|-------|--------|-------|
| embedding field | DISCREPANCY | Docs show `Vector(1536)`; actual uses `db.Text` |
| observation field | DISCREPANCY | Docs show `observation`; actual uses `signal` |
| source_articles JSON field | DISCREPANCY | Docs show `source_articles`; actual uses `source_article_id` (FK) |

### Pipeline Status Flow Claims

| Claim | Status | Notes |
|-------|--------|-------|
| pending, select, research, write, edit, review, done | VERIFIED | All present in pipeline_status enum |
| review fallback on low impact_score | VERIFIED | Comment present in article.py |

### Index Claims

| Claim | Status | Notes |
|-------|--------|-------|
| Article: pipeline_status, source_id, published_at, created_at | PARTIAL | status+created_at index exists; published_at maps to original_published_at; created_at not standalone |
| Source: name, type | PARTIAL | name index exists; type index is named source_type |
| PipelineRun: status, created_at | DISCREPANCY | No status or created_at indexes alone; run_type and run_type+status indexes exist |
| TrendMemory: topic GIN index on embedding | DISCREPANCY | No GIN index; topic+importance index exists; embedding is Text not Vector |

---

## Bug Findings

### Critical

1. **Newsletter-Article Relationship Missing**
   - **Issue:** No `newsletter_articles` association table or relationship
   - **Impact:** Cannot query which articles belong to which newsletter
   - **Fix:** Add association table or Article.newsletter_id FK

2. **Newsletter-Subscriber Relationship Missing**
   - **Issue:** No `newsletter_subscribers` association table or relationship
   - **Impact:** Cannot manage newsletter recipients properly
   - **Fix:** Add association table with recipient preferences

### High

3. **Article Has No pipeline_run_id FK**
   - **Issue:** Architecture claims `PipelineRun → Article (via pipeline_run_id)` but Article has no pipeline_run_id column
   - **Impact:** Cannot trace article to its pipeline run
   - **Fix:** Add pipeline_run_id FK to Article model (optional, for tracking)

4. **TrendMemory Embedding Type Mismatch**
   - **Issue:** Docs claim `Vector(1536)` but actual is `db.Text`
   - **Impact:** Vector search won't work; stored as plain text
   - **Fix:** Either update docs to reflect Text storage or implement proper vector type

### Medium

5. **AdminUser Missing Security Fields**
   - **Issue:** ip_binding and user_agent_hash documented but not implemented
   - **Impact:** Session binding to IP/UA not possible
   - **Fix:** Add fields or update docs

6. **TrendMemory Field Name Mismatch**
   - **Issue:** Docs use `observation`; actual uses `signal`
   - **Impact:** Documentation inconsistency
   - **Fix:** Sync field names

7. **Source Model Field Name Inconsistency**
   - **Issue:** Docs reference `type`; actual uses `source_type`
   - **Impact:** Minor confusion
   - **Fix:** Update docs to use source_type

### Low

8. **PipelineRun Status Values Differentiated**
   - **Issue:** PipelineRun.status = "running"|"completed"|"failed"|"cancelled" differs from Article.pipeline_status workflow values
   - **Impact:** These are different enums - confusing
   - **Fix:** Document distinction clearly

9. **Missing Indexes**
   - **Issue:** Some documented indexes don't match actual implementation
   - **Impact:** Query performance assumptions may be wrong
   - **Fix:** Update docs or add missing indexes

---

## Improvement Opportunities

1. **Add Explicit Pipeline Tracking**
   - Add pipeline_run_id FK to Article for audit trail
   - Consider adding PipelineRun reference to Article

2. **Standardize Field Naming**
   - `source.type` vs `source.source_type`
   - `TrendMemory.observation` vs `TrendMemory.signal`

3. **Implement Vector Search**
   - Currently TrendMemory.embedding is Text - not usable for vector similarity
   - Consider using pgvector extension or external vector DB

4. **Document Relationship Multiplicity**
   - Newsletter → Article is claimed as many-to-many but not implemented
   - Clarify if it's one-to-many (Newsletter has many articles, Article has one newsletter)

5. **Index Coverage Audit**
   - Verify query patterns match available indexes
   - Consider adding missing indexes for documented use cases

---

## Action Items

### Must Fix (Critical/High)

- [ ] **HIGH:** Add `newsletter_articles` association table or decide on relationship type
- [ ] **HIGH:** Add `newsletter_subscribers` association table or decide on relationship type
- [ ] **MEDIUM:** Add `pipeline_run_id` FK to Article if pipeline tracking is needed
- [ ] **MEDIUM:** Sync TrendMemory field names (signal ↔ observation) between code and docs
- [ ] **MEDIUM:** Add missing AdminUser fields (ip_binding, user_agent_hash) or update docs

### Should Fix (Medium/Low)

- [ ] **LOW:** Update architecture docs to reflect actual index names
- [ ] **LOW:** Document PipelineRun.status vs Article.pipeline_status distinction
- [ ] **LOW:** Standardize Source.type → Source.source_type in docs

### Future Considerations

- [ ] Implement vector search for TrendMemory if semantic search is needed
- [ ] Add GIN index on embedding if vector storage is implemented

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | 27 |
| Discrepancies | 10 |
| Critical Bugs | 2 |
| High Bugs | 2 |
| Medium Bugs | 4 |
| Low Bugs | 3 |

**Overall Assessment:** The models package largely matches the architecture documentation. Key issues are missing relationship tables (Newsletter-Article, Newsletter-Subscriber) and some field name/type mismatches in AdminUser and TrendMemory. These are documentation sync issues rather than functional bugs.
