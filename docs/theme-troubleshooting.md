# Theme Troubleshooting Guide

This guide covers common issues when working with custom themes. Each entry follows the **Symptom → Cause → Resolution** format.

Diagnostic codes reference `THEME_DIAGNOSTIC_CODES` from `services/themes/errors.py`.

---

## 1. Custom theme does not appear in the selector

**Symptom:** Theme file is in the custom directory but does not appear in the theme selector UI.

**Causes (check each):**

1. **File not a direct child** — Only `.toml` files directly in `THEMES_CUSTOM_DIR` are discovered. Nested directories are ignored.
   - *Resolution:* Move the file to the root of the custom directory.

2. **File count limit exceeded** — More than 200 files in the directory.
   - *Diagnostic:* `themes.custom_file.count_limit`
   - *Resolution:* Remove unused themes. Only the first 200 are processed.

3. **File too large** — Exceeds `THEMES_MAX_FILE_BYTES` (default 256 KB).
   - *Diagnostic:* `themes.custom_file.size_limit`
   - *Resolution:* Reduce file size below the limit. Max allowed is 1 MB.

4. **Symlink rejected** — The file (or the directory root) is a symlink.
   - *Diagnostic:* `themes.custom_dir.symlink`, `themes.custom_file.unsafe_path`
   - *Resolution:* Use a regular file. Symlinks are rejected for security.

5. **Custom directory disabled** — `THEMES_ALLOW_CUSTOM=false`.
   - *Diagnostic:* `themes.custom_dir.disabled`
   - *Resolution:* Set `THEMES_ALLOW_CUSTOM=true`.

6. **Custom directory not set** — `THEMES_CUSTOM_DIR` is empty.
   - *Resolution:* Set `THEMES_CUSTOM_DIR` to the directory path.

7. **Restart required** — Themes are parsed at startup only.
   - *Resolution:* Restart the web and worker processes.

8. **Theme ID collision** — Another theme (bundled or external) has the same normalized ID.
   - *Diagnostic:* `THEME_ID_COLLISION` or `themes.external.duplicate`
   - *Resolution:* Rename the file to produce a unique normalized ID, or remove the conflicting entry.

---

## 2. Theme rejected as invalid

**Symptom:** Validation script reports errors; theme is skipped at startup.

**Causes:**

1. **Invalid TOML syntax** — Malformed TOML structure.
   - *Diagnostic:* `THEME_PARSE_INVALID_TOML` / `themes.external.parse`
   - *Resolution:* Run `python scripts/validate_themes.py --file theme.toml` to get the exact parse error. Use a TOML linter.

2. **Invalid hex color** — Color value is not `#RRGGBB` or `#RRGGBBAA`.
   - *Diagnostic:* `THEME_COLOR_INVALID`
   - *Resolution:* Use `#` prefix followed by exactly 6 or 8 hex characters. No shorthand (`#FFF`), no named colors (`red`), no CSS functions (`rgb(...)`).

3. **Empty TOML** — File has no content or no recognized sections.
   - *Diagnostic:* `THEME_PARSE_INVALID_TOML`
   - *Resolution:* Add at least one recognized section (`[general]`, `[text]`, `[buffer]`, `[buttons.primary]`, or `[buttons.secondary]`).

4. **Critical contrast failure** — Primary text vs primary background below 4.5:1.
   - *Diagnostic:* `THEME_CONTRAST_CRITICAL` / `contrast.primary_text`
   - *Resolution:* Increase the contrast between `text.primary` and `general.background`. Use a contrast checker tool.

5. **File size exceeded** — Raw bytes or file stat exceeds `THEMES_MAX_FILE_BYTES`.
   - *Diagnostic:* `themes.custom_file.size_limit`
   - *Resolution:* Reduce the file size. The default limit is 256 KB.

6. **Invalid identifier** — Filename normalizes to an empty string.
   - *Diagnostic:* `themes.custom_file.invalid_id`
   - *Resolution:* Ensure the filename contains at least one alphanumeric character.

