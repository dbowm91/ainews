# M3 — Incremental Synthesis, Retirement, and Curated Shared Blackboard

**Status:** OPEN / priority P1  
**Requires:** M2 scoped memory/lineage and retrieval service  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Outcome

Replace the current nightly `LOW -> MEDIUM` promotion with **actual consolidation of knowledge**: merge duplicate observations, synthesize evidence-backed developments, update current understanding, retire obsolete active entries, and selectively expose cross-category facts through a small shared blackboard.

## Lifecycle policy and invariants

Do not equate `importance=HIGH` with immortality. Track independent `importance`, `status`, `expires_at`, `review_due_at`, `last_evidence_at`, and operator-only `pinned` state.

- LOW: eligible for routine expiry/archive around 7 days; MEDIUM: around 30 days; HIGH: **review due around 90 days**, never implicitly exempt from review. These are initial defaults, configured and calibrated; review_due is not an assertion that a memory becomes false on that day.
- `active`: eligible for contextual retrieval; `synthesized`: incorporated into an active synthesis, retrievable as supporting evidence; `superseded`: replaced/contradicted by new authoritative event; `archived`: historical only. Explicit `historical=True` searches can read retained records.
- `pinned` blocks automatic destructive removal and signals operator preference, but does not defeat retrieval relevance, status, budget, or safety filtering.
- A supporting observation can be referenced by several syntheses; never delete a source while descendants require provenance. Honor manual deletion/takedown and source retention policy separately from active memory lifecycle.
- `last_accessed_at` is not a correctness signal for historical validity and must not be the only basis for retention. Retrieval frequency may be sampled for analytics without creating a write per read.

## Consolidation stages

**Stage A — deterministic maintenance (default, no LLM):** For each canonical owner category: find due/dirty clusters using article IDs, time windows, normalized titles/entity keys, exact hashes, similarity candidates, and evidence references. Collapse exact duplicates and repeated same-claim sightings into one observation with additional evidence. Set review eligibility and remove expired records from *active* read view. Compute novelty candidates using explicit thresholds; log decisions. Do not treat embedding similarity alone as factual equivalence.

**Stage B — semantic synthesis (conditional LLM):** Only for clusters that are materially evolving, contradictory, large, or have passed the configured synthesis interval and contain novel evidence. Input is a bounded `ContextPack` with atomic observation IDs, source snippets, timestamps, known uncertainty, last synthesis, and a strict output budget. Use a dedicated configured synthesis role (model/provider/token/time cap; no uncontrolled inherited default) and a versioned Pydantic schema. Output must include: proposed synthesis text, normalized category and entities, supporting IDs, contradicting IDs if any, valid-as-of, confidence qualifier, suggested changes, reason for transition, and `no_change` when appropriate.

**Stage C — deterministic validation and commit:** Reject hallucinated item IDs, unknown categories, unsupported new facts, ungrounded quotations, invalid transitions, oversized outputs, wrong model/schema versions and stale optimistic versions. Confirm supporting IDs were in the submitted evidence set. Maintain uncertainty and explicitly preserve contradictory reports rather than asserting consensus. Persist new revision, lineage links and state transitions atomically; leave old active summary untouched if validation fails. Under concurrent jobs, use per-category advisory/Celery locks or version checks with bounded retries; avoid locking SQLite during inference.

**Stage D — periodic review:** Nightly deterministic sweep marks due items; batches of uncertain/high-impact items may invoke synthesis/review, with limits per run and queue backpressure. No repeated LLM invocation when evidence has not changed (`evidence_digest`, `synthesis_version`, `last_processed_digest`). On provider failure, preserve existing valid state for a bounded grace period and set explicit `review_overdue` diagnostics; do not silently invalidate correct context.

## Blackboard promotion

The shared blackboard is a **visibility index**, not a global narrative prompt and not a second mutable copy. A memory remains owned by exactly one category; promotion adds a shared scope reference. Candidate promotion is triggered by cross-category entity/topic links, multi-category supporting evidence, or explicitly documented operator promotion. Conditional model judgment can decide cross-domain significance only after deterministic candidates exist; an operator can approve or reverse.

Shared promotion requires enough provenance, genuine cross-category utility, and an unambiguous as-of/validity statement. A shared entry can be hidden, retired or de-promoted independently of deleting the underlying memory. Ensure high-volume categories cannot dominate the blackboard; apply per-category quotas and relevance/diversity caps at retrieval time. The default editor gets **at most a few** blackboard hits; no agent receives the entire index.

## Category summary projections

Maintain a small, versioned category summary (e.g. 150–250 tokens) of *current validated trends*, derived from linked syntheses. Update only on dirty evidence, schedule, or explicit operator request. Track a summary revision and evidence IDs; summary generation is conditional and separate from atomic deduplication. Avoid recursively resummarizing older summaries without raw evidence. The writer and editor receive either selected summary portions or relevant atomic observations as needed, not duplicate summaries plus entire histories.

## Task wiring and cost limits

Replace `tasks.cleanup.consolidate_trend_memory` semantics with clear new Celery tasks (maintain/synthesize/review/promote; exact task names implementation choice). Register every task module in `tasks/__init__.py`, schedule via `Config.get_beat_schedule()` and typed `pipeline.yaml`, and extend `tests/test_celery_beat_task_registration.py`. Deprecate the old promotion task only after parity tests; do not run old promotion concurrently with new lifecycle.

New tasks should be idempotent under retry/restart, signed/verified according to `services/task_security.py` conventions, rate-limited by available provider concurrency, chunked per category, timeout-bounded, and isolated from article publication. Reuse the existing out-of-band proposal pattern; never hold a DB transaction during an LLM call. Config must support a feature toggle, maximum items/categories per run, max LLM syntheses per day, and explicit no-model operation.

## Admin/operator interface

Extend `routes/admin/trend_memory.py` or add an authenticated memory management surface, using established CSRF, audit logging and role checks. Show category, shared flag, age/next review, state, evidence count, current synthesis revision and cross-category visibility. Allow pin/unpin, approve/de-promote shared references, archive/supersede and inspect evidence/history. Provide a dry-run preview of consolidation and backfill, explain why an item was retired, and emit no secret/source payload in operational metrics.

## Required adversarial tests

- HIGH observation ages beyond review date; does not remain automatically active forever, is not destroyed just because its review is due, and pinned behavior remains budget-bounded.
- Exact duplicate sources, cross-publisher same story, multiple conflicting reports, false embedding neighbors, a correction/retraction, and repeated identical Celery deliveries.
- Synthesis hallucinating a source ID, contradicting an explicit quote, returning invalid schema, or timing out cannot overwrite the previous trusted revision.
- Shared item retrieval permitted to multiple category readers without data duplication; unshared private item never leaks; source mutation and de-promotion invalidate cache.
- Concurrent synthesis jobs on the same category do not double-write or lose lineage; run without `sentence-transformers` or LLM provider and verify deterministic maintenance remains functional.
- A nightly cycle with no new evidence performs zero semantic synthesis calls. Per-day cap and backpressure persist across task retries.

## Exit criteria

No unconditional/ever-growing HIGH injection, true evidence-linked synthesis, reversible supersession, bounded shared access, human-readable review visibility, idempotent Celery maintenance and measured **zero inference** for no-change cycles. This is not complete merely because a model produces a shorter paragraph.
