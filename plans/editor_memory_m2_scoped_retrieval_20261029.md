# M2 — Category-Scoped Memory and Deterministic Hybrid Retrieval

**Status:** OPEN / priority P1  
**Requires:** M1 corrective wiring and prompt-size guardrails  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Outcome

Provide one back-compatible memory store with distinct editorial category scopes, optional shared visibility, attributable observations, and a deterministic, bounded read API. Existing topic memories must survive upgrade without downtime or data loss.

## Data ownership and schema

Use `Article.category` as the owning editorial category. `Article.topics` is a non-authoritative list of topical tags; use the canonical category/topic catalog (`topics.yaml` or its normalized configured form) to resolve aliases. Do **not** create one SQLite file, physical table, editor agent, or independent LLM process per category.

Before coding, inspect existing article category/topic producers and `TopicNote` semantics. Explicitly define the fallback for null, unmapped, or renamed categories (e.g., controlled `uncategorized` namespace), so old strings never become accidental new owners. The namespace model must be stable across display-name changes.

Suggested additive structures (names can change if more idiomatic):

- `memory_items`: stable ID, owning category ID, type (`observation`/`synthesis`), normalized fact/signal text, importance 1–3, confidence/qualifiers, observed/valid-as-of timestamp, status (`active`, `synthesized`, `superseded`, `archived`), review_due_at, expires_at, is_pinned (operator only), first_seen, last_evidence_at, last_reviewed_at, created/updated; embedding plus embedding_model_id/version/dimension if present. No inferred perpetual retention for importance 3.
- `memory_scopes` (or `memory_visibility`): unique (memory_id, scope_type, scope_id) association; owner category implicit or explicit, `shared` visibility references the same memory ID. Do not duplicate signal text across editor and blackboard rows.
- `memory_evidence`: memory_id, source article ID/version where possible, canonical source URL and source reference, evidence text/claim ID, first/last seen, support/conflict relation; source deletion behavior documented. Reserve room for evidence from multiple independent sources, not just a count.
- `memory_revisions` / `memory_lineage`: previous/next memory IDs or revision snapshots, synthesis membership (`synthesizes`, `supports`, `contradicts`, `supersedes`), actor/model/version, event time; audit-friendly and non-destructive.
- Category summary: one versioned *materialized read projection* per category (or `memory_items` of type `synthesis` with `summary` scope) with concise content and provenance; avoid a second uncontrolled source of facts.

Keep `TopicNote` separate for human editorial instructions; do not silently migrate administrator-authored policy notes into AI-factual memories. Preserve old `TrendMemory` during initial deployment. If a simpler minimal schema meets these constraints, prefer it over needless proliferation, but **do not** omit evidence lineage or lifecycle state.

Add indexes for category + status + importance + review_due, candidate lookup, evidence source/article/version, shared scope, and idempotent fingerprints. Use source/article foreign-key behavior compatible with SQLite foreign keys and existing backup/restore. Ensure uniqueness and check constraints where portable; perform writes in short transactions.

## Online migration and safe transition

1. Write Alembic upgrade and downgrade tests for both empty and populated SQLite/WAL fixtures, including old HIGH entries with no expiry, expired entries, duplicate signals, stale topic spellings, and missing embedding fields. Do not destroy rows in `trend_memory` during M2.
2. Backfill in bounded, restartable batches with a deterministic mapping: primary category from linked `Article.category` where valid; otherwise canonicalize old `TrendMemory.topic` when unambiguous; otherwise send to `uncategorized` and tag for review. Track old→new IDs and migration versions to avoid duplicate imports.
3. Preserve all source links and original signal text. Unknown validity/precision stays unknown; do not convert historical signals into current truths.
4. Keep legacy reads available behind a compatibility facade while new writes land in the new store. Choose one authoritative write path or well-tested dual write with idempotency; avoid diverging mutable copies.
5. Run backfill dry-run counters and verify counts, sample provenance, category distribution and query behavior before switching. Provide a rollback switch and downgrade protocol: reverting an application version must not orphan memory or drop retained history.
6. Plan a separate future legacy table retirement only after verification; not part of M2.

