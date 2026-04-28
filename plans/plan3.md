# AI Agent Harness & Autonomous Pipeline Improvement Plan

**Date:** 2026-04-28  
**Scope:** Deep-dive review of ainews AI agent harness and autonomous production pipeline  
**Status:** Planning phase - implementation not yet started

---

## Executive Summary

Following a comprehensive code review and subagent-led investigation, we identified 14 improvement areas across 4 priority tiers. The ainews pipeline is **well-engineered and production-grade**, but has specific gaps in distributed locking consistency, autonomous adaptation, and operational visibility.

**Key Findings:**
- **P0:** `_acquire_stage_lock` is fail-open (BUG - contradicts AGENTS.md)
- **P1:** Tool registry rebuilt on every call; CircuitBreaker is in-memory only (multi-worker limitation)
- **P2:** No learning from failures; no composite health scoring; Batch API opportunity (50% cost reduction)
- **P3:** Duplicated logic; stringly-typed routing

---

## Priority Index

| ID | Item | Priority | Effort | Impact | Status |
|----|------|----------|--------|---------|--------|
| 1 | Fix `_acquire_stage_lock` fail-open bug | P0 | 5 min | High | Ready |
| 2 | Fix `generate_daily_newsletters` fail-open | P0 | 5 min | High | Ready |
| 3 | Dynamic stage lists in pipeline_monitor.py | P1 | 30 min | Medium | Ready |
| 4 | Cache subagent tool registry | P1 | 1 hr | Medium | Ready |
| 5 | Document CircuitBreaker multi-worker limitation | P1 | 15 min | Low | Ready |
| 6 | Add `SUBAGENT_WORKERS` to `.env.example` | P1 | 5 min | Low | Ready |
| 7 | Error-type-specific retry strategies | P2 | 2 hrs | Medium | Ready |
| 8 | Latency tracking for adaptive timeouts | P2 | 4 hrs | High | Ready |
| 9 | Pipeline health scoring system | P2 | 1 wk | High | Designed |
| 10 | Dead letter root cause aggregation | P2 | 3 hrs | High | Ready |
| 11 | Per-stage timeout configuration | P2 | 4 hrs | Medium | Designed |
| 12 | Batch API integration for research stage | P2 | 2-3 wks | **High (50% cost)** | Ready |
| 13 | Cost-tier model routing | P2 | 2-3 wks | **High (60-85% cost)** | Ready |
| 14 | Priority-based queue system | P2 | 1-2 wks | Medium | Ready |
| 15 | Failure pattern learning system | P2 | 1 wk | High | Designed |
| 16 | Enhance subagent chain conditions | P2 | 3 hrs | Medium | Ready |
| 17 | Refactor `degradation_count` duplication | P3 | 1 hr | Low | Ready |
| 18 | Convert `PipelineStatus` to StrEnum | P3 | 2-3 hrs | Medium | Ready |

---

## P0: Critical Bugs

### 1. Fix `_acquire_stage_lock` Fail-Open Bug

**File:** `tasks/pipeline.py:108-117`  
**Severity:** HIGH - Race condition allows duplicate stage execution

**Problem:**  
The `_acquire_stage_lock()` function returns `True` on RedisError, allowing pipeline stages to proceed without locks. This contradicts AGENTS.md which explicitly states locks must be **fail-closed**.

```python
# CURRENT (BUGGY):
except redis.exceptions.RedisError:
    logger.warning("Could not acquire stage lock, proceeding without")
    return True  # WRONG - proceeds unlocked
```

**Evidence of Inconsistency:**
| Task | File | Behavior |
|------|------|-----------|
| `crawl_source` | tasks/crawl.py:69-71 | FAIL-CLOSED (raises) |
| `retry_stuck` | tasks/retry.py:51-58 | FAIL-CLOSED (raises) |
| `publish_scheduled` | tasks/scheduler.py:31-38 | FAIL-CLOSED (raises) |
| `_acquire_stage_lock` | tasks/pipeline.py:114-117 | **FAIL-OPEN** (bug) |

