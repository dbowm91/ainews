# Theme Toggle

The theme toggle switches between dark and light color schemes. It uses CSS custom properties and data attributes for theming.

## Structure

```html
<button class="theme-toggle" aria-label="Toggle theme">
  <!-- Sun icon (shown in dark mode) -->
  <svg class="theme-icon-dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="5"/>
    <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
  </svg>
  <!-- Moon icon (shown in light mode) -->
  <svg class="theme-icon-light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
  </svg>
</button>
```

## How Theming Works

1. Theme is stored in `document.documentElement.dataset.theme`
2. CSS variables are defined for each theme using selectors:

```css
:root {
  --bg-primary: #0d1117;
  --text-primary: #e6edf3;
  /* ... */
}

[data-theme="light"] {
  --bg-primary: #ffffff;
  --text-primary: #1f2328;
  /* ... */
}
```

## Icon Visibility

Icons are toggled via CSS based on the current theme:

```css
.theme-icon-light,
[data-theme="light"] .theme-icon-dark {
  display: none;
}

[data-theme="light"] .theme-icon-light {
  display: block;
}
```

## JavaScript

The toggle button requires JavaScript to switch themes:

```javascript
document.querySelector('.theme-toggle').addEventListener('click', () => {
  const html = document.documentElement;
  const current = html.dataset.theme;
  html.dataset.theme = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', html.dataset.theme);
});
```

## Persistence

Theme preference is stored in `localStorage` and applied on page load:

```javascript
const saved = localStorage.getItem('theme');
if (saved) {
  document.documentElement.dataset.theme = saved;
}
```

## Focus Styles

```css
.theme-toggle:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}
```

## Styling

```css
.theme-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-2);
  cursor: pointer;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, border-color 0.15s;
}

.theme-toggle:hover {
  color: var(--accent);
  border-color: var(--accent-dim);
}

.theme-toggle svg {
  width: 16px;
  height: 16px;
}
```

## Partial Location

Located in `templates/partials/theme_toggle.html`

## Related Files

- `static/js/theme.js` - Theme persistence logic
- `templates/partials/theme_toggle.html` - Reusable partial
