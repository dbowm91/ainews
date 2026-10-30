# TTS M3 — Operator settings, ready-only public playback and media lifecycle

**Status:** PLANNED.
**Parent:** [TTS roadmap](tts_audio_roadmap_20261030.md).
**Priority:** P1 UX and permission controls.
**Dependencies:** M1 state/read model; M2 encoder/worker interface (use fake worker in CI).

## Outcome

Give an administrator a complete, bounded and default-OFF TTS control plane. A reader sees a small accessible listen control ONLY after a valid Opus file exists, belongs to the currently published content revision, and remains allowed by operator policy.

## Settings surface and configuration contract

- Extend the existing admin settings page with **Audio / TTS** subsection or dedicated admin TTS settings page linked from it; keep editorial pipeline role/provider selection unchanged. Separate **global enabled**, **articles enabled**, **newsletter editions enabled**, and **backfill enabled** (all default false). Allow setting default backend (initial MLX Breeze 4-bit), checkpoint identifier/revision, text language, voice instruction text, CFG scale, eligible voice/reference profile ID, Opus bitrate, max minutes/chars per job, max pending jobs, retry budget and retention policy; safe bounds and immutable per-job config snapshots are required.
- Register configuration through ainews_config/fields.py, validation and transaction machinery where it fits. Runtime agent settings may need a DB-backed versioned snapshot because the macOS worker is remote to local YAML; choose one canonical writable source and document reload propagation. Profile revision increments on changes that affect speech; a bulk change must not regenerate the archive automatically. Expose backend capabilities so unsupported fields (e.g. CFG on a non-Breeze backend) are hidden/validated rather than silently ignored.
- Admin displays backend online/offline, local/external host identity (no sensitive IP/token disclosure), job counts by state, most recent failure/latency/Opus size, a bounded voice preview from an operator-controlled short sample, single-job retry/cancel/regenerate and opt-in bounded backfill. Mutations require auth, CSRF and audit entries. No public script submission, voice cloning, or worker credential value in logs/config responses. Disabling TTS stops new claims and hides UI; in-flight claims can finish safely but must not re-expose the player until re-enabled and valid.
- Implement an explicit credential provisioning/rotation story for the native worker; scoped hashed secret, revocation and safe diagnostics. Expose operator-friendly setup and missing-FFmpeg/model/license errors rather than surfacing internal tracebacks.

## Public route and view behavior

- Add a media route keyed by opaque published target ID and/or a random asset token, not an enumerable internal DB ID; validate public target eligibility, READY state, exact source revision+recipe, and actual file existence on every request. Serve audio/ogg, Content-Disposition inline with safe filename, Accept-Ranges/206 for seek, appropriate Cache-Control/ETag/Content-Length, and HEAD behavior. Avoid path traversal and local-path disclosure. No WAV, source text, model file or reference voice appears under /static.
- Add native HTML5 audio controls to templates/partials/article_detail.html and equivalent edition detail. Render via shared partial so full-page and HTMX fragment paths match. Show optional compact headphone/play icon only when READY (not merely queued/processing), never a disabled or broken control. Announce AI synthesis with clear attribution; include a plain-text equivalent without duplicating the narration script publicly.
- The article HTML route caches server-rendered output for 300 seconds and can serve stale browser cache (routes/public/links.py). Invalidate its response-cache prefix when audio changes state, and decide whether a tiny uncached audio-status fragment is needed for quicker ready visibility. Do not use an aggressive poller; eventual display on ordinary reload is acceptable if documented. Handle conditional requests and browser 404 after withdrawal/disable.
- Implement cache-safe media version URLs or content digests; audio files immutable once ready. Old audio is hidden instantly when source text changes, even if an outdated HTML document remains browser-cached: the media endpoint itself must reject stale revision. Regenerated audio may use a distinct immutable URL.
- Storage root belongs under instance-managed persistent volume, not repo static files; Docker web is read-only apart from mounted application data. Upload atomically with strict codec/duration/size caps. Add safe retention/orphan cleanup that respects current READY assets, backups and active claims. Never GC a file referenced by any current READY asset.

## Tests / required evidence

1. Default-off frontend DOM has no audio URLs/icons and normal article/newsletter workflows continue with no MLX installed.
2. Pending/claimed/encoding/failed/cancelled/withdrawn/wrong-recipe/missing-file states have no playable control; READY+current revision displays one control in full and HTMX fragment. Early cached page cannot reveal stale audio via media route.
3. Valid media GET/HEAD/Range/416, ETag/304, safe content-type/content-disposition, opaque IDs; bad paths, unpublished article, removed edition, stale audio, corrupt file and disabled feature return no content. Check standard browser audio seek.
4. Admin form validation rejects malformed instructions, excessive lengths, unsupported CFG/voice combos and unbounded backfill; session CSRF, auth and audit path tests pass. Worker creds never shown once provisioned.
5. Media storage and cache invalidation behave correctly after process restart, reprocessing, manual edits, feature toggles and file cleanup.
6. No FFMPEG/MLX dependency in web startup and no new public unauthenticated arbitrary binary upload endpoint. Record exact tests, implementation SHA and optional browser smoke outcome.

## Repository touchpoints

routes/admin/settings.py, services/admin_settings.py, templates/admin/settings.html, ainews_config/{fields,validation,transaction}.py, routes/public/links.py, templates/partials/article_detail.html and new audio partial, routes/public audio endpoint, services/cache.py, static/css/articles.css and optional minimal JS, services/tts/storage.py, models job/asset, app.py/blueprint wiring, CSP/media-src rules, docs/configuration.md and docs/operations.md.
