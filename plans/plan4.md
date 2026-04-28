# Frontend Improvement Plan (Plan 4)

## Overview

This plan addresses stylistic and usability improvements identified during a comprehensive frontend review of the ainews webapp. Findings are organized by priority with detailed technical recommendations.

---

## ✅ VERIFIED NOT BUGS (No Action Needed)

### 1. CSS Typo `scroll-be-havior` in `base.css:10`
**Status**: NOT A BUG - Verified correct spelling `scroll-behavior: smooth;`  
**Investigation**: Read file, checked git history, verified no typo exists  
**Action**: None needed

### 2. Broken Links `/admin/pipelines` in `dashboard.html`
**Status**: NOT A BUG - Verified correct spelling `/admin/pipelines` (plural with 's')  
**Investigation**: Route defined in `routes/admin/pipelines.py`, template URLs match  
**Action**: None needed

### 3. CSS Selector Error in `app.js:64`
**Status**: NOT A BUG - Verified selector `.share-dropdown input, .share-dropdown button, .share-dropdown a` is correct  
**Investigation**: Uses descendant combinator properly, matches DOM structure  
**Action**: None needed

---

## 🔴 HIGH PRIORITY - Critical Fixes

### 4. Skip-Link Focus Visibility (Critical Accessibility)

**File**: `static/css/critical.css:100-103` and `templates/partials/critical_css.html:7`

**Issue**: `.skip-link:focus { outline: none; }` removes focus indicator entirely. The global `:focus-visible` rule in `base.css` is overridden by this higher-specificity rule.

**Impact**: Keyboard users cannot see which element is currently focused when using the skip-link.

**Fix**:
```css
/* Remove from critical.css:100-103 and critical_css.html:7 */
.skip-link:focus {
  top: 0;
  outline: none;  /* REMOVE THIS */
}

/* Replace with */
.skip-link:focus-visible {
  top: 0;
  outline: 3px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
  color: var(--bg-primary);  /* Better contrast than #fff */
}

.skip-link:focus {
  top: 0;  /* Keep for positioning only */
}
```

**WCAG**: Fixes missing focus indicator (SC 2.4.7 Focus Visible - Level AA)

---

### 5. Admin Logout Hidden on Mobile (Critical Bug)

**File**: `static/css/layout.css:200-202` and `templates/base_admin.html:46-51`

**Issue**: `.nav-meta { display: none; }` on mobile hides the logout form. Admin users on mobile cannot logout.

**Fix Option A (Recommended)**: Move logout into `.nav-links`:
```html
<!-- In base_admin.html, remove nav-meta div, add to nav-links -->
<div class="nav-links">
  <!-- existing links -->
  <form method="POST" action="/admin/logout" class="inline" hx-boost="false">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button type="submit" class="btn-logout">logout</button>
  </form>
</div>
```

**Fix Option B**: CSS override for admin:
```css
/* In pages.css */
@media (max-width: 640px) {
  .admin-header .nav-meta {
    display: block;
    position: absolute;
    top: 0.75rem;
    right: 60px;
  }
}
```

---

### 6. Mobile Hamburger Menu Keyboard Accessibility

**File**: `templates/base.html:38-41`, `templates/base_admin.html:29-32`, `static/js/app.js`

**Issues**:
- Checkbox has `hidden` attribute, removing it from accessibility tree
- Label has no `role="button"` or `tabindex="0"`
- No `aria-expanded` management
- No Escape key handler to close menu

**Fix**:
```html
<!-- Update label in both base.html and base_admin.html -->
<label for="nav-toggle" 
       class="nav-toggle-label" 
       aria-label="Toggle navigation"
       role="button"
       tabindex="0">
  <span></span>
</label>
```

