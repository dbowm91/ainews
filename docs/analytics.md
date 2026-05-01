# Analytics Guide

## Search Analytics

### Query Stats

**GET** `/admin/api/search/analytics`

Returns top search queries and queries with zero results.

```json
{
  "total_queries": 500,
  "zero_result_queries": [
    {"query": "missing term", "count": 10}
  ],
  "top_queries": [
    {"query": "openai", "count": 150},
    {"query": "llm", "count": 120}
  ]
}
```

### Tracked Data

| Field | Description |
|-------|-------------|
| query | Search term |
| results_count | Number of results |
| clicked_article_id | Article clicked (if any) |
| created_at | Query timestamp |

## Topic Notes CRUD

### Create/Update Note

**POST** `/admin/api/topic-notes`

```json
{
  "topic": "openai",
  "note": "Recent models: GPT-4o, o3, o4-mini",
  "source": "admin"
}
```

### List Notes

**GET** `/admin/api/topic-notes`

Query params:
- `topic`: Filter by topic
- `page`: Page number

### Delete Note

**DELETE** `/admin/api/topic-notes/<id>`

## Subscriber Export

### CSV Export

**GET** `/admin/api/subscribers/export`

Streams CSV with columns:
- email
- newsletter_type
- subscribed_at
- confirmed_at
- active

Uses streaming for large datasets.

### Subscriber Stats

**GET** `/admin/api/subscribers/stats`

```json
{
  "total": 1000,
  "verified": 950,
  "by_type": {
    "main": 800,
    "ai": 200
  }
}
```

## Pipeline SLA Metrics

**GET** `/admin/api/pipeline/sla`

Returns per-metric statistics:

| Metric | Description |
|-------|-------------|
| crawl_to_publish | Total pipeline duration |
| crawl_to_select | Selection stage |
| select_to_publish | Research + write + edit |
| publish_to_deliver | Newsletter delivery |

## Cost Tracking

**GET** `/admin/api/costs`

```json
{
  "total_tokens": 150000,
  "total_cost_usd": 2.50,
  "models": [
    {
      "provider": "openai",
      "model": "gpt-4o",
      "total_tokens": 100000,
      "estimated_cost_usd": 1.50
    }
  ]
}
```

Pricing for DeepSeek, MiniMax, Gemini 2.0 Flash, Groq, and other OpenAI-compatible providers is included.

## Source Health

**GET** `/admin/api/sources/health`

Returns consecutive failures and success counts per source.

## Cache Stats

**GET** `/admin/api/health`

Includes response cache hits/misses and DNS cache size.