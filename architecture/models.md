# Models Module

The `models/` package contains SQLAlchemy database models defining the data layer. All models must be imported before `db.create_all()` runs.

## File Inventory

| File | Models | Purpose |
|------|--------|---------|
| `article.py` | `Article`, `Citation` | Main content unit with pipeline_status; source references |
| `source.py` | `Source` | News source with health tracking (consecutive_failures/successes) |
| `newsletter.py` | `Newsletter`, `Subscriber`, `ArticleMetric` | Newsletters, recipients, engagement tracking |
| `pipeline.py` | `PipelineRun`, `PipelineLog`, `ArticleVersion` | Pipeline orchestration, logging, edit history |
| `context.py` | `TopicNote`, `TrendMemory` | Editor notes; learned trends with embeddings |
| `webhook.py` | `Webhook`, `WebhookEvent` | Event delivery tracking |
| `auth.py` | `ApiToken`, `AdminUser` | API authentication; admin users with TOTP 2FA + backup codes |
| `tag.py` | `Tag`, `article_tags` | Topic/category tags with many-to-many association |
| `search.py` | `SearchQuery` | Search analytics |
| `audit.py` | `AuditLog` | Admin action audit trail |
| `quality.py` | `QualityReport` | Persisted editorial quality verification reports |
| `share.py` | `ShareConfig` | Social sharing platform configuration |

## Key Relationships

```
Article
├── Source (many-to-one) - source_id foreign key
├── Tag (many-to-many via article_tags)
├── Citation (one-to-many)
├── ArticleMetric (one-to-one)
└── ArticleVersion (one-to-many) - edit history

PipelineRun
├── PipelineLog (one-to-many)
└── Article (via PipelineLog.article_id foreign key, not direct relationship)

Newsletter
├── Subscriber (many-to-many via newsletter_subscribers)
└── Article (many-to-many via newsletter_articles)
```

## Article Model

The `Article` model is the central entity with 30+ fields:

```python
class Article(Base):
    __tablename__ = 'articles'

    # Identity & Source
    id = Column(Integer, primary_key=True)
    short_id = Column(String(12), unique=True, index=True)  # Public-facing ID
    source_id = Column(Integer, ForeignKey('sources.id', ondelete='CASCADE'), nullable=False, index=True)
    external_id = Column(String(128), index=True)

    # Original Content
    original_url = Column(String(2048))
    original_title = Column(String(512), index=True)
    original_author = Column(String(128))
    original_published_at = Column(DateTime)
    extracted_text = Column(Text)

    # Pipeline State
    pipeline_status = Column(String(32), default="pending")
    selector_result = Column(JSON)  # {"selected": bool, "score": int, "reason": str}
    research_brief = Column(Text)  # LLM-generated research context
    draft_article = Column(Text)  # Writer output before edit
    final_article = Column(Text)  # Editor output (published)
    original_ai_article = Column(Text)
    writer_model = Column(String(128))  # Model used for writing

    # Scoring & Categorization
    impact_score = Column(Integer, default=0)
    summary = Column(Text)
    category = Column(String(32), index=True)
    topics = Column(JSON)  # List of topic tags
    raw_metadata = Column(JSON)  # Source-specific metadata

    # Processing Metadata
    extraction_status = Column(String(32), default="pending")
    retry_count = Column(Integer, default=0)
    total_retries = Column(Integer, nullable=False, default=0)
    degradation_count = Column(Integer, nullable=False, default=0)
    pipeline_started_at = Column(DateTime)
    last_error = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    scheduled_publish_at = Column(DateTime, nullable=True, index=True)
    crawled_at = Column(DateTime, nullable=True, index=True)
    selected_at = Column(DateTime, nullable=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)

    # A/B Experiment
    experiment_group = Column(String(32), nullable=True, index=True)  # control/variant_a/variant_b

    # Embedding for semantic search
    embedding = Column(Text)

    # Relationships
    citations = relationship("Citation", backref="article", lazy="selectin", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=article_tags, lazy="selectin")
    metrics = relationship("ArticleMetric", backref="article", uselist=False, cascade="all, delete-orphan")
```

