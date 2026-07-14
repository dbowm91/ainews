# Theme Subsystem — Release Hardening and Closure

Phase 7 completion record for the Halloy-compatible theme system. Covers performance measurements, HTTP caching policy, configuration hardening, artifact verification, rollout/rollback, and roadmap closure.

---

## 1. Performance Measurements

### Environment

- Python 3.12, SQLite WAL, single-process Flask dev server
- 48 bundled themes + 1 emergency fallback
- No external custom themes during measurement
- Cold filesystem (first load after process start)

### Startup Measurements

| Metric | Value |
|--------|-------|
| Bundle load (resource discovery) | 2.1 ms |
| Registry build (parse + translate + CSS) | 33.5 ms |
| **Total startup** | **35.5 ms** |
| Warm rebuild (subsequent, no I/O) | 30.7 ms avg |

Registry construction is dominated by TOML parsing and CSS serialization for 48 themes. The 35 ms total is a negligible fraction of overall application startup (which includes database migrations, Celery connection, and Redis warmup).

### Memory Measurements

| Metric | Value |
|--------|-------|
| Registry object (str repr) | ~276 KB |
| Total generated CSS (all themes) | 158,107 bytes |
| Average CSS per theme | 3,293 bytes |
| CSS range (min–max) | 3,175–3,246 bytes |
| Metadata payload (JSON) | 6,071 bytes |

The registry is frozen (`MappingProxyType`) and immutable during the process lifetime. No unbounded growth occurs across requests because themes are parsed once at startup and CSS is pre-computed.

### HTTP Measurements

| Metric | Value |
|--------|-------|
| CSS route response (avg theme) | ~3.3 KB uncompressed |
| CSS route response (all themes) | ~155 KB total |
| Metadata endpoint response | ~6 KB |
| Cache-Control (CSS) | `public, max-age=300` |
| Cache-Control (metadata) | `public, max-age=60` |
| ETag | SHA-256 content digest (16 hex chars) |

### Threshold Policy

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Registry construction | < 100 ms | Must be small fraction of total startup |
| Total CSS output | < 200 KB | Comfortably under 1 MB limit |
| Metadata payload | < 10 KB | Stays compact for embedded JSON |
| Per-theme CSS | < 5 KB | Compact, independently cacheable |
| Layout shift (CLS) | 0 | Palette CSS overrides variables only; no structural changes |
| TOML re-parsing | None | Registry is process-lifetime immutable |

### Acceptance Criteria

- [x] Measurements documented with environment
- [x] No normal request reparses theme files
- [x] No unbounded memory growth across requests
- [x] Registry construction < 100 ms threshold

---

## 2. HTTP Caching and Conditional Request Policy

### Theme CSS Route (`/assets/themes/<theme_id>.css`)

| Property | Value |
|----------|-------|
| Content-Type | `text/css; charset=utf-8` |
| X-Content-Type-Options | `nosniff` |
| Cache-Control | `public, max-age=300` |
| ETag | SHA-256 content digest (strong — `set_etag()` without `weak=True`) |
| 304 handling | Werkzeug `response.make_conditional(request)` |
| 404 for unknown IDs | Controlled 404 (not fallback) |
| 503 when unavailable | Controlled 503 JSON error |

**Cache policy decision:** The current `max-age=300` (5 minutes) with ETag-based conditional requests is the simplest policy consistent with deployment and restart semantics. Rationale:

- Themes are immutable during a process lifetime, so longer cache times would be safe for bundled themes.
- However, operators may replace custom themes and restart, so 5 minutes provides a reasonable balance.
- ETag ensures conditional requests return 304 when content hasn't changed, avoiding redundant transfers.
- Fingerprinted URLs (`/assets/themes/<id>.css?v=<hash>`) were deferred — the ETag approach is standards-compliant and simpler.

### Metadata Endpoint (`/api/v1/themes/metadata`)

| Property | Value |
|----------|-------|
| Content-Type | `application/json; charset=utf-8` |
| Cache-Control | `public, max-age=60` |
| Auth | None required (public) |
| Emergency themes | Excluded from response |

Stale metadata cannot cause persistent breakage because CSS load failures trigger automatic fallback to the default theme in the browser controller.

### Reverse-Proxy Behavior

The CSS route is public and user-independent — no cookie or session dependence in cache keys. Theme CSS responses are identical for all users selecting the same theme, so CDN/proxy caching is safe. After a restart with new themes, the 5-minute max-age ensures stale CSS expires quickly; operators may also purge proxy cache explicitly.

### Acceptance Criteria

- [x] HTTP semantics are standards-compliant (RFC 7232 conditional requests)
- [x] Cache policy documented and tested
- [x] Theme CSS is public and user-independent
- [x] No page HTML cache is fragmented by theme choice

