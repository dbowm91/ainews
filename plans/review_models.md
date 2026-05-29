# Review: architecture/models.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

### File Inventory
- `article.py` → Article, Citation — CORRECT (`models/article.py:10,86`)
- `source.py` → Source — CORRECT (`models/source.py:8`)
- `newsletter.py` → Newsletter, Subscriber, ArticleMetric — CORRECT (`models/newsletter.py:26,50,101`)
- `pipeline.py` → PipelineRun, PipelineLog, ArticleVersion — CORRECT (`models/pipeline.py:8,36,63`)
- `context.py` → TopicNote, TrendMemory — CORRECT (`models/context.py:8,27`)
- `webhook.py` → Webhook, WebhookEvent — CORRECT (`models/webhook.py:8,32`)
- `auth.py` → ApiToken, AdminUser — CORRECT (`models/auth.py:8,31`)
- `tag.py` → Tag, article_tags — CORRECT (`models/tag.py:6,24`)
- `search.py` → SearchQuery — CORRECT (`models/search.py:8`)
- `audit.py` → AuditLog — CORRECT (`models/audit.py:8`)
- `share.py` → ShareConfig — CORRECT (`models/share.py:6`)

### Article Model Fields (30+ claim)
- 35 columns confirmed in `models/article.py` — CORRECT

### Article Model Field Details
- All documented field names, types, and defaults verified against `models/article.py:10-75`
- `pipeline_status` default="pending" — CORRECT (`models/article.py:25`)
- `selector_result` as JSON — CORRECT (`models/article.py:26`)
- `total_retries` nullable=False, default=0 — CORRECT (`models/article.py:40`)
- `degradation_count` nullable=False, default=0 — CORRECT (`models/article.py:41`)
- `experiment_group` nullable=True, index=True — CORRECT (`models/article.py:59`)
- `embedding` as Text — CORRECT (`models/article.py:60`)

### Article Relationships
- `citations` with backref="article", lazy="selectin", cascade — CORRECT (`models/article.py:56-58`)
- `tags` with secondary=article_tags — CORRECT (`models/article.py:61`)
- `metrics` with uselist=False — CORRECT (`models/article.py:62-64`)

### PipelineStatus & Transitions
- `constants.py:VALID_TRANSITIONS` matches documented transitions — CORRECT (`constants.py:52-64`)
- `pending → selecting` and `pending → reviewing` — CORRECT (`constants.py:53`)
- `selecting → selected` — CORRECT (`constants.py:54`)
- `selected → researching` — CORRECT (`constants.py:55`)
- `editing → review, done, failed` — CORRECT (`constants.py:59`)
- `review → done, failed` — CORRECT (`constants.py:60`)
- `done` terminal — CORRECT (`constants.py:61`)
- `failed → pending` — CORRECT (`constants.py:63`)

### Source Model
- Field names `source_type` (not `type`), `last_crawled` (not `last_fetch_at`) — CORRECT (`models/source.py:16,18`)
- `source_key` unique=True — CORRECT (`models/source.py:12`)
- `active` default=True — CORRECT (`models/source.py:17`)
- `consecutive_failures` default=0 — CORRECT (`models/source.py:21`)
- `consecutive_successes` default=0 — CORRECT (`models/source.py:22`)
- `disabled_at` nullable=True — CORRECT (`models/source.py:25`)

### Newsletter Association Tables
- `newsletter_articles` with position and created_at — CORRECT (`models/newsletter.py:8-14`)
- `newsletter_subscribers` with sent_at, opened_at, clicked_at — CORRECT (`models/newsletter.py:16-23`)

### Newsletter Model
- All fields match — CORRECT (`models/newsletter.py:26-38`)
- `delivered_count` default=0 — CORRECT (`models/newsletter.py:35`)
- `error_message` nullable=True — CORRECT (`models/newsletter.py:36`)

### Subscriber Model
- All fields match — CORRECT (`models/newsletter.py:50-76`)
- UniqueConstraint on (email, newsletter_type) — CORRECT (`models/newsletter.py:78-80`)
- `preferences` JSON, nullable=True, default=dict — CORRECT (`models/newsletter.py:73`)
- `bounce_count` default=0 — CORRECT (`models/newsletter.py:74`)
- `last_active_at` nullable=True, index=True — CORRECT (`models/newsletter.py:76`)

### AdminUser 2FA
- `totp_secret`, `totp_enabled`, `backup_codes` as JSON — CORRECT (`models/auth.py:37-39`)
- `username` unique=True, nullable=False, index=True — CORRECT (`models/auth.py:35`)
- `password_hash` — CORRECT (`models/auth.py:36`)

### TrendMemory
- `signal` (not `observation`) — CORRECT (`models/context.py:32`)
- `embedding` as Text — CORRECT (`models/context.py:46`)
- `importance` default=1 — CORRECT (`models/context.py:33`)
- `source_article_id` ForeignKey with SET NULL — CORRECT (`models/context.py:34-36`)
- `expires_at` nullable=True — CORRECT (`models/context.py:37`)
- `last_consolidated_at` nullable=True — CORRECT (`models/context.py:38`)

### TopicNote
- UniqueConstraint on (topic, source) — CORRECT (`models/context.py:21`)
- All fields match — CORRECT (`models/context.py:8-19`)