### Pipeline Status Flow

Valid transitions (from `constants.py:VALID_TRANSITIONS`):

| From | To |
|------|-----|
| `pending` | `selecting`, `researching`, `review` |
| `selecting` | `selected`, `failed` |
| `selected` | `researching`, `failed` |
| `researching` | `writing`, `failed` |
| `writing` | `editing`, `failed` |
| `written` | `editing`, `failed` |
| `editing` | `review`, `done`, `failed` |
| `review` | `done`, `failed` |
| `done` | _(terminal)_ |
| `skipped` | _(terminal)_ |
| `failed` | `pending` |

Typical happy path: `pending → selecting → selected → researching → writing → written → editing → review → done`

Actual statuses used in code: `pending`, `selecting`/`selected`, `researching`, `writing`/`written`, `editing`, `review`, `done`, `skipped`, `failed`

See `constants.py:VALID_TRANSITIONS` for the complete transition map.

## Citation Model

External references linked to articles with positional ordering:

```python
class Citation(db.Model):
    __tablename__ = "citations"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)    # Cited source URL
    title = Column(String(512))                   # Title of cited resource
    author = Column(String(128))                  # Author of cited resource
    context = Column(Text)                        # Surrounding text or justification
    position = Column(Integer, nullable=False, default=1)  # Order within article
```

## Source Model

Health tracking for source reliability:

```python
class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    source_key = Column(String(64), unique=True, nullable=False)  # Unique source identifier
    name = Column(String(128), nullable=False, index=True)
    url = Column(String(512))                     # Source website URL
    feed_url = Column(String(512))                 # RSS/API feed URL
    source_type = Column(String(32), nullable=False, index=True)  # rss, api, web
    active = Column(Boolean, default=True, index=True)
    last_crawled = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # Item 5.8

    # Health tracking
    consecutive_failures = Column(Integer, nullable=False, default=0, index=True)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    disabled_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    articles = relationship("Article", backref="source", lazy="dynamic", cascade="all, delete-orphan")

    # Configuration: adapter config is stored in SourceConfig.config (schemas/source.py)
    # NOT in this model. Adapters access via source_config.config at runtime.
```

## Webhook Model

Event delivery tracking with health monitoring:

```python
class Webhook(db.Model):
    __tablename__ = 'webhooks'

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    url = Column(String(2048), nullable=False)
    secret = Column(String(128), nullable=False)
    events = Column(JSON, nullable=False, default=list)
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Delivery health tracking (Item 5.1)
    last_triggered_at = Column(DateTime, nullable=True)   # Last delivery attempt
    last_success_at = Column(DateTime, nullable=True)     # Last successful delivery
    last_failure_at = Column(DateTime, nullable=True)     # Last failed delivery
    last_error = Column(Text, nullable=True)              # Last error message
    failure_count = Column(Integer, default=0)            # Consecutive failure counter
```

## WebhookEvent Model

Individual webhook delivery attempts:

```python
class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'

    id = Column(Integer, primary_key=True)
    webhook_id = Column(Integer, ForeignKey('webhooks.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    delivered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Delivery tracking (Item 5.2)
    attempt_number = Column(Integer, nullable=False, default=1)           # Retry counter per event
    idempotency_key = Column(String(64), nullable=True, index=True)      # Dedup key
    payload = Column(Text, nullable=True)                                 # Serialized event data
```

## PipelineLog Model

Per-stage execution logging within a pipeline run:

```python
class PipelineLog(db.Model):
    __tablename__ = 'pipeline_logs'

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('pipeline_runs.id', ondelete='CASCADE'), nullable=False, index=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=True, index=True)
    stage = Column(String(32), nullable=False)
    level = Column(String(8), default="info")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Stage timing and status (Item 5.3)
    started_at = Column(DateTime, nullable=True)    # Stage start timestamp
    completed_at = Column(DateTime, nullable=True)  # Stage completion timestamp
    status = Column(String(16), nullable=True)      # Stage result (success/failure)
    error = Column(Text, nullable=True)             # Error message if failed
    meta = Column(JSON, nullable=True)              # Additional structured data
```

## ArticleVersion Model

Per-article edit history with version tracking:

```python
class ArticleVersion(db.Model):
    __tablename__ = "article_versions"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)  # Sequential version counter
    final_article = Column(Text)          # Published content at this version
    original_ai_article = Column(Text)    # AI-generated content before human edits
    source_fields = Column(JSON, nullable=True)  # Source-specific metadata snapshot
    change_reason = Column(String(256))   # Human-readable edit description
    changed_by = Column(String(64))       # Editor identifier
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Unique constraint on (article_id, version_number)
    __table_args__ = (UniqueConstraint("article_id", "version_number", name="uq_article_version"),)

    # Relationship
    article = relationship("Article", backref=backref("versions", lazy="dynamic", cascade="all, delete-orphan"))
```

## SearchQuery Model

Search analytics with article click tracking:

```python
class SearchQuery(db.Model):
    __tablename__ = 'search_queries'

    id = Column(Integer, primary_key=True)
    query = Column(String(256), nullable=False, index=True)
    results_count = Column(Integer, nullable=False, default=0)
    clicked_article_id = Column(Integer, ForeignKey('articles.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship (Item 5.4)
    clicked_article = relationship("Article", foreign_keys=[clicked_article_id])
```

**Note:** `clicked_article` uses explicit `foreign_keys` because `SearchQuery` has a nullable FK to `Article` but Article doesn't have a corresponding backref defined on this model.

## ShareConfig Model

Social sharing platform configuration:

```python
class ShareConfig(db.Model):
    __tablename__ = "share_configs"

    id = Column(Integer, primary_key=True)
    platform_key = Column(String(32), unique=True, nullable=False)  # Platform identifier (e.g., "twitter")
    label = Column(String(64), nullable=False)                      # Display name (e.g., "Twitter / X")
    url_template = Column(String(512), nullable=False)              # URL template with {url} placeholder
    icon_name = Column(String(32), nullable=False)                  # Icon class name
    active = Column(Boolean, default=True)                          # Whether platform is enabled
    sort_order = Column(Integer, default=0)                         # Display ordering
```

## ArticleMetric Model

Per-article engagement tracking with auto-updated timestamps:

```python
class ArticleMetric(db.Model):
    __tablename__ = 'article_metrics'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)

    # Engagement counters (Item 5.5)
    page_loads = Column(Integer, default=0)              # Page view count
    newsletter_clicks = Column(Integer, default=0)       # Click-throughs from newsletters
    share_button_clicks = Column(Integer, default=0)     # Social share button presses
    share_link_views = Column(Integer, default=0)        # Shared link landing page views
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

**Auto-update listener:** A `before_update` event listener on `ArticleMetric` automatically sets `updated_at` to the current UTC time before each update, ensuring the timestamp reflects the most recent modification without relying on application code.

## Newsletter Association Tables

### newsletter_articles

Links newsletters to articles with ordering:

```python
newsletter_articles = db.Table(
    "newsletter_articles",
    db.Column("newsletter_id", db.Integer, db.ForeignKey("newsletters.id", ondelete="CASCADE"), primary_key=True),
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("position", db.Integer, nullable=False, default=0),
    db.Column("created_at", db.DateTime, default=lambda: datetime.now(timezone.utc)),
)
```

### newsletter_subscribers

Links newsletters to subscribers with delivery tracking:

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

## Article-Tag Association

### article_tags

Links articles to tags with cascading deletes:

```python
article_tags = db.Table(
    "article_tags",
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
)
```

**Note:** `Article` model has a `tags` relationship and a `newsletters` dynamic backref (`db.backref("newsletters", lazy="dynamic")`) established in `models/newsletter.py:43`.

## Tag Model

Topic/category tags with slug-based lookup:

```python
class Tag(db.Model):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)        # Display name
    slug = Column(String(64), unique=True, nullable=False, index=True)  # URL-friendly identifier
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

