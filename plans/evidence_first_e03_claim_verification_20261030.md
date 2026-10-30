# E03 — Atomic Claim Ledger, Corroboration Policy, and Dispute Resolution

**Status:** OPEN — P1
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependency:** E02 typed retrieved evidence and trusted IDs.
**Outcome:** A research dossier whose factual assertions can be traced to evidence and qualified before writing, with bounded iterative search for gaps.

## Baseline and constraints

`schemas/llm_responses.py:KeyClaim` currently holds `claim/source/confidence`; `ResearchBrief` centers on `source_summary`. `tasks/research.py:_is_degenerate_research` gates existence of claims and impact score only. `services/quality_report.py` accepts URLs from the LLM-generated brief and lexical word overlap as factual support. These checks cannot reliably distinguish corroborated reporting, unsupported assertion, numerical error, contradiction, and duplicated publishers.

## E03.1 — Typed evidence ledger

Add internal structured `ClaimEvidenceLedger`, separate from public `CondensedArticle`. At minimum:

- `claim_id` (stable per dossier revision), normalized atomic proposition, entity/action/object, number/unit/time qualifiers, scope, materiality, and provenance of initial detection;
- `supports[]` and `contradicts[]` each referring to a **validated evidence_source_id**, bounded evidence span or locator, acquired/revised timestamp and rationale;
- `status` enum: `corroborated`, `primary_supported`, `single_source`, `disputed`, `unverified`; `confidence` as a calibrated editorial assessment separate from objective evidence count;
- `independent_origin_count` computed deterministically from evidence families, not supplied by the LLM; `is_material` and `publish_allowed` policy results with reason codes;
- versioned ledger revision, policy version, timestamps and a content digest. Persist only validated record IDs, not arbitrary URLs sent by a model.

Split compound statements: "X is faster, cheaper and available" must yield separate benchmark, pricing and availability propositions. Keep numbers/units/dates exact and distinguish event date from article publication or retrieval date.

## E03.2 — Verification and contradiction rules

- Verify document relevance and claim entailment from **retrieved** passages, not from snippets. Use a structured LLM judge where semantic entailment warrants it, alongside deterministic exact checks for dates, amounts, units, versions, citations and quote spans.
- Judge may label support/contradiction only against supplied evidence handles. Deterministic validation rejects missing handles, fabricated spans, unsupported numbers, out-of-date qualifiers, or confidence unjustified by provenance.
- Default: material secondary-reporting facts require two independent evidence origins. A single authoritative primary document may establish narrowly attributable facts (`the regulator filed...`, `the release notes state...`), but issuer performance claims or disputed assertions require careful attribution/corroboration, not automatic high confidence.
- Disagreement is **not** resolved by majority vote or counting syndications. Preserve conflicting values, source dates, corrections, methods, and missing methodological context. Either report the disagreement with attribution or hold the material claim.
- Quotes require exact/near-exact source spans and original speaker attribution; a quote repeated in a news article is not independently verified as authentic unless its primary source is accessible or attribution is explicitly bounded.
- Evidence quality/authority is claim-specific; source popularity, domain reputation, and impact_score do not create factual support.

## E03.3 — Bounded targeted follow-up search

After initial extraction and verification, identify unresolved **material** claims, rank by severity and importance, and generate a small number of targeted queries (e.g., official release note/version, original study methods, regulator notice, corrections). Reuse E02's search-and-safe-fetch service.

One additional capped round by default; configurable maximum, but no open-ended agent loop. Deduplicate queries and evidence across retries. If insufficient evidence remains, remove the unsupported claim, narrow attribution, flag as disputed, or hold publication. Never invent confidence to end a retry.

## E03.4 — Research brief and writer handoff

- Produce a compact **fact sheet** from the ledger: established claims, attributed single-primary assertions, qualified disputes, contextual background, source handles and any meaningful unknowns. Order by significance, not the initial article's paragraph order.
- Keep legacy `research_brief` compatible (populate existing keys as appropriate); introduce versioned sidecar ledger rather than changing public payload consumers without migration.
- Separate prior AInews coverage/editor memory from fresh supporting evidence. Historical memory may guide searches or contextualize but cannot count as an independent corroboration of current events.
- If essential material claims remain unsupported, set eligibility `hold` and do not proceed to autonomous publication. Non-essential unsupported claims should be excluded from the fact sheet.

## Required tests

- Two independent original reports supporting one claim yield `corroborated`; two sites reproducing one wire item do not.
- A first-party release note establishes what it states, not an independently measured benchmark; an inaccessible URL or search snippet never counts as support.
- Numeric unit mismatch, version mismatch, withdrawn paper, revised report, stale timestamp and contrary first-party update produce appropriate contrary/hold findings.
- Fabricated evidence ID, URL not in source registry, quotation absent from evidence span, compound claim and model-confident but unsupported claim are rejected.
- Follow-up query cap, cache reuse, retry idempotency, ledger revision changes, and untouched final public schema.
- Deterministic eligibility reason and reproducible claim-to-source trace are exposed in existing quality/admin reporting.

**Exit criterion:** The writer can receive a sufficient fact sheet **without** the original publisher's body, and a claim unsupported in the dossier cannot be laundered into an eligible publication.
