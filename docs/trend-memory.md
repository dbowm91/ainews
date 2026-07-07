# Trend Memory System

## Overview

The trend memory system provides tiered, LLM-judged memory for the editor agent. After an article is finalized, `propose_trend_memory(article)` asks the LLM to extract 0-3 high-signal memory entries that capture factual trends, patterns, or significant observations relevant to the article's topics. These entries are stored and later injected into editor prompts via `get_memory_for_topics()` so the LLM can see prior patterns before contextualizing new articles.

## Importance Tiers

The system uses three importance tiers to manage memory lifecycle:

| Tier | Value | TTL | Use Case |
|------|-------|-----|----------|
| LOW | 1 | 7 days | Ephemeral patterns, short-term observations |
| MEDIUM | 2 | 30 days | Recurring patterns, medium-term trends |
| HIGH | 3 | No expiry | High-signal persistent patterns |

The TTL is calculated from the `importance` value:
- Importance 1: 7 days
- Importance 2: 30 days
- Importance 3: No expiry (expires_at = None)

## Data Model

### TrendMemory (Database Model)

Defined in `models.py:385`, the database model:

```python
class TrendMemory(db.Model):
    __tablename__ = 'trend_memory'

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(128), nullable=False, index=True)
    signal = db.Column(db.Text, nullable=False)
    importance = db.Column(db.Integer, nullable=False)  # 1=LOW, 2=MEDIUM, 3=HIGH
    source_article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'))
    expires_at = db.Column(db.DateTime, nullable=True)  # None for HIGH importance
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_consolidated_at = db.Column(db.DateTime, nullable=True)
```

## All Models Reference

All application models are defined in `models.py` (not a `models/` directory). The 19 models are:

| Model Name | Brief Description |
|------------|-------------------|
| Source | RSS/feed sources for article crawling, tracks crawl health and failure counts |
| Tag | Article tags with unique name/slug for categorization |
| Article | Core article model with pipeline status, content fields, SLA timestamps, and relationships |
| Citation | Article citations with URL, title, author, and context for reference |
| Newsletter | Generated newsletters with HTML content, delivery stats, and send status |
| Subscriber | Email subscribers with preferences, bounce tracking, and verification status |
| ArticleMetric | Per-article engagement metrics (page loads, newsletter clicks, shares) |
| ShareConfig | Social share platform configurations (URL templates, icons, sort order) |
| PipelineRun | Pipeline execution records (crawl/newsletter runs) with status and article counts |
| PipelineLog | Per-stage pipeline logs linked to pipeline runs, with level and message |
| ArticleVersion | Audit trail of article content versions for rollback and change tracking |
| TopicNote | Editorial context notes linked to topics, optionally filtered by source |
| TrendMemory | Tiered trend memory entries with importance, expiration, and topic linkage |
| Webhook | Webhook endpoints for event notifications, with secret and event subscriptions |
| WebhookEvent | Delivery logs for webhook events, including status codes and error messages |
| AuditLog | Admin action audit trail with action, category, target, and user details |
| SearchQuery | Search query logs with result counts and clicked article tracking |
| ApiToken | API tokens for programmatic access, with hashed secret, prefix, expiration, and revocation |
| AdminUser | Admin users with password hash, 2FA secret, and session management |

### Pydantic Models

Defined in `services/trend_memory.py`:

```python
class MemoryImportance(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class TrendMemoryEntry(BaseModel):
    topic: str
    importance: int  # 1-3
    signal: str  # 1-2 sentences

class TrendMemoryEntries(BaseModel):
    entries: list[TrendMemoryEntry]

class TrendMemoryConfig(BaseModel):
    ttl_days_low: int = 7
    ttl_days_medium: int = 30
    ttl_days_high: int = 0
    consolidation_cooldown_hours: int = 24
    max_entries_per_propose: int = 3
    consolidation_merge_window_hours: int = 72
```

## Configuration

Configuration is loaded from `pipeline.yaml` under the `memory:` section:

```yaml
memory:
  ttl_days_low: 7
  ttl_days_medium: 30
  ttl_days_high: 0
  consolidation_cooldown_hours: 24
  max_entries_per_propose: 3
  consolidation_merge_window_hours: 72
```

## Usage in Pipeline

### Memory Propose (Article Finalization)

When an article moves to DONE status, `propose_trend_memory()` is called to extract memory:

```python
def propose_trend_memory(article: Article, engagement_data: dict | None = None) -> SubagentResponse:
    """Extract 0-3 trend memory entries from a completed article."""
```

