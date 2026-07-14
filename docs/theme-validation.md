# Theme Subsystem Validation Matrix

## Purpose

Single source of truth for Phase 6 comprehensive validation of the Halloy-compatible theme system. Covers CSS generation, route delivery, preference persistence, registry integrity, diagnostics, and cross-browser viewport rendering. Every cell in the risk-weighted matrix below must be verified before release.

---

## Theme Representatives

Representative themes selected from the 48 bundled themes in `resources/themes/manifest.json` plus the emergency fallback:

| Category | Theme ID | Appearance | Rationale |
|----------|----------|------------|-----------|
| Configured default dark | `catppuccin-mocha` | dark | Most popular dark theme, default for system-mode dark |
| Configured default light | `catppuccin-latte` | light | Default for system-mode light |
| Very dark / high-contrast | `discord` | dark | Low background lightness, strong accent contrast |
| Low-saturation dark | `nord` | dark | Muted palette, tests low-chroma rendering |
| Bright light | `macaw-light` | light | Bright palette, tests light-mode accent visibility |
| Warm theme | `gruvbox` | dark | Warm amber/brown tones, tests non-cool palettes |
| High-chroma theme | `dracula` | dark | Saturated purple/pink/cyan, tests extreme chroma |
| Halloy built-in | `midnight` | dark | Provenance = Halloy built-in, tests built-in parser |
| Custom external theme | `__test_external__` | dark | Synthetic TOML file placed in custom directory |
| Emergency fallback | `__emergency__` | dark | Code-defined in `services/themes/emergency.py`, always present |
| Non-fatal diagnostics | `cyberpunk` | dark | Triggers contrast warnings (vivid bg vs text) |

---

## Page Representatives

All page families that must render correctly under every validated theme:

| # | Page Family | Route / Template | Notes |
|---|-------------|------------------|-------|
| P1 | Public home / feed | `GET /` → `templates/index.html` | Article cards, pagination, subscribe box |
| P2 | Topic / category page | `GET /topic/<slug>` → `templates/topic.html` | Filtered articles, topic icon |
| P3 | Tag page | `GET /tag/<slug>` → `templates/tag.html` | Tag-filtered feed |
| P4 | Search results | `GET /search?q=...` → via `templates/partials/search.html` | HTMX fragment + full page |
| P5 | Article detail | `GET /article/<slug>` → `templates/article.html` | Full article body, related articles, share macro |
| P6 | Newsletter subscribe | `GET /subscribe` → `templates/unsubscribe.html` | Minimal surface |
| P7 | Empty state | Admin partial `templates/admin/partials/empty_state.html` | No-data rendering |
| P8 | Application error 404 | `templates/errors/404.html` | Standalone error page |
| P9 | Application error 500 | `templates/errors/500.html` | Standalone error page |
| P10 | Application error 429 | `templates/errors/429.html` | Rate-limit error page |
| P11 | Offline | `templates/offline.html` | Service unavailable |
| P12 | Admin login | `GET /admin/login` → `templates/admin/login.html` | Unauthenticated |
| P13 | Admin 2FA setup | `GET /admin/2fa/setup` → `templates/admin/setup_2fa.html` | QR code + backup codes |
| P14 | Admin 2FA verify | `GET /admin/2fa/verify` → `templates/admin/verify_2fa.html` | Verification form |
| P15 | Admin dashboard | `GET /admin` → `templates/admin/dashboard.html` | Charts, metrics, cards |
| P16 | Admin articles list | `GET /admin/articles` → `templates/admin/articles.html` | Data-dense table, pagination |
| P17 | Admin article edit | `GET /admin/articles/<id>/edit` → `templates/admin/article_edit.html` | Form with textareas |
| P18 | Admin sources | `GET /admin/sources` → `templates/admin/sources.html` | Source management table |
| P19 | Admin newsletters | `GET /admin/newsletters` → `templates/admin/newsletters.html` | Newsletter list |
| P20 | Admin pipelines | `GET /admin/pipelines` → `templates/admin/pipelines.html` | Pipeline runs |
| P21 | Admin subscribers | `GET /admin/subscribers` → `templates/admin/subscribers.html` | Subscriber list |
| P22 | Admin webhooks | `GET /admin/webhooks` → `templates/admin/webhooks.html` | Webhook config |
| P23 | Admin review queue | `GET /admin/review` → `templates/admin/review.html` | Article review |
| P24 | Admin trend memory | `GET /admin/trend-memory` → `templates/admin/trend_memory.html` | Trend signals |
| P25 | Admin topic notes | `GET /admin/topic-notes` → `templates/admin/topic_notes.html` | Topic notes table |
| P26 | Admin metrics | `GET /admin/metrics` → `templates/admin/metrics.html` | Prometheus metrics |
| P27 | Admin API tokens | `GET /api-tokens/` | Token management |
| P28 | Admin shares | `GET /admin/shares` → `templates/admin/shares.html` | Share links |
| P29 | Share redirect | `GET /s/<code>` → `templates/share_redirect.html` | Public redirect page |
| P30 | Email verify | `GET /verify/<token>` → `templates/verify.html` | Standalone verification |
| P31 | Theme selector (open) | `templates/partials/theme_selector.html` | Popover with search + options |
| P32 | Theme CSS route | `GET /assets/themes/<theme_id>.css` | CSS asset delivery |
| P33 | Theme metadata API | `GET /api/v1/themes/metadata` | JSON endpoint |
| P34 | Theme diagnostics API | `GET /api/v1/themes/diagnostics` | Admin-only JSON |

