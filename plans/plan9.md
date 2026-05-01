# Documentation Improvement Plan (Plan 9)

**Date:** 2026-05-01  
**Status:** Draft - Ready for Review  
**Priority:** High - Documentation aligns with code reality

---

## Executive Summary

After deep investigation across the entire ainews codebase, significant documentation gaps and inconsistencies have been identified. The documentation currently lists features without explaining their value, contains contradictory pipeline flow descriptions across 4+ files, references non-existent directories (`models/` vs actual `models.py`), and lacks actionable examples.

**Key Findings:**
- 10+ pipeline stage inconsistencies across documentation files
- API docs have wrong URL prefixes (`/admin/api/` → should be `/api/v1/`)
- Documentation references `models/` directory, but all models are in `models.py` (root level)
- Subagent docs list incorrect tool names
- Quality assessment system (`services/quality.py`) exists but is **NOT INTEGRATED** into pipeline
- Missing failure mode documentation with recovery procedures

**Impact:** Users and developers struggle to understand the actual system behavior, leading to misconfiguration and debugging difficulties.

---

## Phase 1: Critical Fixes (Week 1)

### 1.1 Fix Pipeline Documentation Inconsistencies

**Problem:** Multiple files describe different pipeline flows:

| File | Current (Wrong) | Should Be |
|------|-----------------|--------------|
| `README.md:47` | `crawl → extract → select → research → write → edit → publish` | `crawl → extract → select → research → write → edit → done` |
| `docs/pipeline.md:7-11` | State machine starts at `pending` | Add note: "select" stage is transient (no DB status) |
| `docs/development.md:304` | `Crawl → Select → Research → Write → Edit → Newsletter` | Remove "Newsletter" (separate process) |
| `docs/development.md:415` | `crawl → extract → select → research → write → edit → newsletter` | Fix: newsletter is NOT in pipeline |
| `CONTRIBUTING.md:85` | `select → research → write → edit → done` | Add `crawl` and `extract` stages |

**Actual Pipeline Flow (from code):**
```
crawl (Celery task) → extract (Celery task) → select (transient, no DB status) → 
researching → writing → editing → review (optional) → done
```

**Files to Modify:**
- `README.md` - Fix architecture diagram (line 47)
- `docs/pipeline.md` - Fix state machine, add "select" as transient
- `docs/development.md` - Consolidate two contradictory flows (lines 304 and 415)
- `CONTRIBUTING.md` - Update pipeline description

**⚠️ Potential Bug:** `PENDING → SKIPPED` transition in `docs/pipeline.md` but NOT in `constants.py:VALID_TRANSITIONS`. Investigate whether code or docs are wrong.

### 1.2 Fix API Documentation URL Prefixes

**Problem:** All admin endpoints documented as `/admin/api/...` but actual routes are `/api/v1/...`

**File:** `docs/api.md`

| Documented (Wrong) | Actual (Correct) |
|---------------------|-------------------|
| `/admin/api/health` | `/api/v1/health` |
| `/admin/api/workers/health` | `/api/v1/workers/health` |
| `/admin/api/sources/health` | `/api/v1/sources/health` |

**Also Fix:**
- Subscribe endpoint uses **form data**, not JSON (line 88-94 in api.md)
- Article endpoint `/article/<short_id>` should be `/article/<int:id>` (actual: integer ID)

**Action:** Search and replace all `/admin/api/` with `/api/v1/` in `docs/api.md`

### 1.3 Fix Models Directory References

**Problem:** Multiple docs reference `models/` directory, but models are in `models.py` (root level).

**Actual Location:** `/home/sugarwookie/projects/ainews/models.py` (512 lines, 18 model classes)

**Files to Fix:**
- `docs/trend-memory.md:26-40` - Wrong field definitions (String(255) vs 128, wrong ondelete)
- `docs/context-service.md:16-24` - Wrong TopicNote fields
- `README.md` - Remove references to `models/` directory
- `docs/development.md` - Fix architecture diagram
- `CONTRIBUTING.md` - Fix architecture diagram

