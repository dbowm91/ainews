# Milestone G2 — Interaction and Accessibility Correctness

## Purpose

Restore the accessibility guarantees the codebase already claims but does not deliver, and close the measured contrast and target-size gaps that make the public site difficult to read and to operate.

This phase runs after `plans/milestone_g_01_cascade_and_delivery.md`. Every measurement in it depends on the cascade being correct — component spacing, text colours and target sizes all change once the G1 repairs land, so contrast and size findings taken before G1 would be wrong.

## Current state

### The theme validator does not check the tokens that fail

`services/themes/translate.py:67 classify_contrast_findings()` checks 14 pairings and treats *primary text vs primary background* as fatal. `services/themes/translate.py:153 classify_accessibility_findings()` checks category badges at 3:1 and status colours at 4.5:1.

Neither checks `--text-secondary`, `--text-muted` or `--accent` against the surfaces they are actually rendered on. Those are exactly the tokens that fail:

| Theme | Token | Foreground | Surface | Ratio | Required | |
|---|---|---|---|---|---|---|
| `catppuccin-latte` | `--text-secondary` | `#6c6f85` | `#e6e9ef` | **4.06** | 4.5 | FAIL |
| `catppuccin-latte` | `--text-muted` | `#8c8fa1` | `#e6e9ef` | **2.63** | 4.5 | FAIL |
| `catppuccin-latte` | `--text-muted` | `#8c8fa1` | `#eff1f5` | **2.83** | 4.5 | FAIL |
| `catppuccin-latte` | `--accent` | `#1e66f5` | `#e6e9ef` | **4.04** | 4.5 | FAIL |

The existing AAA advisory check reports hundreds of pairings but never fails a theme, because the fatal rule is limited to primary text.

### The shipped fallback palette has the same class of defect

`static/css/variables.css` light-mode block:

| Element | Token | Foreground | Surface | Ratio | Required | |
|---|---|---|---|---|---|---|
| `.card-summary` | `--text-muted` | `#6e7781` | `#f6f8fa` | **4.27** | 4.5 | FAIL |
| `.nav-links a` | `--text-muted` | `#6e7781` | `#f6f8fa` | **4.27** | 4.5 | FAIL |
| `.tag-pill` | `--accent` | `#0969da` | `#eaeef2` | **4.45** | 4.5 | FAIL |
| `.category-badge` (`.cat-ai`) | `--category-ai` | `#8250df` | composited `#e5def6` | **4.33** | 4.5 | FAIL |

The dark-mode fallback palette passes comfortably — `--text-muted` 5.62, `--text-dim` 8.75, `--accent` 6.85, `--green` 6.81, `--orange` 6.85, `--red` 5.16, `--purple` 6.86 on `#161b22`.

### Interaction defects

- The category filter declares `role="tablist"` / `role="tab"` on plain `<a href>` links with no tabpanel, no `aria-controls` and no arrow-key behaviour. Screen readers announce a tab widget that navigates.
- Interactive controls are 14–21px tall on pointer-fine devices. `static/css/layout.css:67` grants 44px targets only under `@media (pointer: coarse)`.
- `@media (prefers-reduced-motion: reduce)` was silently dropped by the G1 critical-CSS defect, removing the global animation safety net.
- `@media (prefers-contrast: high)` exists at `static/css/variables.css:319-333` but adjusts only four tokens, leaving text and accent colours untouched.

## Outcomes

At completion:

1. The theme validator checks secondary text, muted text and accent against the surfaces they render on, and reports failures through stable diagnostic codes.
2. The shipped fallback palette passes AA for every text token it defines in both light and dark modes.
3. Bundled themes that fail the new checks are either remediated or explicitly accepted under a documented policy.
4. Every interactive control is at least 24×24 CSS px on pointer-fine devices and 44×44 on coarse pointers.
5. The category filter exposes a correct navigation pattern with no ARIA role misuse.
6. Reduced-motion and high-contrast preferences are honoured for the whole public UI.
7. The nine minor defects are closed.

---