```javascript
/* Add to app.js */

// Keyboard activation (Enter/Space)
document.addEventListener("keydown", function(e) {
  var label = e.target.closest(".nav-toggle-label");
  if (!label) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    var checkbox = document.getElementById("nav-toggle");
    if (checkbox) {
      checkbox.checked = !checkbox.checked;
      updateNavAriaExpanded(checkbox);
      if (checkbox.checked) {
        var firstLink = document.querySelector(".nav-links a");
        if (firstLink) setTimeout(() => firstLink.focus(), 100);
      }
    }
  }
});

// Update aria-expanded
function updateNavAriaExpanded(checkbox) {
  var label = document.querySelector(".nav-toggle-label");
  if (label) {
    label.setAttribute("aria-expanded", checkbox.checked.toString());
  }
}

// Watch for checkbox changes
document.addEventListener("change", function(e) {
  if (e.target.id === "nav-toggle") {
    updateNavAriaExpanded(e.target);
  }
});

// Close on Escape
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    var checkbox = document.getElementById("nav-toggle");
    if (checkbox && checkbox.checked) {
      checkbox.checked = false;
      updateNavAriaExpanded(checkbox);
    }
  }
});
```

---

## 🟡 MEDIUM PRIORITY - Usability & Accessibility

### 7. Search Input Focus Loss (Major UX Issue)

**File**: `templates/partials/feed.html`, `static/js/app.js:202-209`

**Issue**: Search form is inside `#content` which gets replaced by HTMX swaps. After 500ms debounce, the search input loses focus, interrupting typing flow.

**Root Cause**: `hx-target="#content"` replaces entire content div including the search form.

**Fix Option A (Recommended)**: Move search form outside `#content`:
```html
<!-- In base.html -->
<main class="container">
  <div id="search-area">
    <!-- Include search form via block or move directly -->
  </div>
  <div id="content">
    {% block content %}{% endblock %}
  </div>
</main>
```

**Fix Option B**: Use `hx-preserve="true"` on search form and update server to not return form in partial.

**Fix Option C**: Update `htmx:afterSwap` handler to preserve focus:
```javascript
document.addEventListener("htmx:afterSwap", function(e) {
  var searchInput = document.querySelector("#search-input");
  var isSearchTrigger = e.detail && e.detail.target && 
                       e.detail.target.id === "search-input";
  
  if (isSearchTrigger && searchInput) {
    setTimeout(function() {
      searchInput.focus();
      var len = searchInput.value.length;
      searchInput.setSelectionRange(len, len);
    }, 10);
    return;
  }
  // Original heading focus logic...
});
```

---

### 8. Search UX Improvements

**File**: `templates/partials/feed.html`, `static/css/articles.css`

**Issues Found**:
- No minimum search length (triggers on single characters)
- `<kbd>` element has no tooltip/title
- Search spinner visibility may not work correctly

**Fixes**:

**Add minimum length** (feed.html line 19):
```html
hx-trigger="keyup changed delay:500ms min-length:3, search"
```

**Add tooltip to kbd** (feed.html line 27):
```html
<kbd class="search-kbd" title="Press / to focus search" aria-hidden="true">/</kbd>
```

**Fix spinner visibility** (add to articles.css):
```css
/* Ensure search spinner shows during request */
.search-container .htmx-indicator {
  display: none;
}

.search-container.htmx-request .htmx-indicator {
  display: inline-block;
  opacity: 1;
}
```

---

### 9. Share Dropdown Keyboard Navigation

**File**: `static/js/app.js` lines 229-289

**Issues Found**:
- **Escape key handler missing** (standard way to close dropdowns)
- Arrow keys only target `.share-social-link`, missing input and copy button
- Tab trapping only works on first open dropdown (uses `querySelector` not `querySelectorAll`)
- No delay on focusout handler (can cause race conditions)

**Fixes**:

**Add Escape handler**:
```javascript
document.addEventListener("keydown", function(e) {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".share-details[open]").forEach(function(details) {
    details.open = false;
  });
});
```

**Unify Arrow key scope** (include all focusable elements):
```javascript
document.addEventListener("keydown", function(e) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  var details = e.target.closest(".share-details");
  if (!details || !details.open) return;
  
  var focusable = details.querySelectorAll(
    ".share-dropdown a[href], .share-dropdown button, .share-dropdown input"
  );
  // ... cycle logic
});
```

**Fix Tab trapping for multiple dropdowns**:
```javascript
document.addEventListener("keydown", function(e) {
  if (e.key !== "Tab") return;
  var details = document.activeElement.closest(".share-details");
  if (!details || !details.open) return;
  
  var dropdown = details.querySelector(".share-dropdown");
  var focusable = dropdown.querySelectorAll(
    "a[href], button, input, [tabindex]:not([tabindex='-1'])"
  );
  // ... trap logic
});
```