**Fix:**
```python
# CORRECTED:
except redis.exceptions.RedisError:
    logger.error("Redis unavailable for stage lock, refusing to proceed")
    raise  # Re-raise to trigger Celery retry
```

**Impact:** The `run_stage()` exception handler (lines 345-378) will catch the RedisError and handle it appropriately (retry via Celery). The `finally` block will still release limiters.

**Files to Modify:**
- `tasks/pipeline.py:108-117` (the fix)
- `tests/test_pipeline.py` (update mocks to expect raise, not return)

---

### 2. Fix `generate_daily_newsletters` Fail-Open

**File:** `tasks/newsletter.py:414-417`  
**Severity:** HIGH - Same inconsistency as item #1

**Problem:** Newsletter lock also proceeds on RedisError:
```python
except redis.exceptions.RedisError:
    lock_status = 2  # Proceeds as if lock was acquired
```

**Fix:** Change to fail-closed (raise) for consistency with other locks.

**Files to Modify:**
- `tasks/newsletter.py:414-417`

---

## P1: Medium-Priority Improvements

### 3. Dynamic Stage Lists in pipeline_monitor.py

**Files:** `services/pipeline_monitor.py:137,219`  
**Effort:** 30 minutes | **Impact:** Prevents stale configs

**Problem:** Hardcoded stage lists:
```python
stages = ["crawl", "select", "research", "write", "edit"]  # Duplicated twice
```

**Solution:** Add canonical constant to `constants.py`:
```python
# In constants.py, after STAGE_STATUS_MAP:
_ARTICLE_STAGES = frozenset(STAGE_STATUS_MAP.values())
PIPELINE_STAGES = frozenset(_ARTICLE_STAGES | {"crawl"})
```

Then in `pipeline_monitor.py`:
```python
from constants import PIPELINE_STAGES
# ...
stages = sorted(PIPELINE_STAGES)  # Consistent ordering
```

**Files to Modify:**
- `constants.py` (add `PIPELINE_STAGES`)
- `services/pipeline_monitor.py:137,219` (use constant)
- `tests/test_pipeline_monitor.py:92` (update assertion)

---

### 4. Cache Subagent Tool Registry

**File:** `services/subagent.py:360-371`  
**Effort:** 1 hour | **Impact:** Performance improvement

**Problem:** `_build_context_tools()` and `_build_search_tools()` are called EVERY time `initialize_tool_registry()` is invoked. This happens for EVERY article in research/edit stages.

**Solution:** Module-level cache with double-checked locking (matches codebase patterns like `limiter.py:get_limiter()`):

```python
import threading
from typing import Optional

_context_tools_cache: Optional[list[ToolDefinition]] = None
_search_tools_cache: Optional[list[ToolDefinition]] = None
_tools_cache_lock = threading.Lock()

def _build_context_tools() -> list[ToolDefinition]:
    global _context_tools_cache
    if _context_tools_cache is None:
        with _tools_cache_lock:
            if _context_tools_cache is None:
                tools = []  # ... existing build logic ...
                _context_tools_cache = tools
    return _context_tools_cache
```

**Files to Modify:**
- `services/subagent.py` (add caching)

---

### 5. Document CircuitBreaker Multi-Worker Limitation

**File:** `services/circuit_breaker.py`  
**Effort:** 15 minutes | **Impact:** Knowledge sharing

**Problem:** Circuit state is in-memory using `threading.Lock()`. In multi-worker Celery deployments, each worker has its own CircuitBreaker instance. Failure counts don't aggregate across workers.

**Current Workaround:** The `get_provider_chain()` fallback mechanism partially mitigates this.

**Solution:** Add comment to `circuit_breaker.py` and optionally to AGENTS.md:
```python
# NOTE: Circuit state is in-memory per worker process.
# In multi-worker deployments, failure counts don't aggregate across workers.
# Consider Redis-backed circuit breaker (pybreaker library) for distributed state.
```

**For Future:** Use `pybreaker` library with `CircuitRedisStorage` for distributed state.

**Files to Modify:**
- `services/circuit_breaker.py` (add comment)
- `AGENTS.md` (optional: add known limitations section)

---

### 6. Add `SUBAGENT_WORKERS` to `.env.example`

