# E04 — Evidence-Only Writing, Independent Editing, and Textual Originality Gates

**Status:** OPEN — P1
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependencies:** E03 claim fact sheet and E01 hard eligibility gate.
**Objective:** Draft original high-signal, compact coverage from independently assembled facts and verify the final artifact, while keeping public schema and rendering unchanged.

## Existing implementation anchors

`services/writer.py:build_writer_prompt` receives `original_title` and an 8,000-character research brief truncated by `tasks/write.py`. `services/editor.py` includes draft + selected brief fields; `tasks/edit.py` produces `CondensedArticle` and calls quality_report before routine finalize. `services/quality_report.py` currently checks known URL membership and lexical overlap with the brief, not actual source entailment or phrase reuse. `pipeline.yaml` has writer/editor system prompts and A/B variants; YAML overrides `prompts/*.txt` via `services/prompts.py:get_system_prompt`.

## E04.1 — Writer receives verified findings, not publisher narrative

- Introduce a writer input (`VerifiedEditorialPacket` or similar) assembled from the E03 ledger: event summary in neutral factual terms, claim IDs, support provenance, dispute qualifications, context of relevance, what is established vs still unknown, source attribution map, and constrained exact quotes only where editorially necessary.
- Do **not** send original publisher body, the publisher's article summary, or original headline as an instruction to preserve style/sequence. Preserve discovery provenance separately; writer may see necessary names/dates/terms.
- Do not arbitrarily slice the JSON ledger at 8,000 chars. Allocate token budgets deterministically by essential claims, source handles, disputes, and compact context. If mandatory evidence does not fit, fail/hold rather than dropping a contradiction.
- Instruct writer to organize by public significance: headline, one-sentence TL;DR, why it matters, 3–5 tight paragraphs, key points and what to watch. No opinions passed off as facts, invented quotes or causal leaps.
- Continue to emit exactly `CondensedArticle` with existing fields and citation representation. `original_attribution` remains discovery/credit metadata, not an assertion that only one source informed the piece.

## E04.2 — Non-overridable editorial policy

- Refactor prompt assembly into immutable editorial constraints plus optional tone/style variants. All configured YAML prompts, file prompts and experiment variants must receive the same factual-grounding, originality, attribution and uncertainty instructions.
- Update `pipeline.yaml` as **the active prompt source**, alongside the fallback `prompts/researcher.txt`, `prompts/writer.txt`, `prompts/editor.txt` and synthesis template. Add tests proving YAML/file fallback and A/B variants cannot omit mandatory constraints.
- Require all generated citations to resolve to verified dossier handles. Validate each URL after converting handles to the existing public `citations` format; reject model-invented entries.
- Treat source excerpts, article text, HTML and retrieved tool content as untrusted data. Prevent instruction injection from redefining writer/editor policy or the role/system messages.

## E04.3 — Claim-level final artifact audit

- Extract material propositions from **all** final fields (`headline`, `tldr`, `why_it_matters`, `body`, `key_points`, `what_to_watch`). Check linkage to ledger claim IDs and retrieved evidence; deterministic validation for quoted numbers/dates/version units first, semantic judge for paraphrased entailment as bounded supplementary check.
- Reject unsupported factual additions by editor; permitted behavior is removing unsupported claims, rephrasing correctly supported claims, or requesting E03 verification for new facts.
- Distinguish forward-looking scheduled events from speculation; `what_to_watch` must attribute forecasts and conditions.
- The final quality report should incorporate factual support findings, citation provenance, quote accuracy, originality and format findings. Do not award a high groundedness score merely because text contains a source title.
- Route retryable drafting defects through bounded remediation; unrecoverable evidence gaps through `hold`. Re-run eligibility on the final exact content digest and dossier revision. A fallback draft is never exempt.

## E04.4 — Deterministic overlap and copying risk

Add a source-to-final similarity guard using token n-gram/shingle overlap, longest shared verbatim runs and quote-excluded comparisons across source documents. Compare headline, TL;DR, body, key points and field-level composition; penalize extensive distinctive phrases and parallel paragraph ordering. Treat fixed terminology, stock phrases, mathematical notation, short names and properly attributed limited quotations carefully.

- Never choose a universal "copyright-safe" percent: empirically calibrate risk thresholds on E06's corpus and report exact overlapped spans for review.
- Separate **textual overlap** from semantic topic similarity: true reporting on one event can have high semantic overlap without copying prose.
- A high-risk match triggers re-draft from evidence-only packet or `hold`, not automated string scrambling or superficial synonym substitution.
- Keep excerpts short and access-controlled; record source digest, comparison version, overlap spans and reason code without preserving unnecessary complete third-party articles.

## E04.5 — Smart Brevity-inspired format invariants

Preserve the current concise, scannable output contract without reproducing Axios-specific branded wording or layout. Recommended word-count target remains roughly 200–400 words where the story warrants it, and body paragraphs should remain ≤3 sentences as currently prompted. Treat brevity as a quality dimension rather than adding filler to meet a hard count; no HTML in markdown body. No new required public JSON keys, route changes, theme changes, or newsletter rendering changes.

## Tests and exit criteria

- Writer receives only verified packet, not an entire ingested article or original source headline; evidence and conflict qualifications survive token packing.
- Both control and A/B prompt variants include non-overridable evidence/copyright/quote rules.
- Editor introduces a plausible but unsupported number; final audit catches it. Model adds a fake citation URL or mismatched quote; deterministic gate blocks it.
- Verbatim long passages and structurally copied paragraphs are detected, while standard technical terms, factual overlap and limited attributed quotations are not over-penalized.
- All final fields are checked; high-risk false claims cannot hide in `why_it_matters` or `what_to_watch`.
- Schema/serializer, sanitizer, templates, existing article pages, feed payload and newsletter consumers continue to function unmodified or with backward-compatible adapters.
- Compare actual final artifacts on E06 fixtures; do not claim copying avoidance from prompt-only or synthetically passing checks.

**Non-goals:** Replacing authorial judgment with an embedding threshold, automated legal clearance, unbounded LLM-as-judge calls, new public article layout or vendor-specific model requirements.