---

## Viewports

| Name | Width | Height | Device Pixel Ratio | Notes |
|------|-------|--------|--------------------|-------|
| XS mobile | 320px | 568px | 1 | iPhone SE, oldest supported |
| Mobile standard | 375px | 812px | 2 | iPhone 13 mini / iPhone X |
| Tablet | 768px | 1024px | 1 | iPad portrait |
| Desktop | 1280px | 800px | 1 | Standard laptop |
| Wide desktop | 1920px | 1080px | 1 | Full HD monitor |

---

## State Dimensions

Every combination in the risk-weighted matrix must be tested across these state axes:

| State | Description | How to Set |
|-------|-------------|------------|
| System dark | `prefers-color-scheme: dark` + `"system"` preference | OS dark mode + localStorage `ainews-theme-preference-v2: "system"` |
| System light | `prefers-color-scheme: light` + `"system"` preference | OS light mode + `"system"` |
| Explicit dark | `"theme:catppuccin-mocha"` | Set preference directly |
| Explicit light | `"theme:catppuccin-latte"` | Set preference directly |
| Custom external | `"theme:__test_external__"` | Place synthetic TOML in custom dir, set preference |
| Migrated legacy `dark` | `"dark"` in legacy `ainews-theme` key | Set old key, delete new key |
| Migrated legacy `light` | `"light"` in legacy `ainews-theme` key | Set old key, delete new key |
| Invalid stored preference | `"theme:nonexistent-theme"` | Set preference to unknown ID |
| Removed theme | `"theme:dracula"` after dracula removed | Remove from manifest + rebuild |
| localStorage unavailable | Storage throws | Disable storage in browser devtools |
| CSS route 404 | `/assets/themes/<unknown>.css` | Request nonexistent theme ID |
| CSS route 503 | Theme CSS unavailable | Mock route to return 503 |
| Rapid switching | 10+ theme changes in <2 seconds | Programmatic `activate()` calls |
| Cross-tab sync | Preference changed in other tab | Fire `storage` event with new value |
| HTMX navigation | Fragment swap via HTMX | Navigate between pages with HTMX |
| Full-page navigation | Standard page load | Full browser navigation |

---

## Risk-Weighted Matrix

### Critical (must pass — blocks release)

