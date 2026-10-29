# Editorial Memory, Shared Blackboard, and Deterministic Pipeline Roadmap

**Status:** IMPLEMENTATION IN PROGRESS — runtime work landed locally; release gates remain open
**Created:** 2026-10-29  
**Baseline:** `main` at `60fd18eda3a5e8852943e70bf32d4f957dbb3ff5` (revalidate against the implementation branch before coding)  
**Owner:** AInews editorial pipeline / memory services  
**Scope:** category-specific editor memory, bounded shared blackboard, retrieval correctness, synthesis/retirement, and reductions in unnecessary LLM work.

## Objective and decision

Replace the current flat, topic-keyed, append-only trend-memory exposure with **category-scoped editorial memory**, **a curated shared blackboard**, **source-backed atomic observations**, **versioned synthesized knowledge**, and a **deterministic, bounded retrieval API**. The LLM continues to handle genuine semantic judgment and writing; Python/SQL owns identity, deduplication, selection budgets, lifecycle mechanics, provenance checks, and scheduling.

Use the existing **SQLite/WAL + SQLAlchemy + Celery** stack. Do not add PostgreSQL, a stand-alone vector server, multiple memory databases per editor, or a general agent framework. A category is a logical namespace and editorial ownership boundary; `Article.category` is the primary owner, while `Article.topics` and tags remain searchable secondary associations. Preserve manually maintained `TopicNote` records as a distinct editorial guidance surface.

## Why this work is necessary: verified static findings

1. **Unbounded injection:** `services/trend_memory.py:get_memory_for_topics()` returns all matching active records without limit. The formatter injects all HIGH/MEDIUM records; only LOW is truncated to five. HIGH entries have `expires_at=None` by default.
2. **Not synthesis:** `consolidate_topic()` promotes LOW to MEDIUM within a time window surrounding the newest HIGH; it neither merges facts nor handles duplication, contradictions, or supersession.
3. **Subagent config resolution mismatch:** `tasks/research.py` passes `stage="researcher"` and `tasks/edit.py` passes `stage="editor"` into runners, but `SubagentConfig` defines `research`/`edit`. The runner resolves config again with the supplied stage identifier, apparently selecting the disabled fallback path.
4. **Prompt/tool mismatch:** configured `prompts/subagent_edit_contextualization.txt` omits `{trend_memory}` although the inline fallback template includes it; `pipeline.yaml` configures `trend_memory` but tool registry exports `get_trend_memory`. Audit the separate legacy `stages:` tool declaration as well.
5. **Retrieval inadequacy:** production research/editor injection uses exact string topic matches and priority+recency, not semantic ranking. `semantic_search_trends()` is exposed to admin search but preselects 500 records by priority/recency before similarity, losing older relevant records; has no relevance threshold or bounded/safe search parameters.
6. **Persistence/quality hazards:** proposed memories are extracted from `draft_article` rather than the editor's final artifact, have no topic normalization or durable idempotency key, and the extraction prompt asks for `NONE`/free-form entries although `chat_structured()` expects an `entries` schema. `TrendMemory.last_accessed_at` is present in ORM but no Alembic addition was found in the inspected 016–036 revisions; its `onupdate` does not mean read access.
7. **Insufficient end-to-end evidence:** existing tests cover individual operations and mocked subagent calls, not the configured YAML → runner → tool registry → rendered prompt → injected output path.

These are code-inspection findings, **not** claims about a running deployment or passing tests. Establish a reproducible baseline in M1.

## Design contracts

- **Storage vs exposure:** retaining history must not imply injecting history. The active prompt budget is independent of row count.
- **Three layers:** (a) evidence-backed atomic observations, (b) compact synthesized memories assigned to one owning editorial category, (c) curated cross-category blackboard references/index. Shared records are referenced, not copied.
- **Priority vs lifecycle:** importance is a ranking attribute; status (`active`, `synthesized`, `superseded`, `archived`) and operator `pinned`/review dates determine retention and exposure separately. Even pinned records are relevance/budget constrained.
- **Read-only contextual tools:** `memory_context`, `memory_search`, and `memory_get`; no model-initiated arbitrary database mutation. All writes pass deterministic validation and auditable service APIs.
- **Provenance:** every factual memory maintains links to article/source evidence, confidence/qualifiers, event or valid-as-of date where known, and synthesis lineage. Historical context must not become an unqualified claim of current truth.
- **Single authority:** production stages and subagents use one context-building service, one category normalization contract, and one canonical tool-name registry. Prevent prompt/data drift.
- **Cost and safety:** do not block publication on memory extraction or maintenance; preserve short DB transactions around LLM requests; use idempotent Celery jobs, bounded retries, explicit fallback, and metered context/model calls.

## Execution sequence and detailed handoffs

| Order | Plan | Deliverable | Dependency |
|---|---|---|---|
| M1 | [Correctness and observability](editor_memory_m1_correctness_20261029.md) | Fix wiring/schema hazards; hard caps; regression fixtures; baseline metrics | None |
| M2 | [Namespaces and retrieval](editor_memory_m2_scoped_retrieval_20261029.md) | Backward-compatible schema, per-category memory, shared read API, FTS5/hybrid search | M1 |
| M3 | [Synthesis, lifecycle, blackboard](editor_memory_m3_synthesis_blackboard_20261029.md) | Real synthesis, archival, review of HIGH, cross-category promotion, evidence lineage | M2 |
| M4 | [Deterministic pipeline offload](editor_memory_m4_deterministic_pipeline_20261029.md) | Reuse structured research; conditional LLM work; deterministic gates and tag/citation handling | M2; M3 for synthesis reuse |
| M5 | [Verification and rollout](editor_memory_m5_verification_20261029.md) | Shadow comparison, migration/rollback, deploy and operational evidence, acceptance matrix | M1–M4 |