# Workstream A — Extend theme contrast validation

## A1. Define the new pairing matrix

`classify_contrast_findings()` currently checks 14 pairings. Extend it with the pairs the public UI actually renders, each against the surface it is used on:

| Pairing | Surfaces | Minimum |
|---|---|---|
| `--text-secondary` on page | `--bg-primary` | 4.5 |
| `--text-secondary` on surface | `--bg-secondary` | 4.5 |
| `--text-secondary` on elevated | `--bg-tertiary` | 4.5 |
| `--text-muted` on page | `--bg-primary` | 4.5 |
| `--text-muted` on surface | `--bg-secondary` | 4.5 |
| `--text-muted` on elevated | `--bg-tertiary` | 4.5 |
| `--accent` on page | `--bg-primary` | 4.5 |
| `--accent` on surface | `--bg-secondary` | 4.5 |
| `--accent` on elevated | `--bg-tertiary` | 4.5 |
| `--link` on page | `--bg-primary` | 4.5 |

These are rendered at 12–16px, so the 4.5:1 AA threshold applies. The existing category-badge and status-colour checks stay as they are.

## A2. Add stable diagnostic codes

Extend `THEME_DIAGNOSTIC_CODES` in `services/themes/errors.py:50` with codes that distinguish the new failure classes from the existing primary-text check. The existing codes are `THEME_CONTRAST_WARNING` and `THEME_CONTRAST_CRITICAL`. The new codes must be stable strings because they appear in CLI output, logs and the admin diagnostics endpoint:

- `THEME_CONTRAST_SECONDARY_AA` — secondary text below 4.5:1
- `THEME_CONTRAST_MUTED_AA` — muted text below 4.5:1
- `THEME_CONTRAST_ACCENT_AA` — accent/link below 4.5:1

`get_diagnostic_description()` must return a human-readable description for each.

## A3. Decide the severity policy

The current policy:

| Finding class | Default | `--strict` | `THEMES_STRICT_CONTRAST` |
|---|---|---|---|
| primary text < 4.5 | fatal | fatal | fatal |
| other pairings below AAA | advisory | advisory | advisory |

The new AA failures are a different class from the existing AAA advisories: they are real WCAG AA failures for text the public UI renders. The recommended policy:

| Finding class | Default | `--strict` | `THEMES_STRICT_CONTRAST` |
|---|---|---|---|
| primary text < 4.5 | fatal | fatal | fatal |
| **secondary / muted / accent < 4.5** | **advisory** | **fatal** | **fatal** |
| pairings below AAA | advisory | advisory | advisory |

Advisory by default avoids making every third-party Halloy port a startup failure; fatal under `--strict` so the release gate is meaningful. Add the new codes to `STRICT_PROMOTABLE_CODES` in `services/themes/errors.py` so `is_strict_promotable()` returns `True` for them.

Document the decision in `docs/halloy-theme-contract.md`, which already carries the strict-mode policy table.

## A4. Keep the helpers consistent

`is_fatal_diagnostic()`, `is_strict_promotable()` and `is_advisory_diagnostic()` in `services/themes/errors.py` must classify the new codes consistently with the table above. `scripts/validate_themes.py --strict` and the `THEMES_STRICT_CONTRAST` runtime flag must both honour it.

## A5. Add regression tests

Extend `tests/test_theme_accessibility_validation.py`:

- `test_secondary_text_contrast_reported` — a theme with a failing `--text-secondary` produces a `THEME_CONTRAST_SECONDARY_AA` diagnostic.
- `test_muted_text_contrast_reported` — likewise for `THEME_CONTRAST_MUTED_AA`.
- `test_accent_contrast_reported` — likewise for `THEME_CONTRAST_ACCENT_AA`.
- `test_new_codes_are_strict_promotable` — assert `is_strict_promotable()` is `True` for the new codes.
- `test_new_codes_are_advisory_by_default` — assert `is_fatal_diagnostic()` is `False` and `is_advisory_diagnostic()` is `True` outside strict mode.
- `test_passing_theme_produces_no_new_diagnostics` — a compliant theme produces none.

