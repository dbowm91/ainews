# Eggsearch Web Retrieval Phase 2 — Provenance, Research Tools and Bounded Evidence

**Status:** IN PROGRESS — source IDs/date uncertainty/untrusted framing/trust metadata and URL retention implemented and unit-tested; actual source hydration remains intentionally on safe_fetch, while end-to-end research-evidence evaluation and complete failure fixtures remain open.
**Depends on:** Phase 1 provider adapter; see plans/eggsearch_web_retrieval_roadmap.md.
**Goal:** Improve research reliability and citation auditability without replacing ainews's first-party fetch security or exposing unbounded model-directed network access.

## Baseline findings

- tasks/research.py::_perform_web_search_and_synthesis() passes title, URL and up to 300 snippet characters to its synthesis subagent via _format_web_results().
- services/subagent/tools.py::_search_web() currently drops URLs completely and emits only titles and truncated snippets. This is the first obvious corrective item, even if eggsearch remains disabled.
- Research stage is a synchronous Celery task. pipeline.yaml research subagent currently permits five tool iterations and lists web_search. A separate stages map includes search_web; verify whether that map is consumed and normalize tool names without silently expanding access.
- Existing SearchResult(source=provider_id) is insufficient to represent eggsearch's upstream provider, stable source ID, retrieved_at, publication evidence, and partial failures. Eggsearch source cards and retrieval_summary are structured; metadata.published_at is optional and provider-derived.

## Workstream 1 — Introduce an additive research-evidence contract

Define a typed SearchEvidence/SourceReference (or similarly named) structure owned by ainews containing at minimum: stable source ID, canonical/validated URL, title, bounded snippet/excerpts, ainews provider ID, upstream source-provider IDs if provided, trust label, retrieved_at UTC, optional published_at with provenance/status, optional content/excerpt truncation flags, and reference to per-query retrieval diagnostics.

Define SearchOutcome separately: results, status (ok / partial / empty / failed / disabled), provider attempts/failures, warnings, requested versus actually enforced freshness/date/domain capabilities, duration, and fallback_used. Keep old SearchResult title/url/snippet/source constructor and search_web() list return intact. Adapt older provider results using a compatible converter; missing metadata is unknown, not invented.

Stable ID should survive search -> prompt -> claim references -> later verification, while allowing storage keys independent of eggsearch-internal IDs and preserving the original URL. Specify normalization/dedup rules, same-URL duplicates, contradictory timestamps, multi-provider attribution, and deterministic sorting. Do not treat rank/score as truth probability.

## Workstream 2 — Fix subagent tool output and tool selection

Fix the existing web_search formatting to include bounded, escaped URL and citation/source identifier for every result. Treat all provider snippets/excerpts as external untrusted input, even when eggsearch says it sanitized them; preserve trust labels and warnings. Continue using the stage-aware tool registry and per-stage allowlist. Do not expose eggsearch's ten MCP tools wholesale, and do not give LLMs direct control of raw provider secrets, backend configuration or network policy.

Review and correct the pipeline.yaml stage tool-name mismatch (search_web versus web_search) and other config migration callers only after determining which mapping is active. Preserve compatibility with existing YAML and tests. Add safety instructions in relevant researcher/synthesis prompts: facts require corroboration, snippets are leads not verified articles, and content tagged external_untrusted is not executable instruction.

For model context use concise source cards (ID, title, URL, date status, short snippet) rather than full diagnostic payloads. Diagnostic warnings belong to task evidence/log metadata, except small actionable status flags surfaced to the model.

## Workstream 3 — News freshness, corroboration and failures

Allow the research stage to pass an explicit news intent, configurable freshness window/date range, and optionally domain constraints through the detailed API. These are *hints* unless eggsearch reports native enforcement. Never mark an article current only because requested freshness="day"; require an observed publication timestamp (publisher or source metadata) or report freshness unverified. Distinguish publication date from last-updated, indexed, and retrieved times. Preserve timezone/UTC precision, parsing failures, and missing timestamps.