M1 should land first as a focused corrective PR. M2/M3 should be independently gated and feature-flagged. M4 changes publication behavior and must be measured independently of the memory migration. M5 provides release closure; performance claims require measured baselines.

## Initial retrieval policy (calibrate with fixtures)

For ordinary research: max **900 memory tokens** across category summary, selected category records, shared records, and provenance. For editor: max **640**. For deep investigation: max **1,600**. Set hard record caps as well (for example local 8, shared 3), relevance thresholds, per-scope candidate limits and score explanations. Empty budgets stay empty; do not fill with unrelated HIGH records. Count with provider tokenizer if available, use a conservative deterministic estimator otherwise, enforce the final assembled total, and never slice a citation/memory halfway.

Default priority order: canonical scope eligibility → `active` state → hybrid textual relevance → evidence/recency/confidence → importance → diversity. Do **not** make HIGH bypass relevance or budget limits. Search across archived items only via explicit historical filter.

## Initial lifecycle policy (calibrate, not rigid truth)

LOW: review/expire after approximately 7 days; MEDIUM: 30 days; HIGH: review after 90 days. HIGH is **not perpetual active memory**. Aging triggers deterministic review eligibility; semantic reconsideration, if needed, occurs in a bounded batch. Operator-pinned items may be preserved, but never automatically include every pinned item. Prefer `archived` or `superseded` over destructive deletion when references must remain auditable. Retention of source articles and legal takedowns/deletions must be reflected in memory provenance.

## Risks and non-goals

Prevent memory poisoning through untrusted articles: treat stored text as data, not instructions; escape when constructing prompts, separate provenance from content, limit lengths, and keep tool authorization deterministic. A memory can inform coverage but should not be presented as external verification. When sources disagree, retain conflicting evidence/uncertainty; synthesis may state disagreement, not fabricate consensus. Do not replace the research/editor LLM with heuristics where judgment is essential. Do not implement online/offline training, autonomous write-capable memory tools, vector DB infrastructure, public search endpoints, or full multi-tenant policy in this line.

## Acceptance and handoff

Milestones require failing regression tests first for verified bugs, migration upgrade/downgrade rehearsal, no loss of old entries, token-budget invariants, read path with and without embeddings, cross-category isolation/blackboard tests, citation lineage, idempotent async jobs, and a fixed article-fixture comparison of recall/quality/cost/latency. See M5 for exact release gates.

## Implementation evidence — 2026-10-29

Implementation work is on `plan/editor-memory-blackboard-synthesis-20261029`; the worktree is uncommitted. M1 wiring, prompt/tool validation, structured final-artifact proposals, legacy retrieval bounds, schema/idempotency fixes and metrics are implemented. M2 provides the additive category store, evidence/scopes/lineage/summary schema, FTS5 with bounded lexical fallback, scoped context/search/get, backfill, and feature-flagged V2 reads. M3 adds lifecycle review/archive, evidence-grounded synthesis with persisted retry slots, shared-scope operator actions, diagnostics and a separately registered maintenance task. M4 adds independent rollback switches for deterministic prefiltering, conditional research/edit subagents, structured memory-candidate reuse and optional-call budgets. M5 adds a synthetic retrieval/trigger suite, read-only baseline script and migration/backfill rehearsal evidence. Details and limits are in [verification evidence](../docs/editor-memory-verification-20261029.md).

Verification on the final implementation worktree: full suite **5,074 passed, 6 skipped**; repository mypy **clean (507 source files)**; repository Ruff reports only the same five existing findings, with no new findings in changed code; `git diff --check` clean. A disposable synthetic SQLite/WAL upgrade reached revision 041 with integrity check `ok`, and repeated backfill was idempotent without deleting legacy rows. The local `instance/dev.db` is inconsistent with its Alembic revision and was not modified.

**M1:** code and local regression gates are implemented and pass. Runtime provider-call and article-quality baselines remain deployment evidence.

**M2:** additive migration, scoped retrieval, bounded context, restartable/provenance-preserving backfill and FTS shortlist filtering have local coverage. V2 reads remain disabled pending a target-database shadow retrieval comparison and backup/restore rehearsal.

**M3:** synthesis grounding/rejection/retry, conflicting lineage, persistent attempt caps, operator auth/CSRF/audit, and task registration have local coverage. Maintenance and synthesis remain disabled by default pending a scheduled no-change cycle and deployment canary.

**M4:** conservative prefilter, conditional triggers, candidate reuse and optional-call caps are implemented behind independent flags. Synthetic fixture triggers reduce optional calls from 32 to 16 in the test harness, but no provider-backed quality/cost/latency comparison has run; this is not a production savings claim.

**M5:** local synthetic and migration evidence is recorded. The roadmap remains **OPEN for release closure** because target deployment database migration/rollback, real-article human review, provider A/B and cost/latency comparison, shadow/category/synthesis canaries, scheduled no-change operation and backup/restore evidence require the deployment environment. Keep all behavior flags off until those gates are recorded; do not mark this roadmap COMPLETED based on local tests alone.
