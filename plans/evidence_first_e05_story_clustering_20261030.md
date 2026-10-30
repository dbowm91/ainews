# E05 — Cross-Feed Story Clustering, Duplicate Prevention, and Research Reuse

**Status:** OPEN — P2; optional after verified research path works
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependencies:** E02 source provenance, E01 publication eligibility; integrate with E03 ledger revisions where useful.
**Outcome:** Many RSS/API entries about the same event contribute to **one editorial story** without accidentally erasing materially distinct events or spawning duplicate articles.

## Current anchors

`tasks/extract.py:_find_duplicate_article` checks normalized URL and normalized title, and `_handle_duplicate` appends citations to an existing Article. `models/article.py` uses a required single `source_id` with `uq_source_external_id`; extraction immediately dispatches each novel source item. `services/dedup_service.py` provides read-only URL/title candidate lookup. These are useful exact dedup functions, not event clustering.

## E05.1 — Event identity and clustering

- Define `StoryCluster`, `StoryLead` and join/alias record(s), or the minimal equivalent, linked to current `Article`. A story cluster represents a single event/development with canonical entities, event type, version/date window and all discovery leads.
- Separate same-event duplicate from a related development: "model announced", "released", "updated", "benchmark result", "security issue", and "correction" may deserve separate articles even if companies/models match.
- Cluster candidates by time window, entity/event signatures, normalized headlines and conservative semantic similarity where locally available; use deterministic thresholds for obvious matches, bounded model judgment only for ambiguity. No new mandatory vector service.
- Store candidate scores, decision reasons, event timestamps and membership lineage; ambiguous matches remain separate or queued for review, not silently merged.
- Preserve original feed attribution. Multiple syndications of a wire item must not create false evidence independence.

## E05.2 — Lifecycle and concurrency

- Only one canonical article should be in progress for a cluster at a time. Acquire an idempotent DB/Redis admission guard keyed by cluster identity, resilient to worker loss and duplicate Celery dispatch.
- When a later feed lead joins while research is active, atomically append it as new evidence candidate and mark dossier stale where necessary. Do not mutate a currently publishing verdict without triggering a new evidence revision/evaluation.
- When a lead arrives after publication, decide between `existing coverage with added provenance`, `correction/update requiring editorial re-evaluation`, and `distinct follow-up story`. Never silently rewrite an already published article merely because a source was ingested.
- Reprocessing should avoid duplicate external side effects, orphaned citations and incorrect read-only admin results. Keep `Article.source_id`/`original_url` behavior compatible for current consumers and older DB rows.
- Backfill of historical data is optional and limited; do not make public-release-style migration rehearsals a prerequisite for planning. New tables require normal disposable upgrade/downgrade and data-integrity tests.

## E05.3 — Evidence/cache reuse and source diversity

- Share source fetch records by canonical URL + validated content digest and time/ETag; share only verified *document* evidence, never a model's unsupported conclusions.
- Reuse claim-evidence matches only if ledger policy/version, source version/date and assertion qualifiers still apply; refresh for corrections and changed documents.
- A cluster may collect three publications yet still count one original evidence family; use E02 provenance families and E03 material-claim rules.
- Budget search queries and research calls across concurrent leads in one cluster; preserve a path for high-value contradictions to reopen targeted search.

## E05.4 — Dedup metrics and test matrix

Test exact duplicate source IDs; identical URLs with tracking params; different original publishers; syndication; entity collisions; a repeated release with a different version; rumor → official confirmation; correction/retraction; late evidence; concurrent crawl tasks; deleted/re-enabled sources; queue retries; existing published articles and article IDs.

Required metrics: clusters created, leads merged, ambiguous decisions, duplicate prevented, source-family diversity, research cache hit, stale-ledger rechecks and related false merge/split diagnostic sample. Operator-visible cluster/source ancestry should be accessible from admin without changing public article payloads.

## Exit criterion

On a fixed multi-feed corpus, multiple posts about the same event result in one publication candidate and multiple distinct provenance records, while closely related but different events remain independently publishable. No increase in auto-publication bypasses, unresolved contradictions, or duplicated side effects.

**Non-goals:** A global knowledge graph, an always-on external clustering server, a public agent API change, automatic rewriting of historical published articles, or public multi-tenant scalability.