| ID | Page | Viewport | Theme | State | What to Verify | Automation |
|----|------|----------|-------|-------|----------------|------------|
| C1 | P1 (home) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Cards render, text readable, no overflow | Manual screenshot |
| C2 | P1 (home) | Mobile 375px | `catppuccin-latte` | Explicit light | Cards render, text readable, no overflow | Manual screenshot |
| C3 | P1 (home) | Desktop 1280px | `catppuccin-mocha` | System dark | Theme applies on page load, no FOUC | `test_theme_preferences.py` |
| C4 | P1 (home) | Desktop 1280px | `catppuccin-latte` | System light | Theme applies on page load, no FOUC | `test_theme_preferences.py` |
| C5 | P12 (admin login) | Mobile 375px | `dracula` | Explicit dark | Login form renders, inputs visible | Manual screenshot |
| C6 | P15 (admin dashboard) | Desktop 1280px | `catppuccin-mocha` | System dark | Dashboard cards, charts render | Manual screenshot |
| C7 | P16 (admin articles) | Desktop 1280px | `nord` | Explicit dark | Table renders, all columns visible | Manual screenshot |
| C8 | P32 (CSS route) | N/A | `catppuccin-mocha` | Any | 200 OK, `text/css; charset=utf-8`, `Cache-Control` present | `test_theme_routes.py` |
| C9 | P32 (CSS route) | N/A | `unknown-id` | Any | 404 response | `test_theme_routes.py` |
| C10 | P33 (metadata API) | N/A | All | Any | 200 OK, valid JSON, `defaults.dark`/`defaults.light` keys | `test_theme_routes.py` |
| C11 | P31 (theme selector) | Desktop 1280px | `catppuccin-mocha` | Explicit dark | Popover opens, search works, keyboard nav | Manual screenshot |
| C12 | P5 (article detail) | Mobile 375px | `gruvbox` | Explicit dark | Article body readable, no horizontal scroll | Manual screenshot |
| C13 | P8 (404 error) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Error page renders with theme | Manual screenshot |
| C14 | P1 (home) | Desktop 1280px | `__emergency__` | Invalid stored preference | Emergency fallback renders, no crash | `test_theme_registry.py` |
| C15 | P1 (home) | Desktop 1280px | `catppuccin-mocha` | localStorage unavailable | Fallback CSS loads, no JS errors | Manual test |

### High (should pass — release risk if skipped)

