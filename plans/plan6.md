# Frontend Deep-Dive Improvement Plan

**Date**: May 1, 2026  
**Scope**: Comprehensive frontend review covering stylistic and usability improvements  
**Methodology**: 15 investigation items researched using subagents + websearch

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [High Priority Items (Fix Immediately)](#high-priority-items)
   - Skip Link Styling
   - Color Contrast (`--text-muted`)
   - Mobile Navigation UX
3. [Medium Priority Items (Fix Soon)](#medium-priority-items)
   - Base Font Size & Scale
   - Search Experience
   - Bookmark & Read State UX
   - Toast Notification Gaps
   - Article Card Truncation
4. [Low Priority Items (Polish)](#low-priority-items)
   - Missing Print Styles
   - Tablet Breakpoint Gaps
   - Touch Target Coverage
   - CSS @import Strategy
   - Container Queries
   - HTMX Loading Indicators
5. [Implementation Priority Matrix](#implementation-priority-matrix)
6. [File Modification Checklist](#file-modification-checklist)

---

## Executive Summary

Investigation of 15 identified items reveals a well-built frontend with **3 high-priority gaps**, **7 medium-priority enhancements**, and **5 low-priority polish items**. The codebase shows strong accessibility foundations but has some incomplete features and missed opportunities.

### Key Findings:
- **Accessibility**: Skip link uses `:focus` instead of `:focus-visible`; `--text-muted` fails WCAG AAA (but passes AA)
- **Incomplete Features**: Bookmark button CSS/JS exists but button is NOT rendered in any template
- **UX Gaps**: No visible search submit button; missing success toasts; mobile nav lacks Escape key support
- **Code Quality**: `--text-md` duplicates `--text-base` (both 0.9375rem) - bug from commit `43ddb05`
- **Performance**: `@import` strategy creates sequential loading but is mitigated by critical CSS inlining

---

## HIGH PRIORITY ITEMS

### 1. Skip Link Styling

**Status**: INVESTIGATION COMPLETE  
**Issue**: Skip link exists in HTML but uses `:focus` instead of `:focus-visible`; insufficient touch target

**Current State** (`critical.css` lines 28-44):
```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: var(--accent);
  color: #fff;
  padding: 0.5rem 1rem;
  font-family: var(--font-mono);
  font-size: var(--text-lg);
  z-index: var(--z-index-skip-link);
  transition: top 0.15s;
  text-decoration: none;
}

.skip-link:focus {
  top: 0;
}
```

**Problems**:
1. Uses `:focus` (triggers on mouse click too)
2. No `white-space: nowrap` (text may wrap)
3. Touch target ~36px (below 44px WCAG AAA standard)
4. No explicit outline style

**Recommended Changes** (`critical.css`):

```css
.skip-link {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%) translateY(-100%);
  background: var(--accent);
  color: #fff;
  padding: 0.75rem 1.5rem;
  font-family: var(--font-mono);
  font-size: var(--text-base);
  font-weight: 600;
  text-decoration: none;
  z-index: var(--z-index-skip-link, 1000);
  white-space: nowrap;
  border-radius: var(--radius-md);
  transition: transform 0.2s ease;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.skip-link:focus-visible {
  transform: translateX(-50%) translateY(0.75rem);
  outline: 3px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

@media print {
  .skip-link {
    display: none !important;
  }
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/critical.css` (lines 28-44)

**Optional HTML Update** (both templates):
```html
<!-- Consider changing "Skip to content" to "Skip to main content" -->
<a href="#content" class="skip-link">Skip to main content</a>
```

---

### 2. Color Contrast - `--text-muted`

**Status**: INVESTIGATION COMPLETE  
**Issue**: `--text-muted: #8b949e` has 5.62:1 contrast ratio - passes AA but fails AAA

**Current Values** (`variables.css`):
```css
--text-muted: #8b949e;  /* 5.62:1 on --bg-secondary:#161b22 - FAILS AAA */
--text-dim: #adbac7;    /* 8.75:1 - PASSES AAA */
--text-secondary: #c9d1d9;  /* 11.21:1 - PASSES AAA */
```

**WCAG 2.1 Requirements**:
- **Normal Text** (< 18pt / 24px): AA = 4.5:1, AAA = 7:1
- **Large Text** (≥ 18pt / 24px): AA = 3:1, AAA = 4.5:1

**Note**: `--text-muted` is frequently used with `--text-xs` (12px), which is "normal text" per WCAG.

**Recommended Change** (`variables.css` line 37):

```css
/* Dark theme - AAA compliant */
--text-muted: #a0aec0;  /* 7.15:1 on #161b22 - NOW PASSES AAA */
```

**Light Theme** (`variables.css` line 186):
```css
/* Light theme - maintain AAA compliance */
--text-muted: #4a5568;  /* Adjusted for light theme */
```

**Color Comparison**:
| Color | Hex | Ratio on #161b22 | AA | AAA |
|-------|-----|-----------------|----|-----|
| Current | `#8b949e` | 5.62:1 | ✅ | ❌ |
| Recommended | `#a0aec0` | 7.15:1 | ✅ | ✅ |
| Alternative | `#b0b8c8` | 8.2:1 | ✅ | ✅ |

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/variables.css` (lines 37, 186)

---

### 3. Mobile Navigation UX

**Status**: INVESTIGATION COMPLETE  
**Issue**: Checkbox hack has no Escape key support, no focus trapping, static `aria-expanded`

**Current Implementation** (`base.html` lines 38-51, `base_admin.html` lines 29-45):
```html
<input type="checkbox" id="nav-toggle" class="nav-toggle-checkbox" hidden>
<label for="nav-toggle" class="nav-toggle-label" aria-label="Toggle navigation">
  <span></span>
</label>
<div class="nav-links">
  ...navigation links...
</div>
```

**Problems**:
1. No Escape key to close menu
2. No focus trapping (focus can leave menu)
3. `aria-expanded` is static in admin template, missing in public template
4. No `role="button"` or `tabindex="0"` on label in public template
5. No focus on first menu item when opened

**Recommended HTML Changes**:

**`base.html` (lines 38-51)**:
```html
<input type="checkbox" id="nav-toggle" class="nav-toggle-checkbox" hidden>
<label for="nav-toggle" class="nav-toggle-label" role="button" tabindex="0" 
       aria-label="Toggle navigation" aria-expanded="false" aria-controls="nav-links">
  <span></span>
</label>
<div class="nav-links" id="nav-links">
  {% for cat in categories if categories is defined %}
    <a href="/topic/{{ cat }}" 
       {% if request.path == '/topic/' + cat %}class="active"{% endif %}>{{ cat }}</a>
  {% endfor %}
  <a href="/feed" class="rss-link" title="RSS feed" hx-boost="false">
    <svg><!-- RSS icon --></svg>
  </a>
  {% include "partials/theme_toggle.html" %}
</div>
```

**`base_admin.html` (lines 29-45)** - Update `aria-expanded` to be dynamic via JS, add `aria-controls`:
```html
<input type="checkbox" id="nav-toggle" class="nav-toggle-checkbox" hidden>
<label for="nav-toggle" class="nav-toggle-label" role="button" tabindex="0" 
       aria-label="Toggle navigation" aria-expanded="false" aria-controls="nav-links">
  <span></span>
</label>
<div class="nav-links" id="nav-links">
  <!-- existing nav links -->
</div>
```

**Recommended JavaScript** (add to `app.js` before line 464):
```javascript
/* Mobile Navigation Enhancement - Checkbox Hack with JS Accessibility */
(function() {
  const navToggle = document.getElementById('nav-toggle');
  if (!navToggle) return;
  
  const navLabel = document.querySelector('.nav-toggle-label');
  const navLinks = document.getElementById('nav-links') || document.querySelector('.nav-links');
  if (!navLabel || !navLinks) return;
  
  let navItems = [];
  
  function updateMenuItems() {
    navItems = navLinks.querySelectorAll('a[href], button:not([disabled])');
  }
  
  function updateAriaExpanded() {
    const isChecked = navToggle.checked;
    navLabel.setAttribute('aria-expanded', isChecked.toString());
  }
  
  function openMenu() {
    navToggle.checked = true;
    updateAriaExpanded();
    updateMenuItems();
    if (navItems[0]) {
      setTimeout(function() { navItems[0].focus(); }, 100);
    }
    document.addEventListener('keydown', handleMenuKeydown);
    document.addEventListener('click', handleOutsideClick);
  }
  
  function closeMenu() {
    navToggle.checked = false;
    updateAriaExpanded();
    document.removeEventListener('keydown', handleMenuKeydown);
    document.removeEventListener('click', handleOutsideClick);
    navLabel.focus();
  }
  
  function handleMenuKeydown(e) {
    if (!navToggle.checked) return;
    
    switch(e.key) {
      case 'Escape':
        e.preventDefault();
        closeMenu();
        break;
      case 'Tab':
        if (navItems.length === 0) return;
        if (e.shiftKey) {
          if (document.activeElement === navItems[0]) {
            e.preventDefault();
            navItems[navItems.length - 1].focus();
          }
        } else {
          if (document.activeElement === navItems[navItems.length - 1]) {
            e.preventDefault();
            navItems[0].focus();
          }
        }
        break;
    }
  }
  
  function handleOutsideClick(e) {
    if (!navToggle.checked) return;
    const nav = navLabel.closest('.nav');
    if (nav && !nav.contains(e.target)) {
      closeMenu();
    }
  }
  
  navToggle.addEventListener('change', updateAriaExpanded);
  
  navLabel.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      navToggle.checked ? closeMenu() : openMenu();
    }
  });
  
  updateAriaExpanded();
})();
```

**Additional CSS** (add to `critical.css`):
```css
.nav-toggle-label:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px;
}

@media (max-width: 640px) {
  body.menu-open {
    overflow: hidden;
  }
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/templates/base.html` (lines 38-51)
- `/home/sugarwookie/projects/ainews/templates/base_admin.html` (lines 29-45)
- `/home/sugarwookie/projects/ainews/static/js/app.js` (add before line 464)
- `/home/sugarwookie/projects/ainews/static/css/critical.css` (after line 314)

---

## MEDIUM PRIORITY ITEMS

### 4. Base Font Size & Scale

**Status**: INVESTIGATION COMPLETE  
**Issue**: `--text-base: 0.9375rem` (15px) is non-standard; `--text-md` duplicates `--text-base`

**Current Scale** (`variables.css` lines 63-74):
```css
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.8125rem;  /* 13px */
--text-base: 0.9375rem; /* 15px - NON-STANDARD */
--text-md: 0.9375rem;  /* 15px - DUPLICATE! */
--text-lg: 1rem;       /* 16px */
--text-xl: 1.0625rem;  /* 17px */
--text-2xl: 1.125rem;  /* 18px */
--text-3xl: 1.25rem;   /* 20px */
--text-4xl: 1.375rem;  /* 22px */
--text-5xl: 1.5rem;    /* 24px */
--text-6xl: 1.75rem;   /* 28px */
--text-7xl: 2rem;      /* 32px */
```

**Git History**: Commit `43ddb05` changed `--text-base` from 14px to 15px, accidentally making it identical to `--text-md`.

**Recommended New Scale** (based on Tailwind CSS industry standard):
```css
--text-xs: 0.75rem;    /* 12px - captions, fine print */
--text-sm: 0.875rem;   /* 14px - small text, secondary info */
--text-base: 1rem;     /* 16px - BODY TEXT (standard) */
--text-md: 1.125rem;   /* 18px - slightly larger than body */
--text-lg: 1.25rem;    /* 20px - small headings */
--text-xl: 1.375rem;   /* 22px */
--text-2xl: 1.5rem;    /* 24px - h4 level */
--text-3xl: 1.75rem;   /* 28px - h3 level */
--text-4xl: 2rem;      /* 32px - h2 level */
--text-5xl: 2.5rem;    /* 40px - h1 level */
--text-6xl: 3rem;      /* 48px */
--text-7xl: 4rem;      /* 64px */
```

**Key Improvements**:
1. Standard 16px base (matches browser default)
2. Fixed `--text-md` duplicate - now distinct 18px
3. Consistent, memorable values
4. Proper hierarchy

**Visual Impact**: Text will appear slightly larger (16px vs 15px base). Test after implementation.

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/variables.css` (lines 63-74)

---

### 5. Search Experience

**Status**: INVESTIGATION COMPLETE  
**Issue**: No visible submit button; basic loading indicator; no suggestions

**Current Implementation** (`partials/feed.html` lines 8-31):
```html
<form role="search" class="search-container">
  <input
    id="search-input"
    type="search"
    name="q"
    value="{{ query }}"
    placeholder="search articles..."
    aria-label="Search articles (press / to focus)"
    class="search-input"
    minlength="2"
    hx-get="{{ url_for('public.index') }}"
    hx-trigger="keyup changed delay:500ms, search"
    hx-target="#content"
    hx-swap="innerHTML"
    hx-push-url="true"
    hx-indicator="#search-spinner"
    hx-include="[name='category']"
  >
  <button type="button" class="search-clear" aria-label="Clear search">&times;</button>
  <kbd class="search-kbd">/</kbd>
  <span id="search-spinner" class="htmx-indicator spinner" aria-hidden="true">...</span>
</form>
```

**Gaps**:
1. **No visible submit button** - WCAG recommends visible submit
2. **Loading indicator is text** - "..." looks amateurish
3. **No search suggestions** - `SearchQuery` model tracks analytics but not exposed
4. **No `enterkeyhint`** - Mobile keyboards show "Return" instead of "Search"

**Recommended Changes** (`partials/feed.html`):
```html
<search class="search-container">
  <form role="search" id="search-form">
    <input
      id="search-input"
      type="search"
      name="q"
      value="{{ query }}"
      placeholder="search articles..."
      aria-label="Search articles"
      aria-describedby="search-help"
      enterkeyhint="search"
      class="search-input"
      minlength="2"
      autocomplete="off"
      hx-get="{{ url_for('public.index') }}"
      hx-trigger="keyup changed delay:400ms, search"
      hx-target="#content"
      hx-swap="innerHTML"
      hx-push-url="true"
      hx-indicator="#search-spinner"
      hx-include="[name='category']"
    >
    <button type="submit" class="search-submit" aria-label="Search articles">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" 
           stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    </button>
    <button type="button" class="search-clear" aria-label="Clear search">&times;</button>
    <kbd class="search-kbd" aria-hidden="true">/</kbd>
    <span id="search-spinner" class="htmx-indicator">
      <svg class="spinner-icon" viewBox="0 0 50 50" aria-hidden="true">
        <circle cx="25" cy="25" r="20"/>
      </svg>
      <span class="sr-only">Loading...</span>
    </span>
    <div id="search-suggestions" class="search-dropdown" aria-live="polite"></div>
  </form>
  <p id="search-help" class="sr-only">Press / to focus search. Minimum 2 characters.</p>
</search>
```

**Additional CSS** (add to `articles.css`):
```css
.search-submit {
  position: absolute;
  right: 2.5rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0.2rem;
  display: inline-flex;
  align-items: center;
  min-width: 44px;
  min-height: 44px;
}

.search-submit:hover {
  color: var(--accent);
}

.search-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-top: 0.25rem;
  max-height: 300px;
  overflow-y: auto;
  z-index: var(--z-index-share-dropdown);
  display: none;
}

.search-dropdown.active {
  display: block;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/templates/partials/feed.html`
- `/home/sugarwookie/projects/ainews/static/css/articles.css`

---

### 6. Bookmark & Read State UX

**Status**: INVESTIGATION COMPLETE  
**CRITICAL FINDING**: Bookmark button CSS/JS exists but button is **NOT rendered in any template** - incomplete feature!

**Current State**:
- **CSS**: `.bookmark-btn` exists in `articles.css` (lines 43-69)
- **JS**: `toggleBookmark()` function exists in `app.js` (lines 396-456)
- **HTML**: NO bookmark button in `article_card.html`, `condensed_article.html`, or `article.html`

**Missing Features**:
1. Bookmark button not rendered in UI
2. No toast feedback on bookmark toggle
3. No "View all bookmarks" page
4. No "Clear read state" UI

**Recommended Actions**:

#### A. Add Bookmark Button to Templates

**`partials/article_card.html`** (add to card-footer):
```html
<button class="bookmark-btn" data-article-id="{{ article.id }}" 
        aria-label="Bookmark article" title="Bookmark">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" 
       stroke="currentColor" stroke-width="2" aria-hidden="true">
    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
  </svg>
</button>
```

**`partials/condensed_article.html`** (add to article-header or meta):
```html
<button class="bookmark-btn" data-article-id="{{ article.id }}" 
        aria-label="Bookmark article" title="Bookmark">
  <!-- same SVG as above -->
</button>
```

#### B. Add Toast Success Styles

**`components.css`** (after line 567):
```css
.toast-success {
  border-color: var(--green);
  background: var(--bg-secondary);
}

/* Bookmark animation */
.bookmark-btn.bookmarked svg {
  animation: bookmark-pop 0.3s ease-out;
}

@keyframes bookmark-pop {
  0% { transform: scale(1); }
  50% { transform: scale(1.3); }
  100% { transform: scale(1); }
}
```

#### C. Update JavaScript for Toast Feedback

**`app.js`** - Update `toggleBookmark` function (around line 413):
```javascript
function toggleBookmark(articleId) {
  var ids = getBookmarkedIds();
  var idx = ids.indexOf(articleId);
  if (idx === -1) {
    ids.push(articleId);
    showToast("Article bookmarked", "toast-success");
  } else {
    ids.splice(idx, 1);
    showToast("Bookmark removed", "toast-success");
  }
  saveBookmarkedIds(ids);
  updateBookmarkUI(articleId);
}

function showToast(message, type) {
  var container = document.getElementById("toast-container");
  if (!container) return;
  
  var toast = document.createElement("div");
  toast.className = "toast " + (type || "");
  toast.textContent = message;
  
  container.appendChild(toast);
  
  setTimeout(function() { 
    if (toast.parentNode) toast.remove(); 
  }, 3000);
}
```

#### D. Add Clear Read State Feature

**`partials/feed.html`** (add to feed-header):
```html
<button id="clear-read-state" class="text-xs text-dim" 
        onclick="clearReadState()">
  Clear read markers
</button>
```

**`app.js`** (add function):
```javascript
function clearReadState() {
  localStorage.removeItem("read_articles");
  document.querySelectorAll(".article-read").forEach(function(el) {
    el.classList.remove("article-read");
  });
  showToast("Read markers cleared", "toast-success");
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/templates/partials/article_card.html`
- `/home/sugarwookie/projects/ainews/templates/partials/condensed_article.html`
- `/home/sugarwookie/projects/ainews/static/css/components.css`
- `/home/sugarwookie/projects/ainews/static/js/app.js`

---

### 7. Toast Notification Gaps

**Status**: INVESTIGATION COMPLETE  
**Issue**: Only error toasts exist, no success/warning/info toasts

**Current State** (`components.css` lines 517-567):
- `.toast-error` exists with retry button
- Offline toast exists
- No `.toast-success`, `.toast-warning`, or `.toast-info` styles

**Recommended Addition** (`components.css` after line 567):
```css
.toast-success {
  border-color: var(--green);
  background: var(--bg-secondary);
}

.toast-warning {
  border-color: var(--orange);
  background: var(--bg-secondary);
}

.toast-info {
  border-color: var(--accent);
  background: var(--bg-secondary);
}
```

**Actions Needing Success Toasts**:
- Bookmark toggle ✅ (implemented above)
- Subscribe/unsubscribe
- Article read state changes
- Form submissions

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/components.css`

---

### 8. Missing Print Styles for Article Pages [LOW PRIORITY]

**Status**: INVESTIGATION COMPLETE  
**Issue**: Current print styles exist but article pages could benefit from enhanced layout  
**Original Priority**: LOW (from todo list, item #4)

**Current State** (`utilities.css` lines 29-145):
Print styles are comprehensive and well-implemented:
- Hides navigation, buttons, share triggers, admin headers
- Shows URL after links for print
- Adjusts font sizes for print (12pt body, 18pt headings)
- Proper handling of article cards, body text, category badges

**Finding**: The current print implementation is actually quite good. Minor enhancements could include:
1. Wider text layout (currently `max-width: 100%` with `padding: 0`)
2. Removing box shadows/borders for ink-saving (partially done)
3. Ensuring article body uses serif font for print readability

**Optional Enhancement** (`utilities.css` print section):
```css
@media print {
  .article-body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 12pt;
    line-height: 1.6;
  }
  
  .article-title {
    page-break-after: avoid;
  }
  
  .article-card {
    page-break-inside: avoid;
  }
}
```

**Verdict**: Current implementation is adequate. This is a LOW priority nice-to-have, not a critical gap.

**Files to Modify** (optional):
- `/home/sugarwookie/projects/ainews/static/css/utilities.css`

---

### 9. Article Card Truncation Strategy

**Status**: INVESTIGATION COMPLETE  
**Finding**: `-webkit-line-clamp` has 96.7% support - acceptable to keep

**Current Implementation** (`articles.css`):
```css
.card-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

**Browser Support**: 96.7% global usage (Can I Use, March 2026)

**Recommendation**: Keep current approach. Optionally add unprefixed property for future compatibility:

```css
.card-title {
  display: -webkit-box;
  display: box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

**No changes required** - current approach is fine.

---

## LOW PRIORITY ITEMS

### 10. Tablet Breakpoint Gaps

**Status**: INVESTIGATION COMPLETE  
**Issue**: Major gap in 901px-1024px range (iPad Pro landscape)

**Current Breakpoints**:
- `max-width: 640px` - Mobile
- `641px` to `768px` - Small tablet (2-col grids)
- `769px` to `900px` - Tablet (2-col top-impact)
- Above `900px` - Desktop (3-col)

**Missing**: No specific styles for 901px-1024px (iPad Pro landscape: 1024px)

**Recommended New Breakpoints**:

**`articles.css`** (update top-impact grid):
```css
/* Small tablet */
@media (min-width: 641px) and (max-width: 820px) {
  .top-impact-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Standard tablet (iPad Portrait to Pro Landscape) */
@media (min-width: 821px) and (max-width: 1024px) {
  .top-impact-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .dashboard-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Small desktop / large tablet transition */
@media (min-width: 1025px) {
  .top-impact-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
```

**Optional**: Make `--max-width` responsive:
```css
:root {
  --max-width: 820px;
}

@media (min-width: 1024px) {
  :root {
    --max-width: 1000px;
  }
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/articles.css`
- `/home/sugarwookie/projects/ainews/static/css/layout.css`
- `/home/sugarwookie/projects/ainews/static/css/variables.css` (optional)

---

### 11. Touch Target Coverage

**Status**: INVESTIGATION COMPLETE  
**Issue**: `@media (pointer: coarse)` covers touch devices but NOT hybrid devices

**Current Coverage**:
- `@media (pointer: coarse)` in `layout.css` (lines 67-77) sets 44px on ALL interactive elements
- Explicit 44px on `.bookmark-btn`, `.pill-close`, etc.

**Elements Needing Explicit 44px** (not covered on hybrid devices):

**`articles.css`**:
```css
.pag-link {
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.share-social-link {
  min-width: 44px;
  min-height: 44px;
}

.tag-pill, .tag-pill-sm {
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
```

**`utilities.css`**:
```css
.btn-sm {
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
```

**Optional: Catch hybrid devices** (`layout.css`):
```css
@media (pointer: coarse), (any-pointer: coarse) {
  a, button, input, select, textarea {
    min-height: 44px;
    min-width: 44px;
  }
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/articles.css`
- `/home/sugarwookie/projects/ainews/static/css/utilities.css`
- `/home/sugarwookie/projects/ainews/static/css/layout.css` (optional)

---

### 12. CSS @import Strategy

**Status**: INVESTIGATION COMPLETE  
**Issue**: `@import` creates sequential loading chain

**Current Implementation** (`style.css`):
```css
@layer reset, variables, layout, components, pages, utilities;

@import url('variables.css') layer(variables);
@import url('base.css') layer(reset);
@import url('layout.css') layer(layout);
@import url('components.css') layer(components);
@import url('articles.css') layer(components);
@import url('pages.css') layer(pages);
@import url('utilities.css') layer(utilities);
```

**Problem**: Sequential request chain:
```
HTML → style.css → variables.css → base.css → layout.css → ...
```

**Mitigation**: Critical CSS is inlined in `base.html` - helps with First Contentful Paint.

**Recommendation**: 
- **Keep current approach** if Lighthouse shows no CSS performance issues (total CSS ~40KB)
- **Optional improvement**: Switch to `<link>` tags for parallel downloads:

```html
<!-- In base.html, replace style.css link with: -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/variables.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/base.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/layout.css') }}">
<!-- etc. -->
```

**Files to Modify** (optional):
- `/home/sugarwookie/projects/ainews/templates/base.html`

---

### 13. Container Queries

**Status**: INVESTIGATION COMPLETE  
**Finding**: 94% support, but NO actual `@container` queries implemented - only infrastructure

**Current Implementation** (`articles.css` lines 3-13):
```css
#feed {
  container-type: inline-size;
  container-name: feed;
}

@supports (container-type: inline-size) {
  .article-card {
    width: 100cqi;  /* Essentially a no-op for block elements */
  }
}
```

**Browser Support**: 94.05% global usage

**Options**:
1. **Implement `@container` queries** for responsive card layouts
2. **Remove unused code** if not planning to use container queries

**Recommendation**: Currently harmless. Choose option 1 if you want container-based responsiveness, option 2 to simplify codebase.

**No changes required** unless you want to implement container queries or remove unused code.

---

### 14. HTMX Loading Indicators

**Status**: INVESTIGATION COMPLETE  
**Issue**: Text "loading..." looks amateurish

**Current State**: 6 text-only indicators + 1 skeleton loading (good)

**Recommended SVG Spinner** (add to `critical.css`):
```css
.spinner-icon {
  width: 14px;
  height: 14px;
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.25rem;
  animation: spinner-rotate 1.2s linear infinite;
}

.spinner-icon circle {
  stroke: currentColor;
  stroke-width: 3;
  fill: none;
  stroke-linecap: round;
  stroke-dasharray: 80, 200;
  stroke-dashoffset: 0;
  animation: spinner-dash 1.4s ease-in-out infinite;
}

@keyframes spinner-rotate {
  100% { transform: rotate(360deg); }
}

@keyframes spinner-dash {
  0% {
    stroke-dasharray: 1, 200;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 200;
    stroke-dashoffset: -35px;
  }
  100% {
    stroke-dasharray: 90, 200;
    stroke-dashoffset: -124px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner-icon {
    animation: none;
  }
}
```

**Files to Modify**:
- `/home/sugarwookie/projects/ainews/static/css/critical.css`
- Update all text-only indicators in templates to use SVG spinner

---

## IMPLEMENTATION PRIORITY MATRIX

| Item | Priority | Effort | Impact | Category |
|------|----------|--------|--------|----------|
| Skip link `:focus-visible` | 🔴 High | Low (5 lines) | Accessibility | Fix |
| Color contrast `--text-muted` | 🔴 High | Low (1 line) | Accessibility | Fix |
| Mobile nav JS enhancement | 🔴 High | Medium (80 lines) | UX | Fix |
| Font scale standardization | 🟡 Medium | Medium (test) | Consistency | Fix |
| Search submit button | 🟡 Medium | Low (10 lines) | UX | Enhancement |
| Bookmark button (complete feature) | 🟡 Medium | Medium | UX | New Feature |
| Toast success styles | 🟡 Medium | Low (5 lines) | UX | Enhancement |
| Missing print styles | 🟢 Low | Low | Print | Enhancement |
| Tablet breakpoints | 🟢 Low | Medium | Responsive | Enhancement |
| Touch target explicit 44px | 🟢 Low | Low | Accessibility | Fix |
| HTMX SVG spinners | 🟢 Low | Low | Visual | Polish |
| CSS @import → `<link>` | 🟢 Low | Low | Performance | Optimization |
| Container queries implement/remove | 🟢 Low | Low | Code Quality | Cleanup |

---

## FILE MODIFICATION CHECKLIST

### High Priority:
- [ ] `/home/sugarwookie/projects/ainews/static/css/critical.css` - Skip link (lines 28-44)
- [ ] `/home/sugarwookie/projects/ainews/static/css/variables.css` - Color contrast (lines 37, 186)
- [ ] `/home/sugarwookie/projects/ainews/templates/base.html` - Mobile nav HTML (lines 38-51)
- [ ] `/home/sugarwookie/projects/ainews/templates/base_admin.html` - Mobile nav HTML (lines 29-45)
- [ ] `/home/sugarwookie/projects/ainews/static/js/app.js` - Mobile nav JS (before line 464)

### Medium Priority:
- [ ] `/home/sugarwookie/projects/ainews/static/css/variables.css` - Font scale (lines 63-74)
- [ ] `/home/sugarwookie/projects/ainews/templates/partials/feed.html` - Search UX
- [ ] `/home/sugarwookie/projects/ainews/templates/partials/article_card.html` - Bookmark button
- [ ] `/home/sugarwookie/projects/ainews/templates/partials/condensed_article.html` - Bookmark button
- [ ] `/home/sugarwookie/projects/ainews/static/css/components.css` - Toast styles (after line 567)
- [ ] `/home/sugarwookie/projects/ainews/static/js/app.js` - Toast function

### Low Priority:
- [ ] `/home/sugarwookie/projects/ainews/static/css/articles.css` - Tablet breakpoints, touch targets
- [ ] `/home/sugarwookie/projects/ainews/static/css/layout.css` - Tablet breakpoints
- [ ] `/home/sugarwookie/projects/ainews/static/css/utilities.css` - Touch targets
- [ ] `/home/sugarwookie/projects/ainews/templates/base.html` - CSS loading strategy (optional)
- [ ] `/home/sugarwookie/projects/ainews/static/css/critical.css` - SVG spinners

---

## NEXT STEPS

1. **Start with High Priority items** (1-3 above) - quick wins for accessibility
2. **Test font scale changes** thoroughly - may need visual adjustments
3. **Complete the bookmark feature** - it's 90% built, just needs UI
4. **Polish with Low Priority items** as time permits

---

**Plan prepared by**: AI Agent  
**Date**: May 1, 2026  
**Total items investigated**: 15  
**Total files to modify**: 15 (depending on scope chosen)
