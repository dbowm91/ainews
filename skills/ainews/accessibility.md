---
name: accessibility
description: "Accessibility patterns for ainews - ARIA labels, semantic HTML, keyboard navigation. Triggers: accessibility, ARIA, a11y, pagination, semantic HTML."
---

## Accessibility Patterns in ainews

### Pagination Accessibility

The pagination template (`templates/partials/pagination.html`) includes comprehensive ARIA attributes:

```html
<nav class="pagination" aria-label="Pagination" role="navigation">
  <a href="..." aria-label="Go to previous page">...</a>
  <span aria-disabled="true" aria-label="Previous page (disabled)">...</span>
  <span aria-live="polite" aria-atomic="true">
    Showing items {{ start }} to {{ end }} of {{ total_count }}
  </span>
  <span aria-current="page">{{ current_page }}</span>
  <a href="..." aria-label="Go to next page">...</a>
</nav>
```

Key patterns:
- `aria-label` on navigation links and disabled states
- `aria-live="polite"` region for result count updates
- `aria-current="page"` for current page indicator
- `role="navigation"` on nav element

### Share Accessibility

The share functionality JS was merged into `static/js/app.js` (previously `static/js/share-a11y.js`). Key accessibility fixes:
- Focus management after share actions
- `aria-expanded` fixes with `.toString()` conversion for boolean attributes
- Copy functionality now in `app.js` rather than separate file

### Skip Links

Base templates include skip navigation links for keyboard users:
```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

### RSS Feed Link

The RSS feed link uses an inline SVG icon (at `static/svg/rss.svg`) instead of text. The link element in `templates/base.html` includes proper accessibility attributes:
```html
<a href="/feed" class="rss-link" title="RSS feed" hx-boost="false" aria-label="RSS feed">
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" ... aria-hidden="true">
    ...
  </svg>
</a>
```
CSS (`static/css/critical.css`) provides flexbox centering for the SVG icon.

### Bookmark Button

Articles include a bookmark toggle button (`.bookmark-btn`) for client-side bookmarking:
- localStorage key: `bookmarked_articles`
- Visual state via `.bookmarked` CSS class (turns orange when active)
- Minimum 44x44px touch target for accessibility
- `aria-label` dynamically updates ("Bookmark article" / "Remove bookmark")
- Focus-visible outline styled with accent color

### Form Accessibility

- All forms use `<label>` elements or `aria-label` attributes
- Error messages use `role="alert"` for screen reader announcement
- CSRF tokens are handled via hidden inputs (not JS-only)

### Admin UI Accessibility

- Admin tables use `<th scope="col">` for column headers
- Action buttons have descriptive `aria-label` attributes
- Bulk actions bar uses `aria-live="polite"` for status updates

### Testing Accessibility

Manual checks:
1. Tab through pages - all interactive elements should be focusable
2. Check contrast ratios meet WCAG AA (4.5:1 for normal text)
3. Verify `aria-label` attributes provide meaningful descriptions
4. Test with browser extensions (axe, Lighthouse)

### What NOT to Do

- Do NOT remove `aria-label` attributes from interactive elements
- Do NOT use `tabindex > 0` (causes focus order issues)
- Do NOT add `role` attributes that conflict with native element semantics
- Do NOT use `onclick` handlers without keyboard equivalent (use `<button>` instead)

### Subagent Trigger Keywords

This skill is triggered by: accessibility, ARIA, a11y, pagination, semantic HTML.