| ID | Page | Viewport | Theme | State | What to Verify | Automation |
|----|------|----------|-------|-------|----------------|------------|
| H1 | P2 (topic) | Tablet 768px | `macaw-light` | Explicit light | Topic page renders, category badges visible | Manual screenshot |
| H3 | P3 (tag) | Mobile 375px | `catppuccin-latte` | System light | Tag page renders correctly | Manual screenshot |
| H4 | P4 (search) | Desktop 1280px | `nord` | Explicit dark | Search results render, highlight visible | Manual test |
| H5 | P5 (article) | Desktop 1280px | `dracula` | Explicit dark | Full article, related articles, share macro | Manual screenshot |
| H6 | P7 (empty state) | Desktop 1280px | `cyberpunk` | Explicit dark | Empty state message renders, no broken styling | Manual screenshot |
| H7 | P9 (500 error) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Error page renders | Manual screenshot |
| H8 | P10 (429 error) | Mobile 375px | `catppuccin-latte` | Explicit light | Rate-limit page renders | Manual screenshot |
| H9 | P11 (offline) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Offline page renders | Manual screenshot |
| H10 | P13 (2FA setup) | Desktop 1280px | `catppuccin-mocha` | System dark | QR code renders, backup codes styled | Manual screenshot |
| H11 | P14 (2FA verify) | Mobile 375px | `catppuccin-latte` | System light | Input field renders, button styled | Manual screenshot |
| H12 | P17 (article edit) | Desktop 1280px | `nord` | Explicit dark | Form fields, textareas render correctly | Manual screenshot |
| H13 | P18 (sources) | Desktop 1280px | `gruvbox` | Explicit dark | Source table, status badges render | Manual screenshot |
| H14 | P19 (newsletters) | Desktop 1280px | `catppuccin-mocha` | System dark | Newsletter list renders | Manual screenshot |
| H15 | P20 (pipelines) | Desktop 1280px | `catppuccin-mocha` | System dark | Pipeline runs render | Manual screenshot |
| H16 | P21 (subscribers) | Desktop 1280px | `macaw-light` | Explicit light | Subscriber table renders | Manual screenshot |
| H17 | P22 (webhooks) | Desktop 1280px | `catppuccin-mocha` | System dark | Webhook config renders | Manual screenshot |
| H18 | P23 (review queue) | Desktop 1280px | `nord` | Explicit dark | Review table renders | Manual screenshot |
| H19 | P24 (trend memory) | Desktop 1280px | `dracula` | Explicit dark | Trend signals render | Manual screenshot |
| H20 | P25 (topic notes) | Desktop 1280px | `catppuccin-mocha` | System dark | Notes table renders | Manual screenshot |
| H21 | P26 (metrics) | Desktop 1280px | `catppuccin-latte` | System light | Metrics page renders | Manual screenshot |
| H22 | P27 (API tokens) | Desktop 1280px | `catppuccin-mocha` | System dark | Token list renders | Manual screenshot |
| H23 | P28 (shares) | Desktop 1280px | `catppuccin-mocha` | System dark | Share list renders | Manual screenshot |
| H24 | P29 (share redirect) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Redirect page renders briefly | Manual screenshot |
| H25 | P30 (verify email) | Mobile 375px | `catppuccin-latte` | Explicit light | Verification page renders | Manual screenshot |
| H26 | P34 (diagnostics) | N/A | All | Any | Admin endpoint returns valid JSON with diagnostics | `test_theme_diagnostics.py` |
| H27 | P1 (home) | Desktop 1280px | `catppuccin-mocha` | Migrated legacy `dark` | Legacy preference migrated, correct theme applied | `test_theme_preferences.py` |
| H28 | P1 (home) | Desktop 1280px | `catppuccin-latte` | Migrated legacy `light` | Legacy preference migrated, correct theme applied | `test_theme_preferences.py` |
| H29 | P1 (home) | Desktop 1280px | Any | CSS route 503 | Fallback styling applied, no broken layout | Manual test |
| H30 | P1 (home) | Desktop 1280px | Any | Cross-tab sync | Preference updates across tabs | Manual test |
| H31 | P1 (home) | Desktop 1280px | Any | Rapid switching | No memory leaks, no FOUC, correct final theme | Manual test |
| H32 | P31 (theme selector) | Mobile 375px | `catppuccin-mocha` | Explicit dark | Bottom-sheet mode, touch targets ≥44px | Manual screenshot |

### Medium (nice to have — post-release follow-up)

| ID | Page | Viewport | Theme | State | What to Verify | Automation |
|----|------|----------|-------|-------|----------------|------------|
| M1 | P1 (home) | XS 320px | `catppuccin-mocha` | System dark | No horizontal overflow at smallest viewport | Manual screenshot |
| M2 | P1 (home) | Wide 1920px | `dracula` | Explicit dark | No excessive whitespace, content centers | Manual screenshot |
| M3 | P16 (articles) | Tablet 768px | `gruvbox` | Explicit dark | Table responsive, horizontal scroll if needed | Manual screenshot |
| M4 | P15 (dashboard) | Mobile 375px | `catppuccin-latte` | System light | Dashboard cards stack vertically | Manual screenshot |
| M5 | P31 (theme selector) | Tablet 768px | `nord` | Explicit dark | Popover positioning, search works | Manual screenshot |
| M6 | P6 (subscribe) | Mobile 375px | `catppuccin-latte` | Explicit light | Subscribe form renders | Manual screenshot |
| M7 | P12 (admin login) | Desktop 1280px | `__test_external__` | Custom external | External theme applied correctly | Manual screenshot |
| M8 | P1 (home) | Desktop 1280px | `midnight` | System dark | Halloy built-in theme renders correctly | Manual screenshot |
| M9 | P1 (home) | Desktop 1280px | `cyberpunk` | Explicit dark | Non-fatal contrast warnings logged but page renders | `test_theme_diagnostics.py` |
| M10 | P1 (home) | Mobile 375px | Any | HTMX navigation | Theme persists across fragment swaps | Manual test |
| M11 | P1 (home) | Desktop 1280px | Any | Full-page navigation | Theme persists across full navigations | `test_theme_preferences.py` |
| M12 | P33 (metadata API) | N/A | All | Any | Emergency themes excluded from metadata | `test_theme_routes.py` |

