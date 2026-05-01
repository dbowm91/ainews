# Templates Conventions

Contextual conventions for agents working in the `templates/` directory.

## CSP Directives

`app.py` includes additional CSP directives for defense-in-depth:
- `connect-src 'self'` — allows fetch() to same origin (HTMX, share tracking, service worker)
- `object-src 'none'` — prevents plugin embedding (Flash, Java)
- `base-uri 'self'` — prevents base tag injection
- `form-action 'self'` — restricts form submission targets
- `script-src 'self'` with nonce via `content_security_policy_nonce_in=["script-src"]` — inline scripts must use `nonce="{{ csp_nonce() }}"` attribute
- `style-src 'self' 'unsafe-inline'` — allows dynamic CSS custom properties (e.g., `--bar-width`) in inline styles

## Inline Script Requirement

All `<script>` tags in templates must include `nonce="{{ csp_nonce() }}"` attribute. Templates updated: `webhooks.html`, `articles_table.html`, `base.html`, `base_admin.html`.

## URL Safety in Templates

The `safe_href` Jinja2 filter (defined at `app.py`) validates http/https scheme, checks SSRF via `validate_url_safe()`, and returns `#` for invalid URLs. Used in `article_card.html`, `condensed_article.html`, `article_edit.html`, `share_macro.html`, and `share_redirect.html`. Tests in `tests/test_safe_href_filter.py`.

## Pagination Accessibility

Pagination template (`templates/partials/pagination.html`) includes ARIA attributes: `aria-label`, `aria-live="polite"`, `aria-current="page"`, `role="navigation"`.