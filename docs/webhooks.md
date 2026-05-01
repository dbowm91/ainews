# Webhooks Guide

## Overview

Webhooks notify external systems when events occur in the pipeline.

## Event Types

| Event | Trigger | Data |
|-------|---------|------|
| article.published | Article finalized | article_id, headline, category, impact_score |
| article.selected | Article selected | article_id, score, topics |
| article.failed | Article failed permanently | article_id, error |
| newsletter.sent | Newsletter delivered | newsletter_id, recipients |
| newsletter.failed | Newsletter send failed | newsletter_id, error |

## API Endpoints

### List Webhooks

**GET** `/admin/api/webhooks`

### Get Webhook

**GET** `/admin/api/webhooks/<id>`

### Create Webhook

**POST** `/admin/api/webhooks`

```json
{
  "name": "My Webhook",
  "url": "https://example.com/webhook",
  "events": ["article.published"],
  "secret": "optional-secret"
}
```

### Update Webhook

**PUT** `/admin/api/webhooks/<id>`

```json
{
  "name": "Updated Name",
  "url": "https://example.com/new-webhook",
  "events": ["article.published", "article.selected"],
  "active": true
}
```

### Delete Webhook

**DELETE** `/admin/api/webhooks/<id>`

### Test Webhook

**POST** `/admin/api/webhooks/<id>/test`

Sends a test payload to verify connectivity.

### Webhook Events

**GET** `/admin/api/webhooks/<id>/events`

Returns delivery history with status codes and responses.

## Encryption at Rest

Webhook secrets are encrypted using Fernet (AES-128-CBC) when stored.

- New secrets: prefixed with `enc:`
- Legacy plaintext: supported for decryption
- Key: `WEBHOOK_SECRET_KEY` environment variable

## Payload Format

```json
{
  "event": "article.published",
  "timestamp": "2024-01-01T00:00:00Z",
  "data": {
    "article_id": 123,
    "headline": "Article Title",
    "category": "ai",
    "impact_score": 85
  }
}
```

## Idempotency

Each webhook delivery has an idempotency key to prevent duplicate processing.

## Trigger Integration

Webhooks are triggered from `services/webhooks.py:trigger_event()`:

```python
from services.webhooks import trigger_event

trigger_event("article.published", {
    "article_id": article.id,
    "headline": headline,
    "category": article.category,
    "impact_score": article.impact_score,
})
```

Trigger failures are caught and logged — they never crash the pipeline.