---

## Acceptance Criteria

1. **Matrix committed**: This file is versioned and updated as validation proceeds.
2. **Roadmap coverage**: Every Phase 6 definition-of-done item maps to at least one matrix cell (C/H/M) or an automated test.
3. **Critical pass rate**: 100% of Critical cells must pass before release.
4. **High pass rate**: ≥95% of High cells must pass before release; any failures documented with issue links.
5. **Manual step reproducibility**: Each manual-only step includes setup, expected result, and evidence requirements.
6. **Automated coverage**: ≥80% of matrix cells have corresponding automated test assertions.
7. **No regressions**: Existing test suites (`test_theme_*.py`) must remain green.

---

## Manual Validation Steps

### M-V1: Theme Selector Keyboard Navigation
1. **Setup**: Desktop 1280px, `catppuccin-mocha` active. Navigate to any public page. Click theme selector button.
2. **Expected**: Popover opens. Press ArrowDown to move through options. Press Enter to select. Press Escape to close. Focus ring visible on all focused elements.
3. **Evidence**: Screenshot of open popover with focus ring on selected item.

### M-V2: System Mode OS Preference Switch
1. **Setup**: Desktop 1280px, preference set to `"system"`. Start with OS dark mode.
2. **Expected**: Page renders with `catppuccin-mocha`. Switch OS to light mode. Page transitions to `catppuccin-latte` without page reload (via `matchMedia` listener).
3. **Evidence**: Two screenshots (dark, light) and console log showing no errors.

### M-V3: CSS Route Failure Fallback
1. **Setup**: Desktop 1280px, `catppuccin-mocha` active. Open DevTools Network tab. Block `/assets/themes/catppuccin-mocha.css`.
2. **Expected**: Page loads with fallback styling from `static/css/variables.css`. No unstyled content flash. Console shows one warning about stylesheet load failure.
3. **Evidence**: Screenshot of fallback styling + Network tab showing blocked request.

### M-V4: localStorage Unavailable
1. **Setup**: Desktop 1280px. Open DevTools → Application → Storage. Disable localStorage (or use `Object.defineProperty` override in console).
2. **Expected**: Page loads with fallback CSS. No JS errors in console. Theme selector may show limited functionality but page remains usable.
3. **Evidence**: Screenshot + console output showing no errors.

### M-V5: Invalid Stored Preference Recovery
1. **Setup**: Desktop 1280px. Open DevTools console. Run: `localStorage.setItem('ainews-theme-preference-v2', '"theme:nonexistent-xyz"')`. Reload page.
2. **Expected**: Page loads with configured default theme (`catppuccin-mocha` for dark OS, `catppuccin-latte` for light OS). Invalid preference cleared or ignored.
3. **Evidence**: Screenshot + localStorage dump showing preference handled.

### M-V6: Cross-Tab Preference Sync
1. **Setup**: Two browser tabs open to same origin. Both at Desktop 1280px.
2. **Expected**: In tab A, open theme selector and switch to `dracula`. Tab B updates within 1 second to `dracula` without reload.
3. **Evidence**: Side-by-side screenshots of both tabs after switch.

### M-V7: Rapid Theme Switching
1. **Setup**: Desktop 1280px, theme selector open. JavaScript console ready.
2. **Expected**: Run `for (const id of ['dracula','nord','catppuccin-latte','gruvbox','catppuccin-mocha']) { window.AinewsTheme?.activate(id); await new Promise(r => setTimeout(r, 100)); }`. Final theme should be `catppuccin-mocha`. No console errors. Stylesheet link count should be exactly 2 (app + palette).
3. **Evidence**: Console output + final DOM snapshot of `<link>` elements.

### M-V8: HTMX Fragment Navigation
1. **Setup**: Desktop 1280px, `dracula` active. Navigate to home page. Click a topic link that uses HTMX.
2. **Expected**: Fragment swaps in. Theme CSS link unchanged. All new content styled with `dracula` palette. No FOUC on fragment content.
3. **Evidence**: Screenshot of post-fragment page + Network tab showing fragment request.

