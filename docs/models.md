# Database Models

This document describes all 19 models (plus 1 association table) defined in `models.py`.

## Association Table

| Table | Purpose |
|-------|---------|
| `article_tags` | Many-to-many relationship between articles and tags |

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `Source` | `sources` | News sources (RSS feeds, websites) with crawl health tracking |
| `Tag` | `tags` | Article tags with unique slug for URL-friendly references |
| `Article` | `articles` | Core article model with pipeline fields, SLA timestamps, and embeddings |
| `Citation` | `citations` | Article citations with URL, title, author, and position |
| `Newsletter` | `newsletters` | Generated newsletters with delivery tracking |
| `Subscriber` | `subscribers` | Email subscribers with verification, bounce tracking, and preferences |
| `ArticleMetric` | `article_metrics` | Engagement metrics (page loads, clicks, shares) |
| `ShareConfig` | `share_configs` | Social sharing platform configurations |
| `PipelineRun` | `pipeline_runs` | Pipeline execution tracking (crawl/newsletter runs) |
| `PipelineLog` | `pipeline_logs` | Detailed logs for each pipeline run and article |
| `ArticleVersion` | `article_versions` | Content version history for audit trail and rollback |
| `TopicNote` | `topic_notes` | Editorial notes per topic with source attribution |
| `TrendMemory` | `trend_memory` | Tiered memory for trending topics with TTL |
| `Webhook` | `webhooks` | Webhook endpoints with secret, events, and health tracking |
| `WebhookEvent` | `webhook_events` | Webhook delivery attempts with status and idempotency |
| `AuditLog` | `audit_logs` | Admin action audit trail with category and target tracking |
| `SearchQuery` | `search_queries` | Search query logging with click tracking |
| `ApiToken` | `api_tokens` | API tokens with hashed secret, prefix, expiry, and revocation |
| `AdminUser` | `admin_users` | Admin users with TOTP 2FA support |

## Model Details

### Source
**Table:** `sources`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `source_key` | String(64) | Unique, not null |
| `name` | String(128) | Not null, indexed |
| `url` | String(512) | |
| `feed_url` | String(512) | |
| `source_type` | String(32) | Not null, indexed |
| `active` | Boolean | Default: True, indexed |
| `last_crawled` | DateTime | |
| `created_at` | DateTime | Default: UTC now |
| `consecutive_failures` | Integer | Default: 0, indexed |
| `consecutive_successes` | Integer | Default: 0 |
| `last_success_at` | DateTime | |
| `last_error` | Text | |
| `disabled_at` | DateTime | Indexed |

**Relationships:**
- `articles`: Dynamic relationship to `Article` (cascade delete)

---

### Tag
**Table:** `tags`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `name` | String(64) | Unique, not null |
| `slug` | String(64) | Unique, not null, indexed |
| `created_at` | DateTime | Default: UTC now |

---

### Article
**Table:** `articles`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `short_id` | String(12) | Unique, indexed |
| `source_id` | Integer | FK to sources, not null, indexed |
| `external_id` | String(128) | Indexed |
| `original_url` | String(2048) | |
| `original_title` | String(512) | |
| `original_author` | String(128) | |
| `original_published_at` | DateTime | |
| `extracted_text` | Text | |
| `pipeline_status` | String(32) | Default: "pending" |
| `selector_result` | JSON | |
| `research_brief` | Text | |
| `draft_article` | Text | |
| `final_article` | Text | |
| `original_ai_article` | Text | Immutable AI version |
| `writer_model` | String(128) | |
| `impact_score` | Integer | Default: 0 |
| `summary` | Text | Legacy field |
| `category` | String(32) | Indexed |
| `topics` | JSON | |
| `raw_metadata` | JSON | |
| `extraction_status` | String(32) | Default: "pending" |
| `retry_count` | Integer | Default: 0 |
| `total_retries` | Integer | Default: 0 |
| `degradation_count` | Integer | Default: 0 |
| `pipeline_started_at` | DateTime | |
| `last_error` | Text | |
| `created_at` | DateTime | Default: UTC now |
| `updated_at` | DateTime | Default: UTC now, indexed |
| `scheduled_publish_at` | DateTime | Indexed |
| `crawled_at` | DateTime | Indexed (SLA) |
| `selected_at` | DateTime | Indexed (SLA) |
| `published_at` | DateTime | Indexed (SLA) |
| `citations` | Relationship | To Citation (cascade delete) |
| `experiment_group` | String(32) | Indexed |
| `embedding` | Text | JSON array for vector embedding |
| `tags` | Relationship | Many-to-many via article_tags |
| `metrics` | Relationship | One-to-one to ArticleMetric |

