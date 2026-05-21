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

The `Article` model is the central entity:

```python
class Article(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    url = Column(String(2000))
    source_id = Column(Integer, ForeignKey('sources.id'))
    content = Column(Text)
    summary = Column(Text)

    pipeline_status = Column(String(50))  # pending, select, research, write, edit, review, done
    impact_score = Column(Integer, default=0)

    # Timestamps
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
```

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
    source_key = Column(String(64), unique=True)  # Unique source identifier
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
    signal = Column(Text)

    # Embeddings for semantic search
    embedding = Column(Text)  # Stored as text, not vector type

    # Metadata
    source_articles = Column(JSON)  # Related article IDs
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime)
```

## Indexes

Key indexes for query performance:

- `Article`: `pipeline_status`, `source_id` (FK), `published_at` (as `original_published_at`), `created_at`, plus `ix_articles_impact` on `impact_score`, `ix_articles_category_status` on `(category, pipeline_status)`, and retry/degradation indexes
- `Source`: `name`, `source_type`, `consecutive_failures`, `disabled_at`, unique constraint on `source_key`
- `PipelineRun`: `run_type`, `(run_type, status)` - no index on `created_at`
- `TrendMemory`: `(topic, importance)`, `expires_at`, `last_accessed_at` - embedding stored as text for caching, not vector search
