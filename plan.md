# Consolidated Improvement Plan — April 2026

Merges plan2 (LLM providers), plan3 (code review fixes), plan4 (UI fixes),
plan5 (code quality + providers), and plan6 (UI enhancements) into a single
sequenced plan. Organized into waves for parallel sub-agent execution.

Each wave's items are independent and can run concurrently. Verify after
every wave before proceeding.

## COMPLETED — April 2, 2026

All waves (1-5) completed successfully. All items (1A-1P, 2A-2O, 3A-3G, 4A-4D, 5A-5E) implemented and verified.

### Follow-up fixes (April 2, 2026)

- **1O**: Fixed remaining `Model.query.get_or_404()` in `newsletters.py`, `shares.py`, `pipelines.py`
- **2A**: Fixed hardcoded `color: #fff` in `.unsubscribe-confirm-btn` (pages.css:510)
- **3F**: Verified `.card-source` CSS rule exists (articles.css:125-127)
- **3G**: Updated `feed.html` empty states to use `.empty-title` and `.empty-description` classes

---

## Verification (run after each wave)

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Wave 1: Bug fixes & code quality (parallel-safe: different files)

These are the highest-impact fixes — bugs that cause runtime failures or
incorrect behavior. All verified present in the codebase as of 2026-04-02.

### 1A. Fix `track_metric()` unguarded commit

**Severity:** Critical
**File:** `services/article.py:46-48`

`db.session.commit()` without try/except rollback. Wrap per convention:

```python
try:
    db.session.execute(stmt)
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    raise
db.session.expire_all()
```

### 1B. Fix Celery task dispatch before DB commit

**Severity:** Critical
**File:** `routes/admin/api.py:298-313`

Tasks dispatched with `.delay()` (line 300) before `db.session.commit()` (line 310).
Worker may pick up task before commit is visible. Move commit before dispatch.

### 1C. Fix lock re-acquire race condition in newsletter task

**Severity:** Critical
**File:** `tasks/newsletter.py:308-314`

GET-then-SET pattern is not atomic. Add a Lua script to `services/redis_utils.py`:

```lua
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
```

Replace the GET-then-SET in `generate_daily_newsletters` with a call to this
Lua script.

### 1D. Fix `model` may be `None` in limiter release

**Severity:** Warning
**File:** `tasks/pipeline.py:723`

If `get_provider_for_role()` raises, `model` stays `None`. Change
`"model" in locals()` guard to `model is not None`.

### 1E. Fix crawl failures double-counted

**Severity:** Warning
**File:** `tasks/crawl.py:248-256`

`record_crawl_failure` called in aggregation loop, but `crawl_source` already
calls it in its exception handler (line 162). Remove the duplicate call.

### 1F. Fix error response format in `bulk_article_operations`

**File:** `routes/admin/api.py:403-408`

Returns `{"message": "Invalid action..."}` with 400. Per convention, errors
must use `{"error": "..."}`.

### 1G. Narrow exception catch in `redis_utils.py:release_lock`

**File:** `services/redis_utils.py:42`

Catches bare `Exception`. Change to `except redis.exceptions.RedisError:`.
Add `import redis.exceptions` at module level.

### 1H. Narrow exception catch in `config.py:_validate_llm_providers`

**File:** `config.py:190-191`

Change `except Exception` to `except (ImportError, RuntimeError, KeyError, ValueError)`.

### 1I. Fix `_is_password_hash` in `services/validation.py`

**File:** `services/validation.py:121-125`

Checks for SHA256 hex (`^[a-f0-9]{64}$`) but werkzeug produces
`scrypt:...`/`pbkdf2:...`/`argon2:...` format. Fix to detect werkzeug format.
Remove duplicate in `routes/admin/__init__.py:73-75`, import from
`services/validation.py` instead.

### 1J. Fix ThreadPoolExecutor shutdown in `services/url.py`

**File:** `services/url.py:111-118`

`with ThreadPoolExecutor` calls `shutdown(wait=True)` which blocks
indefinitely, negating the 10s timeout. Replace with explicit
`executor.shutdown(wait=False, cancel_futures=True)` in `finally` block.

### 1K. Add retry to `ModelLimiter.release()`

**File:** `services/limiter.py:54-75`

When `release()` fails due to transient Redis error, the slot leaks until
TTL expiry. Add a single retry with short backoff.