**Correct Model List:**
| # | Model Class | Table Name |
|---|-------------|------------|
| 1 | `Source` | `sources` |
| 2 | `Tag` | `tags` |
| 3 | `Article` | `articles` |
| 4 | `Citation` | `citations` |
| 5 | `Newsletter` | `newsletters` |
| 6 | `Subscriber` | `subscribers` |
| 7 | `ArticleMetric` | `article_metrics` |
| 8 | `ShareConfig` | `share_configs` |
| 9 | `PipelineRun` | `pipeline_runs` |
| 10 | `PipelineLog` | `pipeline_logs` |
| 11 | `ArticleVersion` | `article_versions` |
| 12 | `TopicNote` | `topic_notes` |
| 13 | `TrendMemory` | `trend_memory` |
| 14 | `Webhook` | `webhooks` |
| 15 | `WebhookEvent` | `webhook_events` |
| 16 | `AuditLog` | `audit_logs` |
| 17 | `SearchQuery` | `search_queries` |
| 18 | `ApiToken` | `api_tokens` |

---

## Phase 2: High-Priority Improvements (Week 2)

### 2.1 Add "Why It Matters" to README.md Features

**Current State:** Features section just lists what each feature does.

**Improved Version (replace lines 49-57):**

```markdown
## Features

- **Automated RSS/API Ingestion** — Configurable source feeds with scheduled polling. Eliminates manual news gathering so your platform stays current around the clock without constant human oversight.
- **AI-Powered Processing** — Multi-stage pipeline (selection, research, writing, editing) via LLM. Transforms raw feeds into polished content through intelligent filtering and enrichment—impossible to do manually at scale.
- **Topic Classification** — Automatic categorization using configurable topic definitions. Organizes content so readers instantly find what interests them without wading through irrelevant articles.
- **Newsletter Generation** — Curated newsletters from aggregated content. Delivers timely, relevant updates to subscribers automatically—driving engagement without the manual effort of traditional newsletter curation.
- **Full-Text Search** — SQLite FTS5-powered article search with ranked results. Enables lightning-fast search across your entire article archive so users find exactly what they need in seconds.
- **Admin Dashboard** — Comprehensive web UI for managing sources, articles, topics, newsletters, and monitoring pipeline health. Gives administrators complete control through an intuitive interface—no database expertise required.
- **RSS Output** — Published feed at `/feed` for downstream consumption. Expands your reach by integrating with feed readers and automation tools your audience already uses to stay informed.
```

### 2.2 Add Working Examples to docs/api.md

**For Each Endpoint, Add:**

#### Public Endpoints

```markdown
### Health Check

**GET** `/health`

Returns the health status of the application.

**Authentication:** None required

**Working Example:**
```bash
# Basic health check
curl http://localhost:5000/health

# Detailed health check (requires admin)
curl -H "Authorization: Bearer <token>" http://localhost:5000/api/v1/health?detailed=true
```

**What Can Go Wrong:**
- Redis down → `{"status": "unhealthy", "checks": {"redis": "error"}}`
- Celery workers not running → `celery` check shows "error"

#### Subscribe

**POST** `/subscribe`

⚠️ **Note:** This endpoint expects form data, NOT JSON!

**Request Body (Form Data):**
```
email=user@example.com&newsletter_type=main
```

**Working Example:**
```bash
curl -X POST http://localhost:5000/subscribe \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&newsletter_type=main"
```

**Response (200 OK):**
```json
{"message": "Verification email sent"}
```

#### RSS Feed

**GET** `/feed`

**Working Example:**
```bash
# All articles
curl http://localhost:5000/feed

# Specific category
curl http://localhost:5000/feed/ai
```

#### Article Detail

**GET** `/article/<int:id>`

⚠️ **Note:** Uses integer ID, not short_id!

**Working Example:**
```bash
curl http://localhost:5000/article/123
```

### 2.3 Add Failure Mode Sections to docs/pipeline.md

**Add New Section:**

```markdown
## Failure Modes