## Newsletter & Subscriber Models

Newsletter and subscriber tracking for email delivery:

```python
class Newsletter(Base):
    __tablename__ = 'newsletters'

    id = Column(Integer, primary_key=True)
    newsletter_type = Column(String(32), nullable=False, index=True)
    subject = Column(String(256))
    html_content = Column(Text)
    article_count = Column(Integer, default=0)
    recipients = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)  # Successfully delivered
    error_message = Column(Text, nullable=True)   # Last delivery error
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime, index=True)

    # Relationships
    articles = relationship("Article", secondary="newsletter_articles", backref=db.backref("newsletters", lazy="dynamic"))

class Subscriber(Base):
    __tablename__ = 'subscribers'

    id = Column(Integer, primary_key=True)
    email = Column(String(256), nullable=False, index=True)
    newsletter_type = Column(String(32), nullable=False, index=True)
    unsubscribe_token = Column(String(64), unique=True, nullable=False, index=True)
    verification_token = Column(String(64), unique=True, nullable=True, index=True)
    subscribed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True, index=True)
    active = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True)
    preferences = Column(JSON, nullable=True, default=dict)  # User topic preferences
    bounce_count = Column(Integer, nullable=False, default=0)
    last_bounce_at = Column(DateTime, nullable=True)
    last_active_at = Column(DateTime, nullable=True, index=True)

    # Unique constraint
    __table_args__ = (UniqueConstraint("email", "newsletter_type", name="uq_email_newsletter"),)
```

## AdminUser Security

Admin authentication with 2FA:

```python
class AdminUser(Base):
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128))

    # TOTP 2FA
    totp_secret = Column(String(256))
    totp_enabled = Column(Boolean, default=False)
    backup_codes = Column(JSON)  # 8 backup codes as JSON array
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Session security fields (ip_binding, user_agent_hash) do NOT exist
    # Session hijacking protection is handled in routes/admin/__init__.py
```

## ApiToken Model

API authentication tokens with hashing and expiration:

```python
class ApiToken(db.Model):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False)    # SHA-256 hash of raw token
    token_prefix = Column(String(16), nullable=False, index=True)   # First 16 chars for identification
    name = Column(String(128))                                      # Human-readable label
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime)                                 # Last successful auth
    expires_at = Column(DateTime)                                   # Optional expiration
```

## AuditLog Model

Admin action audit trail for security and debugging:

```python
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(64), nullable=False, index=True)     # Action performed (e.g., "create_source")
    category = Column(String(32), nullable=True, index=True)    # Action category (e.g., "source", "article")
    target_type = Column(String(32))                            # Target entity type
    target_id = Column(Integer)                                 # Target entity ID
    user = Column(String(64), default="admin")                  # Actor identifier
    details = Column(JSON, nullable=True)                       # Structured action metadata
    ip_address = Column(String(45), nullable=True)              # Client IP (IPv4/IPv6)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Composite index on (target_type, target_id)
    __table_args__ = (Index("ix_audit_logs_target", "target_type", "target_id"),)
```

## TrendMemory

Embedding-based semantic trend tracking:

```python
class TrendMemory(Base):
    __tablename__ = 'trend_memory'

    id = Column(Integer, primary_key=True)
    topic = Column(String(128))  # Not String(200)
    signal = Column(Text)
    importance = Column(Integer, default=1)  # Priority level
    source_article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)  # Single FK, not JSON
    expires_at = Column(DateTime, nullable=True)  # Expiration timestamp
    last_consolidated_at = Column(DateTime, nullable=True)  # Last consolidation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_accessed_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))  # Auto-updated on access

    # Embeddings for semantic search
    embedding = Column(Text)  # Stored as text, not vector type
```

