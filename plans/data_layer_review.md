# Data Layer Review: `architecture/models.md` and `architecture/schemas.md`

Generated from codebase audit on 2026-05-28.

---

## Verified Claims

### models.md

- **File Inventory table**: All 11 model files and their exported classes are correctly listed (article.py, source.py, newsletter.py, pipeline.py, context.py, webhook.py, auth.py, tag.py, search.py, audit.py, share.py).
- **Article model field names and types**: All 30 fields match `models/article.py:10-60`. Field names, types, defaults, and constraints are accurate.
- **Source model field names**: `source_type` (not `type`), `last_crawled` (not `last_fetch_at`) — confirmed at `models/source.py:16,18`.
- **Newsletter model**: All fields match `models/newsletter.py:26-38`. `delivered_count` and `error_message` exist as documented.
- **Subscriber model fields**: All fields match `models/newsletter.py:50-76`. Preferences, bounce tracking, and `last_active_at` all present.
- **AdminUser 2FA fields**: `totp_secret`, `totp_enabled`, `backup_codes` (JSON) all confirmed at `models/auth.py:37-39`.
- **TrendMemory field names**: `signal` (not `observation`), `embedding` as `db.Text` — confirmed at `models/context.py:32,46`.
- **PipelineStatus enum values**: All 11 values in `constants.py:30-43` match documentation (PENDING, SELECTING, SELECTED, RESEARCHING, WRITING, WRITTEN, EDITING, REVIEW, DONE, SKIPPED, FAILED).
- **Article composite indexes**: All 7 composite indexes in `__table_args__` at `models/article.py:66-75` match documentation exactly.
- **Unique constraint on (source_id, external_id)**: Confirmed at `models/article.py:67` with name `uq_source_external_id`.
- **PipelineRun indexes**: `ix_pipeline_runs_run_type`, `ix_pipeline_runs_run_type_status`, and `started_at` index all match `models/pipeline.py:27-30`.
- **TrendMemory composite indexes**: `ix_trend_memory_topic_importance` and `ix_trend_memory_expires_at` match `models/context.py:48-51`.
- **Source indexes**: `consecutive_failures` and `disabled_at` indexed, `active` indexed, `source_key` unique — all confirmed.

### schemas.md

- **PipelineRootConfig structure**: All 7 fields match `schemas/pipeline.py:150-159`.
- **StageConfig stub**: Confirmed — only has `tools: list[str]` field at `schemas/pipeline.py:141-147`.
- **SubagentConfig has no `enabled` field**: Confirmed at `schemas/pipeline.py:121-125`. Only `SubagentStageConfig` has `enabled`.
- **SubagentStageConfig fields**: All fields and defaults match `schemas/pipeline.py:93-105`.
- **SubagentChainConfig/SubagentChainStep**: Fields and defaults match `schemas/pipeline.py:108-118`.
- **MemoryConfig fields and defaults**: All 10 fields match `schemas/pipeline.py:128-138`.
- **NewsletterConfig fields and defaults**: All 5 fields match `schemas/pipeline.py:52-57`.
- **SourceConfig fields**: All 7 fields match `schemas/source.py:106-113`.
- **RSSConfig fields**: All 5 fields match `schemas/source.py:29-39`.
- **APIConfig fields**: All 14 fields match `schemas/source.py:42-56`.
- **TopicMatchConfig fields**: All 3 fields match `schemas/source.py:23-26`.
- **WebConfig, ListingConfig, ArticleSelectors**: All fields match `schemas/source.py:73-96`.
- **PaginationConfig with validator**: Fields and `validate_pagination_type` match `schemas/source.py:59-70`.
- **SelectionResult fields**: All 6 fields match `schemas/llm_responses.py:16-22`.
- **ResearchBrief and sub-models**: All fields match `schemas/llm_responses.py:53-81` (KeyClaim, DirectQuote, ExternalSource, RelatedArticle).
- **CondensedArticle fields**: All 9 fields match `schemas/llm_responses.py:101-129`.
- **ExecutiveSummary**: Single `summary` field confirmed at `schemas/llm_responses.py:151-158`.
- **NewsletterBrief fields**: `themes`, `highlight`, `connections` confirmed at `schemas/llm_responses.py:142-148`.
- **SubagentResponse, ResearchSynthesisResponse, EditContextualizationResponse**: All match `schemas/llm_responses.py:164-183`.
- **ToolCall, ToolResult, ToolCallingResponse**: All match `schemas/llm_responses.py:186-202`.
- **SelectArticleTask fields**: Match `schemas/tasks.py:33-42`.
- **ProcessItemTask fields and validators**: All match `schemas/tasks.py:87-117`.
- **GenerateNewsletterTask**: Fields match `schemas/tasks.py:45-56` (note: has email validator).
- **CleanupArticleVersionsTask**: Fields match `schemas/tasks.py:73-84`.
- **schemas/common.py layer violation**: Confirmed — imports `services.config_cache` at `schemas/common.py:74,89`.

