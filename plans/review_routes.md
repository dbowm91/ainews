# Review: routes.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- Blueprint registration in `app.py:188-197`: `public_bp`, `admin_bp`, `admin_api_bp`, `api_tokens_bp` all registered correctly.
- `admin_bp` has `url_prefix="/admin"` at `routes/admin/__init__.py:12`.
- `admin_api_bp` has `url_prefix="/api/v1"` at `routes/admin/__init__.py:13`.
- `api_tokens_bp` registered without `url_prefix` in `app.py:197` — routes include full `/api-tokens` path at `routes/admin/api_tokens.py:9`.
- All route files listed in the structure section exist (verified via glob).
- `admin/auth.py` has `/login` [GET/POST] at line 43 and `/logout` [POST only] at line 188.
- Session hijacking protection (IP + User-Agent binding) at `routes/decorators.py:43-54`.
- CSRF protection via `validate_csrf_json` decorator at `routes/decorators.py:72-94`.
- Rate limiting on login (`@limiter.limit("10 per minute")`) at `routes/admin/auth.py:44`.
- `/admin/articles/<id>/versions` [GET] at `routes/admin/articles.py:440`.
- `/admin/articles/<id>/versions/<version_id>/rollback` [POST] at `routes/admin/articles.py:458`.
- `/admin/topic-notes/row/<topic>` [GET] at `routes/admin/topic_notes.py:172`.
- `/admin/shares/<id>/toggle` [POST] at `routes/admin/shares.py:162`.
- `/api/v1/articles/ids` [GET] at `routes/admin/api/articles.py:152`.
- `/api/v1/articles/counts-by-status` [GET] at `routes/admin/api/articles.py:171`.
- `/api/v1/articles/bulk` [POST] at `routes/admin/api/articles.py:470`.
- `/api/v1/sources/health` [GET] at `routes/admin/api/pipeline.py:167`.
- `/api/v1/pipeline/sla` [GET] at `routes/admin/api/pipeline.py:193`.
- `/api/v1/newsletters/stats` [GET] at `routes/admin/newsletters.py:177`.
- `/api/v1/newsletter/preview` [POST] at `routes/admin/newsletters.py:221`.
- `/api/v1/webhooks/<id>/events` [GET] at `routes/admin/api/webhooks.py:321`.
- `/api/v1/webhooks/events/<id>/resend` [POST] at `routes/admin/api/webhooks.py:363`.
- `/api/v1/workers/health` [GET] at `routes/admin/api/health.py:54`.
- `/api/v1/task/<task_id>` [GET] at `routes/admin/api/health.py:102`.
- `/admin/api/trend-memory/semantic-search` path is correct — registered on `admin_bp` at `routes/admin/trend_memory.py:117`, full path `/admin/api/trend-memory/semantic-search`.

## Incorrect Claims

### Missing `/articles` GET list endpoint
- **Priority: HIGH**
- Lines 107 and 305 claim `GET /articles` returns a list of articles. This endpoint does NOT exist in the codebase. The only article GET endpoints are:
  - `GET /articles/ids` — batch ID lookup (`routes/admin/api/articles.py:152`)
  - `GET /articles/counts-by-status` — counts (`routes/admin/api/articles.py:171`)
  - `GET /articles/<id>` — single article (`routes/admin/api/articles.py:597`)
- There is no `list_articles` function anywhere in `routes/admin/api/articles.py`.

### Incomplete API file listing in structure section
- **Priority: MEDIUM**
- Lines 29-37 list API files but are missing 6 files that actually exist:
  - `alerts.py` — Alert management endpoints
  - `quality.py` — Quality report endpoints
  - `replay.py` — Pipeline replay/rescue endpoints
  - `source_intelligence.py` — Source performance metrics
  - `topic_gap.py` — Topic gap analysis
  - `newsletter.py` — Newsletter performance metrics (separate from admin `newsletters.py`)
  - `utils.py` — API utility functions

### Missing API endpoints from documentation
- **Priority: MEDIUM**
- The following endpoints exist in code but are not documented anywhere in routes.md:
  - `GET /api/v1/alerts` — `routes/admin/api/alerts.py:14`
  - `GET /api/v1/sources/performance` — `routes/admin/api/source_intelligence.py:11`
  - `GET /api/v1/topics/coverage` — `routes/admin/api/source_intelligence.py:74`
  - `GET /api/v1/sources/recommendations` — `routes/admin/api/source_intelligence.py:104`
  - `GET /api/v1/newsletters/performance` — `routes/admin/api/newsletter.py:175`
  - `GET /api/v1/quality/recent` — `routes/admin/api/quality.py:59`
  - `GET /api/v1/articles/<id>/quality` — `routes/admin/api/quality.py:10`
  - `GET /api/v1/articles/<id>/pipeline/history` — `routes/admin/api/replay.py:14`
  - `POST /api/v1/articles/<id>/pipeline/replay` — `routes/admin/api/replay.py:32`
  - `POST /api/v1/articles/<id>/pipeline/restore-version` — `routes/admin/api/replay.py:108`
  - `GET /api/v1/topic-gap/reports` — `routes/admin/api/topic_gap.py:12`
  - `GET /api/v1/search/articles` — `routes/admin/api/search.py:60`

