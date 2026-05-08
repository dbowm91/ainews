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
pending → select → research → writing → editing → done
                    ↓          ↓         ↓
                  review ←──────┴─────────┘
                  (impact_score < threshold)
```

## Source Model

Health tracking for source reliability:

```python
class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    source_type = Column(String(50))  # rss, api, web

    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    consecutive_successes = Column(Integer, default=0)
    last_crawled = Column(DateTime)
    last_success_at = Column(DateTime)

    # Configuration
    adapter_config = Column(JSON)  # Source-specific adapter settings
```

## AdminUser Security

Admin authentication with 2FA:

```python
class AdminUser(Base):
    __tablename__ = 'admin_users'

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True)
    password_hash = Column(String(255))

    # TOTP 2FA
    totp_secret = Column(String(32))
    backup_codes = Column(JSON)  # 8 backup codes as JSON array

    # Session security
    # Note: ip_binding and user_agent_hash not implemented
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

- `Article`: `pipeline_status`, `source_id`, `published_at`, `created_at`
- `Source`: `name`, `type`
- `PipelineRun`: `status`, `created_at`
- `TrendMemory`: `topic` (GIN index on embedding for vector search)
