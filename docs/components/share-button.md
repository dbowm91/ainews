# Share Button

The share button provides a CSS-only dropdown menu for sharing articles. It uses native `<details>/<summary>` elements for accessibility and requires no JavaScript.

## Structure

```html
<div class="share-trigger">
  <details class="share-details">
    <summary class="share-btn" aria-label="Share this article">
      [share icon]
    </summary>
    <div class="share-dropdown">
      <div class="share-dropdown-header">Share</div>
      <div class="share-url-row">
        <input type="text" class="share-url-input" value="https://..." readonly>
        <button class="share-copy-btn" data-copy>Copy</button>
      </div>
      <div class="share-social-links">
        <a href="https://x.com/intent/tweet?url=..." class="share-social-link">
          <span class="share-icon share-icon-x">X</span>
          Share on X
        </a>
        <a href="https://www.facebook.com/sharer/sharer.php?u=..." class="share-social-link">
          <span class="share-icon share-icon-facebook">f</span>
          Facebook
        </a>
        <a href="https://www.linkedin.com/sharing/share-offsite/?url=..." class="share-social-link">
          <span class="share-icon share-icon-linkedin">in</span>
          LinkedIn
        </a>
        <a href="https://www.reddit.com/submit?url=..." class="share-social-link">
          <span class="share-icon share-icon-reddit">r</span>
          Reddit
        </a>
      </div>
    </div>
  </details>
</div>
```

## How It Works

The component uses `<details>` and `<summary>` elements for the toggle mechanism:

1. `<details>` wraps the entire component
2. `<summary>` is the clickable trigger (hidden via CSS)
3. `.share-dropdown` is shown/hidden via `details[open] .share-dropdown { display: block; }`

```css
.share-details[open] .share-dropdown {
  display: block;
}
```

## Copy Button

The copy functionality requires minimal JavaScript:

```javascript
document.querySelectorAll('.share-copy-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = btn.parentElement.querySelector('.share-url-input');
    navigator.clipboard.writeText(input.value);
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  });
});
```

## Styling

### Dropdown Position

```css
.share-dropdown {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 0.5rem;
}
```

### Social Icons

```css
.share-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: #fff;
}

.share-icon-x { background: #000; }
.share-icon-facebook { background: #1877f2; }
.share-icon-linkedin { background: #0a66c2; }
.share-icon-reddit { background: #ff4500; }
```

## Accessibility

- Uses native `<details>/<summary>` for keyboard accessibility
- `aria-label` on the summary element
- Focus styles on all interactive elements
- Sufficient color contrast on social icons

## Related Files

- `static/js/share-a11y.js` - Copy functionality
- `templates/partials/share_button.html` - Reusable partial