**Indexes:**
- `uq_source_external_id`: Unique constraint on (source_id, external_id)
- `ix_articles_status_created`: (pipeline_status, created_at)
- `ix_articles_published`: (original_published_at)
- `ix_articles_impact`: (impact_score)
- `ix_articles_category_status`: (category, pipeline_status)
- `ix_articles_total_retries`: (total_retries)
- `ix_articles_pipeline_status`: (pipeline_status)
- `ix_articles_retry_count`: (retry_count)
- `ix_articles_degradation_count`: (degradation_count)

**Events:**
- `before_update`: Auto-updates `updated_at`

---

### Citation
**Table:** `citations`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `article_id` | Integer | FK to articles, not null, indexed |
| `url` | String(2048) | Not null |
| `title` | String(512) | |
| `author` | String(128) | |
| `context` | Text | |
| `position` | Integer | Default: 1 |

---

### Newsletter
**Table:** `newsletters`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `newsletter_type` | String(32) | Not null, indexed ("main" or topic key) |
| `subject` | String(256) | |
| `html_content` | Text | |
| `article_count` | Integer | Default: 0 |
| `recipients` | Integer | Default: 0 |
| `delivered_count` | Integer | Default: 0 |
| `error_message` | Text | |
| `generated_at` | DateTime | Default: UTC now |
| `sent_at` | DateTime | Indexed |

---

### Subscriber
**Table:** `subscribers`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `email` | String(256) | Not null, indexed |
| `newsletter_type` | String(32) | Not null, indexed |
| `unsubscribe_token` | String(64) | Unique, not null, indexed, default: random URL-safe token |
| `verification_token` | String(64) | Unique, nullable, indexed |
| `subscribed_at` | DateTime | Default: UTC now |
| `confirmed_at` | DateTime | Indexed |
| `active` | Boolean | Default: True |
| `deleted_at` | DateTime | Soft delete |
| `preferences` | JSON | Default: dict |
| `bounce_count` | Integer | Default: 0 |
| `last_bounce_at` | DateTime | |
| `last_active_at` | DateTime | Indexed |

**Constraints:**
- `uq_email_newsletter`: Unique constraint on (email, newsletter_type)

**Properties:**
- `is_verified`: True if `confirmed_at` is set

**Class Methods:**
- `get_active()`: Returns query for active, non-deleted subscribers

---

### ArticleMetric
**Table:** `article_metrics`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `article_id` | Integer | FK to articles, unique, not null, indexed |
| `page_loads` | Integer | Default: 0 |
| `newsletter_clicks` | Integer | Default: 0 |
| `share_button_clicks` | Integer | Default: 0 |
| `share_link_views` | Integer | Default: 0 |
| `updated_at` | DateTime | Default: UTC now |

**Events:**
- `before_update`: Auto-updates `updated_at`

---

### ShareConfig
**Table:** `share_configs`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `platform_key` | String(32) | Unique, not null |
| `label` | String(64) | Not null |
| `url_template` | String(512) | Not null |
| `icon_name` | String(32) | Not null |
| `active` | Boolean | Default: True |
| `sort_order` | Integer | Default: 0 |

---

### PipelineRun
**Table:** `pipeline_runs`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `task_id` | String(64) | |
| `run_type` | String(32) | Not null, indexed ("crawl" or "newsletter") |
| `status` | String(16) | Default: "running" |
| `triggered_by` | String(16) | Default: "scheduled" |
| `articles_fetched` | Integer | Default: 0 |
| `articles_processed` | Integer | Default: 0 |
| `articles_selected` | Integer | Default: 0 |
| `error_message` | Text | |
| `started_at` | DateTime | Default: UTC now |
| `finished_at` | DateTime | Indexed |

**Relationships:**
- `logs`: Dynamic relationship to `PipelineLog` (cascade delete)

---

### PipelineLog
**Table:** `pipeline_logs`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `run_id` | Integer | FK to pipeline_runs, not null, indexed |
| `article_id` | Integer | FK to articles, nullable, indexed |
| `stage` | String(32) | Not null |
| `level` | String(8) | Default: "info" |
| `message` | Text | Not null |
| `created_at` | DateTime | Default: UTC now |

---