---

# Workstream B — Remediate the shipped fallback palette

## B1. Correct the light-mode tokens

`static/css/variables.css`, light-theme block. Candidate values, each computed against every light surface the token is used on:

| Token | Current | Candidate | On `#f6f8fa` | On `#ffffff` | On `#eaeef2` |
|---|---|---|---|---|---|
| `--text-muted` | `#6e7781` (4.27) | `#5d6875` | **5.33** | 5.67 | 4.86 |
| `--accent` | `#0969da` (4.45 on elevated) | `#0a5cc4` | 5.90 | — | **5.39** |

`--text-muted` and `--accent` must be re-checked against `--accent-hover`, `--link`, `--link-hover`, `--border-focus` and `--focus-ring`, and the alpha variants re-derived to match.

Note that `--text-muted` and `--text-secondary` must remain visually distinct. With `--text-secondary` at `#57606a` (6.0 on `#f6f8fa`) and `--text-muted` at `#5d6875` (5.33), the two remain separated but close. If the design requires a wider gap, `--text-muted` may be reserved for text at 14px bold or larger, and every 12px usage of `--text-muted` must move to `--text-secondary`. That decision belongs in Workstream D of `plans/milestone_g_03_visual_identity.md`; this workstream takes the conservative route of making `--text-muted` AA-compliant at every size.

## B2. Correct the category colours

`.cat-ai` renders `--category-ai` on a 15% alpha background, composited to `#e5def6` in light mode — 4.33 against a 4.5 requirement at 12px. Each of `--category-ai`, `--category-privacy`, `--category-security`, `--category-programming`, `--category-hardware` must be checked against its own composited background at the 15% and 40% alpha levels. The 40% alpha variant is used for the badge border, which is a non-text graphical element and is subject to 3:1 instead of 4.5:1.

## B3. Verify the dark-mode palette is unaffected

The dark palette already passes. Any change must not regress it — `--red` at 5.16 and `--text-muted` at 5.62 are the tightest.

## B4. Add regression tests

New test module `tests/test_palette_contrast.py`:

- A table-driven test that computes the WCAG ratio for every text token against every surface it is used on, in both light and dark modes, and asserts ≥ 4.5 for text and ≥ 3.0 for non-text graphics.
- The category badge test composites the alpha background before computing the ratio, and asserts both the 15% and 40% variants.

The compositing step matters: the earlier automated measurement reported a ratio of `1` for the badge because it compared the foreground against an uncomposited `rgba()` background. That check must composite over the parent surface.

---

# Workstream C — Remediate bundled themes

## C1. Measure the full bundled set

Run the extended validator across all 48 bundled themes and produce a table of failing pairings per theme. The `catppuccin-latte` failures above are representative, not exhaustive.

## C2. Decide per-theme remediation

Bundled themes are Halloy ports under `resources/themes/`. Two options:

1. **Adjust the TOML.** `catppuccin-latte`'s `--text-muted` `#8c8fa1` would need to darken to approximately `#5f6278` to reach 4.93 on `#e6e9ef` and 5.30 on `#eff1f5`. This changes the theme's appearance relative to upstream Catppuccin.
2. **Derive an accessible muted tone in the translation layer.** `services/themes/translate.py` already derives missing values and alpha colors. It could derive a contrast-safe `--text-muted` from `--text-secondary` and the theme's background when the declared value fails.

Recommendation: **option 2**, because it preserves fidelity to the upstream theme while guaranteeing the contract, and it applies automatically to externally-supplied themes that would otherwise ship unreadable muted text. The derivation must be deterministic, must be recorded in the theme's provenance, and must be visible in the admin diagnostics endpoint.

Whichever option is chosen, the manifest and `docs/themes-inventory.md` must record that the rendered palette differs from the source TOML.

## C3. Reconcile with the strict-mode CI job

