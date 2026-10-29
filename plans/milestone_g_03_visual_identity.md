# Milestone G3 — Visual Identity for a Technical AI Publication

## Purpose

Rebuild the public site's visual language so that it reads as a technical AI publication — dense, legible, provenance-forward — rather than as an unstyled debug page.

This phase is cosmetic by design and deliberately follows `plans/milestone_g_01_cascade_and_delivery.md` and `plans/milestone_g_02_interaction_and_accessibility.md`. Every visual change made before the cascade is correct is silently cancelled by the critical stylesheet's reset, and every measurement taken before the contrast and target-size work lands is invalidated by it.

## Current state

The site is structurally sound and typographically flat. The three structural defects account for the crudeness — cards with no padding, controls with no padding, headlines in link-blue, no spacing between entries. With those repaired, what remains is a set of genuine design decisions that are currently unconsidered:

- **No editorial hierarchy.** The card headline (`1rem`) and the card deck (`--text-lg`, 15–16px) are nearly the same size, so nothing dominates. `--text-xs` through `--text-xl` span only 11–17px — a total range of 6px for the whole site.
- **Monospace everywhere.** `--font-mono` is applied to the logo, nav, badges, metadata, buttons, the footer and the tagline. The intent is right — a technical publication leans on mono for metadata — but the execution makes every element read as the same kind of element.
- **Accent saturation.** The accent currently carries headlines (a G1 defect), links, the nav, the logo slash, the RSS icon and the subscribe button. Nothing reads as "the interactive part".
- **A single 900px column.** `--max-width: 900px` with one column, so a 1440px display wastes roughly a third of its width.
- **No product identity.** The site's distinguishing feature — that every article is produced by an autonomous pipeline — is reduced to a small `DONE` chip. The model, the quality score, the impact score and the degradation count are stored on every article and never surfaced.
- **Boxed-everything.** `feed-header`, `subscribe-box`, `top-impact`, `article-card`, `filter-btn`, `search-container` each draw their own border, producing four nested rectangles inside one another.

## Outcomes

At completion:

1. A four-tier editorial type hierarchy in which the headline is unmistakably the headline.
2. Mono restricted to metadata, badges and labels; sans for prose and headlines.
3. Accent used only for interactive and active states.
4. A two-column layout at ≥ 1024px with a left rail carrying live pipeline provenance.
5. A hairline-divided article list instead of boxed cards.
6. A single-row feed toolbar instead of four nested boxes.
7. `top stories` restructured as one lead plus two secondary items.
8. A designed dark surface ramp and a designed light surface ramp, replacing the borrowed GitHub fallback.
9. Pipeline provenance — stage, model, quality, impact — visible on every article.

---

# Workstream A — Type hierarchy

## A1. Extend the type scale

`static/css/variables.css:31-36` defines a 6px range. Extend it so that the scale has room for an editorial hierarchy. The existing token names and their meaning must be preserved, because the theme system and the component modules already consume them.

| Token | Current | Proposed | Role |
|---|---|---|---|
| `--text-xs` | 11–12px | 11–12px | badge, label, uppercase section rule |
| `--text-sm` | 12–13px | 12.5–13.5px | metadata row |
| `--text-md` | 14–15px | 14–15px | navigation, secondary UI |
| `--text-lg` | 15–16px | 16–17px | deck / summary |
| `--text-xl` | 16–17px | 18–20px | card headline |
| `--text-2xl` | — | 22–26px | lead-story headline, page title |
| `--text-3xl` | — | 28–34px | article headline on the detail page |

`--text-2xl` and `--text-3xl` are new tokens. The theme system does not need to emit them — they are structural type sizes, not palette tokens, and belong to the same family as `--font-sans` and `--radius-*`, which the theme system deliberately does not override (see `docs/halloy-theme-contract.md`).

## A2. Assign the hierarchy

| Element | Token | Weight | Line height |
|---|---|---|---|
| Card headline | `--text-xl` | 650 | 1.28 |
| Card deck | `--text-lg` | 400 | 1.55 |
| Card metadata | `--text-sm` | 400 | 1.4 |
| Badge / label | `--text-xs` | 600, `letter-spacing .05em`, uppercase | 1.2 |
| Lead-story headline | `--text-2xl` | 680 | 1.2 |
| Article detail headline | `--text-3xl` | 700 | 1.18 |

