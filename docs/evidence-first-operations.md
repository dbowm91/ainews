# Evidence-first editorial operations

## Hold and review

`review` is the operator queue state. Auto-review publishes any structurally valid final article without waiting for a person. Missing, invalid, or incomplete final content remains unpublishable because there is no usable article to publish. Evidence verification, quality reports, degradation, and originality audits remain recorded as diagnostics, but do not block manual or automatic publication.

For a personal aggregator, `evidence.allow_single_source_attributed` may be enabled explicitly. This allows a claim supported by one retrieved reporting source only when the final text attributes the claim to that source and preserves a validated verbatim evidence span. Unsupported research candidates are omitted from the writer packet when at least one other claim is verified. Evidence and originality checks still run and their findings are available for inspection; they are advisory and do not veto publication.

Inspect an article with the authenticated route `GET /api/v1/admin/articles/<id>/editorial-status`. It reports policy version, content digest, evidence revision, stable claim decisions, source counts, final audit findings, and cross-feed lead ancestry. It does not return publisher excerpts or unrestricted fetched content.

## Reviewing diagnostics

1. Read `last_error`, `eligibility.reason_codes`, and `eligibility.diagnostic_codes` from editorial status.
2. For unavailable/unsafe/unsupported sources, repair search or source access and reprocess the article so evidence is retrieved again through safe fetch.
3. For insufficient or disputed claims, add reliable independent reporting or a narrow primary document, then re-run research and final editing. Unknown lineage does not count as independent support.
4. For final audit findings, review the unsupported statement, citation, number, quotation, or overlap and re-run the editor if a correction is warranted.

Admin edits to unpublished material invalidate the prior audit and record that diagnostic. Edits to already-published content are rejected; create and review a correction candidate so the public record remains auditable.

## Retention, revisions, and budgets

The evidence document cache keeps at most a 2,000-character excerpt and content digest per canonical URL for 30 minutes. Article dossiers keep at most eight source records and the same excerpt cap. Initial search uses four queries and retrieves up to six candidates; one follow-up round can retrieve up to two. Research claims are verified in batches of three to keep small local models within structured-output limits. The research brief caps claim, quote, summary, and context lengths. Final claim verification is bounded to 32 final-field statements; failed outcomes are retained as diagnostics. A content edit, additional lead, or evidence update increments/invalidates the dossier revision and invalidates the prior diagnostic result.

Source fetches never run inside a database write transaction. Search snippets, editorial memory, related AInews articles, and model-proposed URLs do not count as evidence. Evidence cache and dossier excerpts are internal and are not added to article APIs, feeds, pages, or newsletters.

## Current rollout

Final-content structure is checked on every publication path. Research provenance, claim verification, quality, and originality checks run and record outcomes but do not block publication. Story clustering uses conservative deterministic matching and is independently bypassed if its short Redis admission guard is unavailable; ambiguous candidates remain separate.
