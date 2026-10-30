# E02 — Multi-Query Research, Safe Document Retrieval, and Evidence-Origin Independence

**Status:** OPEN — P1
**Parent:** [Evidence-first editorial roadmap](evidence_first_editorial_roadmap_20261030.md)
**Dependency:** E01 eligibility interface (source evidence will become a required input).
**Outcome:** Convert original RSS/API input into a discovery lead and produce a verifiable set of **retrieved** sources for a story rather than just relevant search snippets.

## Current anchors

`tasks/research.py` searches `original_title + topics` and passes `SearchResult(title,url,snippet)` through `prepare_web_evidence`. The helper in `services/pipeline_optimizations.py` de-duplicates canonical URLs, caps per-domain to two, but does not prove source independence. Researcher prompts include the original article's extracted prose; `services/subagent/tools.py:_search_web` returns title/snippet but drops URL. `services/content_extractor.py` correctly reuses `services/safe_fetch.py` for untrusted URLs; leverage it.

## E02.1 — Event-oriented research query plan

1. Derive a compact event representation from lead metadata: actors/entities, event/action, date/version, known primary-document identifiers and domain category. Preserve discovery URL and publication time only as provenance, not authoritative framing.
2. Generate bounded, diverse queries from event attributes: primary documentation, independent reporting, technical/regulatory/research record, and gap/disconfirmation query where relevant. Prefer deterministic templates plus one optional LLM rewrite when extraction is ambiguous. Prevent direct copying of the source headline as every query.
3. Initial configurable budgets (tune via E06): maximum 3–5 distinct queries, approximately 8 fetched candidates, one gap-directed follow-up round, and explicit source/token/latency caps. Cache by canonical URL and evidence revision; retain provenance of cache hits.
4. Deduplicate URL variants, tracking parameters, mirrored content and syndicated/republished pages; distinguish publisher/domain from **underlying original reporting origin**. A site quoting a press release is not independent evidence of its announcement.
5. Search provider choice remains behind `services/search`; no migration to eggsearch or dependency on an extra inference provider is required.

## E02.2 — Research fetching interface and tool schema

- Add a typed research-source retrieval service using `safe_fetch_url()`, preserving pinned DNS/redirect SSRF policy, response byte/type limits, timeout and encoding behavior. Reuse `extract_article` or refactor extraction behind a shared safe fetch interface; do not fetch with `requests.get()`, `trafilatura.fetch_url()` or raw urllib.
- A web search returns `lead_only` metadata, never `verified`. Fetch status distinguishes `retrieved`, `retrieved_partial`, `paywalled`, `unsupported_content_type`, `rate_limited`, `unsafe_url`, `failed`.
- Return immutable evidence handles (trusted IDs minted server-side) with URL, title, publisher, canonical URL, acquired timestamp, published/updated timestamp if known, evidence type (`primary_document`, `original_reporting`, `secondary_reporting`, `commentary`), source family and bounded text spans plus a content hash. LLM output may propose but cannot forge IDs or force source promotion.
- Fix `web_search` tool output to include canonical URL and retrieval status; expose narrowly scoped `fetch_research_source` and `inspect_evidence` tools if the subagent needs a fuller document. Tool names must match YAML + registry + templates. Tests should exercise actual loaded configured subagent path, not only mocks of tool responses.
- Mark snippets and inaccessible pages as lead-only. Prevent model text such as "visited" or "corroborated" from changing retrieval state. Reject prompt injection in source text through escaped data boundaries and deterministic tool scoping.
- Do not automatically store unrestricted full publisher text. Use bounded excerpts and hashes with a documented retention policy and an optional short-lived safe cache for repeated research.

## E02.3 — Source independence and provenance

Define independently countable `evidence_origin_id`/family: primary issuer/document, original newsroom investigation or reporter, wire report, syndicated lineage, and known aggregation. Canonical domain is an attribute, **not** proof of independence. Maintain uncertainty when source lineage cannot be determined; unknown independence does not count as positively independent for a strict threshold.

Prefer original first-party sources for precise assertions (official changelog, court/regulator filing, peer-reviewed paper, CVE entry, release artifact) while preserving limitations: an issuer's claim about its own product is evidence of its **claim**, not necessarily independent empirical validation.

A cited page's existence is separate from whether it supports a given claim. E03 establishes support links.

## E02.4 — Backward-compatible data contract

- Introduce versioned internal `EvidenceSource` / `ResearchDossier` structures and persistence, ideally a small additive evidence table with article FK and unique article+canonical-URL+content-revision key. If opting for JSON sidecar, document scale and mutation semantics.
- Keep `Article.source_id` and `Article.original_url` as discovery provenance; keep existing `ResearchBrief` fields readable by current admin/report consumers. Do not make the public article schema expose internal evidence IDs.
- Distinguish data provenance for editorial memory and internal related articles, which are useful contextual leads but do not independently corroborate historical assertions.

## Required tests

- One feed item produces ≥2 independent fetched evidence origins when available, without using source body as verified proof.
- Three syndications of the same press release count as one origin; two URL aliases/canonical redirects do not count twice; a distinct verified original report is separately countable.
- Search query diversification with stable bounds, zero results, timeout, paywall, partial extraction, malformed content type, invalid URL and DNS/redirect-to-private guards.
- The subagent sees URLs and the fetch tools, but cannot mint trusted evidence IDs or launder a snippet into `retrieved`.
- Concurrent source fetches and Celery retry produce no duplicate evidence records; provider errors are measured and do not mark missing evidence verified.
- Post-migration fresh-install and upgrade tests for any new table. Preserve current article/page output.

**Not in scope:** Browser paywall circumvention, web crawling at arbitrary depth, requiring paid APIs, vector DB, direct publisher full-text redistribution, or semantic truth inference without supporting documents.
