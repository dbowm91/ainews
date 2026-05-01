# Newsletter Pipeline

The newsletter generation system produces daily email newsletters by coordinating a 3-stage LLM pipeline that synthesizes top stories into styled HTML emails sent to subscribers.

## Overview

Newsletter generation runs as a Celery orchestrator task (`generate_daily_newsletters`) that:

1. Fetches active newsletter configurations
2. Retrieves top articles for each topic
3. Dispatches per-topic content generation tasks
4. Assembles results into HTML emails
5. Sends to subscribers in parallel batches

## Orchestrator Flow

The main entry point is `tasks/newsletter.py:generate_daily_newsletters()`:

```python
def generate_daily_newsletters(self, dry_run_email=None, run_id=None):
    # 1. Validate inputs via GenerateNewsletterTask schema
    # 2. Check idempotency key (Redis)
    # 3. Acquire distributed lock
    # 4. Call _generate_newsletters_impl()
```

Inside `_generate_newsletters_impl()`:

1. Creates `PipelineRun` for tracking
2. Loads topic configurations via `get_active_newsletter_configs()`
3. Fetches articles for each topic (capped by `nl.max_articles`)
4. Dispatches `_generate_topic_newsletter_impl` tasks in parallel via Celery group
5. Marks run as completed on success

## Newsletter Config

`schemas/pipeline.py:NewsletterConfig` defines per-topic settings:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_articles` | int | 10 | Maximum articles per newsletter (1-50) |
| `send_time` | str | "08:00" | Daily send time (HH:MM) |
| `timezone` | str | "America/New_York" | Timezone for send_time |
| `site_url` | str | "https://ainews.dev" | Base URL for unsubscribe links |
| `prep_minutes` | int | 15 | Minutes before send_time to start |

Topic configurations are loaded from `pipeline.yaml` under `newsletter:` section. The main newsletter ("main") always runs; additional topics are defined there.

## 3-Stage Pipeline

Each newsletter topic uses `services/newsletter_pipeline.py` to generate content through three LLM stages:

### Stage 1: Reader

Calls `get_provider_for_role("newsletter_pipeline.reader")` to get an LLM provider. The reader analyzes article headlines and TL;DRs to produce a JSON brief with:

- `themes`: Key themes identified
- `highlights`: Top stories to emphasize
- `connections`: How stories relate

Uses `NewsletterBrief` response model (Pydantic).

### Stage 2: Writer

Uses the reader's brief to generate the executive summary text. The writer produces:

- `summary`: Multi-paragraph executive summary
- Uses `ExecutiveSummary` response model
- System prompt asks for 3-4 paragraphs, sharp and direct tone

### Stage 3: Editor

Reviews and improves the writer's draft:

- Checks for accurate article references
- Improves tone and flow
- Ensures brevity
- Returns corrected `ExecutiveSummary`

## Return Value

`generate_executive_summary()` returns a dict:

```python
{
    "summary": "...",           # The executive summary text
    "used_fallback": True/False, # Whether any stage used fallback
    "fallback_stages": ["reader", "writer"],  # Which stages fell back
}
```

Callers must check for empty content before sending newsletters.

## Fallback Cascade

Each stage has silent fallbacks built into `_run_pipeline_stage()`:

1. **Rate limit fallback**: If `limiter.acquire()` returns False, the stage is skipped and a fallback metric is emitted
2. **LLM exception fallback**: If the LLM call raises an exception, returns None and appends to `fallback_stages`
3. **Empty content fallback**: If a stage produces empty output, the next stage uses default/empty data

The pipeline continues with degraded content rather than crashing. Metrics track fallbacks:

- `newsletter.pipeline_fallback{stage=reader|writer|editor}`
- `newsletter.pipeline_disabled{stage}`
- `newsletter.pipeline_empty_stage{stage}`

## Article Summaries

After the executive summary, each article gets a brief TL;DR via `generate_article_summaries()` in the same service. These are rendered as individual article blocks in the final HTML.

## Assembly

`_generate_topic_newsletter_impl()` assembles the final newsletter:

1. Generates executive summary via `generate_executive_summary()`
2. Generates per-article summaries via `generate_article_summaries()`
3. Combines into HTML with styling via `assemble_newsletter()`
4. Skips sending if content is empty

## Delivery Tracking

The `Newsletter` model stores delivery metadata:

- `delivered_count`: Number of successful deliveries
- `error_message`: Last delivery error (SMTP or other)

Admin endpoint `GET /admin/api/newsletters/stats` returns:

- Total newsletters generated
- Total deliveries
- Delivery success rate
- Error breakdown

## Celery Schedule

`generate-newsletters` runs daily at 8:00 AMAmerica/New_York) via Celery Beat. The schedule is configurable in `pipeline.yaml` under `schedule:` section:

```yaml
schedule:
  generate-newsletters:
    cron: "0 8 * * *"
```

## Idempotency

A Redis key prevents duplicate generation:

```python
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
idempotency_key = f"idempotency:newsletter:{today}"
if redis_client.exists(idempotency_key):
    return {"skipped": True, "reason": "already_generated_today"}
```

The key is set with a 2-day TTL after successful generation.

## Distributed Lock

A Lua script ensures only one newsletter generation runs at a time:

```lua
-- ainews:newsletter_lock
local current = redis.call('GET', KEYS[1])
if current == ARGV[1] then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return 1
elseif not current then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return 2
else
    return 0
end
```

If another task holds the lock, generation is skipped.

## Dry Run Mode

Pass `dry_run_email=admin@example.com` to send to a single address instead of all subscribers. Useful for testing.

## Webhooks

Newsletter events can trigger webhooks. The `nl` parameter passed to webhooks is a `NewsletterConfig` object (not a `Newsletter` model), so `newsletter_id` is always NULL in webhook payloads.

Known issue: `article.failed` and `newsletter.failed` events are defined in `services/webhooks.py:KOWN_WEBHOOK_EVENTS` but no code currently calls `trigger_event()` for these events.