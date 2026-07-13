# Halloy Theme Phase 4 — Browser Preference Model and Theme Selector

## Goal

Replace the current binary dark/light browser state with a robust, versioned preference model supporting `system` mode and explicit bundled/custom Halloy themes. Add an accessible selector, preserve reader choice across full-page and HTMX navigation, migrate legacy preferences, and prevent a significant flash of the wrong palette.

This phase consumes the immutable registry and cacheable CSS route from earlier phases. Theme choice remains client-local and must not alter page-response cache keys.

## Preconditions

- Registry metadata can be exposed safely to templates.
- Every registered theme has a stable ID, display name, appearance, origin, and CSS URL.
- Configured default, default-dark, and default-light IDs resolve through the registry.
- The fallback static palette is complete.
- Theme CSS route supports exact lookup and caching.

## Workstream 1 — Define the preference schema

Replace ambiguous raw `dark`/`light` storage with a versioned contract. Recommended keys:

```text
ainews-theme-preference-v2
```

Recommended values:

```text
system
theme:<normalized-id>
```

A small JSON object is acceptable if needed:

```json
{"version":2,"mode":"theme","id":"catppuccin-mocha"}
```

Requirements:

- parsing is strict and bounded;
- unknown versions or malformed values fall back to `system`;
- no display names or URLs are trusted from storage;
- only registry IDs supplied by the server are activated;
- storage failure is non-fatal.

## Workstream 2 — Legacy migration

Migrate the current `ainews-theme` values:

- `dark` -> configured default dark theme;
- `light` -> configured default light theme;
- missing value -> `system`;
- any other old value -> `system`.

Migration should:

1. run once when the new key is absent;
2. validate the resolved target against server-provided registry metadata;
3. write the new preference where storage is available;
4. retain or remove the old key according to a documented compatibility policy;
5. never throw during early page initialization.

Keep migration support for at least one release compatibility period.

## Workstream 3 — Expose safe registry metadata to the document

The full document shell should expose only the data needed by the browser:

- theme ID;
- display name;
- appearance;
- origin (`bundled` or `custom`) if used for grouping;
- CSS URL;
- default/default-dark/default-light IDs.

Safe delivery options:

- a nonce-protected JSON `<script type="application/json">` block;
- escaped `data-*` attributes plus selector options;
- a same-origin metadata endpoint loaded after initial resolution.

For no-flash activation, the initial document must at least include default IDs and a safe mapping from known IDs to CSS URLs. Do not embed generated CSS or absolute filesystem paths.

Use standard JSON serialization, not manual string concatenation. Theme display names must be HTML-escaped in visible markup.

## Workstream 4 — Early no-flash bootstrap

Add a minimal script early in `<head>`, compliant with the existing CSP/nonce approach or served as a small external script.

It should:

1. read and migrate stored preference safely;
2. parse the server-provided registry map/defaults;
3. resolve the active ID;
4. for `system`, choose `default_dark` or `default_light` using `matchMedia`;
5. set `data-theme-id` and `data-theme-appearance` on `<html>`;
6. set or update the dedicated theme stylesheet link before normal app initialization;
7. fall back to static/default styling if anything fails;
8. avoid transitions during initial activation.

Recommended document hook:

```html
<link id="ainews-theme-stylesheet" rel="stylesheet" href="...">
```

The bootstrap should avoid duplicate stylesheet downloads. If initial server markup includes the resolved default stylesheet, update only when stored preference differs.

Do not block rendering on an asynchronous fetch for registry metadata.

## Workstream 5 — Stylesheet activation and failure recovery

Implement one central controller responsible for theme changes.

Required behavior:

- activate only known registry IDs;
- update the stylesheet link atomically;
- set document metadata attributes;
- update selector state;
- persist preference after successful selection;
- add a short theme transition only after initial page load and only when reduced motion is not requested;
- listen for stylesheet `error` events;
- on failure, resolve to configured default/emergency behavior and clear stale explicit preference;
- avoid infinite error/fallback loops.

Consider preloading the next stylesheet before switching to reduce flicker:

1. create temporary `<link rel="stylesheet">` with disabled/media strategy;
2. wait for load;
3. activate and remove old link;
4. persist state.

Keep implementation simple and cross-browser; correctness is more important than elaborate animation.

## Workstream 6 — Define system mode

System mode maps OS preference to two configured theme IDs; it does not dynamically alter an arbitrary selected theme.

Rules:

- when preference is `system`, use `matchMedia('(prefers-color-scheme: dark)')`;
- choose configured `default_dark` or `default_light`;
- listen for OS preference changes and switch themes while remaining in `system` mode;
- when preference is explicit, ignore OS changes;
- if one configured pair member is invalid, resolve through registry fallback and emit safe diagnostics;
- update selector to show `System`, not the currently resolved concrete theme, while optionally displaying the resolved theme in supporting text.

## Workstream 7 — Build the selector UI

Replace or augment the current binary toggle with an accessible theme selection surface.

Because the bundled theme set may be large, avoid an unwieldy navigation-bar `<select>` containing dozens of items unless visual testing proves it acceptable. Recommended options:

- compact button opening a dialog/popover with search;
- categorized native select on a settings/preferences panel;
- searchable listbox with robust keyboard behavior.

Prefer native controls where possible to reduce accessibility risk.

Required options/grouping:

```text
System
Built-in themes
Custom themes
```