## A3. Separate the typefaces by function

Mono (`--font-mono`) for: metadata, badges, section labels, the pipeline provenance line, the keyboard hints, timestamps, model names, scores.
Sans (`--font-sans`) for: headlines, decks, body copy, button labels, form field text.

Currently `--font-mono` is applied to `.card-summary` and to the footer tagline. Move the summary to sans; keep the footer tagline in mono but drop it to `--text-xs` and reduce its prominence.

## A4. Add a regression test

- `tests/test_ui_static_contracts.py` — assert `--text-2xl` and `--text-3xl` exist and are used by the expected selectors; assert `.card-summary` does not use `--font-mono`.

---

# Workstream B — Accent discipline

## B1. Reserve the accent

The accent (`--accent`) is for interactive and active state only:

- links on hover, never link text at rest (body links use `--link`, which is currently the same token — consider whether `--link` and `--accent` should diverge);
- the active category filter;
- focus rings;
- the primary submit button;
- the logo slash.

It must **not** be used for:

- article headlines (currently a G1 defect that Workstream B of G1 removes);
- passive metadata;
- the RSS icon, which is a passive affordance — give it `--text-muted` at rest and `--text-primary` on hover.

## B2. Separate `--link` from `--accent`

`--link` and `--accent` are currently identical in the fallback palette. Once headlines stop using the accent, the link colour can be tuned independently for text contrast without affecting interactive chrome. G2 Workstream B already requires `--accent` to pass 4.5:1 on all surfaces; `--link` needs the same treatment.

## B3. Category colour discipline

Category badges use `--category-*` tokens, already distinct from the accent. Keep them: category identity is a legitimate second colour axis and reinforces scannability. Ensure the badge's own contrast passes, per G2.

---

# Workstream C — Layout

## C1. Two-column layout at wide viewports

Introduce a page grid above 1024px:

```
┌──────────────┬─────────────────────────────────────────┐
│  left rail   │  main column                             │
│  240px       │  680px                                   │
│              │                                          │
│  topics      │  top stories (lead + 2)                  │
│  pipeline    │  feed toolbar                            │
│  subscribe   │  article list                            │
└──────────────┴─────────────────────────────────────────┘
```

`--max-width` currently caps the container at 900px. Raise the page container to 1200px at ≥1024px and keep the single-column behaviour below that, where the current 900px cap already works.

The rail is new markup. `templates/base.html` and `templates/partials/feed.html` need a grid container, and the article detail route needs to decide whether it uses the rail or a wider single column. The recommendation is that the detail page uses a single wide column (760px) without the rail — the rail is a discovery surface, not a reading surface.

## C2. Replace the card treatment with hairline rows

`templates/partials/article_card.html` currently renders a bordered rounded box. Change it to a hairline-divided editorial row:

- no per-card border or background;
- a 1px bottom rule in `--border-light`;
- vertical rhythm of 1.5rem between entries;
- the 3px accent stripe moved from the card's left edge to a short leading marker that appears on hover and focus.

The card's `--bg-secondary` fill must be removed, which changes the reading rhythm: the page background becomes the surface and the rules do the separating.

## C3. Rebuild the feed toolbar as one row

`templates/partials/feed.html:7-45` currently stacks the search form, the filter bar, the sort select and the subscribe box inside a bordered `.feed-header`. Restructure to a single row:

```
[ search ................................ ] [ all | ai | privacy | security | programming | hardware ] [ sort ▾ ]
──────────────────────────────────────────────────────────────────────────────────────────────────────
```

- search on the left, flexible;
- category filter as a segmented control in the middle;
- sort on the right as a compact control;
- one hairline rule underneath;
- the subscribe box moves out of the toolbar and into the left rail.

The filter's current markup is a vertical stack of buttons; it must become a horizontal segmented control that wraps below 640px.

## C4. Restructure `top stories`

`templates/partials/top_impact.html` renders a uniform grid. Change to a lead-plus-secondary layout:

- the highest-`impact_score` story is the lead — larger headline, larger deck, optionally a thumbnail or source mark;
- the next two are secondary — smaller headline, no deck or a single-line deck;
- on mobile, the lead renders first and the secondaries stack below it.

This replaces the fixed three-column grid with an intrinsic layout that also resolves G1 Workstream G2.