**File:** `.env.example`  
**Effort:** 5 minutes | **Impact:** Discoverability

**Problem:** The `SUBAGENT_WORKERS` environment variable (controls subagent thread pool size) is not documented in `.env.example`.

**Solution:** Add to `.env.example`:
```bash
# Subagent thread pool size (default: 8)
SUBAGENT_WORKERS=8
```

**Files to Modify:**
- `.env.example`

---

## P2: High-Impact Autonomous Pipeline Improvements

### 7. Error-Type-Specific Retry Strategies

**File:** `services/llm/base.py:119-168`  
**Effort:** 2 hours | **Impact:** Medium - Better handling of different error types

**Problem:** All errors use the same exponential backoff:
```python
delay = min(self.RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5), self.RETRY_MAX_DELAY)
```

**Solution:** Differentiate based on error type:
```python
def _get_retry_delay(self, error_type: str, attempt: int) -> float:
    base = self.RETRY_BASE_DELAY
    if error_type == "rate_limit":
        return min(base * (4 ** attempt), 300.0)  # More aggressive
    elif error_type == "timeout":
        return min(base * (2 ** attempt), self.RETRY_MAX_DELAY)
    elif error_type == "server_error":
        return min(base * (2 ** attempt) + random.uniform(0, 0.5), self.RETRY_MAX_DELAY)
    return min(base * (2 ** attempt), self.RETRY_MAX_DELAY)
```

**Files to Modify:**
- `services/llm/base.py` (add `_get_retry_delay()`, modify `_retry_with_backoff()`)

---

### 8. Latency Tracking for Adaptive Timeouts

**File:** `services/llm/base.py`  
**Effort:** 4 hours | **Impact:** High - Adapts to provider performance

**Problem:** `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` is static. No tracking of observed latencies.

**Solution:** Add latency tracking with P99-based timeout calculation:
```python
from collections import deque

class LatencyTracker:
    def __init__(self, window_size: int = 100):
        self.window: deque = deque(maxlen=window_size)
    
    def record(self, latency_ms: float):
        self.window.append(latency_ms)
    
    def get_percentile(self, p: float) -> float:
        if not self.window:
            return 0.0
        sorted_vals = sorted(self.window)
        k = int(len(sorted_vals) * p)
        return sorted_vals[min(k, len(sorted_vals) - 1)]

# In BaseLLMProvider:
_latency_trackers: dict[str, Optional[LatencyTracker]] = {}

def _get_adaptive_timeout(self, provider_id: str, base_timeout: int = 120) -> int:
    tracker = self._latency_trackers.get(provider_id)
    if not tracker or not tracker.window:
        return base_timeout
    p99 = tracker.get_percentile(0.99)
    return min(int(p99 * 2.0), base_timeout * 2)  # P99 * safety factor
```

**Files to Modify:**
- `services/llm/base.py` (add LatencyTracker, modify chat methods)
- `schemas/pipeline.py` (add `adaptive_timeout: bool` to RoleConfig)

---

### 9. Pipeline Health Scoring System

**Effort:** 1 week | **Impact:** High - Single-pane-of-glass health view

**Design:** Composite health score (0-100) using weighted metrics:

```python
health_score = (success_rate * 0.30) + 
               (throughput_score * 0.20) + 
               (circuit_score * 0.15) + 
               (dead_letter_score * 0.20) + 
               (infra_score * 0.15)
```

**Weight Justification:**
- Success Rate (30%): Primary indicator of pipeline functionality
- Throughput (20%): Indicates capacity issues
- Dead Letters (20%): Affects content availability
- Circuit Breakers (15%): Fallback mechanisms exist
- Infrastructure (15%): Binary up/down status

**Implementation:**

**New File:** `services/pipeline_health.py` (see investigation report for full implementation)

**Modify:**
- `routes/admin/api/pipeline.py` (add `GET /api/pipeline/health-score` endpoint)
- `pipeline.yaml` (add `health:` configuration section)
- `services/metrics.py` (emit `pipeline.health_score` gauge)

**Status:** Fully designed in investigation phase. Ready for implementation.

---

