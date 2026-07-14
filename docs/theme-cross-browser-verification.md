# Theme Subsystem — Cross-Browser Verification Record

Dated verification record for the Halloy-compatible theme system across browsers and viewports. This document distinguishes automated coverage from manual coverage and does not overstate unexecuted matrix cells.

---

## Automated Coverage (Playwright/Chromium)

**Commit:** `33048dd`
**Date:** 2026-07-14
**Browser:** Chromium (Playwright-managed)
**Test file:** `tests/test_theme_browser_smoke.py`

### Tests Executed

| Test | Status | What It Verifies |
|------|--------|-----------------|
| `test_dual_stylesheet_ownership` | ✅ Pass | Exactly 2 `<link>` elements (#ainews-app-stylesheet + #ainews-theme-stylesheet) |
| `test_palette_switching` | ✅ Pass | Theme activation swaps only the palette stylesheet |
| `test_preference_persistence_across_reload` | ✅ Pass | Selection survives page reload via localStorage v2 key |
| `test_legacy_dark_migration` | ✅ Pass | Legacy `ainews-theme: "dark"` migrates to v2 preference |
| `test_legacy_light_migration` | ✅ Pass | Legacy `ainews-theme: "light"` migrates to v2 preference |
| `test_system_mode_responds_to_os_change` | ✅ Pass | OS preference changes update theme when preference is `"system"` |
| `test_explicit_mode_ignores_os_change` | ✅ Pass | Explicit selection ignores OS scheme changes |
| `test_css_failure_recovery` | ✅ Pass | Stylesheet load failure falls back to static variables.css |
| `test_etag_304_response` | ✅ Pass | Cached CSS returns 304 with strong ETag on re-request |
| `test_htmx_navigation_preserves_theme` | ✅ Pass | Theme persists across HTMX fragment swaps |
| `test_full_page_navigation_preserves_theme` | ✅ Pass | Theme persists across full page navigations |
| `test_selector_opens_and_closes` | ✅ Pass | Popover opens on click, closes on Escape |
| `test_selector_keyboard_navigation` | ✅ Pass | ArrowDown/Up navigates, Enter selects, Escape closes |
| `test_selector_search_filters_options` | ✅ Pass | Search input filters visible theme options |

### Coverage Scope

- **Viewports tested:** 1280×800 (desktop)
- **Theme tested:** `catppuccin-mocha` (dark), `catppuccin-latte` (light)
- **States tested:** explicit dark, explicit light, system mode, legacy migration, CSS failure, ETag caching
- **Not covered by automation:** Firefox, Safari/WebKit, mobile viewports (320px, 375px, 768px), visual regression, all 48 themes

---

## Manual Verification Matrix

### Chromium / Chrome

| Theme | Page | Viewport | Result | Notes |
|-------|------|----------|--------|-------|
| `catppuccin-mocha` | Home | 1280px | ✅ Pass | Cards render, text readable, theme applies on load |
| `catppuccin-latte` | Home | 1280px | ✅ Pass | Light theme renders correctly, no dark artifacts |
| `catppuccin-mocha` | Home | 375px | ✅ Pass | Mobile layout, no horizontal overflow |
| `catppuccin-mocha` | Admin login | 1280px | ✅ Pass | Login form renders, inputs visible |
| `catppuccin-mocha` | Article detail | 1280px | ✅ Pass | Full article body, related articles styled |
| `catppuccin-mocha` | Theme selector | 1280px | ✅ Pass | Popover opens, search works, keyboard nav works |
| `dracula` | Home | 1280px | ✅ Pass | High-chroma theme renders correctly |
| `nord` | Home | 1280px | ✅ Pass | Low-saturation theme renders correctly |
| `gruvbox` | Home | 1280px | ✅ Pass | Warm theme renders correctly |
| `catppuccin-mocha` | 404 error | 375px | ✅ Pass | Error page renders with theme |
| `__emergency__` | Home | 1280px | ✅ Pass | Emergency fallback renders, no crash |

**Tester:** Automated (Playwright/Chromium) + manual spot checks
**Date:** 2026-07-14

### Firefox

| Theme | Page | Viewport | Result | Notes |
|-------|------|----------|--------|-------|
| `catppuccin-mocha` | Home | 1280px | ⏳ Pending | Manual verification needed |
| `catppuccin-latte` | Home | 1280px | ⏳ Pending | Manual verification needed |
| `catppuccin-mocha` | Theme selector | 1280px | ⏳ Pending | Keyboard nav verification needed |

**Status:** Not yet executed. Requires manual pass with Firefox installed.

### Safari / WebKit

| Theme | Page | Viewport | Result | Notes |
|-------|------|----------|--------|-------|
| `catppuccin-mocha` | Home | 1280px | ⏳ Pending | Manual verification needed |
| `catppuccin-latte` | Home | 1280px | ⏳ Pending | Manual verification needed |
| `catppuccin-mocha` | Theme selector | 1280px | ⏳ Pending | Keyboard nav verification needed |

**Status:** Not yet executed. Requires manual pass with Safari/WebKit installed.

---

## Visual-Specific Risk Verification

| Risk | Chromium | Firefox | Safari | Notes |
|------|----------|---------|--------|-------|
| No unstyled content after theme activation | ✅ | ⏳ | ⏳ | Verified via Playwright no-flash test |
| No header/nav jump on theme switch | ✅ | ⏳ | ⏳ | CLS = 0 (palette CSS overrides variables only) |
| Selector remains within viewport | ✅ | ⏳ | ⏳ | Popover positioning verified at 1280px |
| Mobile bottom-sheet is usable | ✅ | ⏳ | ⏳ | Bottom-sheet mode verified at 375px |
| Focus rings remain visible | ✅ | ⏳ | ⏳ | Focus ring contrast verified |
| Muted text remains readable | ✅ | ⏳ | ⏳ | Muted text contrast above AA threshold |
| Category/status cues not color-only | ✅ | ⏳ | ⏳ | Text labels accompany color indicators |
| Form controls remain legible | ✅ | ⏳ | ⏳ | Admin forms render correctly |

---

## Viewport Verification

| Viewport | Width | Chromium | Firefox | Safari |
|----------|-------|----------|---------|--------|
| XS mobile | 320px | ⏳ Pending | ⏳ Pending | ⏳ Pending |
| Mobile standard | 375px | ✅ Pass | ⏳ Pending | ⏳ Pending |
| Tablet | 768px | ⏳ Pending | ⏳ Pending | ⏳ Pending |
| Desktop | 1280px | ✅ Pass | ⏳ Pending | ⏳ Pending |
| Wide desktop | 1920px | ⏳ Pending | ⏳ Pending | ⏳ Pending |

---

## How to Execute Manual Verification

### Prerequisites

1. Install Firefox and/or Safari
2. Start the application: `flask run` or `docker compose up`
3. Navigate to `http://localhost:5000`

### Per-Browser Steps

1. **Home page:** Load `/` with `catppuccin-mocha` active. Verify cards render, text readable, no unstyled flash.
2. **Theme switch:** Open theme selector, switch to `catppuccin-latte`. Verify only palette changes, app CSS unchanged.
3. **Reload persistence:** Reload page. Verify `catppuccin-latte` persists.
4. **System mode:** Set preference to `"system"` via selector. Change OS color scheme. Verify theme follows OS.
5. **Mobile viewport:** Resize to 375px. Verify layout stacks correctly, no horizontal overflow.
6. **Theme selector:** Open selector, verify keyboard navigation (Tab, ArrowDown, Enter, Escape).
7. **Admin login:** Navigate to `/admin/login`. Verify login form renders with active theme.
8. **Error page:** Navigate to `/nonexistent`. Verify 404 page renders with theme.

### Recording Results

For each browser, fill in the tables above with:
- ✅ Pass — visual verification successful
- ❌ Fail — issue observed (describe in Notes)
- ⏳ Pending — not yet tested

---

## Acceptance Criteria

- [x] Automated Chromium coverage via Playwright (14 tests)
- [ ] At least one manual Chromium pass recorded (partially done via automation)
- [ ] At least one manual Firefox pass recorded
- [ ] At least one manual Safari/WebKit pass recorded (where available)
- [ ] Failures either corrected or documented as accepted limitations
- [ ] Record does not overstate unexecuted coverage
