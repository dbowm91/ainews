# C01 — Relevance-First Retrieval, Memory Gate Boundaries, and Tool Budgets

**Status:** OPEN / P0. **Baseline:** PR #19 `f3aa498e4d0d`.
**Parent:** [Corrective Overview](editor_memory_corrective_pass_overview_20261029.md).
**Related milestones:** M1, M2, M5.

## Reproduced by code inspection

- `services/memory/repository.py:_candidate_ids()`: FTS5 returns a bounded shortlist, but each owner/shared SQL query then `ORDER BY importance DESC, created_at DESC LIMIT` before `memory_search()` computes overlap/quality score. Older more-relevant hits can be removed from the set before ranking. FTS order/rank is discarded. A broad OR-term FTS match plus initial capped shortlist can also bias recall.
- `memory_search()` uses lexical overlap with a 0.15 cutoff and does not integrate optional local embeddings; it currently describes a lexical pathway as `hybrid_lexical`. `memory_context()` uses a category/title query and keeps only `item_type == "observation"`, filtering out all synthesis records including shared synthesis; summary is inserted separately.
- `pipeline.yaml` advertises `memory_search`/`memory_get` to enabled research/edit subagents regardless of `memory_v2_enabled`. `services/subagent/registry.py` builds the V2 tools even if the flag is off. `services/trend_memory.py:_save_memory_entries()` calls V2 `add_observation()` irrespective of that flag. This may be intentional dual-write, but a **read toggle cannot be described as a full V2 isolation/rollout switch**.
- Automatic context assembly has a token budget, but consecutive tool calls can return independent memory payloads without a cumulative article/stage request budget. `memory_get()` independently returns up to 20 items and up to 20 evidence/lineage entries per item, each with strings; tool binding slices to 8 IDs but still can be repeated.
- `services/subagent/registry.py` can construct tools with an `uncategorized` fallback when trusted category context is absent. Audit all registry call sites to ensure missing trusted category cannot unintentionally expose data.

## Work package C01.1 — Candidate ranking before truncation

1. Introduce a typed `MemoryCandidate` carrying ID, owner/shared eligibility, FTS rank or BM25, match mode and score inputs. Scope/status/expiry filters must run in SQL **before** row fetch or ranking.
2. Preserve FTS5's ordered rank in the shortlist, then compute final ranking before a final top-k. Avoid the present importance-first SQL truncation of FTS hits. Choose a bounded overfetch budget (e.g., at most 5–10x final k, globally capped) and enforce per-scope minimum/caps and deterministic tie order.
3. For FTS-unavailable queries, use bounded SQLite lexical candidate generation with a documented query plan, not an unbounded full-corpus ORM materialization. Reuse existing FTS5 tables/triggers. Handle empty/no-match, punctuation, Unicode, synonyms, stale dates, and malformed FTS query syntax safely.
4. Dedup owner/shared references by memory ID, favor owner-local visibility, apply source-domain/category diversity **after** ranking, and hard-filter not-active/expired records again before serialization.
5. Establish a real optional embedding union/rerank strategy only if target hardware benchmarks justify it: version/dimension checks, local lazy initialization, bounded candidate set and strict no-embedding fallback. If not implemented now, document accurately as *lexical FTS5 retrieval* and keep hybrid work explicitly gated rather than mislabeling it.

## Work package C01.2 — Current synthesis and category context

- Define how `memory_context()` combines category summary, currently active synthesized memories, atomic observations, and genuinely shared records without duplicate facts or double-consuming the budget. Preserve existing evidence IDs and an `as_of`/uncertainty label. Ensure cross-category shared synthesis is eligible when relevant.
- If a category summary conveys the current synthesis, favor it over repeating that synthesis verbatim as an individual record; use item IDs to detect duplication. A retrieval result should be explainable and include the current synthesis revision/visibility.
- Pass article ID to the query builder for provenance and exclude self-generated or superseded article outputs if they risk recursive context. Add tests for null/renamed categories and multi-topic articles.

## Work package C01.3 — Orthogonal gates and budgets

Define **separate explicit controls** for (a) V2 schema/write compatibility, (b) V2 automatic context read, (c) V2 tool exposure, (d) background maintenance and synthesis, (e) optional deterministic/LLM optimizations. Do not reuse a single boolean to imply all five. Feature-off must be safe on legacy schema and must not try to query new tables; feature-on must fail fast with actionable migration preflight. Migration/dual-write intent must be explicit and idempotent.

- Subagent registry only creates V2 tools when both feature capability and trusted article category are present. Missing category context should fail closed for scoped read tools or explicitly return no data; do not silently grant an arbitrary namespace.
- Apply a **cumulative per-article/stage memory-tool budget** that covers automatic injections + all tool responses and retries, with max tool result chars/records, bounded iterations and logging of `remaining_budget`. Enforce server-side even if tool schema/request asks for more.
- Use the established prompt-builder token estimator as a conservative fallback and count wrapper/JSON/provenance. Do not slice memory/evidence mid-record; return a bounded `truncated` marker or empty result.
- Tool selection errors should be detectable in tests and logs. Keep `TopicNote` editorial instructions distinct from factual memory and avoid automatic/tool double inclusion.

## Mandatory regression tests

1. Seed 80–200 high-importance new but irrelevant FTS hits ahead of an older exact-phrase match; assert the older relevant memory wins final top-k.
2. FTS5 present vs absent, quoted punctuation/Unicode, ambiguous synonyms, no embedding, incompatible embedding version, wrong vector shape and candidate caps.
3. Shared synthesized record relevant to a foreign category appears once; active local summary + corresponding synthesis not duplicated; archived/superseded records never enter default context.
4. Two distinct categories cannot read each other's private observations, synthesis or evidence through `memory_search`, `memory_get`, or tool calls.
5. With V2 reads/tools **off**, no V2 SQL query or tool access, even if subagents are enabled; with unupgraded schema, activation yields a clear preflight error. Test planned dual-write behavior separately.
6. Multiple sequential model tool calls cannot evade stage token/char/record caps. 1,000 HIGH or pinned records still produce bounded context and no cross-stage budget leak.

## Exit

Relevance-first, scope-correct retrieval reaches annotated fixture thresholds without sacrificing old relevant memories; all flags have testable non-overlapping semantics; prompt/tool budgets are cumulative; synthesis/blackboard context is current and nonduplicative. Run `EXPLAIN QUERY PLAN`, record measured p50/p95 on representative SQLite data, and attach before/after selected IDs and cost/latency metrics.
