# TTS M4 — Frozen newsletter editions, email independence and private-host qualification

**Status:** IMPLEMENTED — edition software integration and native M4 Pro runtime smoke **VERIFIED**; direct listening accepted overall with voice/accent drift observed; interruption/restart recovery **OPEN**. Docker topology is deferred. Code commits `d4bc9c0` and `8f977d0`.
**Parent:** [TTS roadmap](tts_audio_roadmap_20261030.md).
**Priority:** P1 integration and operational closure.
**Dependencies:** M1–M3, plus PR #20 newsletter edition work merged/reconciled into the implementation branch.

## Outcome

Generate one coherent listenable program per **published immutable NewsletterEdition**, independent of whether that edition is mailed. Ensure the existing edition, email, REST and MCP readers retain their snapshot semantics while an optional audio capability appears only for finished audio. Prove the feature on the intended Apple Silicon machine without requiring public-release or restored-database evidence.

## Integration with PR #20

- Revalidate final merged names and contracts from models/newsletter.py (NewsletterEdition/Item), services/newsletter_editions.py, routes/public/newsletters.py, templates/newsletters/detail.html, tasks/newsletter.py, services/distribution/{dispatch,email}.py, and services/publication.py; do not integrate against the old main-branch HTML-only Newsletter model or rely on an unmerged migration ID.
- When edition status moves to published and commits, record an idempotent narration job for the frozen content_revision, published_at, subject/summary and **ordered** edition items. No extra editorial LLM/research pass: render from immutable headline, why_it_matters, paragraph, citations only as source labels if editorially useful, and source attribution. Do not read personalized recipient HTML, unsubscribe URLs, email tracking URLs or dynamically edited articles. Explicitly bound story count and output length.
- Generate an edition intro, subject/date, short summary (if present) and ordered story sections with natural pauses; don't concatenate every full article's separately generated narration. The frozen text ensures later source article edits cannot mutate an existing edition's audio. Edition withdraw/correction or profile disable invalidates public media eligibility; correction publishes a separately versioned asset.
- Add edition audio to the public archive page and optionally a listen link in outgoing email **only if the link targets an already published stable edition page**, not a pending media URL. Email dispatch never waits for, retries because of, or re-sends after audio work. Existing distribution intent state remains solely about email acceptance/unknown outcomes; do not overload delivery with TTS status.
- Public REST/MCP edition read DTOs may include optional ready-only audio metadata/URL when the same public visibility and cache/privacy policy is satisfied; absent audio remains absent, not a pending/failed leak. Adding metadata must not break older consumers, ETags or quota semantics. No agent-access scope grants TTS-generation rights.
- Site startup and migration path remain backwards compatible when TTS is disabled; newsletter archive switch remains independent of the TTS switch. Private audio worker credentials are not reader API tokens.

## Qualification and reliability matrix

- Publish a test article and an edition while native TTS agent is stopped, without blocking or losing publication/email state. Restart agent and verify each eligible job eventually READY. Ensure disabling the feature keeps archive and email functionality.
- Simulate duplicate edition slot/job, two worker claims, worker crash after synthesis before upload and after upload before ACK, Mac sleep/wake, network timeout and failed FFmpeg; verify reconciliation without multiple public assets, no infinite jobs and no stale claim overwrites.
- Reprocessing/withdrawing an article, withdrawing/correcting an edition, swapping the narrator instruction/model/checkpoint, manually regenerating and deleting source content must never expose out-of-date audio. Verify storage cleanup removes orphans without removing current assets.
- Run real Apple Silicon/Metal mlx-community/Breeze-TTS-2-mlx-4bit smoke with a short article, typical article, and representative edition; listen for clipping, unnatural abbreviations, narrator drift, seams, pauses and section pacing. Record OS/SoC/RAM/model revision, model load time, per-chunk and total generation times, RTF, peak memory pressure, swap usage, FFmpeg output size and quality observations. 3.01 GB on disk is not a RAM capacity assertion.
- Verify safe operator setup for the canonical native macOS worker plus non-Docker service: worker auth/rotation, private TLS or loopback, backend offline/online status, quotas, media upload bounds, file permissions, backups, cleanup, and worker restart; do not enable a public Internet upload endpoint. Docker-host topology is an optional later deployment case, not a current qualification gate.
- Run repo unit/integration suite with fake TTS backend, sqlite migration checks, Celery/Beat reconciliation registration tests, web HTML/HTMX/Range/browser tests, Ruff and mypy. Capture tested SHA and commands; no live subscriber send or public release certification. Runtime Mac smoke is opt-in if that hardware exists; without it mark M2/M4 hardware verification OPEN rather than blocking unrelated code.

## Documentation and handoff

Update docs/newsletter-pipeline.md with immutable audio snapshot behavior and email link rules; docs/operations.md with native macOS worker launch/health and Docker storage, docs/configuration.md with default-off settings and licensing, and the master plan registry with exact milestone SHAs/test reports. Feature activation is an operator choice; default-off mode needs no GPU or MLX at all.

## Non-goals

No podcast publishing feed in this milestone, no independent user-uploaded text-to-audio service, no real-time speech streaming or cross-article playback playlist, no external arbitrary URLs, no subscriber-personalized voice, no automatic archive backfill by enabling a toggle, and no assumption that a Breeze-generated output may be commercially distributed.

## Implementation evidence — 2026-10-30

- **Code:** `d4bc9c0`. Integration targets the merged PR #20 `NewsletterEdition`/`NewsletterEditionItem` schema. Jobs use ordered frozen edition content; job creation happens only after edition commit and does not inspect or wait for email delivery. Public archive, REST and MCP DTOs expose audio metadata only for a current READY asset. Edition audio remains gated by the archive switch and TTS policy.
- **Tests:** all 12 TTS tests passed; the edition case verifies frozen ordered content, source URL exclusion, idempotency, and that an email-requested edition creates narration work without changing email state. Migration/Beat checks passed (17 tests).
- **Native runtime:** On Apple M4 Pro / macOS 26.6.2, native arm64 Python 3.12.16, MLX 0.32.4, mlx-audio 0.6.3 and pinned Breeze revision `3a06d26b172ea4ae1da2f42d708383e9c79d5526`, a published frozen edition with `email_requested=True` completed two chunks in 179.2 s, yielding 149.06 s of mono Ogg Opus (717,703 bytes). The public edition media route returned HEAD 200 and Range 206. See M2 for short and long article measurements and cold-load data.
- **Listening assessment:** direct listening found overall good quality, with an apparent unpredictable change in voice/accent. Chunk-to-chunk consistency remains a follow-up observation.
- **Still open:** restart/recovery and Mac sleep/wake behavior for the canonical native worker and non-Docker service. Docker topology is deferred. No subscriber send or external publication was performed.
