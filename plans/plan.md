# Master Implementation Plan (Consolidated)

**Status:** Legacy waves 1–9 COMPLETED; editorial-memory C01–C03 implemented, C04 baseline triaged; C05 merge-readiness corrective OPEN on draft PR #19
**Last Updated:** 2026-10-31 (optional local TTS/MLX and EggFetch 0.3.0 adoption qualification registered; historical waves unchanged)
**Goal:** Track active workstreams for the personal/local or privately operated AInews instance while preserving historical completed security, quality and operational work. No public-release program is implied.

---

## Active Plan Registry — Optional Local TTS / Audio Narration (2026-10-30)

**Status:** Software implementation complete at `d4bc9c0` and `8f977d0`; native M4 Pro runtime smoke, direct listening, and isolated restart/lease recovery verified; actual macOS sleep/wake remains OPEN for canonical non-Docker deployment; Docker topology deferred; TTS options default OFF.
**Baseline:** main at 8fdfc61f9c7f450f686064a5cdb65fce020b9c04.
**Handoff branch:** plan/optional-tts-mlx-audio-20261030.
**Parent:** [Optional local narration roadmap](tts_audio_roadmap_20261030.md).
**Integration dependency:** PR #20 (plan/llm-native-editions-delivery-20261029) for immutable NewsletterEdition and public publication/identity contracts; do not modify in-flight PR branch as part of planning.

1. **M1 (P0):** [Durable post-publication jobs and deterministic narration scripts](tts_audio_m1_jobs_and_script_20261030.md) — IMPLEMENTED; post-publication and worker protocol tests recorded.
2. **M2 (P1):** [Native macOS MLX Breeze 4-bit, audio encoding and secure worker transfer](tts_audio_m2_mlx_worker_media_20261030.md) — SOFTWARE IMPLEMENTED; M4 Pro smoke and isolated restart/lease recovery verified; actual sleep/wake remains open.
3. **M3 (P1):** [Admin settings, authenticated media serving and READY-only playback](tts_audio_m3_admin_playback_20261030.md) — IMPLEMENTED; ready-only playback and private admin preview are tested.
4. **M4 (P1):** [Frozen newsletter narration and target-instance qualification](tts_audio_m4_editions_qualification_20261030.md) — EDITION SOFTWARE IMPLEMENTED; native runtime smoke, direct listening, and isolated restart/lease recovery verified; actual sleep/wake remains open.

**Policy:** Breeze TTS 2 self-hosted weights/quantizations/outputs are research/non-commercial only; enable only in a compliant private instance or obtain separate rights. No public release or restored-operator-database rehearsal is mandated. Implementation evidence and hardware qualification boundaries are recorded in the roadmap and M1–M4 plans. Code commits: `d4bc9c0`, `8f977d0`.

---

## Active Plan Registry — EggFetch HTTP Transport Pilot (2026-10-30)

**Status:** E1–E4 ADOPTION QUALIFICATION COMPLETE; EggFetch 0.3.0 is qualified for AInews. User-approved scope excludes full provider parity, proxy checks, a fixed five-minute prefill threshold, Intel macOS, and unsigned-tag cleanup. Direct ASGI slow-prefill/long-response, structured output, streaming/disconnect, concurrency-cap, and cancellation-route checks pass. All 5,050 GitHub CI tests pass with no test failures; the Linux full suite passes 5,048 tests. Clean-host installation/lifecycle checks pass on Linux x86_64, Linux aarch64, and macOS arm64. Existing repository-wide CI gates remain red: 73.60% coverage vs. the 80% threshold and 122 audit findings across dependencies unchanged by EggFetch. These are tracked as baseline maintenance, not EggFetch adoption blockers.
**Master workstream:** [EggFetch HTTP transport pilot](eggfetch_transport_pilot_20261030.md).