### ArticleVersion
**Table:** `article_versions`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `article_id` | Integer | FK to articles, not null, indexed |
| `version_number` | Integer | Default: 1 |
| `final_article` | Text | |
| `original_ai_article` | Text | |
| `source_fields` | JSON | |
| `change_reason` | String(256) | e.g., "admin_edit", "pipeline_edit" |
| `changed_by` | String(64) | e.g., "admin", "pipeline:writer" |
| `created_at` | DateTime | Default: UTC now |

**Constraints:**
- `uq_article_version`: Unique constraint on (article_id, version_number)

**Relationships:**
- `article`: Back-referenced from Article.versions

---

### TopicNote
**Table:** `topic_notes`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `topic` | String(128) | Not null, indexed |
| `note` | Text | Not null |
| `source` | String(256) | |
| `created_at` | DateTime | Default: UTC now |
| `updated_at` | DateTime | Default: UTC now |

**Constraints:**
- `uq_topic_source`: Unique constraint on (topic, source)

---

### TrendMemory
**Table:** `trend_memory`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `topic` | String(128) | Not null, indexed |
| `signal` | Text | Not null |
| `importance` | Integer | Default: 1 |
| `source_article_id` | Integer | FK to articles, nullable, indexed |
| `expires_at` | DateTime | |
| `last_consolidated_at` | DateTime | |
| `created_at` | DateTime | Default: UTC now |
| `embedding` | Text | |

**Indexes:**
- `ix_trend_memory_topic_importance`: (topic, importance)
- `ix_trend_memory_expires_at`: (expires_at)

---

### Webhook
**Table:** `webhooks`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `name` | String(128) | Not null |
| `url` | String(2048) | Not null |
| `secret` | String(128) | Not null |
| `events` | JSON | Default: list |
| `active` | Boolean | Default: True, indexed |
| `created_at` | DateTime | Default: UTC now |
| `updated_at` | DateTime | Default: UTC now |
| `last_triggered_at` | DateTime | |
| `last_success_at` | DateTime | |
| `last_failure_at` | DateTime | |
| `last_error` | Text | |
| `failure_count` | Integer | Default: 0 |

---

### WebhookEvent
**Table:** `webhook_events`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `webhook_id` | Integer | FK to webhooks, not null, indexed |
| `event_type` | String(64) | Not null |
| `status_code` | Integer | |
| `response_body` | Text | |
| `error_message` | Text | |
| `attempt_number` | Integer | Default: 1 |
| `idempotency_key` | String(64) | Indexed |
| `delivered_at` | DateTime | Default: UTC now |
| `payload` | Text | |

---

### AuditLog
**Table:** `audit_logs`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `action` | String(64) | Not null, indexed |
| `category` | String(32) | Indexed |
| `target_type` | String(32) | |
| `target_id` | Integer | |
| `user` | String(64) | Default: "admin" |
| `details` | JSON | |
| `ip_address` | String(45) | |
| `created_at` | DateTime | Default: UTC now |

**Indexes:**
- `ix_audit_logs_target`: (target_type, target_id)

---

### SearchQuery
**Table:** `search_queries`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `query` | String(256) | Not null, indexed |
| `results_count` | Integer | Default: 0 |
| `clicked_article_id` | Integer | FK to articles, nullable, indexed |
| `created_at` | DateTime | Default: UTC now |

**Relationships:**
- `clicked_article`: Relationship to Article

---

### ApiToken
**Table:** `api_tokens`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `token_hash` | String(255) | Unique, not null (werkzeug password hash) |
| `token_prefix` | String(16) | Not null, indexed (first 12 chars of secret for lookup) |
| `name` | String(128) | |
| `created_at` | DateTime | Default: UTC now |
| `last_used_at` | DateTime | Updated on successful verification |
| `expires_at` | DateTime | Optional expiration |
| `revoked_at` | DateTime | Nullable, soft revocation timestamp |

---

### AdminUser
**Table:** `admin_users`

| Field | Type | Attributes |
|-------|------|------------|
| `id` | Integer | Primary key |
| `username` | String(64) | Unique, not null, indexed |
| `password_hash` | String(128) | Not null |
| `totp_secret` | String(32) | |
| `totp_enabled` | Boolean | Default: False |
| `created_at` | DateTime | Default: UTC now |
| `updated_at` | DateTime | Auto-updates on change |

---

## Utility Functions

### `slugify(name: str) -> str`
Converts a string to a URL-friendly slug (lowercase, hyphens, max 64 chars).

### `encode_short_url(article_id: int) -> str`
Encodes an article ID into a short URL code (min 6 chars, custom alphabet).

### `decode_short_url(code: str) -> int | None`
Decodes a short URL code back to an article ID.
