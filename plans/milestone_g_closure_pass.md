# Milestone G Closure Pass — Frontend Rendering Verification and Closure

## Purpose

Verify that Milestone G is complete, produce the inspectable closure record, and leave the repository in a state where the same class of defect cannot silently return.

Milestone G addresses defects that every existing test suite passed. The closure pass therefore has two jobs: prove the specific repairs hold, and close the *meta* gap — the absence of assertions that observe rendered output rather than generated text.

## Current state

The repository carries 685+ theme tests, 16 theme test files and 14 Playwright browser smoke tests. Every defect in Milestone G passed all of them, because:

| Defect | Why the existing suite passed it |
|---|---|
| Theme palette inert | Tests assert the *text* of the generated CSS and the presence of a `<link>`; none observed the computed palette |
| Component spacing zeroed | No test computed a component's padding or margin |
| Mobile overflow | The browser smoke tests exercised theme switching at one viewport; none asserted `scrollWidth <= clientWidth` |
| Critical CSS malformed | No test compared brace counts or parsed rule counts |
| Article page 500 | The route was not exercised with a warm related-article cache |
| Error pages returning JSON | No test sent a browser-like `Accept` header |
| Service worker scope rejected | The console-error guard explicitly whitelisted it as benign |

The last row is the clearest signal: `tests/test_theme_browser_smoke.py:159-162` lists the service worker scope error among `BENIGN_CONSOLE_ERRORS`. The defect was known, tolerated and documented as harmless.

## Outcomes

At completion:

1. Every Milestone G requirement has a closure-matrix row with implementation and evidence.
2. The browser-level assertions exist and run in CI.
3. The build-time assertions exist and run on every build.
4. The benign-console-error whitelist is empty of real defects.
5. `docs/frontend-rendering-closure.md` exists as the closure record.
6. `docs/frontend.md`, `docs/halloy-theme-contract.md` and `AGENTS.md` reflect the repaired invariants.
7. The closure record states plainly which defects were previously invisible to the test suite.

---

# Workstream A — Build-time assertions

These run without a browser and must fail the build.

| Assertion | Location | Covers |
|---|---|---|
| Generated critical CSS is brace-balanced | `scripts/build_critical_css.py` | G1 A3 |
| Generated critical CSS rule count equals source rule count | `scripts/build_critical_css.py` | G1 A3 |
| Committed critical partial matches a fresh generation | `tests/test_critical_css_build.py` | G1 A4 |
| Critical CSS contains the mobile media block and the reduced-motion block | `tests/test_critical_css_build.py` | G1 A3 |
| Critical CSS defines no palette tokens | `tests/test_theme_precedence.py` | G1 C5 |
| Palette tokens are defined in exactly one shipped source | `tests/test_theme_precedence.py` | G1 C5 |
| Theme stylesheet follows the sheet carrying the fallback palette | `tests/test_theme_precedence.py` | G1 C5 |
| The inline critical sheet is layered, or contains no rules | `tests/test_cascade_layers.py` | G1 B5 |
| The `*` reset appears in exactly one shipped source | `tests/test_cascade_layers.py` | G1 B5 |
| No duplicate selector blocks across the shipped CSS modules | `tests/test_ui_static_contracts.py` | G2 N1 |
| The category filter uses no ARIA tab roles | `tests/test_ui_static_contracts.py` | G2 E |
| The spinner animation does not target `opacity` | `tests/test_ui_static_contracts.py` | G1 G1 |
| `.top-impact-grid` uses an intrinsic track | `tests/test_ui_static_contracts.py` | G1 G2 |

---

# Workstream B — Browser assertions

These require Chromium and run in the `frontend-rendering` CI job.

| Assertion | Covers |
|---|---|
| `/article/<id>` returns `200` and renders the headline | G1 D |
| The article page returns `200` on the cache-hit path | G1 D2 |
| `--bg-primary` changes when the theme changes, and equals the declared value | G1 C4 |
| `.article-card` padding and margin are non-zero and match the authored values | G1 B4 |
| `.card-title a` computes to `--text-primary`, not `--accent` | G1 B4 |
| `scrollWidth <= clientWidth` at 375, 390, 768, 1280, 1440 px | G1 B5 |
| The mobile navigation toggle is visible and collapses the links at 390 px | G1 B5 |
| A browser navigation to an unknown path returns the styled HTML error page | G1 E |
| The service worker registers without a console error | G1 F |
| No HTMX indicator is visible at rest | G1 G1 |
| The `top stories` panel contains no empty column | G1 G2 |
| Every text token passes AA against the surface it renders on, in both modes | G2 B |
| Every interactive control meets the minimum target size | G2 D |
| The rendered page produces no unexpected console errors | G1 F3 |

The harness in `tests/test_theme_browser_smoke.py` already provides the background server, the viewport override and the console-error guard. The new module `tests/test_frontend_rendering_browser.py` should reuse it rather than build a second one.

---

# Workstream C — Close the benign-error whitelist

`tests/test_theme_browser_smoke.py:159-162` currently whitelists:

- the service worker scope error;
- the `variables.css` MIME-type error.

Both are defects, not noise. The scope error is closed by G1 Workstream F. The MIME-type error must be diagnosed during G1: it is not yet explained by the review, and it must be resolved or explicitly characterised before the whitelist entry is removed.