### 10. Dead Letter Root Cause Aggregation

**File:** `routes/admin/api/pipeline.py`  
**Effort:** 3 hours | **Impact:** High - Debugging superpower

**Problem:** `GET /admin/api/pipeline/dead-letter/stats` returns only counts. No aggregation by failure reason, source, or stage.

**Solution:** Extend endpoint to return aggregations:

```python
@admin_bp.route("/api/pipeline/dead-letter/stats")
@require_auth
def dead_letter_stats() -> Response:
    # Existing counts...
    
    # NEW: Parse failure reasons from article.last_error
    reason_stats = {}
    stage_stats = {}
    failed_articles = Article.query.filter_by(pipeline_status=PipelineStatus.FAILED).all()
    for article in failed_articles:
        reason = _extract_failure_reason(article.last_error)
        reason_stats[reason] = reason_stats.get(reason, 0) + 1
    
    # NEW: Aggregate by source
    source_stats = db.session.query(
        Source.name, func.count(Article.id)
    ).join(Article).filter(...).group_by(Source.id).all()
    
    return jsonify({
        "stuck_articles": stuck_count,
        "failed_articles": failed_count,
        "by_reason": reason_stats,
        "by_source": [{"name": s[0], "count": s[1]} for s in source_stats],
        "by_stage": stage_stats,
    })
```

**Helper Functions:** Add to `services/pipeline_monitor.py` or new file:
- `def _extract_failure_reason(last_error: str) -> str:`
- `def _extract_stage_from_error(last_error: str) -> str:`

**Files to Modify:**
- `routes/admin/api/pipeline.py` (extend endpoint)
- `templates/admin/dead_letters.html` (add root cause section)
- New: `services/pipeline_failure_analytics.py` (helper functions)

---

### 11. Per-Stage Timeout Configuration

**Effort:** 4 hours | **Impact:** Medium - More granular control

**Problem:** Celery `soft_time_limit` and `time_limit` are hard-coded in task decorators. Pipeline timeout (`PIPELINE_TIMEOUT_SECONDS = 3600`) is global.

**Solution:** Add to `schemas/pipeline.py`:
```python
class RoleConfig(BaseModel):
    # Existing fields...
    task_soft_time_limit: int = Field(default=300, ge=60, le=600)
    task_time_limit: int = Field(default=360, ge=120, le=900)
```

**Modify `services/pipeline_utils.py:_dispatch_next()`:**
```python
def _dispatch_next(article_id, run_id=None, next_status=None):
    # ... existing code ...
    
    # Get stage-specific timeouts
    from schemas.pipeline import get_role_config
    stage_to_role = {"select": "selector", "research": "researcher", ...}
    role = stage_to_role.get(STAGE_STATUS_MAP.get(next_status))
    if role:
        rc = get_role_config(role)
        apply_kwargs["soft_time_limit"] = rc.task_soft_time_limit
        apply_kwargs["time_limit"] = rc.task_time_limit
    
    task_fn.apply_async(**apply_kwargs)
```

**Files to Modify:**
- `schemas/pipeline.py` (add timeout fields)
- `services/pipeline_utils.py` (use new fields)
- `tasks/crawl.py` (pass timeouts on initial dispatch)
- `pipeline.yaml` (optional: configure per stage)

**Status:** Designed. Note: Existing `timeout_seconds` in RoleConfig is for **limiter polling**, not task timeout. Keep both with clearer names.

---

### 12. Batch API Integration (HIGH ROI - 50% Cost Reduction)

**Effort:** 2-3 weeks | **Impact:** **HIGH - 50% cost reduction**

**Opportunity:** Use OpenAI/Anthropic Batch APIs for non-real-time stages (research, write). Batch APIs offer 50% cost reduction.

**Implementation Sketch:**

**New File:** `services/batch_llm.py`
```python
class BatchLLMProcessor:
    def __init__(self, provider_id, model):
        self.provider = get_provider_by_id(provider_id)
    
    def submit_batch(self, prompts: list[dict]) -> str:
        """Submit batch, return batch_id."""
        # Use provider's batch API
    
    def get_results(self, batch_id: str) -> list[dict]:
        """Poll for batch completion."""
```

