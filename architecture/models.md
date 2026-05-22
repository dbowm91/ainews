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
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)
    scheduled_publish_at = Column(DateTime, nullable=True, index=True)
    crawled_at = Column(DateTime, nullable=True, index=True)
    selected_at = Column(DateTime, nullable=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)

    # A/B Experiment
    experiment_group = Column(String(32), nullable=True, index=True)  # control/variant_a/variant_b

    # Embedding for semantic search
    embedding = Column(Text)

### Pipeline Status Flow

```
pending → selecting → selected → researching → writing → written → editing → review → done
                                                    ↓
                                               failed (after retries)
```

Actual statuses used in code: `pending`, `selecting`/`selected`, `researching`, `writing`/`written`, `editing`, `review`, `done`, `skipped`, `failed`

## Source Model

Health tracking for source reliability:

```python
class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    source_key = Column(String(64), unique=True, nullable=False)  # Unique source identifier
    name = Column(String(128))
    url = Column(String(512))                     # Source website URL
    feed_url = Column(String(512))                 # RSS/API feed URL
    source_type = Column(String(32))              # rss, api, web
    active = Column(Boolean, default=True)

    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    consecutive_successes = Column(Integer, default=0)
    last_crawled = Column(DateTime)
    last_success_at = Column(DateTime)
    last_error = Column(Text)
    disabled_at = Column(DateTime)

    # Configuration: adapter config is stored in SourceConfig.config (schemas/source.py)
    # NOT in this model. Adapters access via source_config.config at runtime.
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
    articles = relationship("Article", secondary="newsletter_articles", backref="newsletters")

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
```

## AdminUser Security

Admin authentication with 2FA:

```python
class AdminUser(Base):
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True)
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

## TrendMemory

Embedding-based semantic trend tracking:

```python
class TrendMemory(Base):
    __tablename__ = 'trend_memory'

    id = Column(Integer, primary_key=True)
    topic = Column(String(128))  # Not String(200)
    signal = Column(Text)
    importance = Column(Integer, default=1)  # Priority level
    expires_at = Column(DateTime, nullable=True)  # Expiration timestamp
    last_consolidated_at = Column(DateTime, nullable=True)  # Last consolidation

    # Embeddings for semantic search
    embedding = Column(Text)  # Stored as text, not vector type

    # Metadata
    source_article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)  # Single FK, not JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime)
```

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
