# Architecture Review Plan

**Status: INCOMPLETE** - Review completed, implementation work is in progress

This plan coordinates review of architecture documentation against actual implementation code.

**Excluded:** `review_plan.md` (this file)

**Reviewed Modules:**
1. `architecture/overview.md`
2. `architecture/models.md`
3. `architecture/adapters.md`
4. `architecture/services.md`
5. `architecture/tasks.md`
6. `architecture/routes.md`
7. `architecture/schemas.md`
8. `architecture/pipeline.md`
9. `architecture/subagent.md`
10. `architecture/utils.md`

---

## Review Instructions for Subagents

Each subagent will:
1. Read the assigned architecture document
2. Verify claims against actual implementation in the codebase
3. Identify bugs, inconsistencies, and improvement opportunities
4. Write findings to `plans/review/{module}_review.md`

**Verification approach:**
- Cross-reference architectural claims with actual code
- Check field names, method signatures, class relationships
- Identify discrepancies between documentation and implementation
- Note layer violations, security issues, performance concerns

---

## Module Review Assignments

### 1. Overview Module Review
**Subagent:** `explore` agent  
**File:** `architecture/overview.md`  
**Output:** `plans/review/overview_review.md`

Review the system architecture overview, directory structure, layering rules, and data flow summaries. Verify the module index, system diagram, and cross-references to other architecture documents.

---

### 2. Models Module Review
**Subagent:** `explore` agent  
**File:** `architecture/models.md`  
**Output:** `plans/review/models_review.md`

Review database models (article, source, newsletter, pipeline, context, webhook, auth, tag, search, audit, share). Verify:
- Model field names and types
- Relationship cardinalities
- Index definitions
- Security fields (TOTP, backup codes)

---

### 3. Adapters Module Review
**Subagent:** `explore` agent  
**File:** `architecture/adapters.md`  
**Output:** `plans/review/adapters_review.md`

Review RSS, API, and Web adapters. Verify:
- Adapter pattern and registry
- SSRF protection implementation
- Session ownership differences
- Error handling conventions
- Configuration field names (config vs adapter_config)

---

### 4. Services Module Review
**Subagent:** `explore` agent  
**File:** `architecture/services.md`  
**Output:** `plans/review/services_review.md`

Review business logic layer (LLM providers, pipeline services, rate limiter, email, webhooks, trend memory). Verify:
- Provider base class interface
- Circuit breaker pattern
- Rate limiter class name (ModelLimiter) and methods (acquire, release, get_active)
- Email module-level functions vs class
- Layering violations documentation

---

### 5. Tasks Module Review
**Subagent:** `explore` agent  
**File:** `architecture/tasks.md`  
**Output:** `plans/review/tasks_review.md`

Review Celery task implementations. Verify:
- Task inventory by stage
- Stage transitions and quality gates
- run_stage helper signature and behavior
- Celery Beat schedule (14 tasks)
- Degradation behavior

---

### 6. Routes Module Review
**Subagent:** `explore` agent  
**File:** `architecture/routes.md`  
**Output:** `plans/review/routes_review.md`

Review Flask blueprints (public_bp, admin_bp, admin_api_bp). Verify:
- URL prefixes (/, /admin, /api/v1)
- Route inventory matches actual endpoints
- Authentication methods
- Template structure

---

### 7. Schemas Module Review
**Subagent:** `explore` agent  
**File:** `architecture/schemas.md`  
**Output:** `plans/review/schemas_review.md`

Review Pydantic validation models. Verify:
- PipelineRootConfig structure (StageConfig is a stub)
- SourceConfig field_validator behavior
- LLM response schemas (SelectionResult, ResearchBrief, CondensedArticle, NewsletterBrief)
- NewsletterBrief does NOT have preamble/footer/articles fields
- Task validation schemas

---

### 8. Pipeline Module Review
**Subagent:** `explore` agent  
**File:** `architecture/pipeline.md`  
**Output:** `plans/review/pipeline_review.md`

Review newsletter pipeline stages (select, research, write, edit, finalize). Verify:
- Stage status values and transitions
- Quality gates (confidence="low", degenerate checks, validation)
- Degradation behavior (degradation_count >= 2)
- Two-tier retry system (Celery task retry + stage failure retry)
- Circuit breaker and dynamic fallback chain
- Newsletter generation flow (3-stage LLM)

---

### 9. Subagent Module Review
**Subagent:** `explore` agent  
**File:** `architecture/subagent.md`  
**Output:** `plans/review/subagent_review.md`

Review tool-enabled LLM agents. Verify:
- ToolDefinition dataclass (no `cached` field)
- Tool registry entries
- Chain system (SubagentChainStep, SubagentChainConfig in schemas/pipeline.py)
- Middleware pattern (wrap vs as_computed)
- Provider chat() vs chat_with_tools() distinction
- Tool results re-injection behavior within single chat_with_tools() call

---

### 10. Utils Module Review
**Subagent:** `explore` agent  
**File:** `architecture/utils.md`  
**Output:** `plans/review/utils_review.md`

Review pure utility functions. Verify:
- URL validation layering (utils/url.py vs services/url.py)
- validate_url_safe() uses global mutable state (_dns_cache, _dns_executor)
- Text, datetime, security, hash, html utilities
- __all__ exports pattern
- Empty __init__.py in utils/

---

## Execution Order

Launch all 10 subagents in parallel. Each subagent will:
1. Read assigned architecture document
2. Explore relevant codebase sections
3. Verify claims and identify issues
4. Write improvement plan to plans/review/

---

## Success Criteria

Each review plan in `plans/review/` will contain:
- **Verified Claims:** Documentation matches implementation
- **Discrepancies:** Any field names, signatures, or behaviors that differ
- **Bugs:** Identified bugs or potential issues
- **Improvements:** Suggested code improvements with rationale
- **Security Concerns:** Any security-relevant findings
- **Layering Violations:** Any violations not already documented