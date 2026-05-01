---
name: csp
description: "Content Security Policy (CSP) patterns for ainews - nonce usage, inline script handling, and style-src configuration. Triggers: CSP, nonce, content security policy, inline script, unsafe-inline."
---

## CSP Configuration in ainews

The application uses Flask-Talisman for CSP headers, configured in `app.py`.

### Current CSP Directives

```python
csp = {
    "default-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
    "script-src": "'self'",
    "img-src": "'self' data:",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
}
Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_nonce_in=["script-src"],
    ...
)
```

### Nonce Usage for Inline Scripts

All inline `<script>` tags MUST include the `nonce` attribute:

```html
<script nonce="{{ csp_nonce() }}">
  // inline script content
</script>
```

The `csp_nonce()` function is provided by Flask-Talisman and is available in all templates.

### Templates Updated

- `templates/base.html` - Uses nonce for inline scripts
- `templates/base_admin.html` - Uses nonce for inline scripts
- `templates/admin/webhooks.html` - Added nonce to inline script
- `templates/admin/partials/articles_table.html` - Added nonce to inline script

### Inline Styles

Dynamic CSS custom properties (like `--bar-width`) can remain inline when values are dynamic per AGENTS.md:

```html
<div style="--bar-width: {{ pct }}%"></div>
```

This requires `style-src 'unsafe-inline'` in the CSP directive.

### Moving Inline Styles to External CSS

Static inline `<style>` blocks should be moved to external CSS files:

1. Identify the CSS rules in the inline `<style>` block
2. Add them to the appropriate CSS module:
   - `static/css/articles.css` - Article-related styles
   - `static/css/pages.css` - Admin dashboard, forms
   - `static/css/utilities.css` - Utility classes
3. Remove the `<style>` block from the template

**Example:** Skeleton loading styles were moved from `templates/partials/skeleton_article_detail.html` to `static/css/articles.css`.

### What NOT to Do

- Do NOT add new inline scripts without the `nonce="{{ csp_nonce() }}"` attribute
- Do NOT remove `'unsafe-inline'` from `style-src` - it's needed for dynamic CSS custom properties
- Do NOT use `eval()` or `new Function()` in inline scripts (blocked by CSP)

### Verification

After CSP changes, verify:
1. Pages load without CSP violations in browser console
2. Inline scripts execute correctly (check browser console)
3. Dynamic styles (CSS custom properties) apply correctly

### Subagent Trigger Keywords

This skill is triggered by: CSP, nonce, content security policy, inline script, unsafe-inline.