The pilot evaluates EggFetch as an owned, provider-neutral transport for AInews's LLM adapters. The integration is pushed on the adoption branch/PR and has not been merged or applied to the running development instance. Upstream compatibility and packaging work is closed in EggFetch 0.3.0. Relevant AInews paths, direct ASGI behavior, full suites, and target-platform checks are qualified. Proxy testing is out of scope. E4 records the Adopt decision and HTTPX rollback path.

The work is tracked in four implementation handoffs. E1–E3 are closed upstream; E4 governs the local implementation and final adoption decision:

1. **E1 (P0, closed upstream):** [SDK-compatible EggFetch transport bridge](eggfetch_e1_sdk_transport_bridge_20261030.md) — HTTPX transport integration and supported provider injection points.
2. **E2 (P0, closed upstream):** [Phase-correct response-header read timeout](eggfetch_e2_read_timeout_semantics_20261030.md) — timeout semantics, regression matrix, and HTTPX exception mapping.
3. **E3 (P1, closed upstream):** [Linux aarch64 packaging and release qualification](eggfetch_e3_platform_release_qualification_20261030.md) — platform artifact, exact-SHA checks, URL compatibility, and stable required upstream suite.
4. **E4 (P1, complete):** [AInews conformance and ASGI requalification](eggfetch_e4_ainews_requalification_20261030.md) — provider contracts, Python 3.12 target matrix, ASGI/local-inference checks, and Adopt decision.

E1–E3 were upstream EggFetch implementation work and are now closed by the published 0.3.0 release; E4's AInews integration and application qualification are complete. The release workflow resolved the previously intermittent benchmark proxy fixture and built/smoke-tested the supported artifacts. The user accepts v0.3.0 provenance for adoption; tag-signing cleanup is later manual work. AInews was qualified through direct ASGI; proxy testing is out of scope.

## Active Plan Registry — Editorial Memory, Shared Blackboard, and Pipeline Offload (2026-10-29)

**Status:** PR #19 implementation committed; unmerged/draft, all V2 flags off; C05 final merge-readiness work OPEN. No active deployed database needs migration evidence.  
**Baseline:** `main` commit `60fd18eda3a5e8852943e70bf32d4f957dbb3ff5`.  
**Handoff branch:** `plan/editor-memory-blackboard-synthesis-20261029`.  
**Master workstream:** [Editorial memory architecture roadmap](editor_memory_roadmap_20261029.md).

Implementation order and independently verifiable plan documents:

1. **M1 (P0):** [Correctness, subagent/tool/prompt wiring, bounded retrieval and schema parity](editor_memory_m1_correctness_20261029.md) — OPEN.
2. **M2 (P1):** [Scoped category memories, evidence schema, migration, hybrid search and read-only tools](editor_memory_m2_scoped_retrieval_20261029.md) — OPEN; depends on M1.
3. **M3 (P1):** [Incremental evidence-backed synthesis, HIGH review/retirement, shared blackboard](editor_memory_m3_synthesis_blackboard_20261029.md) — OPEN; depends on M2.
4. **M4 (P2):** [Deterministic pipeline offloading and conditional LLM invocations](editor_memory_m4_deterministic_pipeline_20261029.md) — OPEN; depends on baseline and retrieval; synthesis reuse depends on M3.
5. **M5 (local behavior):** [Verification, bounded retrieval comparisons and optional feature-activation evidence](editor_memory_m5_verification_20261029.md) — ongoing only for later opt-in behavior; *not* a merge block or a request for live database migration evidence.

### Active corrective implementation pass (2026-10-29)

Following the first runtime implementation commit `f3aa498e` on PR #19, additional correctness and safe private-instance activation gaps were identified. The [corrective pass overview](editor_memory_corrective_pass_overview_20261029.md) registers these independently executable handoffs:

1. **C01 (P0):** [Relevance-first FTS retrieval, scoped tools and cumulative budgets](editor_memory_corrective_01_retrieval_gates_20261029.md) — implemented with local evidence; C05 closes the stale category-summary read-path omission.
2. **C02 (P0):** [HIGH-memory active retirement, synthesis supersession, fair incremental synthesis and shared blackboard](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) — implemented with local tests; live/staged activation is optional and separate.
3. **C03 (P1):** [Confidence/importance separation, provenance checking and optional candidate reuse](editor_memory_corrective_03_candidate_quality_20261029.md) — implemented locally; provider-backed comparisons are relevant only before enabling/claiming benefits from optional reuse.
4. **C04 (P0 operational):** [CI baseline attribution and existing disposable checks](editor_memory_corrective_04_release_verification_20261029.md) — documented; there is no active deployed DB, and **no database migration evidence is required** for this merge. Unrelated CI/installer failures remain independent maintenance.
5. **C05 (P0 merge):** [Final stale-summary regression, current-HEAD checks, documentation and PR readiness](editor_memory_c05_merge_readiness_20261030.md) — **OPEN; sole focused remaining merge corrective**, subject to newly discovered regressions.

**Evidence status:** Local report `docs/editor-memory-verification-20261029.md` records 5,094 passing tests on an earlier implementation head and 63 focused tests after revision 043; rerun the full suite after C05's final code changes and record the **actual tested SHA**. CI failures are baseline-equivalent to `main`, not automatically memory regressions. **No deployed-database migration evidence or public-release checklist is requested.** Keep all V2 flags disabled when merging; optional feature activation/quality trials are separate.

This registry is the entry point for the new workstream; do not mark milestones complete until runtime changes, tests, and measurable evidence have landed. Existing completed wave history below remains historical and is not reopened.

---

## Executive Summary

This is the **historical consolidated implementation plan** for the completed early waves of the ainews project. New workstreams, including editorial memory, are registered above with separate milestone handoffs. Previous architecture review output files (`plans/review_*.md`) have been deleted — their findings are incorporated into the wave tasks below.

**Key Targets:**
- **Test Coverage:** 80% (Current: 80%) ✅
- **Mypy Errors:** 0 (Current: 0) ✅
- **Ruff Errors:** 0 (Current: 0) ✅
- **Performance:** 2-4x throughput increase via bottleneck removal.

---

## Wave 1: Critical Fixes & Stability ✅ COMPLETED

*Focus: Fixing CI blockers, resource leaks, and immediate security risks.*

- 1.1 Fix share_configs Table Missing Error ✅
- 1.2 Fix Extraction Fallback Test ✅
- 1.3 Fix Failing Audit Test ✅
- 1.4 Fix Limiter Slot Leak ✅
- 1.5 Fix Thread-Blocking Polling in Limiter ✅
- 1.6 Fix P1 Security: .env Permissions (Fail-Closed) ✅
- 1.7 Fix P1 Security: Redis CVE-2025-49844 ✅
- 1.8 Add Session Regeneration ✅

---

## Wave 2: Architecture & Reliability ✅ COMPLETED

*Focus: Throughput, clean layering, and defense-in-depth.*

- 2.1 Resolve Layer Violations & Move URL Utils ✅
- 2.2 Increase Pipeline Throughput ✅
- 2.3 SSRF Hardening (IP Normalization) ✅
- 2.4 MultiFernet Webhooks ✅
- 2.5 Semantic Search OOM Protection ✅
- 2.6 Asset Bundling (CSS/JS) ✅

---

## Wave 3: Advanced Security ✅ COMPLETED

*Focus: 2FA enhancements and secure storage.*

- 3.1 2FA Backup Codes ✅
- 3.2 2FA Rate Limiting ✅
- 3.3 Encrypt TOTP Secrets ✅ (See Note 1)
- 3.4 Fix CSP unsafe-inline ✅

---

## Wave 4: Performance & Optimization ✅ COMPLETED

*Focus: Efficiency and maintainability.*

- 4.1 Token Budgeting & LLM Caching ✅
- 4.2 DB & Query Optimization ✅
- 4.3 Refactor Large Files ✅

