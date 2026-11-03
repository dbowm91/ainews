# E06 — Editorial Evidence Evaluation, Bounded Rollout, and Operational Handoff

**Status:** IMPLEMENTED — local verification and five-lead ephemeral copyright-metric comparison complete; broader factual-quality conclusions are not claimed
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependencies:** Starts with E01; final acceptance E01–E04, then repeat relevant cases after E05.
**Objective:** Prove that stronger gates improve evidence reliability and copying resistance without excessive cost, blocking normal article publication or changing external output contracts.

## Baseline and corpus

Before implementation, create a **redacted, local fixture set** representing at least: routine release note; one-source scoop; two independent reports; three copies of one syndicated report; primary advisory only; scientific preprint with disputed interpretation; number/version mismatch; correction/retraction; contradictory chronology; quoted statement; source unavailable/paywalled; malicious prompt-injection source text; copied prose; synthetic hallucinated citation; search/provider timeout; degraded research/write/edit; stage disabled; and auto-review enabled.

For each case, record expected claim support, source-family count, publication decision and final article shape. For any transient provider-backed comparison, source text and generated prose may be processed within the controlled internal evaluation; do not train on it, expose it, or retain it in the deliverable. Purge source text, excerpts, prompts and generated prose after the run, retaining only aggregate metrics. Do not commit third-party article text or secret provider data. This is a technical handling rule, not a legal conclusion. Capture baseline outcome and provider-call cost/latency without claiming production performance from mocks.

## Automated gates

1. **Publication matrix:** assert a failed research/write/edit gate cannot publish under any `review.enabled` / `auto_approve` combination, including queue drain, direct admin/manual approval path, `_finalize`, scheduled publish, Celery retry, race and previous article version.
2. **Research provenance:** fake snippets, fabricated URLs, unsafe links, three syndications, missing source dates, partial extraction and a false model-origin claim cannot become accepted evidence. Regression coverage for safe-fetch SSRF and redirect/DNS pinning.
3. **Claim fidelity:** material dates, units, quotes, numerical comparisons, corrections and source disagreements preserve true provenance; false support and contradictions produce consistent hold/review reason codes.
4. **Originality:** source text copying and source-specific paragraph order are flagged; standard technical terms, narrowly attributed quotes and factual overlap are not rejected indiscriminately. Calibrate with manually labeled examples and measure false-positive/false-negative rates.
5. **Compatibility:** typed `CondensedArticle` shape, article API, public HTML, feed, newsletter and admin views remain stable; no schema additions required for public clients.
6. **Efficiency:** bounded search queries, source fetches, stored excerpt size, token budgets, independent origin cap, retry/revision idempotence and task timeouts; no source fetch or LLM call while holding a SQLite write transaction.
7. **Repository requirements:** add reproduction regression tests for each confirmed defect; follow `AGENTS.md` on typing, Ruff, mypy and target ≥80% coverage of new modules.

## Metrics and instrumentation

Track at minimum editorial eligibility outcome/reason, fetched vs snippet-only evidence, source-origin diversity, claims corroborated/primary-supported/single-source/disputed/unverified, exact number/unit/quote failures, text overlap findings, citation provenance errors, targeted-search iterations, provider calls/tokens, total per-article time and duplicate publication suppression.

Use low-cardinality metric labels; place article IDs, URLs, evidence hashes and exact claim-level findings in scoped logs/DB. Keep failed source contents and errors appropriately redacted. Distinguish absolute facts from observability heuristics: a passing quality score is not a proof of factual truth.

## Feature flags and local rollout

- E01 hard publication integrity is a correctness fix, not an optional experiment. Land it first with failing tests, then enable universally for new publications.
- E02/E03 evidence collection/ledger may initially run in **shadow** (collect and log evidence without enabling strict source-count gate) to tune extraction/provider behavior. Once accuracy is demonstrated, enforce strict verdicts for new articles; unknown verification fails closed. Version policies and keep a rollback switch to restore prior **non-strict evidence requirements**, never to restore the known auto-approve bypass.
- E04 originality detection may begin shadow to quantify thresholds, then route high-risk overlaps to hold/review. Preserve citation/claim hard fails throughout.
- E05 clustering is optional, separately reversible, with shadow match suggestions before auto-joining leads.
- Do not enable all flags in one commit. An implementation handoff must identify which defaults were actually changed and which are still disabled.
- No claim of public-launch readiness, mandatory full installer matrix, external benchmark, or active deployed database migration evidence. If a real deployment/database exists at implementation time, use its normal backup procedure before a schema change; otherwise disposable SQLite migration tests are sufficient.

## Handoff/closure deliverables

- Report source baseline branch/commit and final **tested SHA**, actual pytest command/results, focused suite, Ruff and mypy, any known inherited failures with comparisons and reasons.
- Evidence sample with per-case final publication decision, source-family ancestry, unresolved claims and overlap findings; no unverifiable "passed" assertions.
- Admin/operator explanation for `hold` vs `review`, manual override audit, source fetch failure, policy version, article reprocess, evidence invalidation, and corrections.
- Update `docs/pipeline.md`, `docs/quality.md`, `architecture/pipeline.md`, `architecture/prompts.md`, `docs/search.md`, and operational documentation only when corresponding code actually changes. Update `plans/plan.md` and roadmap statuses after real milestones land.
- The 2026-10-31 ephemeral cohort paired five leads and retained aggregate copying, source-family, disposition, output-size and latency metrics only; it is documented in `docs/evidence-first-validation-20261030.md`. The requested copyright-focused measurement is complete. Evidence-first held every lead, so it generated no prose for direct overlap comparison; no factual-accuracy or evidence-first copying-rate conclusion is claimed. Any later quality-comparison study must use transient inputs and retain aggregate outcomes only. Calibrate source thresholds instead of asserting two URLs = two sources.

## Final exit gate

A fully autonomous instance can still publish a corroborated, novel, short article in the existing output schema; no unverified source-only fallback or synthetic provenance can become `DONE`; and operator review is needed only when evidence is insufficient, disputed, inaccessible or otherwise policy-ineligible. Re-run tests after any later bypass/citation/publishing changes.
