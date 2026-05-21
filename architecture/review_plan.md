# Architecture Review Plan

**Status:** IN PROGRESS
**Created:** 2026-05-21
**Goal:** Review each architecture document, verify claims in code, and identify improvements and bugs.

---

## Module Review Assignments

Each subagent will:
1. Read the architecture document for their assigned module
2. Verify claims against actual implementation in the codebase
3. Interrogate the code for improvements, bugs, and inconsistencies
4. Write an improvement plan to `plans/<module>_review.md`

---

## Review Tasks

### 1. Overview Module
**Document:** `architecture/overview.md`
**Review Output:** `plans/overview_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- System diagram accuracy
- Module index completeness
- Data flow descriptions
- Configuration file inventory
- Security architecture claims
- Directory structure accuracy
- Layering rules validation

---

### 2. Adapters Module
**Document:** `architecture/adapters.md`
**Review Output:** `plans/adapters_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- BaseSourceAdapter registry pattern correctness
- RSSAdapter fetch/parse implementation
- APIAdapter JSONPath/pagination claims
- WebAdapter CSS selector extraction
- SSRFSafeRedirectHandler blocklist patterns
- Source configuration schema accuracy
- Error handling claims (backoff behavior)

---

### 3. Schemas Module
**Document:** `architecture/schemas.md`
**Review Output:** `plans/schemas_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- StageConfig stub status
- PipelineRootConfig completeness
- SourceConfig.adapter_config field_validator
- RSSConfig/APIConfig/WebConfig schema accuracy
- LLM response schemas (SelectionResult, ResearchBrief, CondensedArticle, ExecutiveSummary, NewsletterBrief)
- Task validation schemas
- Schema field name accuracy vs documentation

---

### 4. Routes Module
**Document:** `architecture/routes.md`
**Review Output:** `plans/routes_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- Blueprint URL prefix accuracy
- Admin API endpoint completeness
- Public routes implementation
- Authentication security features (TOTP, session binding, backup codes)
- CSRF protection claims
- Rate limiting configuration
- api_tokens_bp registration status

---

### 5. Pipeline Module
**Document:** `architecture/pipeline.md`
**Review Output:** `plans/pipeline_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- Pipeline stage status values
- Stage transition logic
- Degradation behavior accuracy
- Newsletter generation flow
- Executive summary 3-stage LLM claims
- Celery Beat schedule accuracy
- Two-tier retry system implementation
- Circuit breaker configuration
- Fallback chain dynamic resolution

---

### 6. Models Module
**Document:** `architecture/models.md`
**Review Output:** `plans/models_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- Article model pipeline_status values
- Source model health tracking fields
- AdminUser TOTP/backup code fields
- TrendMemory embedding storage (text vs vector)
- Relationship accuracy (many-to-one, many-to-many)
- Index definitions
- Model field naming (type vs source_type, last_fetch_at vs last_crawled)

---

### 7. Services Module
**Document:** `architecture/services.md`
**Review Output:** `plans/services_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- LLM provider base interface completeness
- Circuit breaker pattern implementation
- Rate limiter slot management (finally block usage)
- Newsletter pipeline 3-stage orchestration
- Article processing stage responsibilities
- Trend memory service operations
- Search provider inventory
- Layering compliance (no adapter imports)

---

### 8. Subagent Module
**Document:** `architecture/subagent.md`
**Review Output:** `plans/subagent_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- Tool registry completeness (9 tools listed)
- ToolDefinition schema (dataclass fields vs documentation)
- run_subagent/run_subagent_with_tools signatures
- Chain system configuration
- Middleware pattern (sync wrap)
- Error handling (retry, revocation)
- Tool timeout configuration

---

### 9. Utils Module
**Document:** `architecture/utils.md`
**Review Output:** `plans/utils_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- URL validation SSRF protection
- Text utilities implementation
- DateTime parsing accuracy
- Security utilities (token generation, constant-time compare)
- HTML processing (strip_tags, linkify, extract_text)
- Hash utilities
- Pure function claims vs actual global state
- Module dependencies

---

### 10. Tasks Module
**Document:** `architecture/tasks.md`
**Review Output:** `plans/tasks_review.md`
**Assigned To:** Subagent (explore agent)

**Focus Areas:**
- Task file to stage mapping accuracy
- Stage transition table correctness
- run_stage helper lifecycle
- Degradation path claims
- Celery Beat schedule accuracy
- Rate limiting slot management
- Max retries configuration

---

## Verification Checklist for Each Module

For each module, verify:
- [ ] Document claims match actual code implementation
- [ ] File paths referenced exist
- [ ] Class/function names are accurate
- [ ] Field names match model definitions
- [ ] Configuration structures are accurate
- [ ] Error handling behavior is documented correctly
- [ ] No missing or undocumented features
- [ ] No dead code or deprecated patterns
- [ ] Security claims are accurate

## Output Format for Review Plans

Each review plan should contain:

```markdown
# [Module] Architecture Review

## Verified Correct
- List of claims that are correct and verified

## Discrepancies Found
- List of issues where documentation doesn't match code

## Bugs Identified
- Actual bugs discovered in the implementation

## Improvement Suggestions
- Code improvements that don't match documentation

## Questions for Architecture
- Clarifications needed on design decisions
```

---

## Execution

Launch subagents in parallel for each module to maximize efficiency.