# Article Card

Article cards are the primary content unit in the feed view. They display article metadata, summary, and interactive elements.

## Structure

```html
<article class="article-card">
  <div class="card-header">
    <span class="category-badge cat-ai">AI</span>
    <span class="card-time">2h ago</span>
  </div>
  <div class="card-tags">
    <a href="/tag/llm" class="tag-pill tag-pill-sm">llm</a>
  </div>
  <h2 class="card-title">
    <a href="/article/slug">Article Title Here</a>
  </h2>
  <p class="card-summary">Brief summary of the article content...</p>
  <footer class="card-footer">
    <span class="impact-score impact-high">8</span>
    <span class="meta-separator">·</span>
    <a href="/source/arxiv" class="card-source-link">arxiv.org</a>
    <span class="meta-separator">·</span>
    <span class="card-time">Mar 15</span>
  </footer>
</article>
```

## Components

### Card Header

Contains category badge and timestamp.

```css
.card-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.5rem;
}
```

### Card Title

Features animated underline on hover using background gradient technique.

```css
.card-title a {
  color: var(--text-primary);
  background-image: linear-gradient(var(--accent), var(--accent));
  background-position: 0% 100%;
  background-repeat: no-repeat;
  background-size: 0% 2px;
  transition: color 0.15s, background-size 0.2s ease;
}

.card-title a:hover {
  color: var(--accent);
  background-size: 100% 2px;
}
```

### Card Summary

Truncated to 2 lines using `-webkit-line-clamp`.

```css
.card-summary {
  font-size: 0.85rem;
  color: var(--text-muted);
  line-height: 1.5;
  margin-bottom: 0.6rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

### Card Footer

Contains impact score, source link, and date.

```css
.card-footer {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-dim);
  flex-wrap: wrap;
}

.card-source-link {
  color: var(--text-dim);
  font-size: 0.8rem;
  margin-left: auto;
}
```

## States

### Default

```css
.article-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem 1.15rem;
  margin-bottom: 0.75rem;
  background: var(--bg-secondary);
}
```

### Hover

```css
.article-card:hover {
  border-color: var(--border-light);
  background: var(--bg-tertiary);
  transform: translateY(-1px);
}
```

### Active

```css
.article-card:active {
  transform: translateY(0);
}
```

## Skeleton Loader

```html
<div class="skeleton-card">
  <div class="skeleton skeleton-badge"></div>
  <div class="skeleton skeleton-title"></div>
  <div class="skeleton skeleton-text"></div>
  <div class="skeleton skeleton-text-short"></div>
  <div class="skeleton-footer">
    <div class="skeleton skeleton-dot"></div>
    <div class="skeleton skeleton-dot"></div>
  </div>
</div>
```

## Related Classes

- `.article-full` - Full article detail view
- `.related-card` - Cards in related articles section
- `.skeleton-card` - Loading placeholder