### 1L. Fix 5xx errors returning raw SDK exceptions

**Severity:** Warning
**File:** `services/llm/errors.py:49`

5xx errors return the original SDK exception. Add `ProviderServerError` class,
return it for 5xx responses. Add to `autoretry_for` tuples in Celery tasks.

### 1M. Fix `record_provider_success()` fallback tracking

**Severity:** Warning
**File:** `services/llm/__init__.py:72-87`

Records primary provider ID even when fallback was used. Change
`get_provider_for_role()` return type to include actual provider ID.
Update `run_stage()` to pass actual provider ID to `record_provider_success()`.

### 1N. Add LRU eviction to ResponseCache in-memory layer

**Severity:** Warning
**File:** `services/cache.py:78`

L1 in-memory cache grows without bound. Add max size limit with LRU eviction,
similar to `_TTLCache` in `services/url.py`.

### 1O. Replace deprecated `Model.query.get_or_404()`

**Severity:** Minor
**Files:** `routes/admin/articles.py` (7 occurrences), `routes/admin/review.py`,
`routes/admin/sources.py`

Replace with `db.get_or_404(Model, id)`.

### 1P. Fix `_script_cache` memory leak

**Severity:** Minor
**File:** `services/redis_utils.py:35`

Uses plain dict with `id(redis_client)` as key. Clear cache on config reload
or use `weakref.WeakValueDictionary`.

---

## Wave 2: CSS fixes (parallel-safe: different CSS modules)

All CSS/template-only changes. No pipeline, schema, or model logic touched.

### 2A. Fix verify page theming

**File:** `static/css/pages.css:449-519`

Replace 12 hardcoded color values with CSS custom properties:

| Selector | Property | Current | Replace with |
|----------|----------|---------|-------------|
| `.verify-page` | `background` | `#f5f5f5` | `var(--color-bg-page)` |
| `.verify-page` | `font-family` | hardcoded stack | `var(--font-sans)` |
| `.verify-card` | `background` | `#fff` | `var(--bg-primary)` |
| `.verify-card` | `color` | (inherited) | `var(--text-primary)` |
| `.verify-header` | `background` | `#0d1117` | `var(--bg-secondary)` |
| `.verify-header` | `color` | `#fff` | `var(--text-primary)` |
| `.verify-header span em` | `color` | `#58a6ff` | `var(--accent)` |
| `.verify-body h1` | `color` | `#111` | `var(--color-text-heading)` |
| `.verify-body p` | `color` | `#555` | `var(--text-secondary)` |
| `.verify-body a` | `color` | `#58a6ff` | `var(--accent)` |
| `.verify-footer` | `background` | `#f9f9f9` | `var(--bg-subtle)` |
| `.verify-footer` | `border-top` | `#eaeaea` | `var(--border)` |
| `.verify-footer p` | `color` | `#888` | `var(--text-muted)` |

### 2B. Add theme support to verify page

**File:** `templates/verify.html`

Add `data-theme="dark"` to `<html>` tag and load `theme.js` before `</head>`.

### 2C. Extract share redirect inline styles

**Files:** `static/css/articles.css`, `templates/share_redirect.html`

Move 6 inline `style=` attributes to new CSS classes:
`.share-redirect-container`, `.share-redirect-title`,
`.share-redirect-description`, `.share-redirect-input-wrapper`,
`.share-redirect-input`, `.share-redirect-link`.

### 2D. Fix admin offline toast selector mismatch

**File:** `templates/base_admin.html:16`

`class="offline-toast"` doesn't exist in CSS. Change to
`class="toast toast-hidden" role="status" aria-live="polite"`. Remove `hidden`
attribute — `.toast-hidden` handles visibility via opacity.

### 2E. Fix login input focus style

**File:** `static/css/pages.css:47-49`

Add `focus-visible` rule with outline after existing `.login-input:focus`:

```css
.login-input:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}
```

### 2F. Add theme toggle and noscript to login page

**File:** `templates/admin/login.html`

Add `theme.js` script after stylesheet link. Add `<noscript>` warning inside
`<body>` before `<main>`.

### 2G. Add "back to site" link on login page

**Files:** `templates/admin/login.html`, `static/css/pages.css`

Add link below login form pointing to `/`. Add `.login-back-link` CSS rule.

### 2H. Remove inline style on admin logout form