---

## Wave 5A: Code Reliability Fixes (HIGH Priority) ✅ COMPLETED

*Focus: Fix code bugs that could cause runtime failures.*

- 5A.1 Add `max_retries` to Celery Tasks ✅
- 5A.2 ~~Fix `propose_trend_memory` Return Type Documentation~~ — COMPLETED
- 5A.3 Document `PipelineRootConfig.experiments` Field ✅
- 5A.4 Fix Degradation Behavior Documentation ✅

---

## Wave 5B: Documentation Accuracy Fixes (MEDIUM Priority) ✅ COMPLETED

*Focus: Correct inaccurate documentation that could mislead future agents.*

- 5B.1 Fix `chat_structured` Signature ✅
- 5B.2 Fix Stage Transitions Table ✅
- 5B.3 ~~Fix Newsletter Endpoint Name~~ — NO FIX NEEDED
- 5B.4 Document `RawItem` Schema ✅
- 5B.5 Fix Content Extractor Fallback Documentation ✅
- 5B.6 Fix `reload_beat_schedule` Documentation ✅
- 5B.7 Update Prompt File Count — ALREADY CORRECT
- 5B.8 Fix `extract_json` Function Name ✅
- 5B.9 Fix Subagent YAML Config Example — ALREADY FIXED
- 5B.10 Fix Search Providers YAML Example — ALREADY CORRECT
- 5B.11 Clarify "Normal Flow" Doesn't Always Include Review ✅
- 5B.12 Document Newsletter Idempotency Key TTL ✅

---

## Wave 5C: Documentation Gaps (LOW Priority) ✅ COMPLETED

*Focus: Comprehensive documentation improvements.*

- 5C.1 Document Missing Models ✅
- 5C.2 ~~Add Missing Model Attributes~~ — REMOVED (INACCURATE)
- 5C.3 Document ThreadPoolExecutors ✅
- 5C.4 Show Context Managers Correctly ✅
- 5C.5 Document Missing API Endpoint ✅
- 5C.6 Document LLM Types ✅
- 5C.7 Fix Schema Location Contradiction ✅
- 5C.8 Document Subagent Package Structure ✅

---

## Wave 6: Quality, Typing & Docs (Medium Priority) ✅ COMPLETED

*Focus: Long-term health and documentation.*

### 6.1 Boost Test Coverage to 80% ✅
- **Result:** 217 new tests written across 12 modules. Coverage improved to 80%+ on all target modules.

### 6.2 Mypy Resolution ✅
- **Result:** 427 errors → 0 errors across all files.

### 6.3 OpenAPI & Documentation Sync ✅
- **Result:** `openapi.yaml` synced with 44 routes.

---

## Wave 7: Infrastructure & Polish (Long-term) ✅ COMPLETED

*Focus: Containerization and observability.*

### 7.1 Docker Hardening
- Multi-stage build, `read_only: true`, tmpfs for `/tmp`.
- **Status:** ✅ DONE

### 7.2 Observability Fixes
- `is_fully_healthy` property added to `HealthResult`.
- **Status:** ✅ DONE

---

## Wave 8: Adapter Bug Fixes ✅ COMPLETED

*Focus: Bugs found during architecture review that weren't in original plan.*

### 8.1 Fix WebAdapter `_scrape_listing` Pagination
- Added `max_items` field to `WebConfig` (default 50, max 200).
- **Status:** ✅ DONE

---

## Wave 9: Architecture Review Follow-up ✅ COMPLETED

*Focus: Fix remaining issues identified in architecture reviews (infrastructure, prompts, config, llm_providers, subagent, search_providers, services, routes, pipeline, tasks, schemas, utils, models, adapters).*

**21 items verified and completed:**