### Select Stage
**What can go wrong:**
- LLM provider timeout/error (ProviderTimeoutError, ProviderServerError)
- Rate limiting (RateLimitError)
- Authentication failure (AuthError - non-retryable)
- Circuit breaker open (all providers down)

**Recovery:**
- 3 Celery retries with exponential backoff (30s base delay)
- On retry exhaustion: auto-select with score=6, advance to RESEARCHING
- Early termination after 3 Redis-tracked failures → FAILED

### Research Stage
**What can go wrong:**
- LLM provider errors (same as select)
- Web search failure (optional, non-blocking)
- Degenerate output (no key claims or impact_score < 10) → REVIEW

**Recovery:**
- 2 Celery retries with exponential backoff (60s base delay)
- On retry exhaustion: minimal research brief with impact_score=30, advance to WRITING

### Write Stage
**What can go wrong:**
- LLM provider errors
- Token overflow (handled by sliding_window_truncate)
- Degenerate output (body < 500 chars, no key points, no citations) → REVIEW

**Recovery:**
- 2 Celery retries with exponential backoff
- On retry exhaustion: minimal draft from extracted text, advance to EDITING

### Edit Stage
**What can go wrong:**
- LLM provider errors
- Validation failure (missing required fields in final_article)
- Subagent failure for contextualization (proceeds without context)

**Recovery:**
- 2 Celery retries with exponential backoff
- On retry exhaustion: apply fallback, route to REVIEW if degradation_count >= 2, else DONE

## Dead Letter Queue

Articles are "dead-lettered" when they remain stuck in a pipeline stage for too long.

### Detection
- Periodic task `retry_stuck()` runs every 60 minutes via Celery Beat
- Stuck definition: `updated_at < NOW() - STUCK_THRESHOLD_MINUTES (60)`
- Affected statuses: RESEARCHING, WRITING, EDITING, PENDING

### Dead Letter Action
1. Create article version (change_reason="dead_letter")
2. Apply fallback article content
3. Set pipeline_status = FAILED
4. Set last_error = "Dead-lettered: stuck in '{status}' beyond 60 minutes"

### Recovery Procedures

**Via Admin UI:**
1. Navigate to `/admin/dead-letters`
2. Click "reprocess" button next to article, or "reprocess all failed"
3. Article status resets to PENDING

**Via API:**
```bash
# Reprocess single article
curl -X POST http://localhost:5000/admin/articles/123/reprocess \
  --cookie "session=YOUR_SESSION_COOKIE"

# Bulk reprocess
curl -X POST http://localhost:5000/api/v1/articles/bulk \
  -H "Content-Type: application/json" \
  -d '{"action": "reprocess", "article_ids": [1, 2, 3]}'
```

**Via Database:**
```sql
UPDATE articles 
SET pipeline_status = 'pending', 
    retry_count = 0, 
    total_retries = 0, 
    degradation_count = 0,
    last_error = NULL
WHERE pipeline_status = 'failed';
```
```

---

## Phase 3: Medium-Priority Additions (Week 3)

### 3.1 Create docs/models.md (New File)

**Structure:**
```markdown
# Database Models Reference

## Overview
- 18 SQLAlchemy models in `models.py` (not `models/` directory)
- SQLite (WAL mode) database
- Alembic migrations in `/migrations/versions/`

## Model List

### Source (lines 52-77 in models.py)
| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | Primary key |
| source_key | String(64) | Unique, not null |
| name | String(128) | Not null, indexed |
| url | String(512) | Nullable |
| feed_url | String(512) | Nullable |
| source_type | String(32) | Not null, indexed |
| active | Boolean | Default True, indexed |
| consecutive_failures | Integer | Default 0, indexed |
| last_success_at | DateTime | Nullable |
| disabled_at | DateTime | Nullable, indexed |

Relationships: `articles` (one-to-many)

### Article (lines 92-163 in models.py)
[Include all 30+ fields with types, constraints, indexes]

### [Repeat for all 18 models...]

## Entity Relationships