**File:** `templates/base_admin.html`

Change `style="display:inline"` to `class="inline"` (utility class exists).

### 2I. Move subscribe spinner animation to CSS

**Files:** `static/css/layout.css`, `templates/partials/subscribe_box.html`

Add `.htmx-indicator.spinner { animation: pulse 1.5s ease-in-out infinite; }`
to layout.css. Remove inline `style="animation:..."` from template.

### 2J. Refine typography scale

**Files:** `static/css/variables.css`, `static/css/base.css`

Update `html { font-size: 16px; }` and expand the type scale for better
visual hierarchy. Conservative approach — increase sizes incrementally.

### 2K. Expand spacing scale

**File:** `static/css/variables.css`

Add `--space-11` through `--space-16` for card padding and section gaps.

### 2L. Add card elevation

**Files:** `static/css/pages.css`, `static/css/components.css`

Subtle `box-shadow` on `.dash-card` and `.article-card` for depth.

### 2M. Standardize hover transitions

**Files:** `static/css/components.css`, `static/css/articles.css`

`transition: all 0.15s ease` on `.btn-primary`, `.btn-secondary`,
`.filter-btn`, `.nav-links a`.

### 2N. Enhance global focus-visible

**File:** `static/css/base.css`

```css
:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
```

### 2O. Add high contrast mode

**File:** `static/css/variables.css`

`@media (prefers-contrast: high)` with stronger border/muted-text values.

---

## Wave 3: Template improvements (parallel-safe: different templates)

### 3A. Deduplicate source rows via partial include

**File:** `templates/admin/sources.html`

Replace inline source row loop (lines 66-105) with:
```jinja2
{% for s in sources %}
  {% include "admin/partials/source_row.html" %}
{% endfor %}
```

### 3B. Dashboard stats visual hierarchy

**Files:** `templates/admin/dashboard.html`, `static/css/pages.css`

Add `.stat-item`, `.stat-value`, `.stat-label` classes for better stat display.

### 3C. Pipeline status visualization

**Files:** `templates/admin/dashboard.html`, `static/css/pages.css`

Horizontal bar chart showing pipeline status distribution with colored segments.

### 3D. Admin table improvements

**Files:** `templates/admin/articles.html`, `static/css/pages.css`

Sticky table headers, row hover highlighting.

### 3E. Quick actions bar on dashboard

**File:** `templates/admin/dashboard.html`

Section with trigger crawl, review queue, send newsletter, view pipelines buttons.

### 3F. Article card metadata enhancement

**Files:** `templates/partials/article_card.html`, `static/css/articles.css`

Source attribution and clearer timestamps in `.card-meta`.

### 3G. Improved empty states

**Files:** `templates/partials/feed.html`, `static/css/components.css`

Add `.empty-title`, `.empty-description` classes with actionable suggestions.

---

## Wave 4: Mobile & animation (parallel-safe)

### 4A. Touch-friendly targets

**File:** `static/css/layout.css`

44px minimum touch target via `@media (pointer: coarse)`.

### 4B. Mobile article card layout

**File:** `static/css/articles.css`

Compact padding and wrapping metadata at `@media (max-width: 640px)`.

### 4C. Mobile admin navigation

**File:** `static/css/pages.css`

Horizontal scroll with hidden scrollbar for admin nav links on mobile.

### 4D. Smooth infinite scroll animation

**Files:** `static/css/articles.css`, `static/js/app.js`

`fade-in-up` keyframe animation for HTMX-loaded articles. Add/remove
`.article-card-new` class in JS.

---

## Wave 5: New LLM providers (parallel-safe: different provider files)

### 5A. Google Gemini adapter

**Files:** `pyproject.toml`, `schemas/llm.py`, `services/llm/gemini.py` (new),
`services/llm/__init__.py`, `providers.yaml`, `tests/test_llm_adapters.py`

Dedicated adapter. Key differences from OpenAI:
- Message format: `contents` with `parts`, not flat `messages`
- System prompt: `GenerateContentConfig(system_instruction=...)`, not in messages
- Structured output: `response_mime_type="application/json"` + `response_schema`
- Error mapping: `google.genai.errors.ClientError` with `.code` attribute
- Add `google-genai>=1.0.0,<2.0.0` dependency

### 5B. Z.AI provider

**File:** `providers.yaml`