## C5. Add a regression test

- `tests/test_ui_static_contracts.py` — assert the page container has a grid rule above 1024px and that the single-column rule still applies below it.

---

# Workstream D — Pipeline provenance

## D1. Why this matters

The product's entire premise is that an autonomous pipeline selects, researches, writes and edits each article. The data is already on every row:

| Field | Model | Use |
|---|---|---|
| `pipeline_status` | `models/article.py:25` | stage reached |
| `writer_model` | `models/article.py:31` | model that wrote the draft |
| `impact_score` | `models/article.py:32` | editorial ranking |
| `degradation_count` | `models/article.py:39` | how many times the pipeline fell back |
| `original_author` | `models/article.py:21` | the human source author |
| `summary` | `models/article.py:34` | the pipeline's own one-line take |

None of it reaches the reader except a `DONE` chip.

## D2. The metadata line

Replace the current metadata row with a two-tier structure:

```
Amazon swaps mega-event for October hardware drip, caps it with new Echo Dot
Amazon capped a month of rolling October launches with a small NYC event
showing new Echo hardware including a next-gen Echo Dot.

amazon  alexa  smart-home
The Verge · Jennifer Pattison Tuohy · 16 minutes ago · 4 min read
✦ condensed by agent · claude · impact 82 · quality 0.92
```

Rules:

- the **source line** is human provenance — original source, author, publication time, reading time;
- the **agent line** is machine provenance — the pipeline that produced it, rendered in mono at `--text-xs` in `--text-dim`;
- the agent line is visually subordinate: it must not compete with the source line for attention;
- `degradation_count > 0` adds a small marker, because a degraded pipeline run is a meaningful disclosure;
- the agent line must not be shown for articles that were not pipeline-produced (for example manually created entries), so the template must test for the presence of the fields rather than assume them.

Reading time requires a word count. Compute it in the template helper from `final_article` or `summary`; do not add a database column for a derived value.

## D3. The left rail

The rail carries the product's live state:

- **Pipeline status** — counts by `pipeline_status` for recent articles;
- **Topics** — the topic taxonomy with counts;
- **Impact leaders** — the highest `impact_score` articles;
- **Subscribe** — moved here from the feed toolbar.

This is real product surface, not decoration: it makes the autonomy legible.

## D4. Data access

The rail needs aggregate queries. Keep them in the service layer, not in the route:

- new module `services/feed_stats.py`, following the layering convention that services must not import from adapters and must not contain framework imports;
- the route assembles the view model and the template only renders it;
- aggregate queries must not run per article — one grouped query for the status counts, one for the topic counts.

Careful with the `joinedload`-on-collection pattern that caused G1 Workstream D. A grouped query that eagerly loads a collection will need `.unique()`; prefer `selectinload` for aggregates.

## D5. Add regression tests

- `tests/test_ui_static_contracts.py` — assert the agent metadata line renders when `writer_model` is present and is absent when it is not.
- `tests/test_feed_stats.py` — assert the aggregate service returns correct counts and does not trigger the `unique()` error.

---

# Workstream E — Surfaces and palette

## E1. Design the dark surface ramp

The fallback dark palette is borrowed from GitHub. Design a dedicated ramp with four deliberate steps plus a border ramp:

| Token | Role |
|---|---|
| `--bg-primary` | page background |
| `--bg-secondary` | raised surface — cards, panels |
| `--bg-tertiary` | hover and inset |
| `--bg-elevated` | overlays, popovers, the theme selector |

The current palette has `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-subtle` and `--bg-input`, where `--bg-subtle` and `--bg-tertiary` are the same value in the fallback. Consolidate to a four-step ramp with distinct values, and keep `--bg-subtle` and `--bg-input` as aliases of the appropriate step so existing consumers keep working.

The border ramp needs three steps — `--border` (default), `--border-light` (rules and dividers), `--border-focus` (focus) — with `--border` currently doing double duty as both a divider and a container edge.

## E2. Design the light surface ramp

The same treatment for light mode. The light palette has the additional problem that `--bg-secondary` (`#f6f8fa`) and `--bg-tertiary` (`#eaeef2`) are used as page and card surfaces interchangeably.

## E3. Theme compatibility