---

## Incorrect Claims

### HIGH Priority

1. **Article `created_at`/`updated_at` use deprecated `datetime.utcnow`**
   - **Doc** (`models.md:86-87`): `default=datetime.utcnow`
   - **Code** (`models/article.py:44-49`): `default=lambda: datetime.now(timezone.utc)`
   - Both fields use timezone-aware `datetime.now(timezone.utc)` lambdas, not `datetime.utcnow`. The `datetime.utcnow` is deprecated since Python 3.12. Zero occurrences of `datetime.utcnow` exist in the entire models/ package.

2. **Source `name` is NOT nullable and IS indexed**
   - **Doc** (`models.md:119`): `name = Column(String(128))` (implies nullable)
   - **Code** (`models/source.py:13`): `name = db.Column(db.String(128), nullable=False, index=True)`
   - Missing both `nullable=False` and `index=True`.

3. **Article `source_id` FK missing `ondelete="CASCADE"`**
   - **Doc** (`models.md:51`): `source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)`
   - **Code** (`models/article.py:15-17`): `db.ForeignKey("sources.id", ondelete="CASCADE")`
   - The cascade delete behavior is significant and undocumented.

4. **`SendEmailTask` missing email validator**
   - **Doc** (`schemas.md:328-330`): Implies email field has validation
   - **Code** (`schemas/tasks.py:59-63`): No `@field_validator("email")` on `SendEmailTask`. Email format is NOT validated. Compare with `GenerateNewsletterTask` which DOES have `@field_validator("dry_run_email")`.

5. **`SelectArticleInput` does not exist**
   - **Doc** (`schemas.md:376`): `input_data = SelectArticleInput(article_id=article_id)`
   - **Code**: No class named `SelectArticleInput` exists anywhere. The actual class is `SelectArticleTask` (`schemas/tasks.py:33`).

6. **`NewsletterPipelineConfig` fields are NOT required**
   - **Doc** (`schemas.md:44-47`): Shows fields as required (`reader: RoleConfig`, etc.)
   - **Code** (`schemas/pipeline.py:60-90`): All three fields have `default_factory=lambda: RoleConfig(...)` with sensible defaults.

### MEDIUM Priority

7. **PipelineStatus transitions example is wrong**
   - **Doc** (`models.md:52-60`): Shows simplified transitions without SELECTING/SELECTED, and omits FAILED→PENDING.
   - **Code** (`constants.py:52-64`): Includes SELECTING→SELECTED, SELECTED→RESEARCHING, and FAILED→PENDING transitions.

8. **Pipeline flow diagram is oversimplified**
   - **Doc** (`models.md:101-105`): Shows `pending → selecting → selected → researching → writing → written → editing → review → done`
   - **Code** (`constants.py:52-64`): PENDING can go directly to RESEARCHING (skipping select), EDITING can go directly to DONE (bypassing review), and FAILED can return to PENDING.

9. **Article `versions` relationship does NOT exist on Article model**
   - **Doc** (`models.md:29`): Lists `ArticleVersion (one-to-many) - edit history` as an Article relationship
   - **Code**: The `versions` backref is defined on `ArticleVersion` (`models/pipeline.py:81-83`), not on Article. While SQLAlchemy backrefs make it accessible as `article.versions`, it's architecturally misleading to list it as an Article-defined relationship.

10. **Subscriber unique constraint on (email, newsletter_type) undocumented**
    - **Doc** (`models.md:159-175`): No mention of unique constraint
    - **Code** (`models/newsletter.py:78-80`): `db.UniqueConstraint("email", "newsletter_type", name="uq_email_newsletter")`

11. **AdminUser `username` IS indexed**
    - **Doc** (`models.md:186`): `username = Column(String(64), unique=True)` (no index mentioned)
    - **Code** (`models/auth.py:35`): `db.Column(db.String(64), unique=True, nullable=False, index=True)`