**Modify:** `tasks/research.py` to optionally use batch mode when multiple articles are queued.

**Files to Create/Modify:**
- New: `services/batch_llm.py`
- Modify: `tasks/research.py`, `tasks/write.py`
- Modify: `services/cost_tracker.py` (track batch vs real-time costs)

---

### 13. Cost-Tier Model Routing (HIGH ROI - 60-85% Cost Reduction)

**Effort:** 2-3 weeks | **Impact:** **HIGH - 60-85% cost reduction**

**Opportunity:** Route simple articles (low impact score, high confidence) to cheaper models. Use existing `experiments:` framework for A/B testing.

**Implementation Sketch:**

**Add to `pipeline.yaml`:**
```yaml
cost_routing:
  enabled: true
  tiers:
    - name: "cheap"
      max_cost_per_1m: 1.00
      models: ["gpt-4o-mini", "claude-haiku"]
    - name: "standard"
      max_cost_per_1m: 5.00
      models: ["gpt-4o", "claude-sonnet"]
```

**Modify:**
- `services/llm/__init__.py` (add cost-aware provider selection)
- `tasks/select.py` (set `article.preferred_tier` based on confidence/impact)
- `schemas/pipeline.py` (add cost tier config)

---

### 14. Priority-Based Queue System

**Effort:** 1-2 weeks | **Impact:** Medium - Better UX during load

**Opportunity:** Route critical/reprocessed articles to high-priority queues. Defer low-priority articles during high load.

**Implementation:**

**Modify `config.py`:**
```python
CELERY_TASK_QUEUES = (
    Queue('critical', Exchange('critical'), routing_key='critical', priority=10),
    Queue('high', Exchange('high'), routing_key='high', priority=7),
    Queue('default', Exchange('default'), routing_key='default', priority=5),
    Queue('low', Exchange('low'), routing_key='low', priority=1),
)
```

**Modify `tasks/pipeline.py:run_stage()`:** Route by article priority.

---

### 15. Failure Pattern Learning System

**Effort:** 1 week | **Impact:** High - Enables self-healing

**Design:** New service to record and analyze failure patterns:

**New File:** `services/pipeline_learning.py`
```python
def record_failure_pattern(stage: str, provider_id: str, error_type: str):
    """Record failure patterns for learning."""
    # Store in Redis with hourly aggregation
    # Key: ainews:learning:failure_patterns:{stage}:{provider}:{error_type}:{hour}

def get_failure_trends(stage: str, hours: int = 6) -> dict:
    """Analyze failure trends to inform adaptive strategies."""
    # Returns patterns that can be used to:
    # - Prefer providers with lower failure rates
    # - Adjust timeouts based on latency trends
    # - Skip providers that are consistently failing
```

**Integrate into:** `services/pipeline_failure.py` (call `record_failure_pattern()` on failures)

**Status:** Designed. Transform system from rule-based to adaptive.

---

### 16. Enhance Subagent Chain Conditions

**File:** `services/subagent.py:988-1089`  
**Effort:** 3 hours | **Impact:** Medium - More expressive conditions