The ramp must be defined for the fallback in `static/css/variables.css` **and** be reachable by the theme system. `services/themes/translate.py` currently emits `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-subtle` and `--bg-input`. If `--bg-elevated` is introduced, it must be emitted by the translation layer as a derived value (for example `--bg-tertiary` or a lightened `--bg-secondary`) so themes remain valid, and `docs/halloy-theme-contract.md` must record the new token.

This is a theme-contract change. It must be a deliberate, documented addition — not a silent one.

## E4. Verify the theme contract still holds

- `scripts/validate_themes.py --bundled --strict` passes;
- the theme CSS route output remains a `:root`-only palette block;
- `tests/test_theme_package_validation.py` and `tests/test_theme_visual_validation.py` pass unchanged, or are updated in the same commit where the contract changes.

---

# Workstream F — Components

## F1. Buttons

Three button styles exist (`.subscribe-btn`, `.btn-primary`, `.btn-secondary`) with different geometry. Standardise on one geometry — 34px height, `--radius-md`, `--text-md` label, 12px horizontal padding — and express intent through colour, not size.

## F2. Badges and pills

`.category-badge`, `.pipeline-status`, `.tag-pill` and `.nav-tag` are four separate pill geometries. Consolidate to two: a category badge (filled, `--category-*` at 15% with a 40% border) and a tag pill (outlined, `--border`). The `DONE` chip becomes a pipeline-status badge using the same geometry as the category badge.

## F3. The search field

`templates/partials/feed.html:8-31` has three overlapping affordances inside the input — the `/` keyboard hint, the clear button and the spinner — and no dedicated space for any of them. Restructure:

- the input reserves right padding for the clear button and the spinner;
- the `/` hint moves outside the input, to the right of the field, as a separate element that hides once the field has focus;
- the clear button and the spinner occupy the same slot and swap, rather than stacking.

## F4. The share control

`templates/partials/share_macro.html` renders a 16×16 summary element. Give it a 24px minimum target and a visible resting state.

## F5. Focus visibility

`:focus-visible` is defined in `static/css/base.css:14-18` with a 3px `--accent` outline. After the G1 cascade repair this becomes the *only* visible focus indicator on most components, because the component hover rules were overriding the unlayered reset. Verify that every interactive element shows it clearly against its actual background.

---

# Acceptance criteria

- [ ] A four-tier editorial type hierarchy exists and is applied consistently.
- [ ] Mono is used only for metadata, badges and labels.
- [ ] The accent appears only on interactive and active states.
- [ ] The page uses a two-column layout at ≥ 1024px and a single column below.
- [ ] The article list uses hairline rules rather than boxed cards.
- [ ] The feed toolbar is a single row with one hairline rule.
- [ ] `top stories` renders as a lead plus two secondaries.
- [ ] Every article shows human provenance and, where applicable, agent provenance.
- [ ] The left rail shows live pipeline status, topics and impact leaders.
- [ ] The dark and light surface ramps are four distinct steps.
- [ ] Any new palette token is emitted by the theme translation layer and documented in `docs/halloy-theme-contract.md`.
- [ ] Buttons, badges and pills are geometrically consistent.
- [ ] Every interactive element shows a visible focus indicator.
- [ ] `scripts/validate_themes.py --bundled --strict` passes.
- [ ] The theme CSS route output remains `:root`-only.
- [ ] All existing theme tests pass.
- [ ] The full test suite passes; `ruff check` and `mypy` are clean.
- [ ] Screenshot comparison at 375, 768, 1280 and 1440 px shows the intended layout with no overflow.

# Risk and rollback

| Risk | Mitigation |
|---|---|
| The type-scale change reflows every page | Screenshot the six public page families before and after; the change is reversible in one commit |
| The layout grid breaks the article detail page | Give the detail page its own single-column container rather than the rail grid |
| The pipeline metadata queries slow the feed | Aggregate in one grouped query per rail section; cache the rail view model per request |
| Introducing `--bg-elevated` breaks third-party themes | The translation layer derives it, so themes that do not declare it still render; document in the theme contract |
| Mono removal makes the site look less "technical" | The technical character comes from density, metadata and provenance, not from setting every label in mono |

This phase is purely visual and carries no functional risk beyond layout regressions. It is intended to be split into several commits — type hierarchy, layout, components, provenance — each independently reviewable and revertable.
