# Frontend Improvement Plan — UI/UX Enhancements

**Generated**: 2026-04-23
**Status**: Planned (not started)
**Source**: Frontend Deep Dive Review — 2026-04-23

---

## Executive Summary

This plan addresses frontend (CSS/JS/template) improvements identified during a comprehensive frontend review. Most items were found to already be implemented correctly; this plan focuses on the few optional gaps and documentation improvements.

| Priority | Category | Issues | Status |
|----------|----------|--------|--------|
| 🟢 Low | Accessibility | 3 | 1 Optional, 2 Done |
| 🟢 Low | Performance | 2 | Both Done |
| 🟢 Low | Best Practices | 2 | 1 Optional, 1 Done |

---

## Priority 1: 🟢 LOW — Accessibility

### 1.1 Sync aria-expanded on Page Load

**Severity**: LOW (Optional)
**Finding**: Share dropdown updates `aria-expanded` on toggle events, but could sync on page load for pre-opened state.

**Current State**: `app.js:32-51` — handles toggle events:
```javascript
document.addEventListener("toggle", function (e) {
  if (!e.target.classList.contains("share-details")) return;
  var summary = e.target.querySelector("summary");
  if (summary) {
    summary.setAttribute("aria-expanded", e.target.open);
  }
  // ...
});
```

**Location**: `templates/partials/share_macro.html:6` — hardcoded `aria-expanded="false"`:
```html
aria-expanded="false"
```

**Issue**: If HTML is ever rendered with `open` attribute pre-set, the ARIA state won't match until JS runs.

**Required Changes**: Consider adding initialization in `app.js`:

```javascript
// After DOMContentLoaded, sync aria-expanded for any pre-opened details
document.querySelectorAll(".share-details[open]").forEach(function(details) {
  var summary = details.querySelector("summary");
  if (summary) {
    summary.setAttribute("aria-expanded", "true");
  }
});
```

**Effort**: 15 minutes
**Risk**: None — defensive improvement

**Action Items**:
- [ ] Add sync logic for pre-opened details elements
- [ ] Consider updating template to dynamically set `aria-expanded` based on open state

---

### 1.2 Reduced Motion for Toast Animations

**Severity**: LOW
**Finding**: Toast animations (`toast-slide-up`) may not respect `prefers-reduced-motion`.

**Current State**: `critical.css:401-408` has global reduced-motion rule:
```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Analysis**: The global rule should catch toast animations, but explicit overrides provide defense-in-depth. Current coverage:
- `articles.css:27-31` — `.article-card:hover` transform disabled ✅
- `base.css:8-12` — scroll-behavior conditional ✅
- `critical.css:401-408` — Global catch-all ✅

**Recommendation**: No immediate changes needed — global rule catches most cases. Could add explicit toast override for extra safety:

```css
/* Optional: In components.css */
@media (prefers-reduced-motion: reduce) {
  .toast {
    animation: none;
    opacity: 1;
  }
}
```

**Effort**: 15 minutes (optional)
**Risk**: None

**Action Items**:
- [ ] Evaluate if explicit toast reduced-motion is needed
- [ ] Test with `prefers-reduced-motion: reduce` enabled

---

### 1.3 Mobile Navigation Keyboard Accessibility

**Severity**: LOW
**Finding**: Verify mobile navigation toggle is keyboard accessible.

**Current State**: `layout.css:193-202` — CSS-only toggle:
```css
.nav-toggle-checkbox:checked ~ .nav-links {
  display: flex;
  flex-direction: column;
  width: 100%;
}
```

**Current Implementation**: Uses `<label>` for the toggle, which is keyboard-focusable and activates on Enter/Space:
```html
<label for="nav-toggle" class="nav-toggle-label" aria-label="Toggle navigation">
  <span></span>
</label>
```

**Assessment**: ✅ Works correctly — `<label for="...">` is implicitly keyboard-clickable. No changes needed.

**Action Items**:
- [ ] None — keyboard accessibility is correct

---

## Priority 2: 🟢 LOW — Performance

### 2.1 content-visibility Implementation

**Severity**: LOW (already implemented)
**Finding**: Article cards correctly use `content-visibility: auto` with `contain-intrinsic-size`.

**Current State**: `articles.css:11-12`:
```css
content-visibility: auto;
contain-intrinsic-size: 0 200px;
```

**Browser Support**: ✅ Baseline Newly Available (Sept 2025)
- Chrome 85+ ✅
- Firefox 125+ ✅
- Safari 18+ ✅
- Edge 85+ ✅

**Optional Enhancement**: Track content-visibility state changes:

```javascript
// Optional: Listen for contentvisibilityautostatechange event
document.addEventListener("contentvisibilityautostatechange", function(e) {
  if (e.target.classList.contains("article-card")) {
    console.log("Article card rendering:", e.hidden ? "skipped" : "active");
  }
});
```

**Effort**: 30 minutes (optional)
**Risk**: None

**Action Items**:
- [ ] None required — current implementation is correct
- [ ] Consider adding event listener if tracking is needed

---

### 2.2 Image Lazy Loading

**Severity**: N/A
**Finding**: No images exist in article templates that would require lazy loading.

**Analysis**: Grepped all HTML templates — no `<img>` tags found. The article feed is text-only.

**Recommendation**: If images are added in the future, use `loading="lazy"`:
```html
<img src="..." loading="lazy" alt="...">
```

**Action Items**:
- [ ] N/A — no changes needed currently
- [ ] Monitor if images are added to article display

---

## Priority 3: 🟢 LOW — Best Practices

### 3.1 CSS Token Duplication Validation

**Severity**: LOW
**Finding**: Both `critical.css` and `variables.css` define the same CSS custom properties — this is intentional per AGENTS.md but worth noting.

**Current State**:
- `critical.css` (inlined in `<head>`): 36 tokens defined
- `variables.css` (in style.css): ~100 tokens defined
- Light theme overrides duplicated in both

**Rationale**: AGENTS.md explicitly states this is intentional — critical CSS is inlined for first-paint performance.

**Risk**: Token drift between files. Any color changes must occur in BOTH files.

**Required Changes**: None — document the pattern:

```css
/*
 * IMPORTANT: Tokens are duplicated in this file AND variables.css.
 * Any changes must be made to BOTH files to prevent color flash on first paint.
 * See: AGENTS.md - "CSS consolidation note"
 */