The whitelist must end this milestone with no entries that correspond to an unresolved defect. Entries for genuinely benign third-party noise may remain, but each must carry a one-line justification.

---

# Workstream D — Documentation reconciliation

| Document | Change |
|---|---|
| `docs/frontend.md` | Document the cascade-layer invariant, the single-source rule for the palette, the critical-CSS build assertion, and the new browser test module. Update the asset rebuild section to note that `scripts/build_critical_css.py` now fails on unbalanced output. |
| `docs/halloy-theme-contract.md` | Record the new contrast pairings, the new diagnostic codes, the strict-mode policy change, and any new palette token introduced by G3. |
| `docs/themes-inventory.md` | Record any bundled theme whose rendered palette differs from its source TOML because of the G2 derivation. |
| `AGENTS.md` | Add the cascade-layer invariant to the "Known Issues & Gotchas" section: the critical stylesheet must be layered, the palette must be defined in exactly one place, and the theme stylesheet must load after it. Also record the `joinedload`-on-collection `.unique()` requirement and the theme-precedence ordering rule. |
| `docs/frontend-rendering-closure.md` | New closure record — see Workstream E. |

---

# Workstream E — Closure record

Produce `docs/frontend-rendering-closure.md` following the established closure-matrix format used by `docs/config-cli-roadmap-closure.md`.

## Status definitions

| Status | Meaning |
|--------|---------|
| **complete** | Requirement is implemented, tested, documented, and verified against the codebase |
| **accepted limitation** | Requirement is implemented with a documented scope reduction that does not affect the supported operating model |
| **deferred** | Requirement is explicitly out of scope for the current release train |
| **failed** | Requirement was attempted but does not meet acceptance criteria |

## Required sections

1. **Scope** — the pages, endpoints and assets covered, and the date.
2. **Status definitions** — the table above.
3. **G1 — Cascade and delivery correctness** — one subsection per workstream (A–H).
4. **G2 — Interaction and accessibility correctness** — one subsection per workstream (A–G).
5. **G3 — Visual identity** — one subsection per workstream (A–F).
6. **Defect register** — every finding from `docs/ui-review-2026-10.md`, its severity, its status and the evidence that closed it.
7. **Previously invisible defects** — the table from the Current state section above, retained so a future reader can see what the test suite failed to catch and why.
8. **Residual risk** — anything accepted rather than fixed.

Each subsection uses the standard field table:

| Field | Detail |
|-------|--------|
| Requirement | … |
| Status | **complete** |
| Implementation | `<path:line>` — `<symbol>` |
| Unit evidence | `<test module>` — N tests (…) |
| Integration evidence | `<test module>` — N tests (…) |
| Failure-path evidence | Tests cover … |
| Documentation | `<doc path>` |
| Notes | … |

---

# Workstream F — Release gate

Extend the release checklist so that a frontend change cannot ship without the rendering assertions.

`scripts/validate_release.sh` already integrates `scripts/validate_themes.py`. Add:

- the critical-CSS build assertion;
- the build-time assertion modules;
- a note that the browser assertions require Chromium and are gated by the `frontend-rendering` CI job.

The browser assertions must not be added to `scripts/validate_release.sh` unconditionally — they need a browser binary and a running server. The CI job is the correct gate for them, with the release script asserting that the job exists and passed.

---

# Acceptance criteria

- [ ] Every defect from `docs/ui-review-2026-10.md` appears in the defect register with a terminal status.
- [ ] Every Milestone G requirement has a closure-matrix row with implementation and evidence.
- [ ] The build-time assertions fail the build when their defect is reintroduced.
- [ ] The browser assertions fail when their defect is reintroduced.
- [ ] `tests/test_theme_browser_smoke.py` benign-error whitelist contains no unresolved defect.
- [ ] The `variables.css` MIME-type console error is diagnosed and resolved or characterised.
- [ ] `docs/frontend-rendering-closure.md` exists with all required sections.
- [ ] `docs/frontend.md`, `docs/halloy-theme-contract.md`, `docs/themes-inventory.md` and `AGENTS.md` are updated.
- [ ] `scripts/validate_release.sh` includes the frontend assertions.
- [ ] The `frontend-rendering` CI job is green.
- [ ] The full test suite passes; `ruff check` and `mypy` are clean.

# Closure verdict

The milestone is closed when, for every defect in the register:

1. the repair is merged;
2. a regression test exists that fails without the repair;
3. the test is wired into CI, not only into a local run;
4. the documentation states the invariant that prevents recurrence.

A defect closed with a test that is not wired into CI is **not** closed. That distinction is the point of this milestone: the original defects were not undetected because the tests were weak, but because the tests asserted the wrong thing.

# Deferred items

| Item | Reason | Revisit when |
|---|---|---|
| Admin interface redesign | Out of scope for the public-site milestone; the admin templates share the cascade repair but have their own layout | A separate milestone |
| Per-user server-side theme persistence | The browser-local preference model is the intended design | If multi-device sync becomes a requirement |
| Real-time pipeline status in the left rail | Requires a push channel or polling | When the feed volume justifies it |
| Live theme reload without restart | The current semantics are documented as restart-based | If custom themes become commonly edited |
| `static/js/bundle.min.js` disposition | Needs confirmation of its packaging purpose | Before the next release |
