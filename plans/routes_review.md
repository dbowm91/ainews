# Routes Review Plan

Review the `routes/` package and [routes.md](../architecture/routes.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual route implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Security**: TOTP, session binding, CSRF, rate limiting

## Key Files

- `routes/admin/__init__.py` - Dashboard, articles, sources, subscribers, newsletters
- `routes/admin/auth.py` - Login with TOTP support
- `routes/admin/api_tokens.py` - API token management (NOT registered - verify)
- `routes/admin/api/articles.py` - Article CRUD
- `routes/admin/api/sources.py` - Source management
- `routes/admin/api/pipeline.py` - Pipeline control
- `routes/public/feeds.py` - RSS, sitemap, article feeds
- `routes/public/subscribe.py` - Subscription management
- `routes/public/links.py` - Article routing, short URLs

## Known Issues to Verify

- `api_tokens_bp` blueprint is NOT registered - verify all /api-tokens routes return 404
- `/share/<platform>/<article_id>` not implemented - social sharing client-side only

## Review Checklist

- [ ] Verify blueprint registration: admin_bp at /admin, admin_api_bp at /api/v1, public_bp at /
- [ ] Verify api_tokens_bp NOT registered (known issue)
- [ ] Verify admin auth: TOTP 2FA, 8 backup codes, session hijacking protection (IP + User-Agent binding)
- [ ] Verify login lockout via Redis with in-memory fallback
- [ ] Verify CSRF protection via Flask-WTF tokens
- [ ] Verify rate limiting on admin routes via extensions.limiter
- [ ] Verify article CRUD at /api/v1/articles/<id>
- [ ] Verify source refresh at /api/v1/sources/<id>/refresh
- [ ] Verify pipeline trigger at /api/v1/articles/<id>/pipeline

## Output

Save findings to `plans/routes_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found