```

**Effort**: 10 minutes (documentation only)

**Action Items**:
- [ ] Add comment to critical.css about token duplication
- [ ] Create checklist for future token changes

---

### 3.2 Theme System Review

**Severity**: LOW (already implemented correctly)
**Finding**: `theme.js` correctly implements real-time media query support.

**Current State**: `theme.js:65-74`:
```javascript
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
  if (!localStorage.getItem(STORAGE_KEY)) {
    setTheme(e.matches ? DARK : LIGHT);
  }
});
```

This is correct ✅ — the theme auto-switches when OS preference changes, but respects manual user selection.

**Action Items**:
- [ ] None — working as designed

---

## Issue Summary Table

| ID | Priority | Category | Status | Location | Description |
|---|----------|----------|--------|----------|-------------|
| A11Y-001 | 🟢 LOW | Accessibility | Optional | app.js | Sync aria-expanded on page load |
| A11Y-002 | 🟢 LOW | Accessibility | Optional | components.css | Explicit toast reduced-motion |
| A11Y-003 | 🟢 LOW | Accessibility | ✅ Done | layout.css | Mobile nav keyboard accessible |
| PERF-001 | 🟢 LOW | Performance | ✅ Done | articles.css | content-visibility |
| PERF-002 | 🟢 LOW | Performance | N/A | templates | No images present |
| BEST-001 | 🟢 LOW | Best Practices | Optional | critical.css | Add token duplication comment |
| BEST-002 | 🟢 LOW | Best Practices | ✅ Done | theme.js | prefers-color-scheme listener |

---

## Investigation Details

### Investigation 1: Theme System

**Method**: Read `static/js/theme.js`

**Key Findings**:
- `getPreferredTheme()` checks localStorage first, then `prefers-color-scheme`
- `setTheme()` applies to document and stores in localStorage
- `toggleTheme()` provides manual toggle
- Real-time listener at line 65-74 ✅

---

### Investigation 2: content-visibility

**Method**: WebSearch for browser support, Grep for current usage

**Browser Support Results**:
- As of September 2025, `content-visibility: auto` is **Baseline Newly Available**
- Supported in: Chrome 85+, Firefox 125+, Safari 18+, Edge 85+

**Current Implementation**: Correctly uses both `content-visibility` and `contain-intrinsic-size`

---

### Investigation 3: Reduced Motion

**Method**: Grep for animation/transition rules

**Coverage Results**:
- `critical.css:401-408` — Global catch-all ✅
- `articles.css:27-31` — Card hover transform
- `base.css:8-12` — Scroll behavior

**Assessment**: Good coverage, no gaps identified

---

### Investigation 4: aria-expanded State

**Method**: Grep for details/aria patterns, read share_macro.html

**Current Implementation**:
- Template hardcodes `aria-expanded="false"`
- JS handles toggle events to update attribute

**Assessment**: Correct; could add sync for pre-opened state

---

### Investigation 5: Image Lazy Loading

**Method**: Grep for `<img>` in all HTML templates

**Results**: No `<img>` tags found in templates

**Assessment**: Not applicable — no images to load

---

### Investigation 6: CSS Token Duplication

**Method**: Compare tokens in critical.css vs variables.css

**Results**: Duplication is intentional per AGENTS.md

**Risk**: Token drift — any changes must happen in both files

---

## Recommendations Summary

| Recommendation | Effort | Priority | Status |
|----------------|--------|----------|--------|
| Sync aria-expanded on load | 15 min | 🟢 LOW | Optional |
| Explicit toast reduced-motion | 15 min | 🟢 LOW | Optional |
| Add CSS token comment | 10 min | 🟢 LOW | Optional |
| content-visibility | — | N/A | ✅ Done |
| Image lazy loading | — | N/A | Not applicable |
| Theme real-time listener | — | N/A | ✅ Done |

### Overall Assessment

The frontend is **well-implemented** with:
- ✅ Proper CSS modular architecture
- ✅ Critical CSS inlining for first paint
- ✅ Full theme system with real-time OS preference
- ✅ Full accessibility (skip links, aria-live, focus management)
- ✅ HTMX integration with error handling
- ✅ content-visibility performance optimization
- ✅ Reduced motion support

**No urgent issues identified.** Current implementation follows modern best practices.

---

## Approval

- [ ] Ready for implementation (optional items only)
- [ ] Priority acknowledged
- [ ] Low priority status noted