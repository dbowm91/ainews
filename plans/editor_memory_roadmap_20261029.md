# Editorial Memory, Shared Blackboard, and Deterministic Pipeline Roadmap

**Status:** C01–C03 implemented with local evidence; C05 merge-readiness corrective OPEN on draft PR #19. No active deployed DB requires migration evidence; all V2 flags remain off and later activation is separate.
**Created:** 2026-10-29  
**Baseline:** `main` at `60fd18eda3a5e8852943e70bf32d4f957dbb3ff5` (revalidate against the implementation branch before coding)  
**Owner:** AInews editorial pipeline / memory services  
**Scope:** category-specific editor memory, bounded shared blackboard, retrieval correctness, synthesis/retirement, and reductions in unnecessary LLM work.

## Intended operating scope

AInews is being developed for **personal/local or privately operated use**. This roadmap is not a public product launch, general distribution, hosted-service readiness, or multi-platform installer certification program. Treat "release" and "rollout" in earlier milestone language as **code integration and optional enablement on the owner's installation**, not a public release. Memory correctness and actual SQLite backup/restore remain important regardless of who can access the instance. Unrelated CI/installer failures are tracked but are not intrinsically blockers to a disabled memory feature; see [C04](editor_memory_corrective_04_release_verification_20261029.md).

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
| M2 | [Namespaces and retrieval](editor_memory_m2_scoped_retrieval_20261029.md) | Backward-compatible schema, per-category memory, shared read API, ranked lexical FTS5 and bounded SQLite fallback | M1 |
| M3 | [Synthesis, lifecycle, blackboard](editor_memory_m3_synthesis_blackboard_20261029.md) | Real synthesis, archival, review of HIGH, cross-category promotion, evidence lineage | M2 |
| M4 | [Deterministic pipeline offload](editor_memory_m4_deterministic_pipeline_20261029.md) | Reuse structured research; conditional LLM work; deterministic gates and tag/citation handling | M2; M3 for synthesis reuse |
| M5 | [Optional local behavior validation](editor_memory_m5_verification_20261029.md) | Limited real-article comparisons and staged enablement *after merge*, not deployed-database migration evidence | M1–M4 code; separate activation |

M1 should land first as a focused corrective PR. M2/M3 should be independently gated and feature-flagged. M4 changes publication behavior and must be measured independently of the memory migration. M5 closes private-instance implementation/activation checks; performance claims require measured baselines, not a public release process.

## Initial retrieval policy (calibrate with fixtures)

For ordinary research: max **900 memory tokens** across category summary, selected category records, shared records, and provenance. For editor: max **640**. For deep investigation: max **1,600**. Set hard record caps as well (for example local 8, shared 3), relevance thresholds, per-scope candidate limits and score explanations. Empty budgets stay empty; do not fill with unrelated HIGH records. Count with provider tokenizer if available, use a conservative deterministic estimator otherwise, enforce the final assembled total, and never slice a citation/memory halfway.

Default priority order: canonical scope eligibility → active/expiry/review eligibility → lexical relevance and FTS5 rank → evidence/recency/confidence → importance → diversity. Do **not** make HIGH bypass relevance or budget limits. Search across archived items only via explicit historical filter. Local embedding union/reranking is not implemented; it remains gated pending target-device evidence.

## Initial lifecycle policy (calibrate, not rigid truth)

LOW: review/expire after approximately 7 days; MEDIUM: 30 days; HIGH: review after 90 days. HIGH is **not perpetual active memory**. Aging triggers deterministic review eligibility; semantic reconsideration, if needed, occurs in a bounded batch. Operator-pinned items may be preserved, but never automatically include every pinned item. Prefer `archived` or `superseded` over destructive deletion when references must remain auditable. Retention of source articles and legal takedowns/deletions must be reflected in memory provenance.

## Risks and non-goals

Prevent memory poisoning through untrusted articles: treat stored text as data, not instructions; escape when constructing prompts, separate provenance from content, limit lengths, and keep tool authorization deterministic. A memory can inform coverage but should not be presented as external verification. When sources disagree, retain conflicting evidence/uncertainty; synthesis may state disagreement, not fabricate consensus. Do not replace the research/editor LLM with heuristics where judgment is essential. Do not implement online/offline training, autonomous write-capable memory tools, vector DB infrastructure, public search endpoints, or full multi-tenant policy in this line.

## Acceptance and handoff

Milestones require failing regression tests first for verified bugs, migration upgrade/downgrade rehearsal, no loss of old entries, token-budget invariants, read path with and without embeddings, cross-category isolation/blackboard tests, citation lineage, idempotent async jobs, and a fixed article-fixture comparison of recall/quality/cost/latency. See M5 and C04 for local activation checks.

## Corrective pass registration — 2026-10-29

The implementation has undergone code and local-evidence review. One focused **C05 merge-readiness corrective** remains; later M5 staged feature activation is independent of the merge. Detailed corrective overview: [editor memory corrective pass](editor_memory_corrective_pass_overview_20261029.md). These are *implementation plans, not completed fixes*.