## Retrieval API and behavior

Implement `services/memory/` or similarly cohesive service split: `models`, `repository`, `ranking`, `context_builder`, `lifecycle` (later), and `tools`. Names are proposals; preserve clean dependency layering. Provide typed, read-only contracts:

- `memory_context(category_id, article_id, token_budget, stage)`: automatic context assembly with summary + relevant local observations + shared results + compact provenance; deterministic output with item IDs and score reasons.
- `memory_search(query, scope=own|shared|combined, limit, status_filter=active, category_id=..., historical=False)`: validated, top-k search, explicitly scoped; no arbitrary cross-category reads by default.
- `memory_get(ids, category_id, allow_shared=True)`: evidence and history for selected IDs, bounded record count and response size.

The application, not model-generated tool arguments, derives the acting article's category. Tool parameters may narrow the scope but must not elevate permission/access to all category history. Register tools using the canonical registry; validate configured tool names at startup. For research/editor, expose a small read-only tool set, not the whole database.

## Hybrid deterministic search

Use SQLite FTS5 as the baseline lexical index (reuse patterns from existing article FTS). Normalize Unicode, known aliases, entity identifiers, dates and title terms without LLM dependency. Candidate selection must be indexed and bounded by category/shared scope, status and exclusion filters **before** loading full rows. Rank with BM25 and explicit quality/recency/importance weights. If local embeddings exist, rerank or union a bounded embedding candidate set; never rely exclusively on the current `semantic_search_trends` first-500 priority/recency cutoff. A fixed finite embedding scan can be a documented phase-one fallback, with measurement and thresholds; do not pretend it provides full corpus semantic recall.

- Minimum relevance cutoff, per-source diversity, near-duplicate collapse, and stable tie ordering.
- TTL/status filtering occurs in query, with a final post-query safety check. Archived and superseded entries excluded by default.
- Use `sentence-transformers` opportunistically; no heavyweight inference service required. No embedding means lexical fallback, never empty memory solely because dependency is absent.
- Check vector dimensions/model versions explicitly; do not silently use `zip(..., strict=False)` on mismatched vectors. Avoid embedding JSON decoding for every normal read.
- FTS5 availability must have an installation/migration smoke check and a bounded deterministic fallback. All SQLite writes and triggers remain WAL-safe.

## Context budget and provenance

Provide configurable hard caps: per-stage token budget; maximum candidate/selected rows; per-category versus shared allocation; maximum query/record size; maximum tool iterations and tool output chars. Do not inject `TopicNote` and memory twice (automatic context plus tool call) unless specifically requested. For summaries, require cited item/evidence IDs; the LLM sees memories as historical editorial data, not external verified sources. Attach an as-of date for time-sensitive claims.

Retrieve relevant material once per article/stage and serialize a stable typed `ContextPack` with `memory_ids`, `scope`, `ranking_features`, `tokens_estimate`, `truncated`, `cache_version`; render separately as escaped prompt text. Cache keyed by article revision/category, memory index revision, retrieval params, and model/tokenizer, rather than a stale global key. Do not cache access to a now-superseded record indefinitely.

## Tests / acceptance

- Independent category isolation: A category A editor cannot see category B private records; promoted shared records are visible to both without duplication.
- Alias, rename, unknown category, multi-topic article, null category, and old `TrendMemory` import cases.
- FTS matching, optional embeddings, no-model fallback, adversarial lexically similar irrelevant records, relevance thresholds, stable scoring, diversity, and older high-value evidence.
- Input bounds and strict token budget even with 1,000+ HIGH rows; historical scope opt-in and no cross-category leakage.
- SQLite upgrade/downgrade, partial/interrupted/repeated backfill, concurrent reads/updates, FTS index rebuild and legacy facade.
- Instrument `retrieval_mode`, `selected_count`, `selected_tokens`, scoped recall and latency. Query plans avoid full table scan at normal corpus size except explicitly bounded optional embedding rerank.

M2 closes when all actual researcher/editor context assembly uses the new retrieval API behind a feature flag, with functional fallback to existing bounded M1 reads and no semantic-model requirement for lookup.
