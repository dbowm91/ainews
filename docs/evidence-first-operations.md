# Evidence-first editorial operations

## Hold and review

`review` is the operator queue state. `editorial_eligibility.status="hold"` is the decision that the article cannot be published. Both manual and automatic approval call the same eligibility service; changing `review.auto_approve` does not override a hold. The admin review action returns HTTP 409 with the recorded eligibility reasons when a hold blocks approval.

Inspect an article with the authenticated route `GET /api/v1/admin/articles/<id>/editorial-status`. It reports policy version, content digest, evidence revision, stable claim decisions, source counts, final audit findings, and cross-feed lead ancestry. It does not return publisher excerpts or unrestricted fetched content.

## Resolving a hold

1. Read `last_error` and the `eligibility.reason_codes` from editorial status.
2. For unavailable/unsafe/unsupported sources, repair search or source access and reprocess the article so evidence is retrieved again through safe fetch.
3. For insufficient or disputed claims, add reliable independent reporting or a narrow primary document, then re-run research and final editing. Unknown lineage does not count as independent support.
4. For final audit findings, correct the unsupported statement, citation, number, quotation, or copied phrase and re-run the editor and final claim audit.
5. Confirm that the current final-content digest and dossier revision have a passing quality report and audit before approval.

There is no force-approve override. Admin edits to unpublished material invalidate the final audit and keep the article in review. Edits to already-published content are rejected; create and review a correction candidate so the public record remains auditable.

## Retention, revisions, and budgets

The evidence document cache keeps at most a 2,000-character excerpt and content digest per canonical URL for 30 minutes. Article dossiers keep at most eight source records and the same excerpt cap. Initial search uses four queries and retrieves up to six candidates; one follow-up round can retrieve up to two. Claim verification is bounded to 32 final-field statements, with one research verification and one final verification pass. A content edit, additional lead, or evidence update increments/invalidates the dossier revision and invalidates the prior eligibility result.

Source fetches never run inside a database write transaction. Search snippets, editorial memory, related AInews articles, and model-proposed URLs do not count as evidence. Evidence cache and dossier excerpts are internal and are not added to article APIs, feeds, pages, or newsletters.

## Current rollout

The eligibility gate is active for all publication paths. Research provenance, claim verification, and originality checks are active and fail closed for new candidates. Story clustering uses conservative deterministic matching and is independently bypassed if its short Redis admission guard is unavailable; ambiguous candidates remain separate. Feature flags do not disable the publication gate.
