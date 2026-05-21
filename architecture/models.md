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
└── Article (one-to-many) - via pipeline_run_id

Newsletter
├── Subscriber (many-to-many via newsletter_subscribers)
└── Article (many-to-many via newsletter_articles)
```

## Article Model

The `Article` model is the central entity with fields for original content, pipeline state, and AI-generated output:

```python
class Article(Base):
    __tablename__ = 'articles'

    # Identification
    id = Column(Integer, primary_key=True)
    short_id = Column(String(12), unique=True, index=True)  # Public-facing identifier
    source_id = Column(Integer, ForeignKey('sources.id', ondelete='CASCADE'), nullable=False, index=True)
    external_id = Column(String(128), index=True)

    # Original content
    original_url = Column(String(2048))
    original_title = Column(String(512), index=True)
    original_author = Column(String(128))
    original_published_at = Column(DateTime)
    extracted_text = Column(Text)

    # Pipeline state
    pipeline_status = Column(String(32), default="pending")
    selector_result = Column(JSON)  # Selection score, confidence, reasoning
    research_brief = Column(Text)  # LLM-generated research brief
    draft_article = Column(Text)    # Initial AI draft
    final_article = Column(Text)   # Edited final version
    original_ai_article = Column(Text)
    writer_model = Column(String(128))

    # Metrics
    impact_score = Column(Integer, default=0)
    summary = Column(Text)
    category = Column(String(32), index=True)
    topics = Column(JSON)           # Array of topic tags
    raw_metadata = Column(JSON)     # Source-specific metadata

    # Processing tracking
    extraction_status = Column(String(32), default="pending")
    retry_count = Column(Integer, default=0)
    total_retries = Column(Integer, nullable=False, default=0)
    degradation_count = Column(Integer, nullable=False, default=0)
    pipeline_started_at = Column(DateTime, nullable=True)
    last_error = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    scheduled_publish_at = Column(DateTime, nullable=True, index=True)
    crawled_at = Column(DateTime, nullable=True, index=True)
    selected_at = Column(DateTime, nullable=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)

    # Relations
    citations = relationship("Citation", backref="article", lazy="selectin", cascade="all, delete-orphan")
    experiment_group = Column(String(32), nullable=True, index=True)  # A/B testing
    embedding = Column(Text)
    tags = relationship("Tag", secondary=article_tags, lazy="selectin")
    metrics = relationship("ArticleMetric", backref="article", uselist=False, cascade="all, delete-orphan")

    # Indexes (see Indexes section for complete list)
```

### Pipeline Status Flow

```
pending → selecting → selected → researching → writing → written → editing → review → done
                                                     ↓
                                               skipped/failed
```

Actual statuses used in code: `pending`, `selecting`/`selected`, `researching`, `writing`/`written`, `editing`, `review`, `done`, `skipped`, `failed`

## Source Model

Health tracking for source reliability:

```python
class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    source_key = Column(String(64), unique=True, nullable=False)  # Unique source identifier
    name = Column(String(128), nullable=False, index=True)
    url = Column(String(512))                                      # Source website URL
    feed_url = Column(String(512))                                 # RSS/API feed URL
    source_type = Column(String(32), nullable=False, index=True)   # rss, api, web
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Health tracking
    consecutive_failures = Column(Integer, nullable=False, default=0, index=True)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_crawled = Column(DateTime)
    last_error = Column(Text, nullable=True)
    disabled_at = Column(DateTime, nullable=True, index=True)

    # Relations
    articles = relationship("Article", backref="source", lazy="dynamic", cascade="all, delete-orphan")

    # Configuration: adapter config is stored in SourceConfig.config (schemas/source.py)
    # NOT in this model. Adapters access via source_config.config at runtime.
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
    topic = Column(String(200))
    signal = Column(Text)  # Note: field is 'signal', not 'observation'

    # Embeddings for semantic search (stored as text, not vector type)
    embedding = Column(Text)

    # Metadata
    source_articles = Column(JSON)  # Related article IDs
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime)
```

## Indexes

Key indexes for query performance:

| Model | Index Name | Columns | Purpose |
|-------|------------|---------|---------|
| Article | `ix_articles_status_created` | `(pipeline_status, created_at)` | Filter by status with time ordering |
| Article | `ix_articles_published` | `original_published_at` | Date-based article queries |
| Article | `ix_articles_impact` | `impact_score` | High impact article queries |
| Article | `ix_articles_category_status` | `(category, pipeline_status)` | Category-filtered status queries |
| Article | `ix_articles_total_retries` | `total_retries` | Retry monitoring |
| Article | `ix_articles_retry_count` | `retry_count` | Per-stage retry tracking |
| Article | `ix_articles_degradation_count` | `degradation_count` | Degradation monitoring |
| Article | `uq_source_external_id` | `(source_id, external_id)` | Unique article per source |
| Source | `ix_sources_name` | `name` | Source lookups |
| Source | `ix_sources_source_type` | `source_type` | Type-filtered queries |
| Source | `ix_sources_consecutive_failures` | `consecutive_failures` | Health monitoring |
| Source | `ix_sources_disabled_at` | `disabled_at` | Disabled source queries |
| Source | `uq_sources_source_key` | `source_key` | Unique source identifier |
| PipelineRun | `ix_pipeline_runs_run_type` | `run_type` | Run type filtering |
| PipelineRun | `ix_pipeline_runs_type_status` | `(run_type, status)` | Status-filtered run queries |
| TrendMemory | `ix_trend_memory_topic_importance` | `(topic, importance)` | Topic-based trending |
| TrendMemory | `ix_trend_memory_expires_at` | `expires_at` | Expired entry cleanup |
| TrendMemory | `ix_trend_memory_last_accessed` | `last_accessed_at` | Access pattern tracking |