---

## 3. Configuration and Operational Hardening

### Configuration Variables

| Variable | Default | Validated | Description |
|----------|---------|-----------|-------------|
| `THEMES_ENABLED` | `true` | No (bool parse) | Enable/disable theme system |
| `THEMES_CUSTOM_DIR` | `""` | No | External theme directory path |
| `THEMES_ALLOW_CUSTOM` | `true` | No (bool parse) | Allow external themes |
| `THEMES_DEFAULT` | `""` | No | Fallback ID before per-appearance defaults |
| `THEMES_DEFAULT_DARK` | `catppuccin-mocha` | No (runtime fallback) | Default dark theme |
| `THEMES_DEFAULT_LIGHT` | `catppuccin-latte` | No (runtime fallback) | Default light theme |
| `THEMES_MAX_FILE_BYTES` | `262144` | Yes (1024–1048576) | Per-file byte limit for external themes |
| `THEMES_STRICT_CONTRAST` | `false` | No | Treat contrast warnings as errors |

### Misconfiguration Policy

| Condition | Behavior | Severity |
|-----------|----------|----------|
| `THEMES_MAX_FILE_BYTES` out of range | Blocks production startup | Fatal |
| `THEMES_CUSTOM_DIR` set but `THEMES_ALLOW_CUSTOM=false` | Warning; directory ignored | Warning |
| Invalid default theme ID | Falls back through chain; logged | Warning |
| All themes fail to parse | Emergency fallback remains usable | Warning |
| Theme system disabled | Only emergency theme available | Info |

### Startup Logging

The theme subsystem logs:

- Per-theme diagnostics (errors, warnings, info) with diagnostic codes
- Total theme count (bundled/external, excluding emergency)
- Configured default dark and light IDs
- Emergency fallback activation
- Bundle-loading diagnostics
- Registry build diagnostics (errors/warnings counts)

Logs never include: raw theme contents, unredacted filesystem paths, or per-request noise.

### Diagnostics Endpoint

`GET /api/v1/themes/diagnostics` (admin-authenticated) returns:

- Registry health (theme counts by origin, defaults, emergency status, `built_at`)
- Per-theme validity, issue count, warning codes, content digest
- Aggregate diagnostic counts and code distribution
- Override provenance tracking

Fields are unambiguous: `emergency_fallback_active` means the emergency theme is present in the registry (always true), not that it was selected as the active default.

### Operational Refresh Policy

- **Theme changes require restart.** The registry is immutable during a process lifetime.
- **Validate before restart:** Run `python scripts/validate_themes.py --bundled` to check all themes parse correctly.
- **Roll back a broken custom theme:** Remove the file from `THEMES_CUSTOM_DIR` and restart. The theme system falls back to bundled defaults.
- **Browser cache behavior after restart:** CSS ETags change when content changes. Within 5 minutes (max-age), browsers may still serve cached CSS. Use hard refresh (`Ctrl+Shift+R`) or wait for expiry.
- **Remove an override:** Delete the external file and restart. The bundled version resumes.
- **Stale browser preferences:** If a selected theme ID is no longer in the registry, the browser controller falls back to the configured default automatically.
- **No live reload** is provided in this phase.

### Acceptance Criteria

- [x] Production misconfiguration behavior is deterministic
- [x] Logs and diagnostics agree
- [x] Operators have a tested restart and rollback procedure

---

## 4. Artifact and Release Packaging Verification

### Repository Source Distribution

- `resources/themes/manifest.json` — 48 entries, all verified present
- `resources/themes/__init__.py` — package marker present
- All 48 `.toml` files present and matched by manifest entries
- No extra `.toml` files outside manifest
- `.dockerignore` excludes uncommitted root `themes/` directory but includes `resources/themes/`

### Docker Image

The Dockerfile (`COPY --from=builder /app /app`) copies the entire application directory into the runtime image, which includes:

- `resources/themes/manifest.json`
- All 48 bundled `.toml` files
- `resources/themes/__init__.py` package marker
- `scripts/validate_themes.py` and dependencies
- Documentation (`README.md` is included via `!README.md` in `.dockerignore`)

### Reproducibility

- [x] Manifest entries correspond exactly to packaged files (verified programmatically)
- [x] No unapproved root-level import directory included
- [x] No duplicate obsolete theme directory (`themes/` excluded by `.dockerignore`)
- [x] Image build uses `COPY . .` (no uncommitted local file dependency)
- [x] `.dockerignore` does not exclude `resources/themes/`
- [x] `validate_themes.py --bundled` passes (0 errors, 644 documented contrast warnings)