**Add delay to focusout**:
```javascript
document.addEventListener("focusout", function(e) {
  var details = e.target.closest(".share-details");
  if (!details) return;
  
  setTimeout(function() {
    var active = document.activeElement;
    if (!details.contains(active)) {
      details.open = false;
    }
  }, 50);
});
```

---

### 10. Article Card Focus Styles

**File**: `static/css/articles.css` lines 1-40

**Issue**: Mouse users get card-level hover effect (border, shadow, transform), but keyboard users navigating with Tab only see focus on individual links, not the card container.

**Fix** (add after line 40):
```css
/* Mirror hover effect for keyboard navigation */
.article-card:focus-within {
  border-color: var(--border-light);
  background: var(--bg-tertiary);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  transform: translateY(-2px);
}

@media (prefers-reduced-motion: reduce) {
  .article-card:focus-within {
    transform: none;
  }
}
```

**Browser Support**: `:focus-within` has ~95% support (caniuse.com)

---

### 11. Category Badge Color Contrast (WCAG AA)

**File**: `static/css/components.css` lines 15-49, `static/css/variables.css`

**Issue**: Hardcoded alpha background values don't adapt to light theme, causing 5 out of 6 badges to FAIL WCAG AA in light theme.

**Current State** (Light Theme):
| Badge | Text Color | Contrast Ratio | Pass AA? |
|-------|-------------|----------------|----------|
| `.cat-ai` | `#8250df` | 4.46:1 | **FAIL** |
| `.cat-privacy` | `#9a6700` | 4.29:1 | **FAIL** |
| `.cat-security` | `#cf222e` | 4.47:1 | **FAIL** |
| `.cat-programming` | `#1a7f37` | 4.46:1 | **FAIL** |
| `.cat-hardware` | `#0969da` | 4.57:1 | **PASS** |
| `.cat-other` | `#6e7781` | 3.89:1 | **FAIL** |

**Root Cause**: Alpha backgrounds use hardcoded dark theme RGB values.

**Fix**: Add alpha variant CSS variables:
```css
/* In variables.css :root */
:root {
  /* Existing colors... */
  --purple-alpha-15: rgba(188, 140, 255, 0.15);
  --purple-alpha-40: rgba(188, 140, 255, 0.4);
  /* ... repeat for orange, red, green, accent */
}

/* In variables.css [data-theme="light"] */
[data-theme="light"] {
  --purple-alpha-15: rgba(130, 80, 223, 0.15);
  --purple-alpha-40: rgba(130, 80, 223, 0.4);
  /* ... repeat for others */
}
```

Update `components.css` to use variables:
```css
.cat-ai {
  color: var(--purple);
  background: var(--purple-alpha-15);
  border: 1px solid var(--purple-alpha-40);
}
```

---

### 12. CSS Flash Issue (Critical.css vs Variables.css)

**Files**: `static/css/critical.css`, `static/css/variables.css`, `templates/partials/critical_css.html`, `templates/partials/critical_css_admin.html`

**Issue**: `critical.css` inlined in base templates has overlapping CSS custom properties with `variables.css`. If values drift, users see a flash of incorrect color on first paint.

**Current State**: AGENTS.md notes this is "intentional" for first-paint performance, but maintenance is error-prone.

**Recommendation**: No immediate code change, but add a verification step:
1. Create a simple diff script to compare CSS custom properties between files
2. Add to AGENTS.md: "After changing variables.css, always update critical.css to match"
3. Consider a build step in the future (PostCSS, etc.) to auto-generate critical CSS

---

### 13. Content-Visibility + Animation Interaction

**File**: `static/css/articles.css` lines 11-12, 42-55, `static/js/app.js` lines 211-217

**Issue**: Cards with `content-visibility: auto` may not play `fade-in-up` animation if they're off-screen when `.article-card-new` class is added.

**Technical Detail**: Per CSS WG spec, animations in skipped `content-visibility` subtrees don't update their local times until the element becomes visible.

