# Optional local narration — article and edition TTS roadmap

**Status:** SOFTWARE IMPLEMENTATION COMPLETE at code commit `d4bc9c0`; intended Apple Silicon/Metal qualification remains **OPEN**.
**Date:** 2026-10-30
**Priority:** Optional private-instance feature; all switches default OFF.
**Handoff:** plan/optional-tts-mlx-audio-20261030.
**Baseline:** main at 8fdfc61f9c7f450f686064a5cdb65fce020b9c04.
**Dependency:** PR #20 / plan/llm-native-editions-delivery-20261029 for immutable NewsletterEdition, publication guard, opaque public article IDs and newsletter archive. Reinspect the merged head; do not copy unmerged database models onto main.

## Outcome and non-negotiable invariants

Offer optional AI narration of completed published articles and published newsletter editions. Publish written content immediately and independently of TTS, host availability, encoding, storage, email delivery, or worker health. Expose a listen control **only** for an encoded, verified, current-content audio asset whose target is still publicly visible. No text-to-speech call occurs in the HTTP request, editorial editor stage, article publication transaction, or newsletter delivery path.

The target backend is native Apple Silicon MLX with mlx-community/Breeze-TTS-2-mlx-4bit, already used by the operator. This is an approximately 3.01 GB on-disk quantized model, NOT a verified peak-memory requirement. Support a provider interface so the site is not hard-wired to Breeze, MLX, Mac or the non-commercial license. The model, its checkpoint revision, INSTRUCT, speaker/reference profile, CFG scale, and text-renderer revision are part of reproducible asset identity.

No public product launch, multi-tenant voice marketplace, real-time live article speech, automatic narrator voice cloning, paid model hosting, or required GPU CI is planned. TTS functionality may stay completely disabled without adding MLX dependencies to web/regular workers.

## Architectural decision

Use a **durable SQL narration-job outbox** for article/edition targets and a **native macOS pull worker** for initial inference. A private, authenticated claim/text/result protocol avoids trying to access a Docker named volume from a native Mac process, avoids exposing Redis externally, and keeps Metal out of Linux containers. The existing Celery/Beat infrastructure may reconcile stale claims and trigger bounded job creation, but must not be required for actual Metal inference; a dedicated tts daemon polls/wakes and processes one job at a time. Do not create a second generic job/transport framework: this protocol is limited to eligible server-owned published content.

Publication: commit source -> idempotently record pending narration work (transactionally at the publication boundary or recovered by periodic reconciliation) -> return published resource. Separate worker: claim lease -> obtain exact normalized script and recipe -> synthesize bounded chunks -> encode Opus -> submit verified asset -> server atomically marks READY -> invalidate UI cache. Heartbeat, claim tokens, retry policy and idempotency protect crashes and duplicate dispatch. If there is no worker, stories remain readable with no audio UI.

Private endpoints must require an independent hashed/scoped TTS worker credential; validate authenticated origin and HTTPS/private-network constraints, binary and script bounds, and state/claim token for finalization. A public client cannot submit arbitrary TTS prompts or arbitrary media paths. Reference audio, when supported, is operator-provided with required rights and consent; no user-facing upload or voice-cloning API.

## Milestones, ownership and sequencing

| Milestone | Plan | Outcome | Dependency |
| --- | --- | --- | --- |
| M1 P0 | [Publication-independent job ledger and narration contract](tts_audio_m1_jobs_and_script_20261030.md) | Persistent idempotent jobs, exact content/script revisions, eligible publication hooks, authenticated worker protocol, fake-worker tests | Existing article publication; edition schema later |
| M2 P1 | [Apple Silicon MLX worker, encoding and transfer](tts_audio_m2_mlx_worker_media_20261030.md) | 4-bit Breeze on macOS, warm model, INSTRUCT and cfg_scale, chunk handling, Opus output, secure transfer and failure budgets | M1 |
| M3 P1 | [Public playback, admin controls and lifecycle](tts_audio_m3_admin_playback_20261030.md) | Default-off settings, secure media route, cache-correct audio visibility, admin status/preview/manual retry, lifecycle and storage cleanup | M1–M2 (backend may be faked in tests) |
| M4 P1 | [Immutable editions, integration and intended-host qualification](tts_audio_m4_editions_qualification_20261030.md) | Frozen edition scripts/audio, email-link behavior, recovery, operational evidence and bounded Mac benchmarks | PR #20 merged/reconciled and M1–M3 |

All milestone plans require regression tests and code changes on implementation branches or coherent commits; the planning branch contains no application changes. Do not mark a milestone implemented or verified because these documents are registered.

## Model, licensing and source of truth

Official MLX model variants: https://huggingface.co/mlx-community/Breeze-TTS-2-mlx (bf16), https://huggingface.co/mlx-community/Breeze-TTS-2-mlx-8bit, and https://huggingface.co/mlx-community/Breeze-TTS-2-mlx-4bit. Use the explicit 4-bit repository as the default MLX example; the unquantized model link is not the 4-bit checkpoint.

MLX-Audio Breeze reference, including **instruct / cfg_scale** and 24 kHz mono output: https://github.com/Blaizzy/mlx-audio/blob/main/docs/models/tts/breeze-tts.md. Pin a working mlx-audio release and Hugging Face commit at implementation time; verify installed API signatures rather than relying on unpinned documentation. Fallback choices are separate providers and must have independently checked licensing, controls and tests.

Breeze weights, quantizations and self-hosted outputs are governed by BreezeBlue's **research/non-commercial** license, not the Apache-2.0 code license. Commercial usage needs separate authorization; do not silently activate Breeze in a commercial installation. Source: https://huggingface.co/BreezeBlue/Breeze-TTS-2/blob/main/LICENSE. Record model/license attribution in operator docs and serve only outputs for an operator-approved use. A future commercial-friendly provider can be added without changing core media lifecycle.

## Definition of done

The no-TTS baseline behaves as before. All publication paths (editor finalization, manual/auto approval, scheduled publication and newsletter edition publication) have verified idempotent job behavior; a failed or offline worker never blocks source publication. A stale/revoked claim cannot replace fresh audio. The player is absent for disabled, pending, failed, withdrawn or changed content; present for only valid READY assets. No WAV or model file leaks to public routes. Real 4-bit MLX/Metal/FFmpeg on the operator's Mac, with measured cold/warm latency, real-time factor, peak memory, quality samples and crash-restart recovery, is recorded before claiming the feature runnable there. Qualification is limited to intentionally enabled private-instance capabilities; no production DB restore rehearsal or public-release certification is required.

## Registration and implementation handoff

Registered by entry in plans/plan.md. When implementing, update individual milestone status with exact commit SHA, test command/output, and hardware-specific observations; annotate this roadmap rather than retroactively rewriting historical evidence in other workstreams. Coordinate rebase/merge against PR #20 before implementing M4. Avoid changing its in-flight feature branch solely to carry these plans.

## Implementation closure — 2026-10-30

M1–M4 software integration is recorded against `d4bc9c0`; see the per-milestone implementation evidence in the linked plans. The TTS-focused suite passed 11 tests, and migrations plus Celery/Beat registration passed 17 tests. Changed TTS modules passed Ruff and mypy. The full repository Ruff run reports five pre-existing findings in unrelated files. No Apple Silicon device is available in this workspace, so MLX/Metal inference, measured performance, listening review, and the intended-host reliability matrix remain **OPEN**. This software closure does not claim the feature has been qualified to run on the operator's Mac.