---

## 3. Duplicate identifier

**Symptom:** `THEME_ID_COLLISION` diagnostic; one theme is skipped.

**Cause:** Two files produce the same normalized identifier after filename normalization (NFKD → ASCII fold → lowercase → replace non-alphanumeric with `-`).

**Resolution:**

- Rename the losing file to produce a different normalized ID.
- Example: `My Theme.toml` and `my--theme.toml` both normalize to `my-theme`. Rename one.

---

## 4. Stale browser preference

**Symptom:** Browser shows the old theme after switching or after the theme was removed.

**Cause:** `localStorage` persists the theme ID. If the theme is removed server-side, the browser still references it.

**Resolution:**

- The browser will fall back to the configured default theme automatically (the selector shows the default when the stored ID is not in the registry).
- **Note:** The application CSS (layout, typography, structural tokens) remains fully loaded even when a stale or unknown theme triggers the fallback. The `#ainews-app-stylesheet` link is permanent and is never removed by `theme.js`, so the page layout and structure are unaffected by a missing theme stylesheet.
- To force a reset, open browser DevTools → Application → Local Storage → delete the `ainews-theme-preference-v2` key.
- Cross-tab sync via `storage` events updates other tabs automatically.

---

## 5. CSS appears cached after file replacement

**Symptom:** Replaced a theme file with a new version but the browser still shows the old colors.

**Cause:** The CSS route uses `ETag` and `Cache-Control: public, max-age=300`. The ETag is derived from the CSS content hash, so it changes when the content changes. However, the browser may serve from its local cache within the 5-minute window.

**Resolution:**

- **Hard refresh:** `Ctrl+Shift+R` (or `Cmd+Shift+R` on macOS) bypasses the cache.
- **Wait:** Cache expires after 300 seconds.
- **Verify ETag changed:** Use DevTools Network tab to confirm the server returns `200 OK` with a new `ETag` header. If it returns `304 Not Modified`, the browser cache is still valid. The ETag handling uses Werkzeug's `response.set_etag()` and `response.make_conditional(request)` for standards-compliant conditional requests.

---

## 6. Default light/dark misclassification

**Symptom:** A light theme appears under the dark default, or vice versa.

**Cause:** Appearance is auto-detected from the luminance of `general.background` (or `buffer.background` if `general.background` is missing). If the background color is borderline, the classification may differ from your intent.

**Resolution:**

- Ensure `general.background` has a clear light or dark luminance. Light themes typically use backgrounds with hex values `#f0f0f0` or lighter. Dark themes use `#303030` or darker.
- If you need precise control, ensure the background luminance is well above 50% for light themes or well below 50% for dark themes.
- Check the `appearance` field in the registry metadata JSON embedded in the page (`#ainews-theme-metadata` script tag).

---

## 7. Missing mounted directory

**Symptom:** `themes.custom_dir.missing` diagnostic; no external themes loaded.

**Cause:** `THEMES_CUSTOM_DIR` points to a directory that does not exist on disk.

**Resolution:**

- Verify the path is correct. In Docker, paths are relative to the container filesystem.
- Create the directory before starting the container.
- Ensure volume mounts are correctly configured in `docker-compose.yml`.
- Check that the directory exists inside the container: `docker exec -it ainews ls -la /path/to/themes`.

---

## 8. Permissions / read-only behavior

**Symptom:** Theme files exist but produce `themes.custom_dir.unreadable` or `themes.custom_file.read` diagnostics.

**Cause:** The application process cannot read the files. Common in Docker when the mounted directory has restrictive permissions.

**Resolution:**

- Ensure the mounted directory and all `.toml` files are readable by the application user (UID 1000 in the Dockerfile).
- Read-only mounts (`:ro`) are fully supported and should not cause issues. The theme system never writes to the custom directory.
- Fix permissions: `chmod -R 644 /path/to/themes/*.toml && chmod 755 /path/to/themes`