**Fix (Intersection Observer approach)**:
```javascript
// Replace lines 211-217 in app.js
var cards = content.querySelectorAll(".article-card:not(.article-card-new)");

if ('IntersectionObserver' in window) {
  var animationObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        var card = entry.target;
        card.classList.add("article-card-new");
        card.addEventListener("animationend", function() {
          card.classList.remove("article-card-new");
        }, { once: true });
        animationObserver.unobserve(card);
      }
    });
  }, { threshold: 0.1 });
  
  cards.forEach(function(card) {
    animationObserver.observe(card);
  });
} else {
  // Fallback for older browsers
  cards.forEach(function(card) {
    card.classList.add("article-card-new");
    card.addEventListener("animationend", function() {
      card.classList.remove("article-card-new");
    }, { once: true });
  });
}
```

**Alternative**: Simply remove `content-visibility: auto` if performance benefit is minimal.

---

## 🟢 LOW PRIORITY - Code Quality

### 14. Font Size Naming Consistency

**File**: `static/css/variables.css` lines 62-74

**Issue**: `--text-lg` (16px) is labeled "large" but is the browser default. `--text-base` (15px) is smaller than the 16px browser default. `--text-md` is a duplicate of `--text-base`.

**Current Scale**:
| Variable | rem | px | Expected? |
|----------|-----|----|-----------|
| `--text-xs` | 0.75rem | 12px | ✓ Small |
| `--text-sm` | 0.8125rem | 13px | ✓ Small |
| `--text-base` | 0.9375rem | **15px** | ✗ Should be 16px |
| `--text-md` | 0.9375rem | **15px** | ✗ Duplicate of base |
| `--text-lg` | 1rem | **16px** | ✗ Labeled "large" but is default |

**Recommendation**: Add comments to document current behavior (Option B from investigation):
```css
/* NOTE: --text-base (15px) is SMALLER than browser default (16px) */
/* NOTE: --text-lg (16px) is the browser default, not actually "large" */
/* NOTE: --text-md is a DUPLICATE of --text-base */
```

**Long-term**: Consider renaming during a dedicated refactoring sprint.

---

## Implementation Order

1. **Phase 1** (Critical - Do Immediately):
   - Fix skip-link focus (Item 4)
   - Fix admin logout on mobile (Item 5)
   - Add keyboard support to hamburger menu (Item 6)

2. **Phase 2** (Major UX - Do Next):
   - Fix search focus loss (Item 7)
   - Add search UX improvements (Item 8)
   - Fix share dropdown keyboard nav (Item 9)
   - Add article card focus styles (Item 10)

3. **Phase 3** (Accessibility - Do Soon):
   - Fix category badge contrast (Item 11)
   - Fix content-visibility + animation (Item 13)

4. **Phase 4** (Quality - Backlog):
   - Add CSS flash prevention documentation (Item 12)
   - Add font naming comments (Item 14)

---

## Files Requiring Changes

| File | Items | Priority |
|------|-------|----------|
| `static/css/critical.css` | 4 | High |
| `templates/partials/critical_css.html` | 4 | High |
| `templates/partials/critical_css_admin.html` | 4 | High |
| `templates/base_admin.html` | 5, 6 | High |
| `static/css/layout.css` | 6 | High |
| `static/js/app.js` | 6, 7, 9 | High/Medium |
| `templates/base.html` | 6, 7 | High/Medium |
| `templates/partials/feed.html` | 7, 8 | Medium |
| `static/css/articles.css` | 8, 10, 13 | Medium |
| `static/css/components.css` | 11 | Medium |
| `static/css/variables.css` | 11, 14 | Medium/Low |

---

## Testing Recommendations

After implementing fixes:

1. **Keyboard Navigation**: Tab through all interactive elements, verify focus indicators visible
2. **Screen Reader**: Test with NVDA/VoiceOver, verify aria-expanded updates
3. **Mobile**: Test hamburger menu, verify logout accessible
4. **Search**: Type query, verify focus preserved, min-length works
5. **Color Contrast**: Use browser DevTools or axe DevTools to verify WCAG compliance
6. **Share Dropdown**: Test Escape key, Arrow keys, Tab trapping