### External Theme Deployment

External themes are deployed via read-only volume mount:

```yaml
# docker-compose.yml addition for custom themes
volumes:
  - /path/to/themes:/app/custom-themes:ro
environment:
  - THEMES_CUSTOM_DIR=/app/custom-themes
  - THEMES_ALLOW_CUSTOM=true
```

- **Read-only mounts** (`:ro`) are fully supported — the theme system never writes to the custom directory.
- **Ownership:** Files must be readable by the application user (UID 1000 in Dockerfile).
- **Missing directory:** Produces `themes.custom_dir.missing` diagnostic; no external themes loaded; bundled themes unaffected.
- **Invalid files:** Logged as diagnostics; processing continues with remaining files.
- **Override behavior:** External themes with the same normalized ID replace bundled themes wholesale.
- **Restart required:** Changes take effect only after process restart.
- **Backup responsibility:** Operator-managed; no server-side persistence of theme preferences.

### Acceptance Criteria

- [x] Final release artifact contains the intended theme set
- [x] Artifact verification is blocking in release validation
- [x] Custom-theme deployment works from documented read-only storage

---

## 5. Rollout and Rollback Plan

### Rollout Sequence

1. Deploy with bundled themes and custom themes disabled or absent
2. Verify defaults, metadata endpoint, CSS route, and browser activation
3. Enable documented external directory if used
4. Validate operator-provided themes before deployment
5. Monitor startup logs, diagnostics, CSS 404/503 rates, and frontend errors

### Rollback Procedure

1. **Disable custom theme directory:** Set `THEMES_ALLOW_CUSTOM=false` or clear `THEMES_CUSTOM_DIR`
2. **Restore configured bundled defaults:** Ensure `THEMES_DEFAULT_DARK` and `THEMES_DEFAULT_LIGHT` reference valid bundled IDs
3. **Restart application:** `docker compose restart web celery-worker`
4. **Stale preference recovery:** Browsers automatically fall back to configured defaults when stored theme ID is not in registry
5. **Emergency fallback:** Always available as last resort (`__emergency__` theme)
6. **Invalidate proxy cache:** If using a CDN/reverse proxy, purge cached CSS responses

Rollback requires no database migrations — browser-local storage keeps rollback low risk.

### Monitoring

| Signal | Source | Action |
|--------|--------|--------|
| Theme registry startup failure | Application logs | Check `THEMES_ENABLED`, custom dir config |
| Invalid custom-theme counts | Diagnostics endpoint / logs | Review file validity |
| Emergency fallback activation | Diagnostics endpoint | Verify bundled theme parsing |
| CSS route 404/503 rates | Access logs / metrics | Check registry build, theme IDs |
| Frontend stylesheet load errors | Browser console / telemetry | Verify CSS route availability |
| Startup duration regression | Application logs | Profile `build_registry()` |

### Acceptance Criteria

- [x] Rollout and rollback steps documented and tested
- [x] Operators can return to bundled defaults without code changes
- [x] No user data migration required for rollback

---

## 6. Roadmap Closure Audit

Verification of every item from the original roadmap definition of done.