`.github/workflows/ci.yml` runs `scripts/validate_themes.py --bundled --strict` in the `theme-validation` job. Under the new policy the strict mode promotes the new AA codes to fatal. Every bundled theme must therefore pass the extended matrix, or the job must be configured with an explicit, documented exclusion list — which is worse. The remediation in C2 exists so that no exclusion is needed.

## C4. Add regression tests

Extend `tests/test_theme_package_validation.py`:

- `test_all_bundled_themes_meet_aa_text_contrast` — every bundled theme passes the extended matrix.
- `test_derived_tokens_are_reported_in_provenance` — when a token is derived rather than declared, the provenance records it.

---

# Workstream D — Target sizes

## D1. Raise the pointer-fine floor

`static/css/layout.css:67` grants 44px minimums under `@media (pointer: coarse)`. Add a pointer-fine floor of at least 24×24 CSS px for interactive controls, which is the WCAG 2.2 "Target Size (Minimum)" threshold.

Current measured sizes at 1280px:

| Element | Size | Note |
|---|---|---|
| `button.subscribe-btn` | 59 × 14 | padding zeroed by the G1 cascade defect; restored to ≈24px by G1 alone |
| `select.sort-select` | 858 × 16 | needs explicit control styling |
| `summary.share-btn` | 16 × 16 | needs a minimum |
| `a.filter-btn` | 15–75 × 21 | restored by G1 to ≈24px |
| `a.tag-pill` | 35–68 × 21 | restored by G1 to ≈24px |
| `input.search-input` | 858 × 21 | restored by G1 to ≈33px |

Most of these are consequences of the G1 padding defect. After G1 lands, re-measure and fix only what remains. `summary.share-btn` and `select.sort-select` are expected to need explicit treatment.

## D2. Keep the coarse-pointer floor

The 44px floor under `@media (pointer: coarse)` must be preserved and must not be overridden by the new pointer-fine rule. Both media queries are mutually exclusive by definition, so no conflict arises, but the ordering must be explicit.

## D3. Add regression tests

- `tests/test_ui_static_contracts.py` — assert a pointer-fine minimum-target rule exists for the enumerated interactive selectors.

---

# Workstream E — Correct the category filter semantics

## E5.1 Replace the tab pattern

`templates/partials/feed.html:33-38`:

```html
<div id="category-filter" class="filter-bar" role="tablist" aria-label="Category filter">
  <a href="/" role="tab" aria-selected="{% if not category %}true{% else %}false{% endif %}" class="filter-btn {% if not category %}active{% endif %}">all</a>
```

These are navigation links. As `role="tab"` they promise a tab widget with no `tabpanel`, no `aria-controls` and no arrow-key navigation, and `aria-selected` is not a valid attribute on a link that navigates.

Recommended correction — present it as a navigation group with a selected item:

- replace `role="tablist"` / `role="tab"` / `aria-selected` with `role="navigation"` (or a `<nav>` element) and `aria-current="page"` on the active link;
- keep the visual active state driven by the existing `.filter-btn.active` class;
- keep the `aria-label` on the group.

If a true tab widget is wanted instead, it must filter content in place without navigating, expose a `tabpanel`, and support arrow-key movement — a larger change that conflicts with the current HTMX navigation model. The navigation-group correction is the right size for this defect.

## E5.2 Add regression tests

- `tests/test_ui_static_contracts.py` — assert the category filter does not use `role="tab"` or `aria-selected`, and that the active link carries `aria-current="page"`.
- `tests/test_routes.py` — assert the rendered category filter markup for an active category.

---

# Workstream F — Honour user preferences

## F1. Reduced motion

`@media (prefers-reduced-motion: reduce)` was dropped by the G1 critical-CSS defect. After G1 it returns, but the review must confirm the rule covers the whole public UI rather than only the two hover transforms that `articles.css` declares.

Audit every animation and transition in the public stylesheets: `fade-in-up` (`articles.css:113`), `pulse` (`layout.css:22`), `toast-slide-up` (`components.css:530`), the theme cross-fade (`critical.css`), and the scrollbar rules.

## F2. High contrast