The function:
1. Extracts draft, topics, and summary from the article
2. Optionally includes engagement metrics (newsletter clicks, page loads)
3. Calls the LLM with the trend memory prompt
4. Saves 0-3 memory entries to the database

The LLM prompt instructs it to extract only high-signal memories that:
- Capture factual trends or patterns
- Are specific enough to be useful in future articles
- Represent compounding information (company directions, regulatory themes, emerging standards)

### Memory Retrieval (Editor Contextualization)

Before editing, `get_memory_for_topics()` retrieves relevant memory:

```python
def get_memory_for_topics(
    topics: list[str],
    min_importance: int = 1,
    max_age_days: int | None = None,
    limit: int = 10
) -> list[TrendMemory]:
    """Get trend memory entries for given topics."""
```

The returned entries are formatted and injected into the editor prompt under the `<trend_memory>` tag, allowing the LLM to see prior patterns before contextualizing.

## Consolidation Algorithm

The `consolidate_trend_memory` nightly task promotes low-importance entries to medium when a high-importance entry exists for the same topic.

### Logic Flow

1. **Find topics with HIGH importance**: Query for active HIGH-importance entries
2. **Check cooldown**: Skip topics consolidated within `consolidation_cooldown_hours` (24 hours)
3. **Find overlapping LOW entries**: For each topic with HIGH, find LOW entries with overlapping time windows
4. **Promote to MEDIUM**: Update LOW entries to importance=2, apply 30-day TTL

### Functions

| Function | Description |
|----------|-------------|
| `consolidate_topic(topic)` | Consolidate one topic's memory entries |
| `consolidate_all_topics()` | Iterate all topics with HIGH importance, consolidate each |
| `_should_consolidate_topic(topic)` | Check if topic is eligible for consolidation (not in cooldown) |

## Admin UI

The trend memory system includes an admin interface at `/admin/trend-memory` providing:

- **List view**: Display all trend memory entries with topic, importance, signal, expiration
- **Filtering**: Filter by topic name or importance tier
- **Delete**: Remove individual entries
- **Purge expired**: Bulk delete expired entries

## Celery Beat Schedule

Three scheduled tasks manage trend memory lifecycle:

| Task | Schedule | Purpose |
|------|----------|---------|
| `consolidate-trend-memory` | Daily 3:30 AM | Promote LOW→MEDIUM for topics with HIGH |
| `purge-trend-memory` | Daily 3:45 AM | Delete expired memory entries |
| `cleanup-old-article-versions` | Daily 3:45 AM | Clean up old article version history |

## Memory Extraction Prompt

The LLM is prompted with:

```
You are an editorial trend analyst. After editing an article, extract high-signal insights...

<article_draft>
{draft}
</article_draft>

<topics>
{topics}
</topics>

<article_summary>
{summary}
</article_summary>

Return 0 to 3 entries in this format:
## memory_entry_<N>
topic: <the topic this applies to>
importance: <1=low, 2=medium, 3=high>
signal: <the factual insight, 1-2 sentences>
reason: <why this matters for future coverage>

If no meaningful trend memory applies, respond with "NONE".
```

## Metrics

The system emits metrics for monitoring:

| Metric | Labels | Description |
|--------|--------|-------------|
| `trend_memory.propose_failure` | article_id | Counter for failed memory proposals |

## Known Issues

1. **Admin UI time inconsistency**: The admin UI at `/admin/trend-memory` uses `db.func.now()` for the count query but `datetime.now(timezone.utc)` for delete queries. This is a display inconsistency only - not a data corruption issue. The mismatch affects filtered count display but doesn't affect actual deletion operations.

2. **Dead code**: The function `_find_overlapping_low_entries` is defined at `services/trend_memory.py:270-281` but is never called anywhere in the codebase. It can be safely ignored or removed to clean up dead code.

## Integration with Subagent

Trend memory integrates with the subagent system via the `get_trend_memory` tool:

```python
def _get_trend_memory(
    topics: list[str], min_importance: int = 1, max_age_days: int | None = None
) -> str:
    """Get stored trend memory entries for topics."""
    entries = get_memory_for_topics(topics, min_importance, max_age_days)
    if not entries:
        return "No trend memory found for these topics."
    return "\n".join(
        f"[importance={e.importance}] [{e.topic}] {e.signal}" for e in entries
    )
```

This tool is available to subagent stages that configure it in their `tools:` list (typically the edit stage).