| # | Item | Implementation | Tests | Docs | Status |
|---|------|---------------|-------|------|--------|
| 1 | Approved themes packaged with provenance | `resources/themes/manifest.json` (48 entries with provenance) | `test_theme_packaging.py`, `test_theme_package_validation.py` | `docs/theme-provenance.md` | **Closed** |
| 2 | Complete `AinewsTheme` translation | `services/themes/translate.py` (all Halloy fields mapped) | `test_theme_translate.py` (31 tests) | `docs/halloy-theme-contract.md` | **Closed** |
| 3 | Injection/path safety | `services/themes/registry.py` (traversal, symlink, ID normalization) | `test_theme_registry.py` (53 tests), `test_theme_accessibility_validation.py` | `docs/halloy-theme-contract.md` §Security | **Closed** |
| 4 | Read-only custom directory support | `services/themes/registry.py:_build_external_registry()` | `test_theme_registry.py` (external dir tests) | `docs/theme-authoring.md` | **Closed** |
| 5 | External override precedence | `services/themes/registry.py:835-867` (external-over-bundled) | `test_theme_registry.py` (override tests) | `docs/halloy-theme-contract.md` §Precedence | **Closed** |
| 6 | Once-per-process parsing | `services/themes/loader.py:build_app_registry()` (startup only) | `test_theme_lifecycle.py` (45 tests) | `docs/theme-release-hardening.md` §1 | **Closed** |
| 7 | Reader selection and persistence | `static/js/theme.js` (localStorage v2 key) | `test_theme_preferences.py` (51 tests) | `docs/theme-preferences.md` | **Closed** |
| 8 | System light/dark mapping | `static/js/theme.js` (matchMedia + configured defaults) | `test_theme_preferences.py` (system mode tests) | `docs/theme-preferences.md` §System mode | **Closed** |
| 9 | Legacy migration | `static/js/theme.js:37-61` (v1→v2 migration) | `test_theme_preference_validation.py` (38 tests) | `docs/theme-preferences.md` §Migration | **Closed** |
| 10 | Theme-neutral page/fragment caches | Theme choice not in cache keys (`pub:` prefix) | `test_theme_lifecycle.py` (HTMX tests) | `docs/theme-release-hardening.md` §2 | **Closed** |
| 11 | HTMX persistence | `static/js/theme.js` (dual-stylesheet ownership) | `test_theme_lifecycle.py` (HTMX nav tests) | `docs/theme-release-hardening.md` §1 | **Closed** |
| 12 | Critical/generated CSS sync | `scripts/build_critical_css.py --check` + `variables.css` fallback | `test_theme_css_contract.py` (38 tests) | `docs/theme-release-hardening.md` §1 | **Closed** |
| 13 | Semantic token use on public/admin pages | `static/css/variables.css` (all pages use `--color-*` tokens) | `test_theme_visual_validation.py` (25 tests) | `docs/frontend.md` | **Closed** |
| 14 | Bundled parser/translation/contrast/artifact validation | `scripts/validate_themes.py` (CLI) + `tests/test_theme_validation_cli.py` (42 tests) | `test_theme_colors.py` (53), `test_theme_halloy.py` (28) | `docs/theme-validation.md` | **Closed** |
| 15 | Custom-theme validation and documentation | `scripts/validate_themes.py --file/--directory` + `docs/theme-authoring.md` + `docs/theme-troubleshooting.md` | `test_theme_validation_cli.py` | `docs/theme-authoring.md`, `docs/theme-troubleshooting.md` | **Closed** |
| 16 | Docker/release resource inclusion | `Dockerfile` (`COPY . .`), `.dockerignore` (includes `resources/themes/`) | `test_theme_package_validation.py` | `docs/theme-release-hardening.md` §4 | **Closed** |
| 17 | Emergency fallback independence | `services/themes/emergency.py` (code-defined, always present) | `test_theme_failure_recovery.py` (75 tests) | `docs/theme-troubleshooting.md` §9 | **Closed** |
| 18 | Full repository validation | `scripts/validate_release.sh --full`, 685+ theme tests, ruff, mypy | All 16 theme test files | `docs/release_checklist.md` | **Closed** |
| 19 | Strict validation policy | `STRICT_PROMOTABLE_CODES` in `services/themes/errors.py`, `is_fatal_diagnostic()`, `is_strict_promotable()`, `is_advisory_diagnostic()` helpers | `tests/test_theme_validation_cli.py` (strict-promotable tests) | `AGENTS.md`, `docs/theme-release-hardening.md` | **Closed** |
| 20 | Browser smoke tests | `tests/test_theme_browser_smoke.py` (14 Playwright/Chromium tests) | Dual-stylesheet ownership, palette switching, preference persistence, legacy migration, system mode, CSS failure recovery, ETag 304, HTMX navigation, selector keyboard interaction | `AGENTS.md` | **Closed** |

### Accepted Limitations

| Item | Limitation | Rationale |
|------|-----------|-----------|
| Contrast warnings | 644 non-fatal contrast warnings across 48 themes | Halloy themes designed for IRC, not web content; warnings documented, not blockers |
| Fingerprinted URLs | Deferred to future phase | ETag-based conditional requests provide equivalent cache-busting with simpler implementation |
| Live reload | Not implemented | Process-lifetime immutability is deliberate; restart is explicit operator action |

### Acceptance Criteria

- [x] Every item closed with implementation, test, and documentation locations
- [x] No item marked complete solely from a commit message
- [x] Closure record suitable for future maintainers

---

## 7. Release Validation Summary

| Check | Result |
|-------|--------|
| Bundled theme validation (`validate_themes.py --bundled`) | 48 themes, 0 errors, 644 warnings |
| Critical CSS sync (`build_critical_css.py --check`) | Token check passed |
| JS bundle/source-map | `bundle.min.js` + `.map` present, built from `app.js`, `theme.js`, `toast.js`, `admin.js` |
| CSS bundle | `style.bundled.css` (76,518 bytes) built from 7 source files |
| Manifest consistency | 48 entries, all files present, no extras |
| Theme test suite | 685+ tests pass |
| Ruff lint | Clean |
| Mypy type-check | Clean on changed files |
| Working tree | Clean (no uncommitted changes) |
