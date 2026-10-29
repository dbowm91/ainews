# C02 — HIGH-Memory Retirement, Synthesis Supersession, and Blackboard Currentness

**Status:** IMPLEMENTED and verified in the full local suite. Target-instance maintenance/synthesis trial remains under C04 until the owner's database is restored. **Priority:** P0. **Baseline:** PR #19 `f3aa498e4d0d`.
**Parent:** [Corrective Overview](editor_memory_corrective_pass_overview_20261029.md).
**Related milestones:** M3, M5. **Prerequisite:** C01 read-side context/synthesis eligibility design.

## Reproduced by code inspection

- `services/memory/lifecycle.py:maintain_memory()` archives expired LOW/MEDIUM observations, but merely **counts** active HIGH rows where `review_due_at <= now`. HIGH has no expiration in `add_observation()`, so high-priority active state can accumulate forever. Existing tests explicitly assert a due HIGH remains active; this should only hold during a bounded review grace period.
- `services/memory/synthesis.py:synthesize_category()` creates a new active synthesis and materialized category summary, while marking supporting observations `synthesized`. It does not retire/supersede the prior active synthesis revision in the same transaction. Summaries and historical synthesis rows can diverge.
- `synthesize_category():_snapshot()` considers just eight priority/recency-selected observations and 32 evidence rows. Changed evidence outside that window can be overlooked, yielding a false `unchanged` result; candidate selection should follow dirty/novelty markers and coverage quotas, not perpetually starve lower-ranked changes.
- Shared visibility is attached to a single memory ID. When a synthesis is replaced, its old shared scope is not automatically reconciled with the current revision; stale shared content can remain `active`.
- The current status model provides `active/synthesized/superseded/archived`; it needs an explicit **review decision** mechanism and bounded retry/backpressure without deleting evidence.

## Work package C02.1 — Review lifecycle with finite HIGH active period

1. Separate **retention** from **active eligibility**. HIGH becomes review-due after its configurable interval (initial 90 days), not automatically immortal or automatically false. Define review states as columns or a small review-record table (suggest `review_status`, `review_due_at`, `review_attempted_at`, `review_reason`, `review_count`; no unnecessary new state machine if simple fields suffice).
2. Nightly deterministic job builds bounded due queues and scores candidates by recency of supporting evidence, provenance, impact, potential contradiction and pinning. For **unchanged/no-evidence** items, use a documented finite grace/renewal policy; when review cannot complete, exclude stale items from default *active* retrieval after the grace cutoff and report `overdue` explicitly, while keeping records historically available.
3. When new independent evidence supports continued validity, renew review date with an auditable revision. When replaced, set `superseded` and link successor; when no longer timely/relevant, archive. Operator pinning prevents destructive removal and supports explicit renewal, **not** unbounded automatic inclusion. Never let a transient model outage delete history or block publication.
4. Do not infer freshness from `last_accessed_at`. Track `last_evidence_at` separately. Make review batching/caps persisted and idempotent across Celery retries, interruptions and restarts. Expose high-review backlog/overdue and renewal/archive counts to authenticated admin metrics.

## Work package C02.2 — One current synthesis per category

- Enforce a coherent current materialization: at most one **current** active synthesis for a category and its summary projection, while historical syntheses retain provenance and lineage. Choose the canonical representation (e.g., `MemoryCategorySummary.current_memory_id` plus status and revision) and add a DB uniqueness/index constraint or atomic service invariant with SQLite tests.
- On an accepted proposal, atomically: validate against the latest category evidence digest; retire/supersede previous current synthesis; persist new item with source links and `supersedes` lineage; update projection revision and supporting IDs; reconcile any shared scope; mark included observations `synthesized` as appropriate. On failure, keep prior verified projection and status unchanged.
- A genuinely `no_change` proposal must preserve the current synthesis and record the evidence digest/attempt such that unchanged nightly runs cost zero additional inference. Contradictory evidence should remain linked with uncertainty; never promote an LLM result to externally verified fact.
- If the prior current synthesis was shared, determine policy for review/approval of replacement shared content: default to hiding or revoking stale shared visibility until reapproved, or promote a verified successor under explicit policy; do not leave old shared synthesis visible as current.

## Work package C02.3 — Fair incremental synthesis and compaction

- Replace the snapshot-only top-eight selection with a deterministic **dirty cluster index** or persisted latest-processed/last-evidence cursor. Small new/corrected facts need fair consideration even when existing HIGH content fills the top window.
- Separate exact dedup/compaction, no-change checks and orphan cleanup (**zero LLM calls**) from conditional semantic synthesis. Preserve independent sources, support/conflict edges and article version provenance. Avoid merging merely similar contradictory claims.
- Cap candidate set, source diversity, token budget, jobs/day, optional model calls and retries. No SQLite write lock across inference. Prefer clear chunks per category and stable ordering; conflicts caused by optimistic version changes should reschedule, not silently lose updates.
- Ensure syntheses themselves do not become unlimited candidates in subsequent syntheses; use the underlying atomic evidence and current summary, not recursively reducing summary text without source truth.

## Work package C02.4 — Maintenance ownership and scheduling

- Existing Beat schedule runs `consolidate_trend_memory`, `maintain_editorial_memory` and `purge_trend_memory`. Define which task owns each legacy and V2 transition. On V2 activation, **do not** simultaneously mutate priority/lifecycle under legacy consolidation if it would conflict. Preserve legacy rows for rollback but make the scheduling policy deterministic and documented.
- Verify task registration in `tasks/__init__.py`, signed invocation, retry/revocation semantics, bounded transaction per batch and observability. Add dry-run and audit record support for operator review.
- Ensure when all memory flags are off, maintenance is a no-op for V2 tables, and legacy reads remain bounded.

## Mandatory regression tests

- Due HIGH remains active during configured grace only, then leaves default retrieval; pinned HIGH persists historically but is budgeted and reviewable; renewed HIGH gets a documented next review date. Repeated runs are idempotent.
- Successful second synthesis supersedes the first, creates lineage, changes summary ID/revision atomically; failed/cancelled/invalid second synthesis leaves first intact; old shared visibility cannot leak as current.
- Old records with identical source headlines but different claims are not collapsed; corrections/retractions and contradictory evidence preserve the disagreement and valid-as-of dates.
- After 8+ HIGH observations fill the old snapshot, a new lower-priority but material observation must eventually trigger consideration/synthesis; unchanged runs cost zero LLM calls.
- Simulate Celery crash and concurrent same-category synthesis, optimistic conflict, no LLM provider, and daily cap exhaustion. Archive/renewal must not hold writer locks during network inference.
- Admin overview shows overdue/retired/renewed HIGH rows and version history; historical searches still reach archived/superseded items via explicit operator filter.

## Exit

HIGH active memory is bounded by lifecycle policy even with no manual curation; one versioned current synthesis/category exists; shared references are synchronized with current status; a long-running category cannot starve new evidence; evidence history is preserved. Demonstrate with a simulated multi-year data/time fixture and repeated no-change maintenance cycles.