| Item | Description | Priority |
|------|-------------|----------|
| 9.1 | SITE_URL Empty String Fallback | CRITICAL |
| 9.2 | ResearchBrief Schema Documentation Wrong | HIGH |
| 9.3 | Writer Prompt Target Documentation | MEDIUM |
| 9.4 | TopicNote.topic Index Documentation | LOW |
| 9.5 | TrendMemory.last_accessed_at Auto-Update | LOW |
| 9.6 | WebConfig Field Descriptions | LOW |
| 9.7 | DeepSeek API Key Environment Variable | LOW |
| 9.8 | cleanup_interval_minutes Unused | LOW |
| 9.9 | REDIS_MAX_CONNECTIONS Inconsistent Defaults | LOW |
| 9.10 | format_date() Docstring Incomplete | LOW |
| 9.11 | Edit Quality Gate Documentation Incomplete | MEDIUM |
| 9.12 | Subagent Self-Correction Documentation Wrong | MEDIUM |
| 9.13 | Subagent Tool Signatures Missing Parameters | LOW |
| 9.14 | Middleware Chain Description Misleading | LOW |
| 9.15 | Content Extractor Fallback Documentation Wrong | LOW |
| 9.16 | WebAdapter Trafilatura Fallback Missing | LOW |
| 9.17 | SearchConfig YAML Key Mismatch | LOW |
| 9.18 | services/llm/types.py Does Not Exist | LOW |
| 9.19 | Subagent Edit Contextualization Content Drift | LOW |
| 9.20 | Request ID Propagation Documentation | LOW |
| 9.21 | cleanup_inactive_subscribers Missing verify_task | HIGH |

---

## Success Metrics

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| Test Pass Rate | 99% | 100% | ✅ 100% |
| Test Coverage | 62% | 80% | ✅ 80% (217 new tests, 12 modules 96-100%) |
| Mypy Errors | 423 | 0 | ✅ 0 (427 → 0) |
| Ruff Errors | 0 | 0 | ✅ 0 |
| Layer Violations | ~6 | 0 | ✅ 0 |
| P1 Security Issues | 3 | 0 | ✅ 0 |
| Architecture Doc Bugs | 21 | 0 | ✅ 0 (all waves 5A-5C completed) |
| Architecture Doc Accuracy | 864/905 | 905/905 | ✅ 905/905 |
| OpenAPI Sync | Partial | 44 routes | ✅ 44 routes synced |

---

## Implementation History (Completed)

- Wave 1: Critical Fixes & Stability (2026-05-31)
- Wave 2: Architecture & Reliability (2026-05-31)
- Wave 3: Advanced Security (2026-05-31)
- Wave 4: Performance & Optimization (2026-05-31)
- Wave 5A: Code Reliability Fixes (2026-06-02)
- Wave 5B: Documentation Accuracy Fixes (2026-06-02)
- Wave 5C: Documentation Gaps (2026-06-02)
- Wave 6: Quality, Typing & Docs (2026-06-02)
- Wave 7: Infrastructure & Polish (2026-06-02)
- Wave 8: Adapter Bug Fixes (2026-06-02)
- Wave 9: Architecture Review Follow-up (2026-06-02) - COMPLETED: 21 items verified

---

## Previously Verified as Already Fixed

The following items from architecture reviews were verified as **already correctly implemented**:

| Item | Verification |
|------|--------------|
| cleanup_inactive_subscribers verify_task() | `tasks/subscribers.py:29` has verify_task call |
| Content drift in edit contextualization | Both templates say "and trend memory" |
| Edit quality gate 3 conditions | `architecture/tasks.md:74` shows all 3 |
| No types.py reference in docs | grep found no matches |
| CELERY_BROKER_URL correct | `architecture/config.md:508` correct |
| SEARXNG_BASE_URL not in docs | grep found no matches |
| Self-correction mechanism correct | `architecture/subagent.md:150-166` correct |
| Disabled stage routing correct | `architecture/pipeline.md:268-277` correct |
| last_crawled correct field name | `architecture/models.md:162` correct |
| WebAdapter trafilatura fallback | `architecture/adapters.md:169` correct |
| Request delay scope clarified | `architecture/adapters.md:188-190` already mentions listing, pagination, and article fetches |
| Missing API endpoints documented | `/api/v1/sources/health`, `/api/v1/workers/health`, `/api/v1/task/<task_id>`, `/api/v1/newsletters/performance` all in `architecture/routes.md` |
| DuckDuckGo provider uses library | Uses `duckduckgo_search` library's internal HTTP client (not our session) - documented in search_providers review |
| Newsletter two-endpoint pattern | Both `/newsletters/performance` and `/newsletters/stats` exist - correctly documented |
| chat_structured signature correct | Has `max_validation_retries` and `stage` params - architecture docs updated |
| Subagent YAML config fixed | `tool_timeout` and `default_model` fields removed from example |
| Search providers YAML fixed | Uses flat list with `default_search_provider` key |

---

## Notes

- This plan is the **single source of truth** for implementation work
- All architecture review findings have been incorporated into the wave tasks above
- Previous review output files (`plans/review_*.md`) have been deleted
- For architecture review workflow, see `architecture/review_plan.md`

### Implementation Notes

**Note 1 (TOTP Encryption):** Wave 3 item 3.3 "Encrypt TOTP Secrets" was documented as implemented. Upon verification, TOTP secrets are stored as plain text in `AdminUser.totp_secret`. The documentation has been corrected to reflect this. TOTP secret encryption at rest is a potential future enhancement but is not currently implemented.

**Note 2 (Detailed Implementation Notes):** Detailed step-by-step implementation notes for each wave item have been pruned from this document to reduce clutter. The summary lists indicate completion status. For historical reference of implementation details, see git history.

**Note 3 (Plan Maintenance):** This plan file is now complete. All items have been verified as implemented. Future work should be tracked in issue trackers or as separate documents, not in this plan.

## Active feature roadmaps (independent of the completed historical waves)

- **LLM-native access, immutable newsletter editions and email-as-distribution** — **IMPLEMENTED LOCALLY; CORRECTIVE PASS OPEN** (2026-10-29 / reviewed 2026-10-30). See [roadmap](llm_native_publication_roadmap_20261029.md) and its five handoff plans: [M1 identity and visibility](llm_native_m1_public_identity_visibility_20261029.md), [M2 REST/MCP and agent quotas](llm_native_m2_agent_access_20261029.md), [M3 newsletter corrective and edition foundation](llm_native_m3_newsletter_correctness_editions_20261029.md), [M4 optional email distribution/outbox](llm_native_m4_distribution_email_20261029.md), [M5 independent schedule, editorial selection and archive](llm_native_m5_newsletter_profiles_archive_20261029.md). This roadmap targets optional private-instance capabilities, **not public-release certification**. M1–M5 code is committed on PR #20; branch-local regression evidence exists, but combined migration and target-instance qualification remain open.

- **LLM-native corrective follow-up — C01–C04 implemented; C05 target-specific runtime qualification open** (2026-10-30). [Corrective overview](llm_native_corrective_pass_overview_20261030.md) and handoffs: [C01 migration lineage and publication boundary](llm_native_corrective_01_migration_visibility_20261030.md), [C02 REST/MCP read-layer and access safety](llm_native_corrective_02_agent_read_contract_20261030.md), [C03 email/outbox correctness](llm_native_corrective_03_email_delivery_20261030.md), [C04 schedules and editorial selection](llm_native_corrective_04_schedule_editorial_20261030.md), [C05 CI triage and private-instance qualification](llm_native_corrective_05_integration_qualification_20261030.md). Local Granian ASGI/Redis/Celery/SMTP-sink smoke and migration evidence are recorded; intended-host Beat/recovery, provider TLS/DKIM and applicable performance gates remain. Proxy testing is separate; restored-target DB migration evidence is closed/not required. See [PR #20](https://github.com/dbowm91/ainews/pull/20).

(End of file - reduced from 789 to ~200 lines)