12. **TrendMemory field order is wrong in doc**
    - **Doc** (`models.md:208-222`): Shows `topic, signal, importance, expires_at, last_consolidated_at, embedding, source_article_id, created_at, last_accessed_at`
    - **Code** (`models/context.py:30-46`): Actual order is `topic, signal, importance, source_article_id, expires_at, last_consolidated_at, created_at, last_accessed_at, embedding`

13. **Missing Article relationships in doc**
    - **Doc** (`models.md:24-37`): Only shows Citation in relationship tree
    - **Code** (`models/article.py:56-63`): Article has `citations`, `tags`, and `metrics` relationships. The `tags` and `metrics` relationships are not mentioned anywhere in the documentation.

---

## Improvement Opportunities

### HIGH Priority

1. **Add complete TopicNote model documentation**
   - `TopicNote` is listed in file inventory but has no field listing or schema doc. It has 5 fields (`id`, `topic`, `note`, `source`, `created_at`, `updated_at`) and a unique constraint on `(topic, source)` at `models/context.py:21`.
   - Priority: HIGH

2. **Document Article relationships completely**
   - Add `citations` (one-to-many, selectin lazy), `tags` (many-to-many via article_tags, selectin lazy), and `metrics` (one-to-one, selectin lazy) to the relationship diagram.
   - Priority: HIGH

3. **Document Newsletter association table columns**
   - `newsletter_articles` has `position` and `created_at` columns (`models/newsletter.py:12-13`). `newsletter_subscribers` has `sent_at`, `opened_at`, `clicked_at` columns (`models/newsletter.py:20-22`). These are not documented.
   - Priority: MEDIUM

4. **Add missing schemas to schemas.md**
   - `schemas/common.py`: `ProviderDef` schema (used by LLM and search providers)
   - `schemas/admin.py`: `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams` (5 schemas)
   - `schemas/webhook.py`: `WebhookCreate` and `WebhookResponse` (listed in inventory but not fully documented)
   - `schemas/llm.py`: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig` (listed in inventory but not documented)
   - Priority: MEDIUM

5. **Document SourceConfig validator logic**
   - `schemas/source.py:115-131` has two validators: `validate_type` (ensures type is rss/api/web) and `validate_adapter_config` (validates config dict against the appropriate adapter schema). The doc mentions `validate_adapter_config` in a comment but doesn't explain the logic.
   - Priority: MEDIUM

### LOW Priority

6. **Add PipelineLog meta field documentation**
   - `PipelineLog` has a `meta` (not `metadata`) JSON field at `models/pipeline.py:57`. This is documented in AGENTS.md but not in models.md.
   - Priority: LOW

7. **Document ArticleVersion unique constraint**
   - `ArticleVersion` has a unique constraint on `(article_id, version_number)` at `models/pipeline.py:87`.
   - Priority: LOW

8. **Document SearchQuery relationship**
   - `SearchQuery` has a `clicked_article` relationship at `models/search.py:19`. Not documented.
   - Priority: LOW

---

## Stale Content

1. **`datetime.utcnow` references** (models.md:86-87)
   - The doc uses `datetime.utcnow` which is deprecated. The code uses `datetime.now(timezone.utc)`.
   - Priority: HIGH

2. **Pipeline status flow diagram** (models.md:101-105)
   - The diagram doesn't reflect the actual VALID_TRANSITIONS in constants.py. Missing SELECTING, SELECTED states and FAILED→PENDING transition.
   - Priority: MEDIUM

3. **`SelectArticleInput` reference** (schemas.md:376)
   - References a class that doesn't exist. Should be `SelectArticleTask`.
   - Priority: MEDIUM

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | ~45 |
| Incorrect Claims | 13 |
| Improvement Opportunities | 8 |
| Stale Content | 3 |

### Critical Fixes Needed (HIGH)

1. Fix `datetime.utcnow` → `datetime.now(timezone.utc)` in Article doc (models.md:86-87)
2. Fix Source `name` to include `nullable=False, index=True` (models.md:119)
3. Add `ondelete="CASCADE"` to Article `source_id` FK doc (models.md:51)
4. Add email validator to `SendEmailTask` doc OR note its absence (schemas.md:328-330)
5. Fix `SelectArticleInput` → `SelectArticleTask` in usage example (schemas.md:376)
6. Fix `NewsletterPipelineConfig` to show default factories (schemas.md:44-47)
7. Add complete TopicNote model documentation (models.md)
8. Add missing Article relationships (citations, tags, metrics) to doc