## TopicNote

Manual editor notes per topic:

```python
class TopicNote(Base):
    __tablename__ = 'topic_notes'

    id = Column(Integer, primary_key=True)
    topic = Column(String(128), nullable=False, index=True)  # Indexed for fast topic lookups
    note = Column(Text, nullable=False)
    source = Column(String(256))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Unique constraint on (topic, source)
    __table_args__ = (UniqueConstraint("topic", "source", name="uq_topic_source"),)
```

## QualityReport

Persisted editorial quality verification reports generated during the edit stage:

```python
class QualityReport(Base):
    __tablename__ = 'quality_reports'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    article_version_id = Column(Integer, ForeignKey('article_versions.id', ondelete='CASCADE'), nullable=True, index=True)
    stage = Column(String(32), nullable=False, default='edit')

    # Quality scores (0.0-1.0)
    overall_score = Column(Float, nullable=False, default=0.0)
    groundedness = Column(Float, nullable=True)
    coherence = Column(Float, nullable=True)
    completeness = Column(Float, nullable=True)
    safety = Column(Float, nullable=True)
    citation_score = Column(Float, nullable=True)
    claim_score = Column(Float, nullable=True)

    # Gate results
    passed = Column(Boolean, nullable=False, default=False, index=True)
    needs_review = Column(Boolean, nullable=False, default=True, index=True)

    # Detailed findings and metadata
    findings = Column(JSON, nullable=False, default=list)  # List of quality issues found
    meta = Column(JSON, nullable=False, default=dict)  # Additional metadata

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships (Item 5.7: cascade="all, delete-orphan" on article)
    article = relationship("Article", backref=backref("quality_reports", lazy="dynamic", cascade="all, delete-orphan"))
    article_version = relationship("ArticleVersion", backref=backref("quality_reports", lazy="dynamic"))

    # Composite indexes
    __table_args__ = (
        Index("ix_quality_reports_article_stage", "article_id", "stage"),
        Index("ix_quality_reports_created", "created_at"),
    )
```

**Quality Gate Routing:** Failed quality reports (where `passed=False` or `needs_review=True`) route articles to `review` for manual inspection. The `build_quality_report()` function in `services/quality_report.py` evaluates article quality and the edit stage task (`tasks/edit.py:378-419`) uses the report to decide whether to route to `review` or proceed to `done`.

## Indexes

Key indexes for query performance:

- `Article`:
  - `ix_articles_status_created` on `(pipeline_status, created_at)` - filtered article queries
  - `ix_articles_published` on `original_published_at` - published article listings
  - `ix_articles_impact` on `impact_score` - impact-based sorting
  - `ix_articles_category_status` on `(category, pipeline_status)` - category filtering
  - `ix_articles_total_retries` on `total_retries` - retry tracking
  - `ix_articles_retry_count` on `retry_count` - per-stage retry tracking
  - `ix_articles_degradation_count` on `degradation_count` - degradation tracking
  - `uq_source_external_id` unique constraint on `(source_id, external_id)` - dedup
  - Plus individual indexes on: `short_id`, `source_id` (FK), `original_title`, `external_id`, `category`, `experiment_group`, `updated_at`, `scheduled_publish_at`, `crawled_at`, `selected_at`, `published_at`
- `Source`: unique constraint on `source_key`, index on `active`, index on `consecutive_failures`, index on `disabled_at`
- `PipelineRun`: index on `run_type`, composite index on `(run_type, status)`, index on `started_at`
- `TrendMemory`: indexes on `(topic, importance)`, `expires_at`, `last_accessed_at`
- `QualityReport`: composite index on `(article_id, stage)`, index on `created_at`