### Indexes
- `ix_articles_status_created` on (pipeline_status, created_at) — CORRECT (`models/article.py:68`)
- `ix_articles_published` on original_published_at — CORRECT (`models/article.py:69`)
- `ix_articles_impact` on impact_score — CORRECT (`models/article.py:70`)
- `ix_articles_category_status` on (category, pipeline_status) — CORRECT (`models/article.py:71`)
- `ix_articles_total_retries` on total_retries — CORRECT (`models/article.py:72`)
- `ix_articles_retry_count` on retry_count — CORRECT (`models/article.py:73`)
- `ix_articles_degradation_count` on degradation_count — CORRECT (`models/article.py:74`)
- `uq_source_external_id` unique constraint — CORRECT (`models/article.py:67`)
- `Source` consecutive_failures index — CORRECT (`models/source.py:21`)
- `Source` disabled_at index — CORRECT (`models/source.py:25`)
- `PipelineRun` run_type index — CORRECT (`models/pipeline.py:28`)
- `PipelineRun` (run_type, status) composite index — CORRECT (`models/pipeline.py:29`)
- `PipelineRun` started_at index — CORRECT (`models/pipeline.py:20`)
- `TrendMemory` (topic, importance) index — CORRECT (`models/context.py:49`)
- `TrendMemory` expires_at index — CORRECT (`models/context.py:50`)

---

## Incorrect Claims

### Source Model: source_type nullable
- **Claim (implicit):** Source model does not mark `source_type` as nullable
- **Actual:** `source_type = db.Column(db.String(32), nullable=False, index=True)` (`models/source.py:16`)
- **Impact:** The doc shows `source_type = Column(String(32))` without `nullable=False`. While the doc doesn't explicitly say nullable, the omission of `nullable=False` implies nullable. The actual column is NOT NULL.
- **Priority:** LOW

### Newsletter ↔ Subscriber Relationship Direction
- **Claim:** Newsletter has `articles` relationship (many-to-many via newsletter_articles)
- **Actual:** The `subscribers` relationship is defined on the `Subscriber` model, NOT on `Newsletter`. Newsletter has NO direct relationship to Subscriber in code.
  - Subscriber side: `newsletters = db.relationship("Newsletter", secondary="newsletter_subscribers", ...)` (`models/newsletter.py:94-98`)
  - Newsletter side: only has `articles` relationship (`models/newsletter.py:40-44`)
- **Impact:** The relationship diagram implies bidirectional access from Newsletter. In code, you access subscribers via `subscriber.newsletters` (backref) or query the association table directly.
- **Priority:** LOW

---

## Bugs Found

### ProcessItemTask topics validation missing
- **Location:** `schemas/tasks.py:99` — `topics: Optional[list[str]] = Field(default_factory=list, description="Article topics")`
- **Issue:** The doc claims `topics: Optional[list[str]]` with description "Article topics (max 20)". The actual code has NO max_length constraint and NO `validate_topics` validator on ProcessItemTask (the validator exists on a different schema, SelectArticleTask). The topics list can grow unbounded.
- **Priority:** MEDIUM

---

## Improvement Opportunities

### Missing Model: QualityReport
- **Location:** `models/quality.py:10` — `QualityReport` model
- **Issue:** `QualityReport` is defined in `models/quality.py` and exported in `models/__init__.py:14,39`. It is NOT documented in models.md. This model stores editorial quality verification results (groundedness, coherence, completeness, safety scores) and is referenced by ArticleVersion.
- **Priority:** HIGH

### Missing Model Fields: Source.created_at
- **Location:** `models/source.py:19` — `created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))`
- **Issue:** Source model has a `created_at` field that is not documented in the Source Model section of models.md.
- **Priority:** LOW

### Missing Model Fields: Webhook
- **Location:** `models/webhook.py:8-29` — Webhook model
- **Issue:** Webhook model has 12 fields (id, name, url, secret, events, active, created_at, updated_at, last_triggered_at, last_success_at, last_failure_at, last_error, failure_count). The doc lists Webhook in the file inventory but never documents its fields. The WebhookEvent section mentions `status_code, response_body, error_message` but misses `attempt_number`, `idempotency_key`, and `payload`.
- **Priority:** MEDIUM

### Missing Model Fields: ArticleMetric
- **Location:** `models/newsletter.py:101-119` — ArticleMetric model
- **Issue:** ArticleMetric has fields `page_loads`, `newsletter_clicks`, `share_button_clicks`, `share_link_views`, `updated_at`. Documented in file inventory but fields are never described.
- **Priority:** LOW

### Missing Model: models/utils.py
- **Location:** `models/utils.py:14-28`
- **Issue:** Utility functions `slugify()`, `encode_short_url()`, `decode_short_url()` are exported in `models/__init__.py` but not documented in models.md.
- **Priority:** LOW

### Missing Index Documentation
- `Source.source_type` has index=True (`models/source.py:16`) — not documented
- `Source.active` has index=True (`models/source.py:17`) — not documented
- `TrendMemory.last_accessed_at` has index=True (`models/context.py:40-45`) — not documented
- `AuditLog` has composite index on (target_type, target_id) (`models/audit.py:21`) — not documented
- `ArticleVersion` has UniqueConstraint on (article_id, version_number) (`models/pipeline.py:86-88`) — not documented
- **Priority:** LOW

### Source Config Comment Misleading
- **Location:** `models/source.py` — no `adapter_config` field exists
- **Issue:** The doc says "adapter config is stored in SourceConfig.config (schemas/source.py)" which is correct, but the comment format in the doc's code block implies Source had this field at some point. The actual Source model has never had an adapter_config column.
- **Priority:** LOW

---

## Stale Content

### None identified
All documented models, fields, and relationships exist in the current codebase. No stale references to removed models or deprecated fields were found.