`static/css/variables.css:319-333` adjusts only four tokens under `@media (prefers-contrast: high)`. Extend it to cover text and accent tokens, and verify the result passes AA with margin.

## F3. Add regression tests

- `tests/test_ui_static_contracts.py` — assert a `prefers-reduced-motion` block exists in the shipped critical CSS and covers the universal selector.
- `tests/test_palette_contrast.py` — assert the high-contrast override set includes text and accent tokens.

---

# Workstream G — Minor defects

| ID | Defect | Location | Correction |
|---|---|---|---|
| N1 | `.search-container` declared twice with identical declarations | `static/css/articles.css:836`, `static/css/articles.css:861` | Remove the duplicate |
| N2 | The `/` keyboard hint is clipped by the input edge and collides with the clear button and the spinner | `static/css/articles.css:841`, `templates/partials/feed.html:27-29` | Reserve space with input padding, or move the hint out of the input |
| N3 | `.search-clear` has no visible styling, so the control is invisible while occupying space | `templates/partials/feed.html:27` | Give it explicit dimensions and a visible resting state |
| N4 | The 3px accent stripe on a card is overlapped by the bookmark button | `static/css/articles.css:29` | Resolved by G1 restoring the card padding; confirm visually |
| N5 | `select.sort-select` renders as a raw full-width browser control | `templates/partials/feed.html:40` | Style it to match the other controls |
| N6 | The card title link's `aria-label` duplicates the visible headline, producing verbose announcements | `templates/partials/article_card.html:21` | Remove the redundant `aria-label`; the visible text is the accessible name |
| N7 | `templates/errors/404.html` renders no `<h1>` | `templates/errors/404.html` | Add a heading |
| N8 | The subscribe spinner is a permanent `…` glyph | `templates/partials/subscribe_box.html:28` | Resolved by G1 Workstream G |
| N9 | `static/js/bundle.min.js` is a 65KB generated artifact that no template loads | `static/js/bundle.min.js` | Confirm intent; if it is a packaging artifact, document it, otherwise stop shipping it |

## G.1 Add regression tests

- `tests/test_ui_static_contracts.py` — assert no duplicate selector blocks exist in the shipped CSS modules; assert the search hint and clear control have explicit geometry; assert `aria-label` is absent where it would duplicate the accessible name; assert the 404 template contains an `h1`.

---

# Acceptance criteria

- [ ] `classify_contrast_findings()` checks secondary text, muted text and accent against their rendered surfaces.
- [ ] The new diagnostic codes are registered in `THEME_DIAGNOSTIC_CODES` with descriptions.
- [ ] The new codes are strict-promotable and advisory by default, and the policy is documented.
- [ ] The shipped fallback palette passes AA in both light and dark modes.
- [ ] All bundled themes pass the extended matrix, or the deviation is documented and intentional.
- [ ] Every interactive control is ≥ 24×24 on pointer-fine devices and ≥ 44×44 on coarse pointers.
- [ ] The category filter uses no ARIA tab roles and marks the active link with `aria-current`.
- [ ] `prefers-reduced-motion` and `prefers-contrast` are honoured across the public UI.
- [ ] All nine minor defects are closed.
- [ ] The new tests pass and the full suite is green.
- [ ] `ruff check` and `mypy` are clean.

# Risk and rollback

| Risk | Mitigation |
|---|---|
| Tightening contrast changes the look of every bundled theme | The derivation in Workstream C is deterministic and recorded; the inventory documents the difference from source |
| Making new AA findings strict-promotable fails the CI theme job | Run the extended validator across all 48 themes before flipping the policy; sequence the CI change after the theme remediation |
| Raising target sizes alters dense layouts | Apply the floor to the smallest set of selectors that actually fail, and re-measure after G1 |
| Replacing the tab roles affects assistive-technology behaviour | Verify with the accessibility assertions in `tests/test_theme_accessibility_validation.py` |
| Changing `--text-muted` affects both themes and the fallback | The fallback and the theme system read the same token names, so a single change applies to both |

Each workstream is independently revertable. No schema, configuration or data change is required.