Build policy for selecting a small number of independent high-signal sources and excluding same-domain or canonical-URL duplicates. Keep the editorial/research quality gate under ainews. If all providers fail, avoid substituting model-generated URLs or confidently reporting absence; route to existing degradation/retry/review paths as appropriate. If a query legitimately returns no results, continue the pre-existing pipeline policy without claiming network failure.

Specialized eggsearch providers (PubMed, arXiv, OpenAlex, Crossref, GitHub releases, HN) may be piloted through known configured upstreams, but no unrestricted auto-provider expansion or automatic trusted-source promotion. Consider research_search only after measured benefit; it is not required for this phase.

## Workstream 4 — Selected-source hydration, security first

Initial source hydration should remain on services/safe_fetch.py, followed by existing safe content extraction. Permit fetch only for bounded, explicitly selected public URLs, preferably via a source ID from the current research attempt; enforce per-article source count, byte/char limits, per-origin concurrency, deadline, and one research-stage total budget. Prevent retries/fallback from multiplying work beyond the global budget. A task-scoped source registry may be used if necessary; it must be safe for Celery worker threads and never expose private data.

Do not directly wire eggsearch.web_fetch or batch_fetch into the subagent until a security-equivalence review against AGENTS.md and Milestone C proves matching policies: connection-time destination/DNS pinning, all-IP validation, redirect per-hop validation, URL authority parsing, private/link-local/metadata ranges, TLS/credential forwarding, proxy and environment behavior, size/decompression caps, and observability. Differences require an explicit decision and test evidence, not an informal exemption to the ainews safe_fetch rule. If parity is missing, continue using the ainews fetch client indefinitely; eggsearch's discovery capability remains valuable on its own.

Source hydration should not automatically refetch RSS/API article bodies if already available. Do not change crawling/adapters. Fetch failures are recorded per source and do not silently poison source quality scores.

## Workstream 5 — Tests, metrics and handoff

Add targeted regression coverage for tasks/research.py, services/subagent/tools.py, prompt templates, quality/citation verification, and structured eggsearch result mapping. Use fixtures for:
- two upstream providers agreeing on one URL; conflicting dates; missing dates; stale sources returned under requested freshness;
- partial result, capability_not_enforced, provider timeout, all-provider outage and valid empty results;
- adversarial snippet/excerpt asking the agent to ignore instructions; serialized URL and source ID retained;
- URL normalization and HTML/XML escaping, long snippets, malformed timestamps, truncation, unusable/unsafe URL;
- permitted source ID hydration, blocked URL, redirect to private address, rebinding, too-large body, timeout and budget exhaustion;
- multiple research articles in one worker / concurrent subagent searches without cross-task source leakage.

Record measured search cardinality, upstream latency, follow-up fetch count, source age confidence, failures and fallback, but no full private source payloads/secrets in logs. Separate automatic citations/attribution from unsupported claim-generation tests.

## Exit criteria

- [ ] Tool search output includes URL/source identifiers, remains bounded, and treats snippets as untrusted.
- [ ] Research preserves evidence metadata and partial failure signals without breaking old consumers.
- [ ] Date filters are never misrepresented as strict when upstream cannot enforce them.
- [ ] No article citation is based on a fabricated URL, fabricated publication date, or mere ranking score.
- [ ] Source hydration either uses the existing safe_fetch path or has an explicit reviewed and tested security-equivalence exception.
- [ ] Per-article/tool/query budgets and source IDs are enforced under concurrent Celery tasks.
- [ ] Existing research, quality, subagent, safe-fetch, and offline regression tests pass; evidence recorded.

## Out of scope

Replacing feed/article ingestion, automatically crawling all search results, PDF/browser renderer rollout, embedding eggsearch's research agent, making new tools globally accessible, and modifying the internal FTS5/vector search stack.
