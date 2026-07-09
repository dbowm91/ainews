# Context Service

This document covers the context service for topic notes and related article lookup.

## Overview

`services/context_service.py` provides:
- CRUD operations for topic notes (editor context stored in database)
- Related article lookup for research and editor stages
- Admin endpoints for managing topic notes

## TopicNote Model

The `TopicNote` model (`models.py`) stores editor context:

```python
class TopicNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(255), nullable=False, index=True)
    source = db.Column(db.String(100), nullable=True)  # optional source filter
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

## All Models Reference

All application models are defined in the `models/` package directory. The 19 models are:

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

- `topic`: The topic keyword (e.g., "LLM", "AI safety")
- `source`: Optional source identifier for source-specific notes
- `note`: Free-form text content (typically LLM-generated context)

## TopicNote CRUD Operations

### Get Single Note

```python
from services.context_service import get_topic_note

note = get_topic_note("LLM", source=None)  # returns TopicNote or None
```

Query by topic. If `source` is provided, filters by source as well.

### Batch Retrieval

```python
from services.context_service import get_topic_notes_for_topics

notes = get_topic_notes_for_topics(["LLM", "AI safety"])
# Returns: {"LLM": ["note1", "note2"], "AI safety": ["note3"]}
```

Takes a list of topics and returns a dict mapping each topic to a list of note strings.

### Create Note

```python
from services.context_service import create_topic_note

note = create_topic_note(topic="LLM", note="Recent developments in...", source=None)
```

Creates a new TopicNote record. Commits to database immediately.

### Update Note

```python
from services.context_service import update_topic_note

updated = update_topic_note(topic="LLM", note="Updated note content", source=None)
```

Updates the `note` field of an existing note. If no note exists for the topic/source combination, returns `None`.

**Note**: This function only updates the `note` field. If you pass a different topic/source than an existing note, it will NOT change the topic/source — it will simply change the note text for the matched record.

### Delete Note

```python
from services.context_service import delete_topic_note

deleted = delete_topic_note(topic="LLM", source=None)  # returns True/False
```

Deletes a note by topic (and optional source). Returns `True` if deleted, `False` if not found.

### Get All Notes for Topic

```python
from services.context_service import get_all_topic_notes

notes = get_all_topic_notes("LLM")  # returns list of TopicNote objects
```

Returns all notes for a given topic regardless of source.

## Related Articles

### Find Related Articles

```python
from services.related import find_related_articles

related = find_related_articles(article, limit=5)
# Returns list of Article ORM objects
```

Finds related articles using scored matching:

1. **Category match** (+3.0 points): Same category as the source article
2. **Tag overlap** (+2.0 per tag): Shared tags with the source article
3. **Keyword overlap** (+0.5 per word): Word overlap in titles (stop words filtered)
4. **Impact boost** (+1.0): High-impact articles (score >= 75)

Candidates are limited to 50, sorted by composite score, and returned up to `limit`.

### Find Related Articles for Editor

```python
from services.context_service import get_related_articles_for_edit

related = get_related_articles_for_edit(topics=["LLM", "AI"], exclude_id=123, limit=5)
# Returns list of dicts with title, category, snippet, created_at
```

Used by the pipeline researcher. Takes topics list instead of Article object. Returns dicts compatible with prompt builders.

### Caching

```python
from services.related import find_related_articles_cached

related = find_related_articles_cached(article, limit=5)
```

Cached wrapper with 600-second TTL. Cache key format: `pub:related:{article_id}`.

**Important**: The cache is NOT invalidated when articles are updated. The 600s TTL provides eventual consistency — updated articles will appear in related lists after the cache expires.

## Admin Endpoints

### List Topic Notes

```
GET /admin/topic-notes
```

Returns HTML page with list of topic notes (up to 100, ordered by updated_at desc).

### Create Topic Note

```
POST /admin/topic-notes/create
```

Form parameters:
- `topic`: Topic string (required)
- `note`: Note content (required)
- `source`: Optional source string

Creates a new note or updates existing if topic+source match.

### Edit Topic Note

```
POST /admin/topic-notes/edit
```

Form parameters:
- `id`: Note ID (required)
- `note`: New note content (required)

### Delete Topic Note

```
POST /admin/topic-notes/delete
```

Form parameters:
- `id`: Note ID (required)

### Get Note Row (HTMX)

```
GET /admin/topic-notes/row/<topic>
```

Returns HTMX-swappable table row for a topic.

## Usage in Pipeline

### Research Stage

The research stage injects topic notes via `get_topic_notes_for_topics()` to provide context about ongoing developments in relevant topics:

```python
from services.context_service import get_topic_notes_for_topics

notes_by_topic = get_topic_notes_for_topics(article.topics)
# Injected into research prompt
```

### Editor Stage

The editor stage uses `get_topic_note()` for contextualization:

```python
from services.context_service import get_topic_note

editor_note = get_topic_note(article.category)
# Used in editor prompt for consistency
```

Also uses `get_related_articles_for_edit()` to find relevant prior articles:

```python
from services.context_service import get_related_articles_for_edit

related = get_related_articles_for_edit(
    topics=article.topics,
    exclude_id=article.id,
    limit=5
)
```

## Known Issues

### Cache Invalidation

`find_related_articles_cached()` cache key is NOT invalidated when articles are updated. The 600s TTL provides eventual consistency. If you need immediate invalidation, call `cache.delete()` with the appropriate key pattern.

### Update Behavior

`update_topic_note()` only updates the `note` field. If you pass a different topic/source than an existing record, the function will simply update the note text for the matched existing record — it won't create a new record or change topic/source.

### Keyword Extraction

The related articles algorithm uses stop word filtering (see `_STOP_WORDS` in `services/related.py`). Common words like "new", "AI", "the" are excluded from keyword matching. This may cause false negatives for articles with generic titles.