OpenAI-compatible at `https://open.bigmodel.cn/api/paas/v4`. Reuse
`type: openai` with custom `base_url`. No new adapter needed.
Contingency: build custom adapter if Z.AI deviates from OpenAI spec.

### 5C. OpenCode Go / OpenCode Zen

**Files:** `providers.yaml`, optionally `services/llm/opencode.py` (new)

Verify API format first. If OpenAI-compatible → config-only. If custom →
dedicated adapter using `requests` (no new dependency).

### 5D. OpenAI-compatible providers

**File:** `providers.yaml`

Config-only additions. All `type: openai`, disabled by default:
DeepSeek, Groq, OpenRouter, xAI, Together AI, Fireworks AI, Cerebras.

### 5E. Provider tests

**File:** `tests/test_llm_adapters.py`

- `TestGeminiProvider` — mock `google.genai` SDK, test chat, schema, errors
- Registry tests — verify all provider types resolve via `get_provider_class()`
- Config tests — verify `ADAPTER_CONFIGS` entries validate correctly
- `providers.yaml` validation — verify all entries load without errors

---

## Parallelization summary

Each wave is independent. Within a wave, items can run concurrently via
separate sub-agents since they touch different files. Dependency graph:

```
Wave 1 (bug fixes) ──→ Wave 2 (CSS fixes) ──→ Wave 3 (templates)
                                           ──→ Wave 4 (mobile/animation)
     Wave 1 (bug fixes) ──→ Wave 5 (LLM providers)
```

Waves 2+3+4 can run together after Wave 1. Wave 5 can also start after
Wave 1 (no dependency on CSS/template waves).

---

## Files changed summary

### Wave 1 — Bug fixes
- `services/article.py` — 1A
- `routes/admin/api.py` — 1B, 1F
- `tasks/newsletter.py` — 1C
- `services/redis_utils.py` — 1C (Lua script), 1G, 1P
- `tasks/pipeline.py` — 1D
- `tasks/crawl.py` — 1E
- `config.py` — 1H
- `services/validation.py` — 1I
- `routes/admin/__init__.py` — 1I
- `services/url.py` — 1J
- `services/limiter.py` — 1K
- `services/llm/errors.py` — 1L
- `services/llm/__init__.py` — 1M
- `services/cache.py` — 1N
- `routes/admin/articles.py` — 1O
- `routes/admin/review.py` — 1O
- `routes/admin/sources.py` — 1O

### Wave 2 — CSS fixes
- `static/css/pages.css` — 2A, 2E, 2G, 3B, 3C, 3D, 4C
- `templates/verify.html` — 2B
- `static/css/articles.css` — 2C, 2M, 3F, 4B, 4D
- `templates/share_redirect.html` — 2C
- `templates/base_admin.html` — 2D, 2H
- `templates/admin/login.html` — 2F, 2G
- `static/css/layout.css` — 2I, 4A
- `static/css/variables.css` — 2J, 2K, 2O
- `static/css/base.css` — 2J, 2N
- `static/css/components.css` — 2L, 2M, 3G

### Wave 3 — Template improvements
- `templates/admin/sources.html` — 3A
- `templates/admin/dashboard.html` — 3B, 3C, 3E
- `templates/admin/articles.html` — 3D
- `templates/partials/article_card.html` — 3F
- `templates/partials/feed.html` — 3G

### Wave 4 — Mobile & animation
- `static/js/app.js` — 4D

### Wave 5 — LLM providers
- `pyproject.toml` — 5A
- `schemas/llm.py` — 5A
- `services/llm/gemini.py` — 5A (new file)
- `services/llm/__init__.py` — 5A
- `services/llm/opencode.py` — 5C (new file, if needed)
- `providers.yaml` — 5A, 5B, 5C, 5D
- `tests/test_llm_adapters.py` — 5E

---

## Risk assessment

| Risk | Mitigation |
|------|-----------|
| Typography scale breakage | Conservative increments; visual regression check at each step |
| Gemini SDK API changes | Pin `google-genai>=1.0.0,<2.0.0` |
| Z.AI not fully OpenAI-compatible | Start config-only, escalate to custom adapter if needed |
| OpenCode API format unknown | Verify before building; fall back to OpenAI adapter |
| Template partial dedup regression | Manual check that HTMX enable/disable toggles still work |
| Lock race condition Lua fix | Test concurrent newsletter generation scenarios |
