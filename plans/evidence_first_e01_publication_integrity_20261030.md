# E01 — Mandatory Editorial Eligibility and Publication Bypass Closure

**Status:** OPEN — P0
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependencies:** None. Must land before mandatory source corroboration is activated.
**Objective:** Make an editorial quality failure a true publication blocker even in autonomous mode, with no accidental loss of good-story throughput.

## Verified inspection anchors

- `pipeline.yaml` currently sets `review.enabled: false`, `auto_approve: true`.
- `tasks/pipeline.py:_transition_article_status` delegates `REVIEW` to `services/auto_review.py:route_to_review`. That helper publishes immediately under `auto_approve`.
- `tasks/research.py:_handle_quality_gate_and_transition` and `tasks/write.py` send degenerate results to review, which may be auto-published. `tasks/edit.py` similarly routes validation and quality-report failures.
- `services/pipeline_degradation.py:_degrade_research` creates a source-only, empty-claim research brief; `_degrade_edit_stage` can mark an unreviewed draft `DONE`; `_finalize` may publish a fallback without an editorial report.
- `tasks/pipeline.py:_handle_disabled` bypasses ordinary stage logic. `services/auto_review.py:approve_article/publish_article/auto_approve_queued` and scheduled/admin publication paths must be enumerated, not assumed safe.

## E01.1 — Reproduce and inventory the publish boundary

1. Add failing tests for failing research/write/edit gates with `auto_approve: true`, `review.enabled: false`; explicitly verify neither `DONE` nor `published_at`/webhook/embedding is produced.
2. Exercise research failure, write failure, editor failure, stage disable, quality-report exception, manual queue approval, scheduled publication, and resumption/retry paths. Enumerate callers of `publish_article`, `post_finalize_article`, direct `pipeline_status = DONE` and `published_at` assignments.
3. Verify auto-review semantics separately from `review.enabled`. Test combinations of settings; do not assume one flag cancels the other.
4. Review `tests/test_pipeline_research.py`, `tests/test_pipeline_write.py`, `tests/test_pipeline_edit.py`, `tests/test_quality_report.py`, `tests/test_publication_lock.py`, `tests/test_tasks_edit.py`, `tests/test_scheduler.py`, and relevant admin routes.

## E01.2 — Implement a single mandatory eligibility decision

Introduce an independently testable `services/editorial_eligibility.py` (or equivalent) returning typed `eligible | hold | review_required` plus stable reason codes and a policy version. Input is an immutable snapshot of the final candidate, required source-evidence state, current verification result, and any operator exception. It must not infer eligibility from `impact_score`, `degradation_count`, `review.enabled`, or a model's confidence alone.

- Early E01 may enforce only existing structural/quality integrity and explicit degraded-state blocking; E02–E04 layer in source provenance, corroboration, and originality. Unknown/unavailable required evidence is **hold**, never pass.
- For idempotence, identify the exact article version/content hash + evidence revision + policy version evaluated. An edit invalidates a previous pass.
- Make the publish transition validate this verdict at the last trusted transition, preferably via one service called by all routes. Administrative approval and auto-review share this enforcement; avoid second, parallel implementations.
- Distinguish `review` as an operator workflow from `hold` as publication eligibility. Avoid a state-machine breaking rewrite: start with policy verdict metadata and existing statuses, add a new status only with all call sites and migrations covered.
- Persist hold reason/findings and expose them in existing article quality/admin views; do not silently enqueue the editor in a loop.

## E01.3 — Safe review and override semantics

- `auto_approve` may approve an **eligible** article awaiting optional editorial review. It must never publish an ineligible/unknown article.
- Either disallow forced approval of blocked content or introduce an explicit privileged operator-only exception with reason, actor, timestamp, exact claim/policy exceptions and audit trail. No background job, default toggle, or unqualified bulk approval may supply this exception.
- Ensure approval is transactional/idempotent across Celery retries, concurrent publish calls and webhooks. A late job cannot publish an older artifact after a failed re-edit.
- Separate recoverable provider unavailability (retry/hold) from terminal editorial failures (hold) without calling the article a success.

## E01.4 — Degradation and direct-path corrective work

- Never interpret `research_disabled` or source-only research fallback as verified synthesis. In strict mode send such records to `hold`/manual review, not writer → publish.
- A failed editor can retain a draft for diagnosis, but a draft may publish only if it has passed the **same** final eligibility gate.
- Audit `_finalize`, `_degrade_edit_stage`, `route_to_review`, `auto_approve_queued`, scheduled publication, direct admin publish, and article reprocess/retry. Use a single policy authority; ban unguarded direct `DONE` writes in production paths.
- Avoid firing post-publish events or memory proposals for held articles. Existing published articles should not be silently unpublished by a new gate; re-evaluate when they are substantively updated.

## Required tests and acceptance

- All path/flag combinations in E01.1 reproduce before correction and pass afterward; include a controlled failing quality report that `auto_approve` cannot bypass.
- No external side effects (`published_at`, webhook, newsletter eligibility, embedding dispatch, trend-memory proposal) occur for a held article.
- Genuine passing articles still publish autonomously with `auto_approve` on. Manual eligible approval works. Concurrent duplicate approval runs effects at most once.
- Missing quality report/evidence is not misclassified as a pass; policy verdict is visible and stable on restart.
- Existing response shape, URLs, templates and newsletters are unchanged. Log real test commands and commit SHA.

**Non-goals:** Building the evidence ledger in E01; banning all operator edits; changing the front-end article format; forcing manual review for every article. E01 is the first independent, mergeable corrective.
