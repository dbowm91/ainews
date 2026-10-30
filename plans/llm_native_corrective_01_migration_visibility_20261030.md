# C01 — Alembic convergence, public visibility contract and migration safety

**Status:** IMPLEMENTED; local migration and publication tests pass. C01 migration qualification is closed; restored-target rehearsal is not required at this stage (see C05).
**Scope decision:** Historical steps below that require restoring an operator database, measuring migration against its data volume, or rehearsing rollback on that copy are superseded for this roadmap. They are not required evidence; combined fresh/idempotent/both-parent SQLite tests close this migration workstream.
**Parent:** [corrective pass](llm_native_corrective_pass_overview_20261030.md).
**Prerequisite:** none; complete before combining PR #19 and PR #20 or migrating a real AInews installation.

## Reproduced-from-source conflict

- PR #20 adds migrations/versions/037_llm_native_publication.py, revision 037_llm_native_publication, down_revision 036_api_token_phase2.
- Open PR #19 independently introduces 037_trend_memory_proposal_idempotency -> 038_category_memory_store -> 039_memory_synthesis_runs -> 040_memory_maintenance_state -> 041_memory_synthesis_attempts -> 042_editor_memory_corrective_state -> 043_memory_synthesis_fairness_cursor, beginning after the same 036_api_token_phase2.
- GitHub reports the PRs individually mergeable against main; that does not verify that both migration histories can be deployed in either order.
- Shared services/publication.py implements a strict published_article_query() (publicly_visible=true + pipeline_status=done + nonblank final content), but routes/public/api.py category/tag counts, services/mcp_public.py, some feed/search and short-link paths independently check fewer conditions. services/auto_review.py has a direct publicly_visible=True assignment on one route. Audit for policy drift rather than assuming centralized logic makes every path safe.

## Decision to implement

Choose a single canonical revision graph **based on merge order**, not a blindly duplicated 037 revision. Preferred if PR #19 lands first: rebase PR #20 onto the resulting main; reissue its migration with a unique revision ID after memory revision 043 (or actual head discovered at rebase time), correct down_revision, and update every fixture, Alembic assertion and doc. If PR #20 lands first: PR #19 must rebase and renumber its first revision after the now-merged newsletter revision, with all descendants updated. A deliberate two-head Alembic merge revision is only acceptable if the combined upgrade/downgrade graph is validated from both deployed states; do not introduce divergent permanent heads or fake/stamp a head to hide state.

**Important:** Revision names are not a sequence guarantee beyond current PR source. Query real alembic heads/history when implementing, including changes to PR #19 after this plan. Do not rewrite applied production migrations in place; if either branch already migrated an operator database, use a new merge/repair revision and explicit upgrade path instead of silently changing an applied revision.

## Work items

1. Establish baseline migration graph for main, PR #19 and PR #20, and inspect migrations/versions plus models imported by db.create_all(). Record actual heads and any local database drift. Decide merge order jointly; update plan dependency.
2. Write pre-fix migration conflict test or script that imports the combined revision graphs and proves multiple independent heads from 036. Add a code-integration check that invokes alembic heads and fails if multiple heads remain without an approved merge.
3. Implement the appropriate linearized or explicit merge revisions without destructive table rebuilds. Protect old Newsletter, newsletter_articles, subscribers, article internal IDs, Article.public_id generation, and PR #19 memory evidence/reference tables. Ensure schema equality against ORM metadata, especially newsletter_occurrences.dispatched_at and final_article/publicly_visible/published_at backfill.
4. Handle SQLite-specific constraints. Test UNIQUE identity backfill and collision handling; index duplication; batch schema alterations and integrity in local tests. Make migration failure diagnosable. A restored operator database rehearsal is not required for this stage.
5. Centralize a **single** publicly_visible/published-only predicate for public article read/list/category/tag/search/RSS/sitemap/related/short-link/newsletter selector paths. Use a service-level predicate/DTO contract where direct joins differ; no public count may include a row that detail would reject. Audit admin-review/auto-review/scheduled-publish/failed-reprocess transitions and cache invalidation (withdrawal before/after cached HTML and API).
6. Clarify historical numeric /article/<int:id> policy: remain disabled by default; optional legacy redirect only on visible article; no numeric IDs in returned DTO, cursors, shares or next-page URLs. Coordinate C02 for cursor conversion. Make retained short links honor the exact published predicate.
7. Update docs/operations.md, docs/api.md, docs/newsletter-pipeline.md, plans/llm_native_m1_public_identity_visibility_20261029.md and parent roadmap only when corresponding code/evidence exists.

## Tests and evidence matrix

- **Migration graph:** fresh DB and each supported parent state -> combined latest. SQLite PRAGMA integrity_check, foreign_key_check, Alembic heads; verify representative Article/Newsletter/Subscriber/Memory schema and fixture-row preservation. Restored copies of operator databases and backup artifacts are not required.
- **Idempotent data:** existing published, unfinished, skipped, review, degraded/failed rows; duplicate public-ID generation injected; historical newsletter HTML stays admin-only; all memory evidence survives. Re-run migration on disposable clone or exercise safe stamp/no-op path as applicable; downgrade only with explicit preservation plan.
- **Cross-surface:** create done+visible+final, done+hidden+final, skipped+visible+final, done+visible+blank, review+visible+final, scheduled+not due and withdrawn rows. Assert detail/list/count/search/RSS/sitemap/MCP/API/short link agree and no hidden count or snippet leaks. Post-withdrawal cache probe.
- **Lifecycle:** pipeline completion, auto-approve, scheduled release, manual admin review, failed/retry/degraded transition call the same publication helper; published_at semantics and explicit withdrawn behavior stable.
- **Operator qualification:** no operator-database restore/replay evidence is required for this stage. Target application runtime qualification is scoped separately in C05.

## Files / boundaries

migrations/versions, alembic config/env.py, models/article.py, models/newsletter.py and combined PR #19 memory models, services/publication.py, services/auto_review.py, routes/public/{api,feeds,links}.py, services/{article,related,rss}.py, services/search/{sqlite_fts,hybrid}.py, services/newsletter_editions.py, tests/test_llm_native_publication.py plus dedicated combined-migration and publication-parity tests. Avoid unrelated repository migrations.

## Stop criteria and handoff

Do not merge or enable both feature sets with independent, unapproved heads. Do not declare safe public access while publication membership/counts differ between surfaces. Record exact migration IDs, merge order, sample DB checks, downgrade/restore policy, failed reproduction, fixed test commands, and implementation SHAs. C05 validates target-instance execution after this work.

## Implementation evidence — 2026-10-30

- Publication migration renumbered to `044_llm_native_publication` after the existing `036_api_token_phase2` base. `045_merge_publication_and_memory` has both real parents; `046_newsletter_distribution_intent` is the sole current head.
- Fresh SQLite upgrade, repeated upgrade, and upgrades beginning at each independently deployable parent (`043_memory_synthesis_fairness_cursor` and `044_llm_native_publication`) converge to `046`; integrity check passes and representative memory/newsletter schema is present (`tests/test_smoke_migrations.py`). These tests close C01 migration qualification; a restored operator database is not required for this roadmap.
- `published_article_filters()` now governs public listing/count/link/related/REST/MCP/feed and edition selection paths; numeric legacy link fallback is disabled.
- Structural graph regression: `tests/test_migration.py::TestMigrationChain::test_publication_and_memory_histories_merge_to_one_head`. Focused SQLite upgrade regression: `tests/test_smoke_migrations.py::TestFlaskDbUpgrade::test_publication_and_memory_parent_states_converge`.