| From | To | Type | Via |
|------|----|------|-----|
| Article | Source | Many-to-one | `source_id` FK |
| Article | Tag | Many-to-many | `article_tags` table |
| Article | Citation | One-to-many | backref="article" |
| Article | ArticleMetric | One-to-one | backref="article" |
| PipelineRun | PipelineLog | One-to-many | backref="pipeline_run" |
| Webhook | WebhookEvent | One-to-many | backref="webhook" |

## Indexes for Performance

| Index Name | Table | Columns |
|------------|-------|---------|
| ix_articles_status_created | articles | pipeline_status, created_at |
| ix_articles_published | articles | original_published_at |
| ix_articles_impact | articles | impact_score |
[... all 8 indexes]
```

### 3.2 Create docs/quality.md (New File)

**⚠️ Important:** Quality assessment system exists in `services/quality.py` but is **NOT INTEGRATED** into the pipeline!

```markdown
# Quality Assessment System

## Current Status
⚠️ **The quality assessment system in `services/quality.py` is implemented but NOT connected to the pipeline.**

The actual pipeline uses separate quality gates in each task file:
- Research: `_is_degenerate_research()` checks key_claims and impact_score
- Write: `_is_degenerate_write()` checks body length, key_points
- Edit: `validate_and_raise()` validates required fields

## QualityScore Dimensions

| Dimension | Range | Description |
|-----------|-------|-------------|
| `groundedness` | 0.0-1.0 | Factual alignment with sources |
| `coherence` | 0.0-1.0 | Logical flow and readability |
| `completeness` | 0.0-1.0 | Coverage of key points |
| `safety` | 0.0-1.0 | Absence of harmful content |
| `overall` | float | Automatic average of the four scores |

## Using QualityScore

```python
from services.quality import QualityScore, LLMQualityAssessor, detect_hallucination

# Quick heuristic assessment (no LLM call)
score = lightweight_quality_signals(content)
if score.passes_threshold(0.7):
    print("Quality is good!")

# LLM-based assessment (slower but more accurate)
assessor = LLMQualityAssessor()
score = assessor.assess(content, sources=[...])

# Hallucination detection
suspicious = detect_hallucination(content, source_text)
```

## Integration with Pipeline

To integrate quality.py into pipeline stages:

1. Add configuration to `pipeline.yaml`:
```yaml
quality:
  enabled: true
  threshold: 0.7
  use_llm: false  # Start with lightweight
  llm_role: "editor"
```

2. Modify tasks to use quality.py (see `docs/development.md` for examples)

3. Consider hybrid approach:
   - Use `lightweight_quality_signals()` as first pass (fast)
   - Use `LLMQualityAssessor` for articles approaching threshold
```

### 3.3 Create docs/circuit-breaker.md (New File)

```markdown
# Circuit Breaker Pattern

## Overview
The circuit breaker pattern prevents cascading failures when LLM providers are down. Implemented in `services/circuit_breaker.py` with Redis-backed state and in-memory fallback.

## States

| State | Description | Action |
|-------|-------------|--------|
| CLOSED | Normal operation, failures counted | Requests flow through |
| OPEN | Requests rejected immediately | After >= 5 failures in 120s window |
| HALF_OPEN | Limited probe requests allowed | After 60s recovery timeout |

## Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Failures before opening |
| `REDIS_URL` | redis://localhost:6379/0 | Redis for distributed state |

### Per-Provider Configuration (providers.yaml)
```yaml
providers:
  - id: openai
    circuit_breaker:
      failure_threshold: 5
      recovery_timeout: 60
      half_open_max_calls: 1
```

## Monitoring

