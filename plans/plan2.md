# Documentation Improvement Plan (plan2.md)

**Date:** 2026-04-28  
**Scope:** Rewrite/update documentation to add operational value, fix errors, and fill documentation gaps across the ainews project.

---

## Executive Summary

A deep-dive audit of all documentation files revealed **20+ specific issues** across 10 documentation files, plus 3 entirely missing documents. The core problems are:

1. **Bare feature lists** — README.md "Features" section and multiple tables list *what* exists but not *why it matters* or *what to do* with the information.
2. **Documented-but-not-implemented claims** — Wrong pipeline flow, wrong Celery decorator, wrong API URLs, wrong environment variables.
3. **Implemented-but-not-documented features** — Cost tracking, A/B experiments, ShareConfig, AuditLog, ArticleMetric, newsletter delivery stats.
4. **Dead references** — Component docs reference `share-a11y.js` (doesn't exist) and `share_button.html` (actual: `share_macro.html`).

---

## TIER 1: Critical Fixes (Do First — Prevent User/Developer Errors)

### 1. Fix `docs/development.md` — Lines 182-207 (Wrong LLM Provider Section)

**Problem:** The first "Adding a New LLM Provider" section tells users to create `adapters/myprovider.py` with `LLMAdapter` base class. Actual providers live in `services/llm/` and use `BaseLLMProvider`. This section is entirely wrong and contradicts the correct section at lines 383-408.

**Action:** Delete lines 182-207 entirely. Keep only the correct section at lines 383-408.

**Verification:** After deletion, search `docs/development.md` for "adapters/" — should return 0 results.

---

### 2. Fix `docs/development.md` — Lines 208-225 (Wrong Celery Decorator)

**Problem:** Uses `@celery_app.task(bind=True, ...)` but actual tasks use `@shared_task(...)`. Also missing `run_id` parameter and `autoretry_for` details.

**Replace lines 218-222 with:**
```python
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def new_stage(self, article_id: int, run_id=None):
    from tasks.pipeline import run_stage

    def work(article, provider, model, max_tokens):
        # Implementation using provider.chat_structured()
        pass

    return run_stage(
        "new_role", article_id, work,
        task_self=self, run_id=run_id, skip_next="next_status"
    )
```

---

### 3. Fix `docs/pipeline.md` — Lines 72-79 (Wrong Per-Stage Failure Action)

**Problem:** Doc says "After 3 failures, article is routed to **review**". Actual code in `services/pipeline_failure.py:105` marks article `FAILED`, not `REVIEW`.

**Action:** Change line 77 (table row) to:
```
| After 3 failures, article is marked `failed` (permanent failure for that stage) |
```

**Also fix line 79:** Change "Articles with 2+ degradations are routed to manual review" → "Articles with 2+ degradations are routed to review OR marked done (depending on degradation count and content quality)."

---

### 4. Fix `docs/pipeline.md` — Valid Transitions Table (Lines 15-30)

**Problem:** Rows 20 (`researching → review`) and 23 (`writing → review`) are listed but NOT in `constants.py VALID_TRANSITIONS`. These transitions will raise `InvalidStateTransitionError`.

**Actions:**
- Remove row 20 (`researching → review`) — not valid
- Remove row 23 (`writing → review`) — not valid  
- Change row 30 from `review → researching` to `failed → pending` with note "Reprocess via admin"
- Add row: `pending → review` with note "Low-confidence selection or manual override"

---

### 5. Fix `docs/api.md` — Authentication Section (Lines 599-611)

**Problem:** Says "HTTP Basic Authentication" for admin endpoints. Actual implementation uses **session-based auth** via `@require_auth` checking `session.get("admin")`. HTTP Basic Auth is NOT used anywhere.

**Replace with:**
```markdown
## Authentication

Admin endpoints require session-based authentication via `/admin/login`.

### Login
**POST** `/admin/login`
- Rate limited to 10 requests per minute
- After 5 failed attempts within 15 minutes → 15 minute lockout (Redis Lua script with in-memory fallback)

**Request Body (form-data):**
- `password`: Admin password (hashed with scrypt/pbkdf2/argon2)

**Response:**
- Success: Redirects to `/admin/`
- Failure: Returns login page with error, or 429 if locked out

### Logout
**POST** `/admin/logout` — Clears session and redirects to homepage.
```

---

### 6. Fix `docs/api.md` — Public Endpoint URLs

**Problem:** Multiple URL errors:
- Line 58: Says `/rss` but actual route is `/feed`
- Line 75: Says `/article/<short_id>` but actual param is numeric `article_id`
- Lines 82-99: Subscribe says JSON body but actual uses `request.form` (HTML form)

**Changes:**
- Line 58: Change `**GET** '/rss'` to `**GET** '/feed'`
- Line 66: Add note: "Parameters: `sort` (optional): 'recent', 'impact', or 'published'"
- Lines 75-80: Change to `**GET** '/article/<article_id>'` with note that numeric ID is used
- Add after line 80: "**Short URLs:** `GET /s/<short_id>` redirects to article; `GET /a/<short_id>` shows share tracking page"
- Lines 82-99: Rewrite subscribe section to show form-data, not JSON; add that response is HTML partial (HTMX) or redirect

---

## TIER 2: High-Value Additions (Do Next — Fill Documentation Gaps)

### 7. Add Cost Tracking Section to `docs/configuration.md`

**Problem:** Cost tracking is fully implemented in `services/cost_tracker.py` with 18+ model pricing tiers, but is completely absent from `docs/configuration.md`.

**Add new section after line 305 (memory section):**
```markdown
### Cost Tracking

LLM cost estimation is provided by `services/cost_tracker.py`. The system reads
`llm.tokens` and `llm.calls` counters from `MetricsCollector` and applies
configurable pricing rates.

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `COST_RATES` | (see defaults) | JSON pricing rates per 1M tokens (USD) |
| `COST_INPUT_RATIO` | `0.6` | Blended rate: percentage treated as input tokens |
| `COST_OUTPUT_RATIO` | `0.4` | Blended rate: percentage treated as output tokens |

**Default rates** (defined in `services/cost_tracker.py:_DEFAULT_RATES`):
OpenAI gpt-4o ($2.50/$10.00), Anthropic claude-sonnet-4-5 ($3.00/$15.00),
DeepSeek ($0.27/$0.42), MiniMax ($0.20/$1.10), Gemini 2.0 Flash ($0.10/$0.40),
and 12 more provider/model combinations.

**API Endpoint:** `GET /admin/api/costs` returns cost summary as JSON.
```

---

### 8. Add Experiments Section to `docs/configuration.md`

**Problem:** A/B experiment system is implemented (`pipeline.yaml:experiments:`, `tasks/select.py:_assign_experiment_group()`) but entirely missing from configuration docs.

**Add new section after pipeline stages section:**
```markdown
### `experiments:` — A/B Testing

Controls A/B testing for writer and editor stages. When enabled, articles are
deterministically assigned to control or variant groups using MD5 hashing.

```yaml
experiments:
  enabled: true
  assignment_salt: "${EXPERIMENT_SALT}"
  prompt_variants:
    writer:
      control: |
        You are a professional tech news writer...
      variant_a: |
        You are a data-driven tech writer...
      variant_b: |
        You are a narrative tech journalist...
    editor:
      control: |
        You are a meticulous editor...
      variant_a: |
        You are a copy editor...
      variant_b: |
        You are a content strategist editor...
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `enabled` | Enable/disable A/B experiments |
| `assignment_salt` | Salt for deterministic MD5-based assignment (from `EXPERIMENT_SALT` env var) |
| `prompt_variants` | Variant prompts for `writer` and `editor` stages |

**How it works:**
1. Article ID + salt → MD5 hash → 70% control / 15% variant_a / 15% variant_b
2. `article.experiment_group` stores the assignment
3. Pipeline uses variant prompt if assigned to variant group
```

---

### 9. Fix Beat Schedule Count in Multiple Files

**Problem:** `docs/configuration.md` line 338, `docs/operations.md` line 5, and `docs/monitoring.md` say "Nine scheduled tasks" but `config.py:get_beat_schedule()` has **12 tasks**.

**Files to fix:**
- `docs/configuration.md` line 338: Change "Nine scheduled tasks" to "Twelve scheduled tasks"
- `docs/operations.md` line 5: Change "Nine scheduled tasks" to "Twelve scheduled tasks"
- `docs/monitoring.md`: Search for "9 tasks" or "Nine" in beat schedule context, fix similarly

**Also add missing tasks to configuration.md table (lines 344-355):**
- Add row: `purge-trend-memory | Daily 3:45 AM | Purge expired memory entries`
- Fix row: `cleanup-old-article-versions` → `cleanup-old-versions` (to match config.py name)

---

### 10. Rewrite README.md Features Section (Lines 49-58)

**Problem:** Bare feature list with no operational context. Each bullet says *what* the system does but not *why it matters* or *what the user should know*.

**Replace lines 49-58 with:**
```markdown
## Features

| Feature | What It Does | Why It Matters | What to Do |
|---------|---------------|----------------|------------|
| **AI-Powered Pipeline** | 4-stage LLM processing (select → research → write → edit) | Each stage has independent retry budgets; degradation handlers ensure articles publish even when non-critical stages fail | Monitor `/admin/api/pipeline/stats`; if `failure` > 5% → check `/admin/api/pipeline/dead-letter/stats` |
| **Automated Ingestion** | Scheduled polling of configurable RSS/API sources | Fresh content without manual intervention; auto-disable after 10 consecutive failures | Monitor `/admin/api/sources/health`; re-enable via admin UI |
| **Topic Classification** | Automatic categorization using configurable regex patterns | Readers find relevant content faster; admins can override via UI | Configure `topics.yaml` with display names and colors |
| **Newsletter Generation** | Curated newsletters from aggregated content, sent daily | Hands-off audience engagement with configurable schedules | Preview at `POST /admin/api/newsletter/preview` |
| **Full-Text Search** | SQLite FTS5-powered article search with analytics | Users find content fast; zero-result queries highlight gaps | Check `/admin/api/search/analytics` for top queries |
| **Admin Dashboard** | Web UI for managing sources, articles, topics, newsletters | Single pane of glass for operations | Access at `/admin/login` |
| **RSS Output** | Published feed at `/feed` for downstream consumption | Allows feed readers and aggregators to syndicate content | Validate with `curl http://localhost:5000/feed` |
| **PWA Support** | Offline-capable with service worker and manifest | Mobile-friendly reading experience even without connectivity | Install prompt appears automatically on compatible browsers |
| **Cost Tracking** | LLM token usage and cost estimation per provider/model | Predictable LLM spend; identify expensive models at a glance | Monitor `GET /admin/api/costs` for cost breakdown |
```

---

### 11. Fix README.md Pipeline Flow (Line 47)

**Problem:** Shows `crawl → extract → select → research → write → edit → publish` but:
- `extract` is part of crawl task, not a separate pipeline stage
- `publish` is not a status; article becomes `done` after edit stage
- Missing `selecting` transient status

**Change to:**
```markdown
**Pipeline:** `crawl (extract) → select → research → write → edit → done`
```
(Note: extract runs during crawl; publish happens when edit stage sets `pipeline_status=DONE`)
```

---

### 12. Fix README.md Architecture Diagram (Lines 33-45)

**Problem:** Shows "Granian (WSGI)" but Granian is an **ASGI** server with `WsgiToAsgi` adapter. Also missing Celery Beat and has wrong LLM list.

**Change to:**
```markdown
```
Nginx → Granian (ASGI) → Flask (WSGI via WsgiToAsgi adapter)
                      │
           ┌──────────┴──────────┐
           │                     │
      Celery Worker        SQLite (WAL)
      Celery Beat              │
           │                  │
         Redis ←──────────────┘
      (broker + cache)

      LLM (Ollama / OpenAI / Anthropic / DeepSeek / Gemini / ...)
```
```

---

## TIER 3: Missing Documentation (Create/Expand)

### 13. Create `docs/share-config.md` (New File)

**Problem:** ShareConfig model exists in `models.py:260-272`, admin UI at `/admin/shares`, public share buttons rendered from database config — but NO documentation exists.

**New file content:**
```markdown
# Share Configuration

## Overview

The share configuration system allows administrators to manage social sharing platforms
via the database. Share buttons on article pages are rendered based on active
`ShareConfig` records.

## ShareConfig Model

| Field | Type | Description |
|-------|------|-------------|
| platform_key | String(32), unique | Internal key (e.g., "x", "facebook") |
| label | String(64) | Display name shown to users |
| url_template | String(512) | Share URL with `{url}` and `{title}` placeholders |
| icon_name | String(32) | Icon identifier for the share macro |
| active | Boolean | Whether this platform shows on articles |
| sort_order | Integer | Display order (lower = first) |

## URL Template Placeholders

- `{url}` - Replaced with the article's short URL
- `{title}` - Replaced with the URL-encoded article title

Example template for X (Twitter):
```
https://x.com/intent/tweet?url={url}&text={title}
```

## Admin UI

**URL:** `/admin/shares`

### Managing Platforms
- **Add**: Click "+ add platform", fill in the form (all fields required)
- **Edit**: Click the edit button on a row, modify, save
- **Delete**: Click delete button (with confirmation)
- **Toggle**: Click the status toggle to activate/deactivate

### Default Platforms

Seeded on first run (in `app.py:_seed_share_configs()`):
1. X (Twitter) - sort_order: 1
2. Facebook - sort_order: 2
3. LinkedIn - sort_order: 3
4. Reddit - sort_order: 4

## Share Tracking

Share interactions are tracked via `ArticleMetric`:

| Event | Metric Field | Triggered By |
|-------|--------------|---------------|
| Button click | `share_button_clicks` | User clicks share button in dropdown |
| Link view | `share_link_views` | User visits `/s/<short_id>` or `/a/<short_id>` |

## Public Routes

- `GET /s/<short_id>` - Short URL redirect (302 to `/article/<id>`)
- `GET /a/<short_id>` - Share tracking page with social links
- `POST /api/track/share-click/<article_id>` - Track share button click (CSRF protected)
```

---

### 14. Expand `docs/analytics.md` — Add ArticleMetric and SearchQuery Sections

**Problem:** ArticleMetric model (page_loads, newsletter_clicks, share_button_clicks, share_link_views) only mentioned in passing for reading time. SearchQuery model not documented. Cost tracking section missing `call_count` field.

**Add after Search Analytics section:**
```markdown
## Article Metrics

**GET** `/admin/metrics`

Tracks article engagement metrics stored in the `article_metrics` table.

### Metric Types

| Field | Description | Triggered By |
|-------|-------------|---------------|
| `page_loads` | Article detail page views | Visiting `/article/<id>` |
| `share_button_clicks` | Share button clicks | Clicking share in dropdown (tracked via API) |
| `share_link_views` | Short URL views | Visiting `/s/<short_id>` or `/a/<short_id>` |
| `newsletter_clicks` | Clicks from newsletter | Clicking article link in newsletter |

### Implementation

Metrics are incremented using `track_metric()` in `services/article.py`:
```python
from services.article import track_metric
track_metric(article_id, ArticleMetric.page_loads)
```
Uses SQLite `INSERT ... ON CONFLICT DO UPDATE` for atomic increments.

### Metrics Page

The `/admin/metrics` page shows:
- Summary cards (total page loads, share clicks, link views)
- Top articles by page loads, share clicks, share link views
- Date range filtering (7, 30, 90 days or all time)
```

**Also expand Cost Tracking section to add:**
```markdown
### Response Fields

| Field | Description |
|-------|-------------|
| `total_tokens` | Sum of all tokens consumed |
| `total_cost_usd` | Sum of all estimated costs |
| `total_calls` | Sum of all API calls |
| `models` | Per-model breakdown with `call_count` |
```

---

### 15. Expand `docs/security.md` — Add AuditLog and CSP Sections

**Problem:** AuditLog model + `log_admin_action()` + audit API endpoint are barely mentioned. CSP section documents Nginx headers but not actual Flask-Talisman directives from `app.py`.

**Add after line 261 (Audit Logging section):**
```markdown
### AuditLog Database Table

All admin actions are persisted to the `audit_logs` table.

| Field | Type | Description |
|-------|------|-------------|
| action | String(64) | Action performed (e.g., "article_edit") |
| category | String(32) | Grouping: auth, article, pipeline, webhook, config, subscriber |
| target_type | String(32) | Entity type acted upon |
| target_id | Integer | ID of entity (nullable) |
| user | String(64) | User performing action (default: "admin") |
| details | JSON | Additional context about the action |
| ip_address | String(45) | IP address of the user |
| created_at | DateTime | Timestamp |

### Using log_admin_action()

```python
from services.audit import log_admin_action

log_admin_action(
    action="article_bulk_delete",
    target_type="article",
    category="article",
    details={"count": 5, "ids": [1, 2, 3, 4, 5]},
)
```

### Audit API Endpoint

**GET** `/admin/api/audit-logs`

Query parameters:
- `action` (optional) - Filter by action type
- `target_type` (optional) - Filter by target type
- `page` (default: 1) - Page number
- `per_page` (default: 50, min: 10, max: 200) - Results per page
- `days` (default: 7, min: 1, max: 90) - Only show logs from last N days

Response:
```json
{
  "logs": [
    {
      "id": 1,
      "action": "article_edit",
      "target_type": "article",
      "target_id": 123,
      "user": "admin",
      "details": {"category": "ai"},
      "ip_address": "127.0.0.1",
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "page": 1,
  "per_page": 50,
  "total": 150,
  "has_next": true
}
```
```

**Also update Security Headers section (lines 265-273) to show actual Flask-Talisman CSP:**
```markdown
## Security Headers

### Application-Level Headers (Flask-Talisman)

Configured in `app.py` using Flask-Talisman:

| Header | Value |
|--------|-------|
| Content-Security-Policy | default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self' |
| X-Content-Type-Options | nosniff |
| X-Frame-Options | SAMEORIGIN |
| Referrer-Policy | strict-origin-when-cross-origin |
| Strict-Transport-Security | max-age=31536000 |

### CSP Nonce for Inline Scripts

Inline `<script>` tags must include `nonce="{{ csp_nonce() }}"` attribute.
Configured via `content_security_policy_nonce_in=["script-src"]`.
```
---

### 16. Add Workflow Guidance to `docs/api.md`

**Problem:** Endpoint lists are bare — they show request/response but not *how to accomplish tasks* using multiple endpoints.

**Add "Common Workflows" subsection after each major endpoint group:**

Example for Bulk Article Operations:
```markdown
### Common Workflows

**Workflow: Reprocess stuck articles**
1. Get dead letter stats: `GET /admin/api/pipeline/dead-letter/stats`
2. Get article IDs: `GET /admin/api/articles/ids?status=failed&limit=100`
3. Bulk reprocess:
   ```bash
   curl -X POST /admin/api/articles/bulk \
     -H "Content-Type: application/json" \
     -d '{"article_ids": [1,2,3], "action": "reprocess"}'
   ```

**Workflow: Bulk tag articles**
1. Get article IDs by filter: `GET /admin/api/articles/ids?source_id=5`
2. Add tags:
   ```json
   {"article_ids": [1,2,3], "action": "add_tags", "tags": ["breaking", "ai"]}
   ```

Add similar workflows for:
- Configure a new LLM provider (providers.yaml → config reload)
- Set up newsletter delivery (sources → articles → newsletter preview → send)
```

### 17. Add Admin Article Search Documentation to `docs/api.md`

**Problem:** `docs/api.md` lines 593-595 briefly mentions article search but doesn't document all capabilities found in `routes/admin/articles.py`: URL search, source filtering, date range, impact score range, tag filtering.

**Add after the bulk operations section:**
```markdown
### Admin Article Search

The admin articles page (`/admin/articles`) supports advanced filtering:

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | String | Search query — searches title by default, or URL if query looks like URL |
| `status` | String | Filter by pipeline status (pending, researching, writing, completed, failed) |
| `category` | String | Filter by category |
| `source_id` | Integer | Filter by source ID |
| `date_from` | ISO Date | Filter articles created on or after this date |
| `date_to` | ISO Date | Filter articles created on or before this date |
| `impact_min` | Integer | Minimum impact score |
| `impact_max` | Integer | Maximum impact score |
| `tag` | String | Filter by tag slug |
| `page` | Integer | Page number (default: 1) |

### URL Detection

If the search query:
- Starts with `http://` or `https://`, OR
- Parses as a URL with scheme and netloc

...then the search filters by `original_url` instead of `original_title`.

### API for Bulk Selection

**GET** `/admin/api/articles/ids`

Returns up to 1000 article IDs matching the current filter params (same parameters as above).

Response:
```json
{
  "ids": [1, 2, 3],
  "count": 3
}
```
```

### 18. Create `docs/components/pagination.md` (New File)

**Problem:** Pagination component exists in `templates/partials/pagination.html` and `static/css/articles.css:1085-1121` but has no documentation.

**New file content:**
```markdown
# Pagination Component

## Overview

The pagination component provides page navigation for article lists and admin tables.

## Structure

```html
<nav class="pagination" aria-label="Pagination">
  <a href="?page=1" class="page-link">&laquo; First</a>
  <a href="?page=2" class="page-link">&lsaquo; Prev</a>
  <span class="page-current">3</span>
  <a href="?page=4" class="page-link">4</a>
  <a href="?page=5" class="page-link">Next &rsaquo;</a>
  <a href="?page=10" class="page-link">Last &raquo;</a>
</nav>
```

## CSS Classes

| Class | Description |
|-------|-------------|
| `.pagination` | Container nav element |
| `.page-link` | Individual page link |
| `.page-current` | Current page indicator (no link) |
| `.page-ellipsis` | Ellipsis separator for skipped pages |

## Usage

The `pagination_nav()` macro in `templates/partials/pagination.html` generates pagination:
```jinja2
{{ pagination_nav(pagination, request.args) }}
```

**Parameters:** Passes the pagination object and current request args to preserve query parameters.

## Related Files

- `templates/partials/pagination.html` — Jinja2 macro
- `static/css/articles.css` — Styles at lines 1085-1121
```

### 19. Create `docs/components/search-container.md` (New File)

**Problem:** Search container component exists in `static/css/articles.css:760-831` (`.search-container`, `.search-input`, `.search-kbd`) but has no documentation.

**New file content:**
```markdown
# Search Container Component

## Overview

The search container provides the article search UI with keyboard shortcut support (press `/` to focus).

## Structure

```html
<div class="search-container">
  <form method="GET" action="/" class="search-form">
    <svg class="search-icon"><!-- magnifying glass icon --></svg>
    <input type="text" name="q" class="search-input"
           placeholder="Search articles..." aria-label="Search articles">
    <kbd class="search-kbd">/</kbd>
    <button type="button" class="search-clear" aria-label="Clear search">&times;</button>
  </form>
</div>
```

## CSS Classes

| Class | Description |
|-------|-------------|
| `.search-container` | Wrapper div with relative positioning |
| `.search-form` | The form element |
| `.search-icon` | Magnifying glass SVG icon |
| `.search-input` | Text input field (full width, with padding for icon) |
| `.search-kbd` | Keyboard shortcut hint (`/` key) |
| `.search-clear` | Clear/reset button (hidden when input is empty) |

## Keyboard Shortcut

Press `/` key anywhere on the page to focus the search input. The shortcut is registered in `static/js/app.js`.

## Usage

Used on the homepage and topic pages via:
```jinja2
{% from "partials/search.html" import search_box %}
{{ search_box() }}
```

## Related Files

- `templates/partials/search.html` — Search box partial
- `static/css/articles.css` — Styles at lines 760-831
- `static/js/app.js` — Keyboard shortcut registration
```

---

## TIER 4: Low-Effort Cleanup

### 20. Fix `docs/pipeline.md` — Duplicate Detection Limit (Line 88)

**Problem:** Says "Max 1000 comparisons" but actual default is 200 (`DUPLICATE_DETECTION_LIMIT` env var, default 200).

**Fix:** Change line 88 to: `| Limit | Max 200 comparisons per check (configurable via `DUPLICATE_DETECTION_LIMIT`, default 200) |`

---

### 21. Remove Duplicate Sections in `docs/api.md`

**Problem:** Worker Health (lines 158-180 and 546-561) and Task Status (lines 182-197 and 563-578) appear twice.

**Fix:** Remove the second occurrence of each (lines 546-578). Keep the first occurrence.

---

### 22. Add "What to Do" Column to Pipeline Status Table in `docs/pipeline.md`

**Problem:** Table (lines 33-43) lists 8 statuses with meanings but no operational guidance.

**Add column:**
```markdown
| Status | Meaning | What to Do |
|--------|---------|------------|
| pending | Awaiting selection | No action; waits for scheduled run or manual trigger |
| researching | LLM evaluating newsworthiness | Monitor; if stuck >30min check Celery worker health |
| writing | LLM drafting article | Same as researching |
| editing | LLM reviewing/polishing | Same as researching |
| review | Needs manual review | **Action required**: Visit `/admin/review` to approve/reject |
| done | Published | No action needed |
| failed | Permanently failed (can be reprocessed) | **Action**: Check `/admin/api/pipeline/dead-letter/stats`; reprocess via bulk API |
| skipped | Not selected (below min_score) | No action needed |
```

---

### 23. Fix Component Docs — Dead References

**Problem:** Multiple component docs reference non-existent files.

**Fix `docs/components/share-button.md` line 115:**
- Change `static/js/share-a11y.js` to `static/js/app.js`
- Change `templates/partials/share_button.html` to `templates/partials/share_macro.html`

**Fix `docs/components/badge.md`:**
- Line 71-81: CSS uses hardcoded `rgba()` values, not `--purple-alpha-10` variables. Update doc to show actual CSS values OR update CSS to use variables (prefer fixing CSS to match doc).

**Fix `docs/components/article-card.md`:**
- Line 71: Change `font-size: 0.85rem` to `font-size: var(--text-lg); /* 1rem */` (actual value in articles.css)
- Line 124: Change `transform: translateY(-1px)` to `translateY(-2px)` (actual value in articles.css)

**Fix `docs/components/theme-toggle.md`:**
- Lines 9-17: SVG icons are swapped — "Sun icon (shown in dark mode)" actually shows moon SVG. Swap labels to match actual implementation.

---

## Implementation Order

Execute in this exact order to maximize impact and prevent errors:

```
1. README.md (Tier 2 items 10,11,12)     — Highest visibility, first impression
2. development.md (Tier 1 items 1,2)        — Prevents new developer errors
3. pipeline.md (Tier 1 items 3,4 + Tier 4 items 20,22)
4. configuration.md (Tier 2 items 7,8,9)    — Fill major gaps
5. api.md (Tier 1 items 5,6 + Tier 4 item 21 + Tier 3 items 16,17)
6. security.md (Tier 3 item 15)            — Expand AuditLog + CSP docs
7. analytics.md (Tier 3 item 14)         — Expand ArticleMetric + cost sections
8. Create share-config.md (Tier 3 item 13)  — New file
9. Create pagination.md (Tier 3 item 18)    — New component doc
10. Create search-container.md (Tier 3 item 19) — New component doc
11. Component docs (Tier 4 item 23)        — Fix dead references
```

---

## Verification Checklist

After each file is updated, verify:

- [ ] All dead references removed (search for share-a11y.js, share_button.html)
- [ ] All code references match actual implementation (check constants.py, models.py, services/)
- [ ] All tables have "What to Do" or operational context columns
- [ ] All API endpoints verified against actual routes in routes/
- [ ] All env vars cross-checked against config.py
- [ ] All new sections follow existing documentation style (code blocks, tables, markdown formatting)
- [ ] Run `.venv/bin/ruff check . --exclude .venv` to ensure no syntax errors in any .py code examples
- [ ] Run `.venv/bin/python -m pytest tests/ -x -q` to ensure no regressions

---

## Estimated Effort

| Task | Est. Time | Risk |
|------|-----------|------|
| README.md updates | 20 min | Low |
| development.md fixes | 15 min | Low |
| pipeline.md fixes | 20 min | Low |
| configuration.md expansions | 25 min | Low |
| api.md workflow additions | 45 min | Low |
| security.md expansions | 20 min | Low |
| analytics.md expansions | 20 min | Low |
| Create share-config.md | 30 min | Low |
| Component doc fixes | 20 min | Low |
| **Total** | **~3 hours** | All Low risk |

---

## Success Criteria

When complete, a new developer should be able to:
1. Read README.md and understand not just *what* ainews does, but *why each feature matters* and *what to monitor*
2. Follow development.md to add a new LLM provider without hitting wrong directories or classes
3. Check pipeline.md to understand not just status names, but *what action to take* for each state
4. Configure cost tracking via configuration.md and monitor spend via the API
5. Set up A/B experiments following the new configuration.md section
6. Use api.md workflows to accomplish tasks (reprocess articles, configure webhooks)
7. Understand share configuration via the new share-config.md
8. Trust that all component doc references point to real files