| Corrective | Priority | Plan | Focus |
| --- | --- | --- | --- |
| C01 | P0 | [Relevance-first retrieval, feature gates and tool budgets](editor_memory_corrective_01_retrieval_gates_20261029.md) | Prevent importance-first truncation of relevant FTS matches; scope reads; cumulative context/tool bounds; coherent current synthesis |
| C02 | P0 | [HIGH lifecycle, synthesis succession and shared currentness](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) | FINITE active HIGH review/retirement, single current synthesized view, fair dirty-evidence selection and shared-state cleanup |
| C03 | P1 | [Memory candidate provenance and importance](editor_memory_corrective_03_candidate_quality_20261029.md) | Decouple evidence confidence from editorial significance; validate final-article evidence and dedup |
| C04 | P0 operational | [CI baseline attribution and scoped checks](editor_memory_corrective_04_release_verification_20261029.md) | CI baseline and disposable checks documented; **no target deployed DB or migration evidence required for merge** | 
| C05 | P0 merge | [Merge-readiness final corrective](editor_memory_c05_merge_readiness_20261030.md) | Suppress stale category summaries, final-HEAD tests/static checks, docs/registry cleanup and PR review handoff |

**Execution order:** C01 first; C02 and C03 separately. CI baseline and disposable migration checks are recorded under C04. Keep V2 read, maintenance, synthesis and optional optimizations **disabled until their staged local behavior checks pass**. Maintain original M1–M5 plans; this corrective pass supplements them.

**Merge vs later activation:** C05 gates **merging disabled code**; it does not require a restored, migrated or benchmarked database. If features are later enabled, stage scoped retrieval first, maintenance/synthesis second, and optional inference-saving features only after limited real-article comparisons. All these gates currently default off.

**Current CI:** GitHub Actions implementation SHA `f3aa498e`, runs `40928360912` (CI) and `40928361243` (Installer Smoke), failed. Logs indicate baseline Ruff findings, missing CI test secrets/`.env`, unavailable Redis in theme tests, Gitleaks API permission error, Werkzeug audit advisory, installer runner disk exhaustion, and a broken aarch64 launcher path. Root causes must be classified against `main` before attribution to the memory branch. The local 5,074-passing test claim requires relevant CI/reproduction checks; classify inherited/unrelated CI jobs independently rather than blocking private memory work on the entire installer matrix. See C04.

## Implementation evidence — 2026-10-29

Implementation work is committed on `plan/editor-memory-blackboard-synthesis-20261029` as `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636` (PR #19, still unmerged at corrective-pass review). M1 wiring, prompt/tool validation, structured final-artifact proposals, legacy retrieval bounds, schema/idempotency fixes and metrics are implemented. M2 provides the additive category store, evidence/scopes/lineage/summary schema, FTS5 with bounded lexical fallback, scoped context/search/get, backfill, and feature-flagged V2 reads. M3 adds lifecycle review/archive, evidence-grounded synthesis with persisted retry slots, shared-scope operator actions, diagnostics and a separately registered maintenance task. M4 adds independent rollback switches for deterministic prefiltering, conditional research/edit subagents, structured memory-candidate reuse and optional-call budgets. M5 adds a synthetic retrieval/trigger suite, read-only baseline script and migration/backfill rehearsal evidence. Details and limits are in [verification evidence](../docs/editor-memory-verification-20261029.md).

Verification on the final implementation worktree: full suite **5,074 passed, 6 skipped**; repository mypy **clean (507 source files)**; repository Ruff reports only the same five existing findings, with no new findings in changed code; `git diff --check` clean. A disposable synthetic SQLite/WAL upgrade reached revision 041 with integrity check `ok`, and repeated backfill was idempotent without deleting legacy rows. The local `instance/dev.db` is inconsistent with its Alembic revision and was not modified.

**M1:** code and local regression gates are implemented and pass. Runtime provider-call and article-quality baselines remain deployment evidence.

**M2:** additive migration, scoped retrieval, bounded context, restartable/provenance-preserving backfill and FTS shortlist filtering have local coverage. V2 reads remain disabled pending a target-database shadow retrieval comparison and backup/restore rehearsal.

**M3:** synthesis grounding/rejection/retry, conflicting lineage, persistent attempt caps, operator auth/CSRF/audit, and task registration have local coverage. Maintenance and synthesis remain disabled by default pending a scheduled no-change cycle and deployment canary.

**M4:** conservative prefilter, conditional triggers, candidate reuse and optional-call caps are implemented behind independent flags. Synthetic fixture triggers reduce optional calls from 32 to 16 in the test harness, but no provider-backed quality/cost/latency comparison has run; this is not a production savings claim.

**M5:** local synthetic and migration evidence is recorded. The roadmap remains **OPEN for private-instance activation closure**: before enabling V2, verify migration/backup/restore on a copy of the owner's real database, relevant category isolation, representative article retrieval, and bounded lifecycle behavior. Provider-backed comparisons are needed before asserting savings or enabling optional M4 optimizations, not to merge feature-disabled code. Existing unrelated CI/installer work is separate; do not mark the roadmap COMPLETED based on local synthetic tests alone.
