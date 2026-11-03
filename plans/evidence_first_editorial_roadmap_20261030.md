# Evidence-First Research, Independent Synthesis, and Publication Integrity Roadmap

**Status:** IMPLEMENTED — E01–E06 complete for the requested internal, metrics-only qualification scope; five-lead copyright-metric cohort recorded
**Date:** 2026-10-30
**Baseline:** `main` at `8fdfc61f9c7f450f686064a5cdb65fce020b9c04`
**Handoff branch:** `plan/evidence-first-article-synthesis-20261030`
**Scope:** Existing AInews article discovery → research → write → edit → publish workflow. Preserve the current public-facing CondensedArticle contract and Smart Brevity-inspired, compact editorial format.
**Operating posture:** Personal/local or privately operated AInews; this is an editorial correctness and reliability workstream, **not** a public-release program.

## Decision

Feeds, APIs, and manually supplied sources are **discovery leads**, not privileged source articles to be summarized. The pipeline's product is an original, concise synthesis of corroborated facts about an event, with appropriate citations and explicit uncertainty. No mandatory new frontend layout or public article JSON fields are permitted.

**Trust boundary:** A generated research brief is NOT evidence. Search snippets are leads, not proof. A URL proposed by a model is not an accepted citation until a deterministic retrieval/provenance service validates it. The final gate operates on the actual edited/fallback artifact and verified evidence.

## Code-grounded baseline and hazards

1. `tasks/extract.py` creates one `Article` from one feed item, with `Citation` to its original URL. `_find_duplicate_article` checks normalized URL/title, not cross-publisher event identity; `models/article.py` ties `Article.source_id` to one source.
2. `tasks/research.py:_perform_web_search_and_synthesis` builds one query from original title + topics, obtains normally five search snippets, and passes source article text to researcher. `services/researcher.py` labels supplemental results `external_sources`. `services/subagent/tools.py:_search_web` omits URLs in its model-visible result and does not fetch evidence.
3. `schemas/llm_responses.py:ResearchBrief` has source_summary, key_claims with only one source and free-form confidence, optional external_sources, and impact score. `_is_degenerate_research` gates only nonempty claims and impact score ≥10, not independent confirmation.
4. `services/writer.py` uses `original_title` and the research brief; `tasks/write.py` truncates the brief to 8,000 characters. `services/editor.py` verifies against the generated brief rather than retrieved evidence; arbitrary truncation can hide critical source support and contradictions.
5. `services/quality_report.py` checks citation URLs against URLs supplied in the brief or stored citations, and uses lexical overlap with those same generated claims/snippets. It is a useful structural quality report, **not** independent source-fact verification or a copyright/originality check.
6. Critical: `pipeline.yaml` currently has `review.enabled: false` and `review.auto_approve: true`. `tasks/pipeline.py:_transition_article_status` sends review transitions through `services/auto_review.py:route_to_review`; that helper can immediately publish a quality-gate failure. `services/pipeline_degradation.py` can also advance with source-only fallback, publish a degraded edit directly, or finalize without the post-edit quality gate.
7. `services/prompts.py:get_system_prompt` prefers YAML over prompt files; writer A/B variants can replace base instructions. Changing only `prompts/*.txt` does not reliably enforce an editorial policy.
8. Existing safe-fetch, trafilatura content extraction, Celery stage orchestration, quality reports, editorial memory, and search provider interface are reusable. Memory and related AInews articles are context, **never independent corroborating evidence** by themselves.

These are static code findings, not a claim of successful runtime reproduction on the user's installation. Implementation must start with failing regression tests.

## Superseding publication decision (2026-10-31)

The original fail-closed editorial hold requirement was removed for the private personal instance after real local-model qualification showed that the audit/verifier combination kept completed output from ever being published. Evidence verification, quality, degradation, and originality results remain recorded for inspection but do not veto publication. Only missing, invalid, or incomplete final content is unpublishable. This decision supersedes the stricter publication-gate requirements below.

## Target internal flow

1. **Discover** events from RSS/APIs and retain discovery provenance; optional cross-source event clustering is later.
2. **Search and retrieve** primary documents plus reporting from independent evidence origins using bounded queries; a search result alone cannot promote a claim to verified.
3. **Decompose and verify** atomic factual claims, link each to retrieved evidence spans, classify agreements/contradictions and unresolved assertions, and perform bounded gap-directed follow-up searches.
4. **Compose** an evidence-only writer input ordered by significance, not by publisher paragraph order; the original source text is unavailable to the production writer except attributed, bounded factual excerpts or verified quotes.
5. **Edit and inspect** material statements, citations, quotes, dates, numbers, and originality risks against the evidence ledger. Record findings for operators.
6. **Publish or review** structurally valid final content according to review settings. Editorial evidence and originality findings are diagnostic; only absent, invalid, or incomplete final content blocks publication.

## Internal contracts