### Misleading unsubscribe route representation
- **Priority: LOW**
- Lines 171-173 show the unsubscribe route as a single declaration supporting both GET and POST:
  ```python
  @subscribe_bp.route("/unsubscribe/<token>")
  @subscribe_bp.route("/unsubscribe/<token>", methods=["POST"])
  def unsubscribe(token): ...
  ```
- In reality, these are TWO SEPARATE route handlers:
  - `unsubscribe()` at `routes/public/subscribe.py:137` — GET only (shows confirmation page)
  - `unsubscribe_confirm()` at `routes/public/subscribe.py:153` — POST only (processes unsubscription)
- The code block implies a single function handles both methods, which is incorrect.

### Incomplete template structure
- **Priority: LOW**
- Lines 337-351 list templates but are missing many that exist:
  - Missing root templates: `base.html`, `base_admin.html`, `topic.html`, `tag.html`, `unsubscribe.html`, `verify.html`
  - Missing admin templates: `article_versions.html`, `pipeline_logs.html`, `login.html`, `review.html`, `setup_2fa.html`, `verify_2fa.html`
  - Missing partials: `search.html`, `pagination.html`, `article_card.html`, `article_body.html`, `share_macro.html`, `top_impact.html`, `subscribe_box.html`, `related_articles.html`, `theme_toggle.html`, `skeleton_card.html`, `skeleton_article_detail.html`, `topic_icon.html`, `critical_css.html`, `critical_css_admin.html`, `condensed_article.html`, `empty_state.html`
  - Missing macros: `badges.html`

### Trend memory semantic search endpoint placement is misleading
- **Priority: LOW**
- Lines 79, 132, and 330 list `/admin/api/trend-memory/semantic-search` in the `admin_api_bp` endpoints table. However, this endpoint is registered on `admin_bp` (not `admin_api_bp`) at `routes/admin/trend_memory.py:117`. While the full path `/admin/api/trend-memory/semantic-search` is correct, listing it under the `admin_api_bp` table is misleading about which blueprint owns it.

## Bugs Found

### Missing `Article` import in `get_pipeline_history()`
- **Priority: HIGH**
- In `routes/admin/api/replay.py:21`, the function `get_pipeline_history()` uses `Article` without importing it:
  ```python
  article = db.session.get(Article, article_id)
  ```
- The `Article` import is only inside `replay_article_stage()` at line 45. This will cause a `NameError` at runtime when the endpoint is called.
- Fix: Add `from models import Article` at the top of `get_pipeline_history()` or at module level.

### Documentation claims `api_tokens_bp` has DELETE endpoint but route name differs
- **Priority: LOW**
- Line 267 documents `DELETE /api-tokens/<id>` but the actual route at `routes/admin/api_tokens.py:66` uses parameter name `token_id`:
  ```python
  @api_tokens_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
  ```
- The URL path is correct, but the parameter name `token_id` (not `id`) is worth noting for API consumers.

## Improvement Opportunities

### Add `@validate_csrf_json` to API token routes
- **Priority: MEDIUM**
- The `create_token` and `delete_token` routes in `routes/admin/api_tokens.py` use `@require_auth` but do NOT use `@validate_csrf_json`. While these routes are behind auth, adding CSRF protection would provide defense-in-depth for state-changing operations.

### Document the `api_tokens_bp` endpoints more completely
- **Priority: LOW**
- The API tokens section (lines 262-267) lists endpoints but could include more detail about:
  - The `POST /api-tokens` request body (`name`, `expires_in` fields)
  - The response format (includes `token` in plaintext on creation)
  - Token format: `plain_token.token_hash` (first 16 chars of hash used for lookup)

### Document the public health endpoint
- **Priority: LOW**
- Line 197-201 documents the `/health` endpoint but doesn't mention it supports a `?detailed=true` query parameter that returns extended health info (only for admin sessions). See `routes/public/__init__.py:115-117`.

### Consider documenting the `@limit_content_length` decorator usage
- **Priority: LOW**
- Several routes use `@limit_content_length()` (e.g., login at 1024 bytes, bulk operations at 32768 bytes) but this is not documented in the security section.

## Stale Content

### Rate limiting claim needs clarification
- **Priority: MEDIUM**
- Line 380 states: "Admin login routes have explicit rate limits via `extensions.limiter` (`@limiter.limit("10 per minute")`). Other admin routes rely on the global default limit."
- The login rate limit is confirmed at `routes/admin/auth.py:44` and `routes/admin/auth.py:98` (verify-2fa also has `@limiter.limit("10 per minute")`).
- However, the claim about "global default limit" for other admin routes is not verifiable from the routes code alone. The global default would be configured in `extensions.py` or `config.py`, which is outside the scope of this review. The documentation should either confirm the global default value or remove the vague claim.

### Newsletter endpoints location
- **Priority: LOW**
- The newsletter API endpoints are split across two files:
  - `routes/admin/newsletters.py` — contains `/newsletters/stats` and `/newsletter/preview` on `admin_api_bp`
  - `routes/admin/api/newsletter.py` — contains `/newsletters/performance` on `admin_api_bp`
- The documentation only mentions the first file. The second file with the performance endpoint is undocumented.