**Current Limitations:**
- No arithmetic operations (blocked: `+`, `-`, `*`, `/`)
- No aggregation functions (blocked: `sum()`, `len()`, `min()`, `max()`)
- No datetime access (can't check article age)

**Recommended Approach:** Provide pre-computed values in context rather than expanding AST whitelist (maintains security):

```python
# In chain context, pre-compute:
context["article_age_hours"] = (now - article.created_at).total_seconds() / 3600
context["recent_success_rate"] = get_recent_success_rate(provider)
```

**Alternative (Higher Risk):** Allow safe functions (`len`, `sum`, `min`, `max`) via `_ALLOWED_FUNCTIONS` dict.

**Files to Modify:**
- `services/subagent.py` (add pre-computed context values)
- `pipeline.yaml` (example conditions using new context)

---

## P3: Low-Priority Cleanup

### 17. Refactor `degradation_count` Duplication

**File:** `services/pipeline_degradation.py`  
**Effort:** 1 hour | **Impact:** Low - Code quality

**Problem:** Both `_apply_degrade_config()` (lines 92-109) and `_degrade_edit_stage()` (lines 142-161) duplicate logic for checking `degradation_count >= 2` and emitting `pipeline.multi_stage_degradation` metric.

**Solution:** Extract shared helper:
```python
def _check_and_handle_multi_degradation(
    article, run_id: int, stage: str = "unknown",
    extra_review_condition: bool = False
) -> bool:
    """Returns True if routed to REVIEW (caller should return early)."""
    if article.degradation_count >= 2:
        get_metrics().counter_inc("pipeline.multi_stage_degradation")
    
    if article.degradation_count >= 2 or extra_review_condition:
        article.pipeline_status = PipelineStatus.REVIEW
        db.session.commit()
        return True
    return False
```

**Files to Modify:**
- `services/pipeline_degradation.py` (extract helper, refactor both functions)

---

### 18. Convert `PipelineStatus` to StrEnum

**File:** `constants.py`  
**Effort:** 2-3 hours | **Impact:** Medium - Type safety

**Problem:** `PipelineStatus` is a plain class (not Enum). 353+ raw string literals exist throughout codebase.

**Quick Win:** Convert to `StrEnum` (Python 3.11+):
```python
from enum import StrEnum

class PipelineStatus(StrEnum):
    PENDING = "pending"
    SELECTING = "selecting"
    RESEARCHING = "researching"
    WRITING = "writing"
    EDITING = "editing"
    REVIEW = "review"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
```

**Benefits:**
- Type safety (mypy catches `"invalid_status"`)
- IDE autocomplete
- Backward compatible (StrEnum == string)
- Can iterate: `list(PipelineStatus)`

**Migration:** Can be gradual since StrEnum compares equal to strings.

**Files to Modify:**
- `constants.py` (convert to StrEnum)
- Gradually update function signatures: `stage: str` → `stage: PipelineStatus`

---

## Implementation Order Recommendation

### Phase 1: P0 Bug Fixes (Day 1)
1. Fix `_acquire_stage_lock` fail-open bug
2. Fix `generate_daily_newsletters` fail-open

### Phase 2: P1 Quick Wins (Day 1-2)
3. Dynamic stage lists in pipeline_monitor.py
4. Cache subagent tool registry
5. Document CircuitBreaker limitation
6. Add `SUBAGENT_WORKERS` to `.env.example`

### Phase 3: P2 High-ROI (Weeks 1-3)
7. Error-type-specific retry strategies
8. Latency tracking for adaptive timeouts
10. Dead letter root cause aggregation
11. Per-stage timeout configuration

### Phase 4: P2 Major Features (Weeks 3-6)
12. Batch API integration (50% cost reduction)
13. Cost-tier model routing (60-85% cost reduction)
9. Pipeline health scoring system
15. Failure pattern learning system

### Phase 5: P3 Cleanup (Week 6+)
17. Refactor `degradation_count` duplication
18. Convert `PipelineStatus` to StrEnum
16. Enhance subagent chain conditions (if needed)

---

## Success Metrics

| Metric | Baseline | Target (Post-Implementation) |
|--------|---------|-------------------------------|
| Pipeline cost per day | $X | **50-70% reduction** (Batch API + cost-tier routing) |
| Pipeline health score | N/A | **>75** (composite scoring) |
| Dead letter debugging time | Minutes/hours | **Seconds** (root cause aggregation) |
| Timeout accuracy | Static 120s | **Adaptive P99-based** |
| Failure adaptation | None | **Pattern-based routing** |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking changes to pipeline | Implement behind feature flags; gradual rollout |
| Redis dependency for new features | Document as optional; graceful degradation |
| Increased complexity | Follow existing patterns (double-checked locking, Redis error handling) |
| Cost-tier routing errors | A/B test with `experiments:` framework first |

---

## References

- Investigation reports available in conversation context (14 subagent investigations completed)
- AGENTS.md conventions for code style and patterns
- Existing patterns: `ModelLimiter` (Redis Lua scripts), `ResponseCache` (L1/L2), CircuitBreaker