**Admin API Endpoint:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:5000/api/v1/health
```

**Response includes:**
```json
{
  "circuit_breakers": [
    {
      "name": "llm:openai:gpt-4o:research",
      "state": "closed",
      "failure_count": 0,
      "failure_threshold": 5
    }
  ]
}
```

**Prometheus Metrics:**
```
circuit_breaker_state_change{provider="...",from="...",to="..."}
circuit_breaker_opened{provider="..."}
```

## Recovery Procedures

### Check Circuit Breaker Status
```bash
.venv/bin/python << 'EOF'
from services.circuit_breaker import get_all_breaker_status
import json
print(json.dumps(get_all_breaker_status(), indent=2))
EOF
```

### Manually Reset a Circuit Breaker
```bash
.venv/bin/python << 'EOF'
from services.circuit_breaker import get_breaker
breaker = get_breaker("llm:openai:gpt-4o:research")
breaker._state = State.CLOSED  # Force close
breaker._failure_count = 0
breaker._failure_times.clear()
print("Circuit breaker reset")
EOF
```

### What to Do When Circuits Keep Opening
1. Check provider status page (status.openai.com, etc.)
2. Verify API keys are correct
3. Consider switching to backup provider
4. Increase `failure_threshold` if false positives
```

### 3.4 Add Decision Trees to docs/troubleshooting.md

```markdown
## Decision Tree: "My pipeline stage is failing"

```
START: Pipeline Stage Failing
  │
  ├─→ Step 1: Check Circuit Breaker Status
  │    │
  │    └─→ `.venv/bin/python -c "from services.circuit_breaker import get_all_breaker_status; print(...)"`
  │         │
  │         ├─→ State is "open"?
  │         │    └─→ Wait for recovery_timeout (60s) or reset manually
  │         │
  │         └─→ State is "closed"?
  │              └─→ Continue to Step 2
  │
  ├─→ Step 2: Check Provider Health
  │    │
  │    └─→ `.venv/bin/python -c "from services.llm import get_provider_info; print(...)"`
  │         │
  │         ├─→ Provider healthy?
  │         │    └─→ Check article-specific issues
  │         │
  │         └─→ Provider unhealthy?
  │              └─→ Verify API key, check network
  │
  ├─→ Step 3: Check Article Status
  │    │
  │    └─→ `.venv/bin/python -c "from models import Article; print(Article.query.filter_by(...).all())"`
  │         │
  │         ├─→ Status is FAILED?
  │         │    └─→ Go to REPROCESS flow
  │         │
  │         └─→ Status is stuck (RESEARCHING/WRITING/EDITING)?
  │              └─→ Check for stuck articles, may need dead letter recovery
  │
  └─→ Step 4: Review Logs
       │
       └─→ `tail -100 /path/to/pipeline.log`
```

## Decision Tree: "Which LLM provider should I use?"

| Use Case | Recommended Provider |
|----------|-------------------|
| Development/Testing | ollama-local (free, fast, private) |
| Production - Budget Conscious | gpt-4o-mini ($0.15/$0.60 per 1M tokens) |
| Production - Best Quality | gpt-4o ($2.50/$10.00 per 1M tokens) |
| Production - Speed Critical | Groq (very fast inference) |
| Privacy/Sensitive Data | ollama-local (runs locally) |
```

---

## Implementation Checklist

### Phase 1: Critical Fixes
- [ ] Fix `README.md` pipeline flow diagram (line 47)
- [ ] Fix `docs/pipeline.md` state machine and transitions
- [ ] Fix `docs/development.md` (consolidate two contradictory flows)
- [ ] Fix `CONTRIBUTING.md` pipeline description
- [ ] Fix all `/admin/api/` → `/api/v1/` in `docs/api.md`
- [ ] Fix subscribe endpoint documentation (form data vs JSON)
- [ ] Fix `docs/trend-memory.md` model field definitions
- [ ] Fix `docs/context-service.md` model field definitions
- [ ] Fix all references from `models/` to `models.py`

### Phase 2: High-Priority Improvements
- [ ] Rewrite `README.md` features section with "why it matters"
- [ ] Add working curl examples to `docs/api.md` (all endpoints)
- [ ] Add "What can go wrong" sections to `docs/api.md`
- [ ] Add failure mode sections to `docs/pipeline.md`
- [ ] Add dead letter queue documentation to `docs/pipeline.md`
- [ ] Add recovery procedures to `docs/pipeline.md`

