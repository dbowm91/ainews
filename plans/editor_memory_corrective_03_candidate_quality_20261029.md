# C03 — Editorial Importance, Candidate Extraction, and Evidence-Quality Corrections

**Status:** OPEN / P1. **Baseline:** PR #19 `f3aa498e4d0d`.
**Parent:** [Corrective Overview](editor_memory_corrective_pass_overview_20261029.md).
**Related milestones:** M1, M3, M4.

## Inspection findings

`services/trend_memory.py:_deterministic_candidates()` accepts medium/high-confidence `ResearchBrief.key_claims` whose source matches `source_article`, the original URL, or a listed external source; it maps `confidence == "high"` to `importance=3` and medium to 2. **Evidence confidence and editorial importance are independent axes.** A reliably reported trivial fact is not a durable HIGH trend. Enabling `memory_candidate_reuse_enabled` risks generating numerous perpetual/long-lived high-priority entries. The current `_save_memory_entries()` writes both legacy and V2 memories, even with the V2 read flag disabled, and V2 dedup uses normalized text rather than semantic identity.

The proposal path has a genuine improvement: it uses `Article.final_article` and `ResearchBrief` rather than `draft_article`. Preserve that. But deterministic candidate acceptance still needs explicit article/final-source alignment, material significance checks and lifecycle caps before bypassing the memory-proposal LLM.

## C03.1 — Separate validated confidence and editorial priority

- Define a schema/algorithm distinction:
  - `evidence_confidence`: quality/corroboration/validity of the supporting source-backed claim; numeric or enumerated, with `unknown` supported.
  - `editorial_importance`: significance to the coverage area, temporal persistence, expected downstream relevance and strategic impact; independently estimated.
  - `retention/review_due`: policy derived from type, relevance, fresh evidence and operator decisions; not automatically perpetual for high evidence confidence.
- For deterministic extraction, begin with **MEDIUM or lower importance** unless objective significance criteria are met (e.g., clearly matched entity, policy/technology version milestone, multi-source corroboration, impact threshold). Ambiguous significance should be escalated to a configured semantic judge or remain a low-priority observation pending synthesis.
- Do not use a hardcoded `confidence == high -> importance=3` mapping, and do not let category labels or presence of a URL alone boost importance.
- Store the decision features, policy version and reason code so later retuning can be audited and replayed. Reuse existing `MemoryItem.confidence` and `importance`; extend schemas minimally only if evidence representation requires it.

## C03.2 — Trust/source and final-artifact validation

1. Confirm each candidate corresponds to a claim actually supported in **the final published article and research evidence**, not just a previously generated brief. A brief source URL must be known/validated, and text must not be accepted simply because it appears in `external_sources`. Reuse existing article provenance/citation validators and do not add a second speculative fact checker.
2. Preserve an explicit evidence provenance tuple: source article and version, original URL, cited external source URL/claim identity, observed/valid-as-of time, whether independently corroborated, uncertainty and correction status. Do not treat an AInews article as independent external verification.
3. Validate `source_article` as a special marker only when linked to the actual source article and final output. Normalize URLs, reject invalid source schemes and contradictory `valid_as_of` timestamps; avoid arbitrary external requests from candidate extraction.
4. Reject or defer ephemeral/unsupported/highly time-sensitive candidates as **active durable memory** unless date and relevance are encoded. Never silently imply a historical claim is currently true.
5. Use deterministic exact dedup plus explicit relation candidates for near-duplicates; exact-text fingerprints must not merge distinct conflicting claims, and repeated publishers must not count as independent corroboration. Corrected/retracted claims should produce supersession evidence rather than duplicate active variants.
6. The async proposal task must remain idempotent across retry/edit/republication. A claim unmodified by article version should reuse the observation and add new evidence; a materially revised/corrected claim should be distinguishable. Ensure no SQLite transaction remains open during model inference, and failure cannot roll back publication.

## C03.3 — Avoid inference work where evidence and decisions are deterministic

- Keep separate flags for deterministic candidate extraction, conditional semantic proposal, semantic synthesis and read-path activation. Extraction should return typed `candidate`, `accepted`, `deferred` and `rejected` states with reason codes.
- If no valid novel candidate exists, skip the memory-proposal LLM and record the skip. If the candidate is objectively supported but significance is uncertain, optionally send a bounded batch to a configured semantic judge; do not invoke once per claim. If no provider is configured, preserve the candidate in a non-HIGH or review-required form rather than fabricating judgment.
- Reuse `ResearchBrief.key_claims` and `services/quality_report.py` / `services/article_provenance.py` contracts. Do not add a third LLM pass that repeats the existing research/editor work.
- Keep `reserve_optional_llm_call` semantics explicit: distinguish a cap-induced skip from provider failure and Redis bypass; a failed cap backend must not be reported as actual savings. Record provider/model, per-article optional call count, prompt/response/cache tokens where available and accepted-candidate counts.

## Mandatory tests

- High-confidence but inconsequential fact is never assigned HIGH solely from confidence. High-impact uncertain fact cannot be silently promoted as reliable. Explicit source confidence and importance are tested independently.
- Two articles repeat one fact with independent sources: one V2 observation with two distinct evidence records, not two immortal HIGH memories. Same publisher duplicated source is not counted twice. Source article revision retains version provenance.
- A disputed/newly corrected claim is not merged into the earlier valid state or presented as current fact; article-final discrepancy causes reject/defer, not silent commit.
- Invalid source URL, fabricated `ResearchBrief` claim, missing final artifact, degraded article, and invalid topic/category do not create active factual memory.
- Repeated Celery proposal and re-edit are idempotent; the legacy/V2 dual-write gate is explicit and safe with unupgraded schema.
- On a corpus of routine articles, test the number of skipped, accepted and escalated candidates with and without the feature enabled; no unsupported model-call savings or quality claim.

## Exit

A high-confidence/low-importance claim does not become an endless HIGH observation; accepted factual memory remains final-article-grounded, sourced, revision-aware, idempotent and auditable. Provider-backed quality comparisons show that fewer optional proposal calls do not measurably harm novelty detection, source attribution or correction handling.
