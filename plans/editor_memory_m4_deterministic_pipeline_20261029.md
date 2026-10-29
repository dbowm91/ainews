# M4 — Deterministic Pipeline Offload and Conditional LLM Work

**Status:** OPEN / priority P2  
**Requires:** M1 baselines, M2 retrieval; synthesis reuse depends on M3  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Outcome

Lower unnecessary inference cost, context size and latency **without replacing editorial judgment with brittle heuristics**. Treat determinism as a prefilter, validator and orchestrator; preserve core LLM research, writing and editing when semantic reasoning is needed. Optimize and measure one stage at a time with rollback switches.

## Establish the current per-article inference graph

Instrument actual calls (including retries, fallback chain and tool iterations), model/provider, input/output/cache tokens when reported, elapsed time, failed calls, and prompt assembly token size. Do not infer costs from YAML alone. Existing flow to audit: selection → research web-search synthesis subagent → structured research brief → writer → edit contextualization subagent → structured editor → asynchronous trend-memory proposal, plus conditional review/newsletter work. Confirm which optional subagents execute after M1 fixes. Record current published-article quality before enabling optimizations.

## Workstream A — selection and discovery

- Keep selector LLM for subjective newsworthiness; move hard checks before it: canonical URL/title duplicate, source health/disabled status, known blocked domains, invalid content, freshness metadata, insufficient extractable text, known already-published story clusters where confidence is high.
- Use existing `services/dedup_service.py`, `services/trend_detector.py`, article/search services and `Source` metadata, but audit their constraints and false-positive rates before using a rule to skip publication.
- Distinguish `deterministic reject`, `LLM selected`, `LLM rejected`, and `needs review`. Conservative rules may skip only provable duplicates or invalid artifacts; ambiguous similarity must defer to the selector.
- Reuse canonical category/entity classifications for later memory routing; do not ask the LLM to reassign an already validated identity without reason.

## Workstream B — research evidence assembly

- Retrieve local related articles, topic notes, scoped memories, source health and relevant original reporting in Python. Deduplicate and cluster sources by canonical URL/publisher/claim identity, limit per-domain redundancy, sort with deterministic relevance. Preserve underlying source links and chronology.
- Replace automatic external-source summarization with **conditional** subagent synthesis only for genuinely heterogeneous/conflicting or high-complexity evidence. For routine cases, feed a bounded structured evidence bundle directly to the main researcher; its ordinary structured brief generation remains LLM-driven.
- Do not convert search snippets into verified facts: distinguish original article, fetched content, snippets, and other AInews summaries. If full source retrieval is required, use existing safe-fetch infrastructure and explicitly configured bounds.
- Avoid copying the same memory/topic text into research prompt, subagent prompt, returned brief and editor prompt. Define a compact `EvidencePack` with source and memory IDs that is reused across stages.
- Where current web retrieval may eventually move to eggsearch, keep this plan focused on stage orchestration; do not duplicate or block the separate `plan/eggsearch-web-retrieval-20261028` workstream.

## Workstream C — editing and deterministic quality gates

- Keep the main editor LLM for substantive corrections, accuracy/clarity and style judgment. Move format/schema checks to Pydantic, citation URL validation/normalization, deduplication, quote-match checks, explicit attribution presence, word/sentence/section limits, tag slug normalization, and canonical tag reuse to deterministic code where objectively verifiable.
- Reuse `services/quality_report.py`, `services/article_validation.py`, `services/article_provenance.py` rather than introducing parallel scoring pipelines. Structural failures go to the existing review/fallback policy; deterministic checks must not silently rewrite unsupported facts.
- Make contextualization subagent conditional on detectable gaps: conflicting dated claims, missing references, substantial source disagreement, unsupported changes in the draft, or explicit editorial policy. For easy, well-grounded articles, provide the preassembled evidence pack to the main editor directly.
- Use a single canonical tag registry and deterministic match/fuzzy alias candidates. Request an LLM only for truly novel semantic tag assignment, not every hyphenation or duplicate tag. Keep compatibility with present editor `CondensedArticle.tags` schema.

## Workstream D — memory proposal reuse

- Replace unconditional rereading of `draft_article` with candidate observation extraction from the **final** article and `ResearchBrief.key_claims`, supported by article/source IDs. Deterministically discard duplicate, ephemeral/nonfactual, low-confidence or unsupported candidates; use relation to existing memory as a novelty filter.
- Trigger a separate memory LLM only for claims whose significance/meaning cannot be decided deterministically, for difficult synthesis, or for high-impact new phenomena. For straightforward factual observations, persist normalized source-backed candidates through a validated deterministic path.
- Do not equate repeated publisher coverage with independent corroboration; source grouping and cited URLs must remain visible in evidence.
- Keep memory proposal asynchronous and optional. If no meaningful candidate emerges, use zero LLM calls and explicit skip reason. Avoid chaining proposal and M3 synthesis requests for unchanged evidence.

## Resource/cost controls

Expose typed `pipeline.yaml` switches independently: selector prefilter, conditional research synthesis, conditional edit contextualization, memory-candidate reuse, semantic memory synthesis, and per-article/per-day optional LLM call caps. Prefer stage-specific model overrides rather than automatically routing all subagent work through the primary editor. Ensure model/provider failures fall back to current safe publication behavior; avoid disabling necessary research or falsely marking unverified content complete.

Track provider-agnostic `llm_calls_per_article`, input/output/cache tokens, optional subagent trigger rate, shadow vs active decision differences, stage durations, article degradation/review rates, attribution/quality findings and estimated model cost if provider pricing is known. A zero-call optimization is a success only if downstream coverage and accuracy remain acceptable.

## Testing and controlled experiment

Use fixed representative fixture sets: single-source routine release, complex multi-source investigation, conflicting evidence, corrections/retractions, time-sensitive policy, near duplicate, missing content/embedding, weak citation, mixed-category article. For each, snapshot evidence bundles, model calls, routing decision and quality outcomes before and after a flag is enabled.

- Prefilter must never reject a novel story simply because titles are semantically close; ambiguous candidates route to selector or review.
- Structural validation is deterministic and cannot fabricate citations or silently correct facts.
- Conditional subagent trigger respects confidence thresholds and only fires when needed; tests prove skipped calls and forced calls.
- No duplicate tag or memory proposal despite retries; provider switch does not change deterministic category ownership.
- Performance measurements include retries and failures; report both means and tail latency on target hardware.

## Acceptance and rollback

Do not assert a fixed percentage reduction as guaranteed. Set measurable target bands during baseline collection (e.g. fewer optional LLM calls per published article and lower total memory/prompt tokens at equal or better attribution/quality). A milestone is acceptable only with comparative evidence; if recall, citation precision, unsupported claims or review burden worsen materially, revert **that feature flag**, not the entire memory migration. Document tradeoffs and explicitly retain LLM use wherever semantics require it.