### M-V9: Theme Selector Mobile Bottom-Sheet
1. **Setup**: Mobile 375px (Chrome DevTools device mode). Navigate to any page. Tap theme selector.
2. **Expected**: Bottom-sheet slides up. All theme options visible with scroll. Touch targets ≥44px height. Close button accessible.
3. **Evidence**: Screenshot of open bottom-sheet.

### M-V10: Cross-Browser Spot Check
1. **Setup**: Desktop 1280px. Test in Chrome, Firefox, and Safari (or WebKit nightly).
2. **Expected**: `catppuccin-mocha` renders identically across browsers. CSS custom properties resolve correctly. `@media (prefers-color-scheme)` works in all.
3. **Evidence**: Three screenshots (one per browser) side-by-side.

---

## Automated Test Coverage Map

| Matrix Cells | Test File | What It Covers |
|--------------|-----------|----------------|
| C3, C4, H27, H28, M11 | `tests/test_theme_preferences.py` | Preference read/write, migration, system mode, cross-tab (unit) |
| C8, C9, C10, H26, M12 | `tests/test_theme_routes.py` | CSS delivery (200/404/304), metadata API, diagnostics API |
| C14 | `tests/test_theme_registry.py` | Registry build, emergency theme presence, external theme inclusion |
| All bundled themes | `tests/test_theme_packaging.py` | Manifest validation, bundled file inclusion, loader integration |
| M9 | `tests/test_theme_diagnostics.py` | Diagnostic codes, contrast warnings, severity classification |
| All themes | `tests/test_theme_colors.py` | Hex parsing, contrast ratio calculation, WCAG thresholds |
| All themes | `tests/test_theme_halloy.py` | TOML parsing, field mapping, error handling for malformed input |
| All themes | `tests/test_theme_translate.py` | Halloy → AinewsTheme translation, field coverage |
| C8 | `tests/test_theme_css_contract.py` | CSS output structure, variable naming, alpha variants |
| CLI modes | `tests/test_theme_validation_cli.py` | `--bundled`, `--directory`, `--file`, `--strict`, `--format json` |

---

## Validation Execution Plan

### Phase 6a: Automated (Week 1)
1. Run full `test_theme_*.py` suite — all must pass.
2. Run `scripts/validate_themes.py --bundled --strict` — zero warnings.
3. Run `scripts/validate_release.sh --fast` — lint + smoke pass.

### Phase 6b: Manual Critical (Week 1)
1. Execute all Critical (C1–C15) manual steps.
2. Record evidence in `docs/theme-validation-evidence/` directory (screenshots, logs).
3. File issues for any failures.

### Phase 6c: Manual High (Week 2)
1. Execute all High (H1–H32) manual steps.
2. Focus on admin pages (H12–H23) and state transitions (H27–H31).
3. Record evidence.

### Phase 6d: Manual Medium + Cross-Browser (Week 2)
1. Execute Medium (M1–M12) steps.
2. Cross-browser spot check (M-V10).
3. Final sign-off: all Critical pass, ≥95% High pass, issues filed for Medium failures.

---

## Appendix: Synthetic External Theme for Testing

Create `tests/fixtures/themes/test-external.toml`:

```toml
[colors]
background = "#1a1a2e"
text = "#e0e0e0"
primary = "#e94560"
secondary = "#0f3460"
success = "#16c784"
danger = "#ea3943"
warning = "#f5a623"
info = "#4a90d9"

[colors.accent]
background = "#16213e"
text = "#e94560"

[colors.category]
ai = "#e94560"
ml = "#0f3460"
robotics = "#16c784"
```

This file validates the external theme loading path (`THEMES_CUSTOM_DIR`). It should be placed in a temp directory during tests and cleaned up after.

---

## Appendix: Emergency Theme Verification

The `__emergency__` theme is code-defined in `services/themes/emergency.py`. Verification:

1. `test_theme_registry.py` asserts `registry.get_exact("__emergency__")` returns a valid theme.
2. Invalid preference recovery (C14) verifies fallback to emergency when configured default fails.
3. Manual test: set preference to `"theme:__emergency__"` — CSS should render with hardcoded emergency palette.
