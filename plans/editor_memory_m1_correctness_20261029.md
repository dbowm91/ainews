# M1 — Memory Retrieval Correctness, Wiring, and Baseline Observability

**Status:** OPEN / priority P0  
**Dependency:** none  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Outcome

Make the currently deployed memory mechanism verifiably functional and bounded **before** changing storage. Supply a transparent before/after baseline. This milestone must be deployable independently.

## Work packages

### M1.1: Reproduce stage-resolution and prompt/tool defects

Inspect `tasks/research.py:_perform_web_search_and_synthesis`, `tasks/edit.py:_gather_editor_context`, `services/subagent/runner.py`, `schemas/pipeline.py:resolve_subagent_config`, `pipeline.yaml`, and `services/subagent/registry.py`. Write failing integration tests using actual loaded `pipeline.yaml`, `SubagentStageConfig`, real registry selection and rendered external prompt templates. Stub only provider network responses, not stage resolver or template builder.

- Standardize stage identifiers to **`research`/`edit`** at config lookup and runner boundaries, retaining separate `researcher`/`editor` role names for model selection, events, and tracing. If aliases are kept, make a single explicit normalized mapping with tests.
- Ensure configured `prompts/subagent_edit_contextualization.txt` contains `<trend_memory>{trend_memory}</trend_memory>` and matches the tested inline fallback contract; add template schema/placeholder validation at configuration load.
- Resolve `trend_memory` versus `get_trend_memory`, and audit `pipeline.yaml:stages` against the active subagent path. Unknown configured tools should cause a clear validation error, not silently disappear.
- Confirm that `run_subagent_with_tools` does not return the disabled fallback after a correctly enabled configured stage, and that a formatted memory is actually visible to the intended model. Verify the research path as well.
- Replace `if not ... and not trend_memory` guards that are defeated by nonempty sentinel strings with explicit `has_memory` or typed context results.
- Test both enabled and disabled subagent paths, tool-capable and no-tools providers, and fallback behavior.

### M1.2: Fix persistence and extraction correctness

- Reconcile the `TrendMemory.last_accessed_at` ORM column with actual Alembic schema. Inspect SQLite `PRAGMA table_info(trend_memory)` and migration history; add the **next proper linear Alembic revision** only if missing, including index strategy and upgrade/downgrade tests. Do not assume `db.create_all()` reflects upgraded installs.
- Stop conflating `onupdate` with read access. If retaining access telemetry, update explicitly and asynchronously/batched; do not perform a write for every read.
- Feed successful final content (`final_article`) and valid structured research context to memory proposal, not raw draft alone. Do not propose from degraded/failed/unpublished artifacts without explicit policy. For a missing final artifact, fail safely with a measured skip.
- Align `TREND_MEMORY_PROMPT` with the `TrendMemoryEntries` structured response: empty `entries: []`, documented bounds and field schema; no free-form `NONE` contract. Validate canonical category/topic against configured taxonomy; reject malformed or out-of-scope entries, log safe diagnostics, and retain source article ID.
- Make proposal idempotent under Celery retry, duplicate post-finalize dispatch, and article re-edit. Define a stable article/version + normalized memory fingerprint and a DB uniqueness/upsert behavior; avoid deriving idempotency from a transient Celery task ID.
- Keep the DB transaction closed while the model responds; persist in one short transaction. Ensure failures never roll back a published article.

### M1.3: Immediate retrieval guardrails

- Extend `get_memory_for_topics` and the model-facing `get_trend_memory` tool with validated `limit` and `max_age_days` (clamped), consistent expiration filters, and safe topic-count constraints.
- Introduce a **hard assembled token budget** at injection sites, including HIGH/MEDIUM/LOW records, manual topic notes and blackboard-ready context fields. Set conservative defaults in typed `MemoryConfig`; no unlimited default. SQL limit and formatter cap must both be enforced.
- Avoid returning complete ORM rows where only signal and provenance are needed; ensure stable deterministic sort and no redundant fetches between prompt generation and tool use.
- Fix naive/aware datetime comparisons with a single persisted UTC convention and cross-SQLite tests. Do not use timestamp `onupdate` as a read signal.
- Preserve `semantic_search_trends` admin endpoint but cap query and limit; remove unused dead code, handle invalid vectors/dimension mismatch, and avoid false claims that it is used for normal pipeline retrieval.

### M1.4: Instrument and measure

Log per-stage `memory_candidates`, `memory_selected`, `memory_tokens`, `retrieval_mode`, `memory_age`, `memory_relevance` where available, `memory_miss_reason`, `subagent_config_enabled`, `tools_selected`, `template_id`, and `memory_proposal_skipped/created/failed`. Avoid per-article IDs as metric label cardinality; use traces/logs for IDs. Capture a redacted fixture set and baseline of provider calls, prompt tokens, context latency, failures, duplicated proposals and article quality.

### M1.5: Documentation

Update `docs/trend-memory.md`, `docs/context-service.md`, `architecture/subagent.md`, and relevant `AGENTS.md` claims to match the real implementation. Current docs incorrectly describe a retrieval `limit` that is absent from code and equate consolidation with merging. Keep documentation changes paired with tested behavior.

## Required tests

- Configured `edit`/`research` subagent is invoked with loaded config; disabled path is intentional; correct tools are selected and missing tool names are rejected.
- Edit contextualization contains the actual memory string in the final provider input for file-based **and** fallback templates.
- Memory with HIGH importance is capped even with 1,000 seeded entries; cap applies to rendered text, not only SQL row count.
- Exact-topic, empty topic, expired, timezone edge, missing embedding, and SQL-error behavior.
- Duplicate task dispatch/retry and article version update do not multiply identical memories.
- Existing upgrades that lack `last_accessed_at` are repaired, fresh install/downgrade work, and app queries do not fail due to column drift.
- No article publishing rollback when memory proposal fails; provider model responses never hold SQLite write locks.

## Exit criteria

All reproducible wiring failures have regression tests; configured memory is observed in the appropriate model request; zero unbounded HIGH retrieval paths remain; new retrieval budgets are measured and enforced; schema/retry hazards are closed; shadow metrics exist. Record test command output and any baseline failure explicitly. Only then start M2.
