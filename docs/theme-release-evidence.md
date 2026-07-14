# Theme Subsystem — Release Evidence

Machine-readable release evidence for the Halloy-compatible theme system.
Generated from a clean checkout at commit `33048dd` on 2026-07-14.

---

## Verification Commands and Results

### 1. Bundled Theme Validation (strict mode)

```bash
.venv/bin/python scripts/validate_themes.py --bundled --strict --format json
```

**Result:**
- valid: true
- themes_validated: 48
- errors: 0
- warnings: 644 (advisory contrast, non-blocking under strict)
- promoted: 0
- duration: 114ms

### 2. Theme Unit Tests

```bash
.venv/bin/python -m pytest tests/test_theme_*.py -x --tb=short -q
```

**Result:** 727 passed, 2 warnings

### 3. CLI Exit-Code Tests

```bash
.venv/bin/python -m pytest tests/test_theme_validation_cli.py -x -v
```

**Result:** 66 passed

### 4. Browser Smoke Tests (Playwright/Chromium)

```bash
.venv/bin/python -m pytest tests/test_theme_browser_smoke.py -x -v --tb=short
```

**Result:** 14 passed (32.25s)

### 5. Ruff Lint

```bash
rtk ruff check . --exclude .venv
```

**Result:** Clean (no output)

### 6. Mypy Type Check

```bash
rtk mypy . --exclude .venv
```

**Result:** 2 pre-existing errors (not from theme changes):
- `utils/html.py:71` — no-any-return (pre-existing)
- `celery_support.py:3` — var-annotation (pre-existing)

### 7. CSS Asset Build

```bash
.venv/bin/python scripts/build_assets.py css
```

**Result:** `static/css/style.bundled.css` written

### 8. Critical CSS Build

```bash
.venv/bin/python scripts/build_critical_css.py
```

**Result:** `templates/partials/critical_css.html` generated

### 9. JS Asset Build

```bash
.venv/bin/python scripts/build_assets.py js
```

**Result:** `static/js/bundle.min.js` written (reflects theme.js source changes)

### 10. Generated Asset Diff

```bash
rtk git diff --stat
```

**Result:**
- `static/js/bundle.min.js` — rebuilt from source (expected)
- `static/js/bundle.min.js.map` — rebuilt from source (expected)
- `tests/test_theme_validation_cli.py` — new tests added

---

## Coverage Summary

| Category | Count | Status |
|----------|-------|--------|
| Bundled themes validated | 48 | ✅ 0 errors |
| Advisory contrast warnings | 644 | ✅ Non-blocking under strict |
| Theme unit tests | 727 | ✅ All pass |
| CLI exit-code tests | 66 | ✅ All pass |
| Browser smoke tests | 14 | ✅ All pass (Chromium) |
| Ruff lint | — | ✅ Clean |
| Mypy type-check | — | ✅ 0 new errors |

---

## CI Job References

| Job | File | Status |
|-----|------|--------|
| `lint-and-test` | `.github/workflows/ci.yml` | ruff + mypy + pytest |
| `theme-validation` | `.github/workflows/ci.yml` | validate_themes.py --bundled --strict |
| `theme-browser-smoke` | `.github/workflows/ci.yml` | Playwright/Chromium smoke |

---

## Acceptance Criteria

- [x] `--bundled --strict` exits 0 with 0 errors, 644 advisory warnings, 0 promoted
- [x] 727 theme unit tests pass
- [x] 66 CLI exit-code tests pass
- [x] 14 browser smoke tests pass (Chromium)
- [x] Ruff lint clean
- [x] Mypy clean on changed files (2 pre-existing errors in unrelated files)
- [x] CSS/JS/critical CSS builds succeed
- [x] Generated asset diff matches source changes only