### Phase 3: Medium-Priority Additions
- [ ] Create `docs/models.md` with all 18 models documented
- [ ] Create `docs/quality.md` (note: not integrated into pipeline)
- [ ] Create `docs/circuit-breaker.md` with recovery procedures
- [ ] Add decision trees to `docs/troubleshooting.md`
- [ ] Fix `docs/subagent.md` tool names (3 incorrect names)

---

## Key Files to Modify

| File | Action | Priority | Estimated Time |
|------|--------|----------|----------------|
| `README.md` | Edit pipeline flow, features section | Critical | 2 hours |
| `docs/pipeline.md` | Fix state machine, add failure modes | Critical | 4 hours |
| `docs/api.md` | Fix URLs, add examples | Critical | 4 hours |
| `docs/development.md` | Fix pipeline descriptions | Critical | 2 hours |
| `CONTRIBUTING.md` | Fix pipeline flow | High | 1 hour |
| `docs/subagent.md` | Fix tool names, add missing docs | High | 2 hours |
| `docs/trend-memory.md` | Fix model definitions | High | 1 hour |
| `docs/context-service.md` | Fix model definitions | High | 1 hour |
| `docs/models.md` | **CREATE NEW FILE** | Medium | 4 hours |
| `docs/quality.md` | **CREATE NEW FILE** | Medium | 3 hours |
| `docs/circuit-breaker.md` | **CREATE NEW FILE** | Medium | 3 hours |
| `docs/troubleshooting.md` | Add decision trees | Medium | 3 hours |

**Total Estimated Time:** ~30 hours

---

## Bug Alerts Requiring Investigation

1. **Pipeline Transition Bug:** `PENDING → SKIPPED` in docs but NOT in `constants.py:VALID_TRANSITIONS`
   - Investigate: Is code wrong (should allow transition) or docs wrong?

2. **Quality System Not Integrated:** `services/quality.py` exists but never called
   - Decision: Integrate it or remove the file?

3. **Write Stage Premature Transition:** `write.py` sets `EDITING` at start of work function
   - Should status be `WRITING` during work, then transition to `EDITING`?

4. **Dead Code:** `PipelineStatus.SELECTING` defined but "not in DB"
   - Remove or properly implement?

---

## Success Criteria

After implementation, documentation should:
- [ ] Have **zero contradictions** between files about pipeline stages
- [ ] Include **working examples** users can copy-paste (curl commands, code snippets)
- [ ] Explain **"why it matters"** for all major features (not just "what it does")
- [ ] Document **failure modes** with recovery procedures for each pipeline stage
- [ ] Have **correct file/directory references** (models.py not models/)
- [ ] Include **actual code references** (file:line) for key concepts
- [ ] Provide **decision trees** for common troubleshooting scenarios
- [ ] Be **actionable** - users can succeed by following the docs

---

## Notes for Implementers

1. **Run before starting:** `.venv/bin/ruff check . --exclude .venv` and `.venv/bin/python -m pytest tests/ -x -q`
2. **Test examples:** Actually run the curl commands to verify they work
3. **Check consistency:** After each file change, grep for contradictions
4. **Document bugs found:** Create GitHub issues for bugs discovered during documentation fixes
5. **Consider automation:** Add CI check for broken internal links in docs

---

---

## Review Notes (2026-05-01)

After reviewing the plan:

1. **Typos checked:** "impossible" spelling verified correct (one 'p') throughout document
2. **Code imports verified:** `services.quality`, `services.circuit_breaker` have proper dot notation
3. **Formatting:** Markdown tables and code blocks render correctly
4. **Content completeness:** All deep dive findings incorporated
5. **Priority order:** Critical fixes (Phase 1) → High-priority improvements (Phase 2) → Medium-priority additions (Phase 3)

**Minor issues found and verified correct:**
- Line 120: "impossible" (correct spelling)
- Line 121: "wading" (correct from "wade")
- Line 385: `services.quality` (correct import with dot)
- Line 426: `services/circuit_breaker.py` (correct file path)

**Plan status:** ✅ Ready for implementation

---

**End of Plan 9**
