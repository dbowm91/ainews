# TTS M1 — Durable post-publication jobs and deterministic script

**Status:** PLANNED.
**Parent:** [TTS roadmap](tts_audio_roadmap_20261030.md).
**Priority:** P0 publication correctness and worker trust boundary.
**Dependencies:** Existing article model; PR #20's publication guard/public IDs for final integration.

## Goal

Establish a post-publication, idempotent, independently recoverable narration ledger. No inference, FFmpeg or network-bound work can hold an article/edition transaction open or transition a published article back into editing/review. A disabled TTS installation behaves exactly as before.

## Implementation

1. Add an additive SQLAlchemy model/migration for **NarrationJob** (and an asset record if separation materially simplifies lifecycle): internal integer key; target_kind article/edition; target_id; target_public_id snapshot; source revision/content_sha256; script_sha256 and renderer_version; voice/profile/model/checkpoint/recipe digest; state pending/claimed/encoding/ready/failed/cancelled; attempt_count, eligible_at, claim_token hash, claim_deadline, heartbeat timestamp, error class/message (bounded and sanitized); output metadata (opaque storage key, content sha256, duration, channels, sample rate, codec, byte size), created/updated/ready timestamps. Unique identity includes target + source revision + recipe digest; add indexes for bounded fair pending claims and stale-claim recovery. Store no credentials in job metadata.
2. Implement pure deterministic **services/tts/text.py** narration renderer from finalized article JSON: headline, TL;DR, why it matters, key takeaways, condensed body, what to watch; no original publisher extracted_text, related articles, unverified quotes, HTML tags, URLs, tracking tokens or citations read aloud. Convert safe markup to plain spoken text; keep narrative accuracy, avoid inventing claims; sanitize numerals/acronyms and punctuation with explicit versioned rules and bounded configurable pronunciation aliases. Avoid optional second LLM call. Reject empty/overlong scripts and set an explicit per-target max. Segment at sentence/paragraph boundaries under both character/token/time budgets, record deterministic chunk order and pauses.
3. Implement a single idempotent **ensure_narration_job_for_published(target)** service invoked after successful publication from all known paths. Inspect tasks/edit.py, services/pipeline_degradation.py::post_finalize_article, services/auto_review.py, tasks/scheduler.py and future edition publication. Handle code that already committed before hooks; do not enqueue a Celery task before transaction commit and risk a worker seeing uncommitted content. Prefer insert-on-conflict into a durable job table and bounded periodic reconciliation to catch crash-between-commit-and-hook; no reliance on best-effort .delay alone. Only include explicitly published, nonwithdrawn targets using shared services/publication.py filters once PR #20 is integrated. A zero-worker installation accrues bounded jobs and never affects publication.
4. Add a **private worker protocol** suitable for macOS native worker with Docker-hosted web app: authenticated claim+script fetch, heartbeat/lease renewal, result submit and explicit failure release. Restrict by hashed TTS-worker credential and scoped action; audit issuance/revocation, return no secrets in logs. Claims are atomic compare-and-set with expiry; completion rejects stale tokens, non-current script hash, withdrawn content, disabled policy, oversized bodies or wrong codec. Accept only exact server-owned job IDs and bounded binary Opus, never arbitrary prompts from public clients. Upload via streaming temporary file under dedicated private media root; validate then atomic rename and short DB finalization. Prefer private/loopback access; TLS with pinned service origin for any cross-host setup.
5. Expose a small read-only service giving audio READY/absent state to public renderers. On article edit, reprocessing, deletion, withdraw or model/profile change, hide outdated ready assets and enqueue a new revision if enabled. Keep older assets private for bounded retention or GC, never present wrong narration.

## Repository touchpoints

models/article.py and/or models/newsletter.py, models/__init__.py, migrations/versions, services/tts/{jobs,text,eligibility,worker_protocol,storage}.py (proposed), tasks/__init__.py, tasks/tts.py (reconcile only), services/auto_review.py, services/pipeline_degradation.py, tasks/edit.py, tasks/scheduler.py, routes/internal/tts.py (proposed authenticated blueprint), services/cache.py, app.py, tests/ and docs/operations.md. Do not use public article integer URLs; use server-side target PKs and opaque external IDs from PR #20.

## Required tests and acceptance evidence

- Parameterized publication-path tests: auto-editor, review approval, auto-approval, schedule, and retry; each creates at most one job for identical content+recipe; failure to create/enqueue narration never prevents DONE/public visibility.
- Crash after publication before scheduling, crash while claiming, lease expiration and duplicate-worker race; reconciler repairs missing jobs and at most one valid current claim owns result. Simulate Redis being unavailable without stopping DB publication.
- Concurrent update while worker holds claim; old completion cannot make audio READY or generate a visible player. Withdrawn/unpublished resources cannot be claimed or served, and existing assets are not discoverable.
- Worker credential missing/malformed/revoked, forged IDs, mismatched sha, CSRF/session vs internal auth, oversized payload, unsupported format and bad file path are rejected without disk exposure.
- Script snapshots are deterministic for same revision; mixed HTML/Markdown, URL/citation removal, numbering, edge-case whitespace, Unicode, punctuation and long structured input have golden tests; no publisher source text injected.
- Fresh/idempotent migrations and model indexes tested in disposable SQLite; no real database restoration rehearsal required. All tests run without Mac/MLX dependencies and default-off.
- Progress evidence: actual implementation SHA, concise test command, state transitions and crash/recovery results. No claim of full article publication unification without inspecting final PR #20 integration.