Option metadata should include display name and optionally a `Light`/`Dark` label. Do not use color swatches as the sole indication of identity.

Selector requirements:

- explicit accessible label;
- keyboard operation;
- visible focus;
- selected state announced;
- usable at 320px width;
- no dependence on hover;
- works with long names and Unicode;
- selector remains reachable in mobile navigation;
- theme change does not unexpectedly navigate or submit unrelated forms.

## Workstream 8 — Preserve current controls and compatibility

The existing `.theme-toggle` hooks may be used elsewhere. Audit templates and scripts before removal.

Migration options:

- repurpose the current toggle button to open the selector;
- retain a quick-cycle button temporarily while adding the full selector;
- remove only after all templates/tests are updated.

Update ARIA labels, tooltip text, icons, and keyboard shortcuts. Avoid a sun/moon icon that falsely implies only two themes when explicit Halloy themes are available.

## Workstream 9 — HTMX lifecycle integration

The theme stylesheet and preference metadata belong to the full document shell, not HTMX fragments.

Verify:

- fragment responses do not include duplicate registry JSON or stylesheet links;
- feed pagination preserves active theme;
- topic/tag/search navigation preserves active theme;
- article expansion and related-content replacement preserve active theme;
- `htmx:afterSwap` does not need to reinitialize global theme state except for selector elements newly inserted by design;
- full-page cache and fragment cache remain theme-neutral.

If selector markup can appear in swapped fragments, use idempotent event delegation rather than duplicate listeners.

## Workstream 10 — Cross-tab synchronization

Optional but low-cost: listen for the browser `storage` event so changing theme in another tab updates the current tab.

Requirements:

- validate incoming preference;
- avoid writing it back and causing loops;
- fall back on removed/unknown theme IDs;
- update system-mode listener state correctly.

If omitted, document it as deferred; it should not block the core phase.

## Workstream 11 — Accessibility and browser preferences

Preserve:

- `prefers-reduced-motion`;
- `prefers-contrast`/forced-colors behavior;
- focus-visible indicators;
- readable selector state under every theme.

During theme switching:

- do not animate every property for long durations;
- do not animate when reduced motion is requested;
- avoid temporarily removing focus;
- keep current control labels accurate.

Use `data-theme-appearance` only for narrowly scoped behavior that cannot be expressed through semantic tokens. Avoid reintroducing full `[data-theme="light"]` palette definitions.

## Workstream 12 — Storage and privacy behavior

Theme preference is device/browser-local and contains no sensitive data. Document:

- localStorage key;
- local-only persistence;
- reset behavior;
- private-browsing/storage-disabled fallback.

Do not create server accounts, cookies, database rows, analytics identifiers, or cache variants solely for theme preference.

## Tests

Add JavaScript and route/template tests covering:

1. no stored preference -> system;
2. old `dark` migration;
3. old `light` migration;
4. malformed/unknown stored value;
5. localStorage read/write exceptions;
6. system dark resolution;
7. system light resolution;
8. OS change while in system mode;
9. OS change ignored for explicit theme;
10. explicit bundled selection;
11. explicit custom selection;
12. selected theme removed/unknown;
13. stylesheet load failure fallback;
14. no infinite fallback loop;
15. selector state and accessible label;
16. keyboard interaction where custom UI exists;
17. mobile selector presence;
18. HTMX swaps do not duplicate global resources/listeners;
19. full-page navigation preserves preference;
20. reduced-motion behavior;
21. server metadata JSON escaping for punctuation/Unicode;
22. no display name used as a CSS ID/path;
23. cross-tab storage event if implemented.

If no browser test runner exists, keep controller logic in pure functions where possible and test through a lightweight DOM harness or targeted Node tests. Add manual browser verification steps for remaining lifecycle behavior.

## Manual validation matrix

Test at least:

- default dark;
- default light;
- one dark high-chroma bundled theme;
- one light bundled theme;
- one custom external theme;
- invalid/removed theme preference.

Viewports:

```text
320px
375px
768px
1280px+
```

Flows:

- first visit;
- legacy preference migration;
- theme switch from feed;
- HTMX pagination;
- article detail/full navigation;
- mobile menu open/close;
- OS preference change in system mode;
- storage disabled.

## Validation commands

Run focused route/template and JavaScript tests plus:

```bash
.venv/bin/pytest tests/test_theme_preferences.py tests/test_routes.py -q
python scripts/build_assets.py js
.venv/bin/ruff check . --exclude .venv
.venv/bin/python scripts/build_critical_css.py --check
```

Run the full repository validation before handoff.

## Deliverables

- versioned preference model;
- legacy dark/light migration;
- server-provided safe theme metadata;
- early no-flash bootstrap;
- central stylesheet controller with failure recovery;
- system-mode light/dark pairing;
- accessible bundled/custom selector;
- HTMX-safe event lifecycle;
- updated bundled JavaScript assets and tests;
- reader-facing preference documentation hooks.

## Acceptance criteria

- Existing users with dark/light preferences retain equivalent appearance.
- New users default to system mode.
- Explicit Halloy selections persist locally and survive navigation.
- OS preference changes affect only system mode.
- Invalid or removed themes recover without breaking the page.
- No significant incorrect-theme flash occurs in normal cached operation.
- Selector is usable by keyboard, screen reader, and at 320px width.
- HTMX fragments remain theme-neutral and global listeners remain idempotent.
- Theme preference creates no server-side cache variants or user records.