---

## 9. Emergency fallback active

**Symptom:** `THEME_EMERGENCY_FALLBACK` diagnostic; the UI shows the built-in emergency theme instead of your theme.

**Cause:** Every bundled and external theme failed to parse, or the theme system is disabled.

**Resolution:**

- Check `THEMES_ENABLED` is `true` (default).
- Check `THEMES_CUSTOM_DIR` and `THEMES_ALLOW_CUSTOM` are set correctly.
- Run the validation script to identify parse errors: `python scripts/validate_themes.py --bundled`
- If the emergency theme is the only usable theme, the registry still functions — it just has no operator-visible theme choices.
- The emergency theme identifier `__emergency__` is excluded from the theme selector UI.

---

## Diagnostic Code Reference

For machine-readable diagnostics, run the validation script with `--format json`:

```bash
python scripts/validate_themes.py --file theme.toml --format json
```

### Parser / Validator Codes

| Code | Description |
|------|-------------|
| `THEME_PARSE_INVALID_TOML` | TOML parsing failed |
| `THEME_COLOR_INVALID` | Invalid hex color value |
| `THEME_ID_COLLISION` | Duplicate normalized identifier |
| `THEME_PATH_OUTSIDE_ROOT` | File path escapes configured root |
| `THEME_SYMLINK_REJECTED` | Symlink not allowed |
| `THEME_RESOURCE_MISSING` | Bundled resource file not found |
| `THEME_EMERGENCY_FALLBACK` | Emergency fallback theme active |
| `THEME_DEFAULT_MISSING` | Configured default theme not found in registry |

### Contrast Codes

| Code | Description |
|------|-------------|
| `THEME_CONTRAST_WARNING` | Contrast below AAA threshold |
| `THEME_CONTRAST_CRITICAL` | Contrast below AA threshold (fatal) |
| `contrast.primary_text` | Primary text vs background contrast too low |
| `contrast.secondary_text` | Secondary text vs background contrast too low |
| `contrast.accent_link` | Accent vs background contrast too low |
| `contrast.button_text` | Text on accent (button) contrast too low |
| `contrast.focus_ring` | Focus ring vs background contrast too low |
| `contrast.error` | Error color vs background contrast too low |
| `contrast.success` | Success color vs background contrast too low |

### Custom Directory Codes

| Code | Description |
|------|-------------|
| `themes.custom_dir.missing` | Custom theme directory does not exist |
| `themes.custom_dir.symlink` | Custom theme root must not be a symlink |
| `themes.custom_dir.not_directory` | Custom theme path is not a directory |
| `themes.custom_dir.unreadable` | Could not read custom theme directory |
| `themes.custom_dir.disabled` | Custom theme directory configured but not allowed by policy |
| `themes.custom_file.count_limit` | External theme file limit reached |
| `themes.custom_file.size_limit` | File exceeds size limit |
| `themes.custom_file.read` | Could not read file |
| `themes.custom_file.invalid_id` | Skipping file: invalid normalized identifier |
| `themes.custom_file.unsafe_path` | Skipping file: unsafe path |

### External Theme Codes

| Code | Description |
|------|-------------|
| `themes.external.duplicate` | Duplicate normalized id in external directory |
| `themes.external.parse` | Could not parse external theme file |
| `themes.external.override` | External theme overriding bundled entry (`RegistryDiagnostics.overrides` records which bundled IDs were overridden; admin diagnostics API exposes an `overrides_bundled` boolean per theme) |
| `themes.external.reserved` | External theme shadows reserved emergency identifier |

### Registry Codes

| Code | Description |
|------|-------------|
| `themes.registry.empty` | No usable bundled or external themes |
| `themes.default.fallback` | Configured default theme not found; using fallback |
| `themes.disabled` | Theme system disabled; only emergency fallback available |