- **Public contract invariant:** Preserve `CondensedArticle` fields `headline`, `tldr`, `why_it_matters`, `body`, `key_points`, `what_to_watch`, `citations`, `original_attribution`, and `tags`, including current article rendering/newsletter consumption. Do not conflate Smart Brevity *inspiration* with copying Axios's distinctive prose or branded presentation.
- **Evidence provenance:** canonical URL, publisher, original reporting/wire/press-release family where inferable, publication/retrieval time, extraction status, source type, content digest and bounded evidence spans; treat model-provided metadata as untrusted.
- **Claim identity:** canonicalized atomic proposition, entity/value/unit/date qualifier, support/contradiction links, evidence type and decision (`corroborated`, `primary_supported`, `single_source`, `disputed`, `unverified`). A claim's model-reported confidence is not proof.
- **Corroboration:** default two independent *evidence families* for material, non-primary-origin facts; allow clearly identified authoritative primary-document exceptions with narrow attribution and stronger handling for disputed/high-risk claims. Two syndicated stories do not equal two independent sources.
- **Operational bounds:** capped queries, fetched documents, full-text bytes, per-source excerpts, total evidence tokens, follow-up iterations, stage time, optional model calls, and per-story duplicate work. Preserve the existing single-node SQLite/Redis/Celery architecture.
- **Persistence:** Add versioned internal evidence/dossier storage (a normalized set of tables or versioned sidecar linked to Article); keep existing `research_brief` backward-compatible for readers. Never migrate or embed evidence into public fields simply for convenience.
- **Failure posture:** missing search, provider outage, low confidence, no independent origin, failed extraction, and a degraded stage are recorded as diagnostics. They may route an article to the review queue when auto-review is off, but they do not block approval of structurally valid final content.
- **Private-instance focus:** no public launch, installer certification, large multi-tenant system, browser automation, mandatory infrastructure change, or costly vector infrastructure is required.

## Registered executable milestones

| Sequence | Priority | Plan | Dependency |
| --- | --- | --- | --- |
| E01 | P0 | [Publication-eligibility gate and bypass closure](evidence_first_e01_publication_integrity_20261030.md) | None; **first implementation** |
| E02 | P1 | [Discovery-lead research, source retrieval and independent origins](evidence_first_e02_research_sources_20261030.md) | E01 gate interface |
| E03 | P1 | [Atomic claim ledger, corroboration and contradiction resolution](evidence_first_e03_claim_verification_20261030.md) | E02 evidence records |
| E04 | P1 | [Original evidence-only writing, editing and anti-copy checks](evidence_first_e04_original_synthesis_20261030.md) | E03 ledger; E01 gate |
| E05 | P2 | [Cross-feed event clustering, deduplication and bounded reuse](evidence_first_e05_story_clustering_20261030.md) | E02 provenance; E01 publishing invariants |
| E06 | P1 cross-cutting | [Real-fixture verification, operational rollout and documentation](evidence_first_e06_verification_rollout_20261030.md) | Start with E01; finish after E02–E04, revisit after E05 |

E06 owns validation throughout, not a license to defer regression tests until the end. E05 can be implemented later without blocking verified single-lead synthesis. Do not mark a milestone complete without code, tests, current-HEAD evidence and registry updates.

## Pre-implementation decisions to settle with tests

- Where every production publication entry point converges: edit success, edit fallback, disabled stage, quality route, `approve_article`, scheduled publishing, and admin approval. A structural final-content check must be on ALL paths; editorial findings are advisory.
- Whether an external search provider can fail silently (currently `search_web` may return `[]`); record unknown rather than negative evidence and never treat an empty result as independent verification.
- Which primary evidence types may independently establish narrow facts (e.g., official changelog, CVE advisory, scientific paper, regulator filing) and which claims require independent corroboration or explicit uncertainty.
- Precise retention and caching strategy for publisher text; preserve sufficient audit evidence without accumulating unnecessary copyrighted full text.
- Editorial findings are diagnostic and may not block manual or automatic publication. Missing, invalid, or incomplete final content cannot be published.

## Cross-workstream compatibility

The editorial-memory M1–M4 work is already merged on the baseline main commit; it remains **context, not external corroboration**. Avoid replacing its scoped bounded retrieval. Preserve existing search provider abstraction; replacing/augmenting harness-side search with eggsearch belongs to its separate workstream, but may be used through an adapter. Do not introduce mandatory live services beyond those already configured for AInews.

## Final acceptance

- Every publication path requires a structurally valid final article.
- Evidence, quality, and originality findings are retained as diagnostics but do not prevent manual or automatic publication.
- Material final-article claims and quotes map to retrievable provenance; unresolved disputes are attributed/qualified or held.
- Writer output is independently structured from evidence, and deterministic lexical similarity and quote checks reliably flag excessive reuse.
- Site/newsletter readers and article JSON/rendering remain compatible; the Smart Brevity-inspired concise shape is preserved.
- Replayed fixture corpus, performance budgets, security checks, and actual head SHA are recorded without fabricated test claims.

**Implementation:** Completed on `plan/evidence-first-article-synthesis-20261030` after rebasing from `origin/main`. E01–E05 and the requested E06 copyright-focused qualification are recorded in [evidence-first-validation-20261030.md](../docs/evidence-first-validation-20261030.md). Five provider-backed leads were paired across the baseline and evidence-first implementation; only aggregate source-family, disposition, copying-signal, output-size and latency metrics remain. Evidence-first held all five, so this does not establish a copying rate for evidence-first prose or comparative factual accuracy. The evaluation processed source material transiently and retained aggregate metrics only; it makes no legal determination.
