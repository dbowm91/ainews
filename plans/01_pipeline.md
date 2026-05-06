# Pipeline Architecture Verification Plan

## Verification Results

### Verified Claims

| Claim | Status | Evidence |
|-------|--------|----------|
| **5-stage pipeline**: select → research → write → edit → finalize | VERIFIED | `constants.py` lines 43-44: `PIPELINE_STAGES = ("crawl", "select", "research", "write", "edit")` |
| **Stage purposes match implementation** | VERIFIED | Each stage task (select.py, research.py, write.py, edit.py) implements documented purpose |
| **Score thresholds (>= 6 for select)** | VERIFIED | `pipeline.yaml` line 10: `min_score: 6` |
| **Degradation behavior for disabled stages** | VERIFIED | `pipeline_degradation.py` handles edit-stage degradation; `_handle_disabled()` in `tasks/pipeline.py` handles skip logic |
| **Degraded articles go to review** | VERIFIED | `pipeline_degradation.py` lines 99-110: degradation_count >= 2 routes to REVIEW |
| **PipelineLog model exists** | VERIFIED | `models/pipeline.py` lines 36-55: PipelineLog with run_id, stage, article_id, created_at, level, message |
| **PipelineMonitor tracks success/failure counts** | VERIFIED | `services/pipeline_monitor.py` records stage results and provides get_stage_stats() |
| **Automatic retry mechanism** | VERIFIED | `tasks/pipeline.py` uses Celery's retry with `retry_backoff=True`; stage tasks define `default_retry_delay` |
| **Circuit breaker exists** | VERIFIED | `services/circuit_breaker.py` implements CircuitBreaker and RedisCircuitBreaker classes |
| **Circuit breaker: 5 failures opens, 30s half-open** | DISCREPANCY | Default is `failure_threshold=5`, `recovery_timeout=60.0` (not 30s). Document says 30s half-open, code says 60s recovery timeout |
| **Fallback chain exists** | VERIFIED | `services/llm/__init__.py` lines 58-99: `get_provider_chain()` iterates through providers |
| **Newsletter batch size 500** | VERIFIED | `tasks/newsletter.py` line 85: `BATCH_SIZE = 500` |
| **Daily newsletter at 8AM ET** | VERIFIED | `pipeline.yaml` line 169: `send_time: "08:00"`; `config.py` line 141: reads `generate_newsletters_hour` defaulting to 8 |
| **Executive summary 3-stage pipeline** | VERIFIED | `services/newsletter_pipeline.py` implements reader → writer → editor chain |

### Discrepancies

| Claim | Documented | Actual | Severity |
|-------|-----------|--------|----------|
| **Circuit breaker half-open timeout** | 30 seconds | 60 seconds (`services/circuit_breaker.py` line 22: `_LLM_RECOVERY_TIMEOUT = 60.0`) | MEDIUM |
| **Retry backoff (30s, 60s, 120s)** | Exponential (30s, 60s, 120s) | Celery `retry_backoff=True` uses exponential backoff with `retry_backoff_max=300`; individual stages have different delays: select=30s, research=60s, write=60s, edit=60s | MEDIUM |
| **Max 3 retries** | 3 retries per stage | `constants.py` line 9: `MAX_STAGE_RETRIES = 3` - VERIFIED, but actual task-level retry behavior uses Celery's `max_retries=CELERY_TASK_MAX_RETRIES=3` and `default_retry_delay` varies by stage | LOW (works as documented) |
| **PipelineMonitor queue depth** | Tracks queue depth per stage | NOT IMPLEMENTED - no queue depth tracking found in `pipeline_monitor.py` | MEDIUM |
| **PipelineMonitor source health correlation** | Source health correlation | NOT IMPLEMENTED - no correlation tracking in `pipeline_monitor.py` | MEDIUM |
| **PipelineLog fields** | Document lists: run_id, stage, article_id, started_at, completed_at, status, error, metadata | Actual: run_id, article_id, stage, level, message, created_at - missing: started_at, completed_at, status (as document describes), error, metadata | HIGH |
| **Degradation table accuracy** | Shows select - research - write - edit degrade to review | Implementation: degradation_count >= 2 triggers review; earlier stages only degrade once before advancing | LOW (behavior similar) |
| **Fallback chain order** | ollama-local - openai - anthropic - gemini - deepseek | Hard-coded order not found; `get_provider_chain()` iterates enabled providers from config | LOW (dynamic) |

---

## Bug Findings

### HIGH Priority

1. **PipelineLog Missing Fields**
   - **Issue**: Document describes fields: `started_at`, `completed_at`, `status`, `error`, `metadata` - actual model only has: `id`, `run_id`, `article_id`, `stage`, `level`, `message`, `created_at`
   - **Impact**: Monitoring/logging gaps, cannot track stage duration accurately
   - **Fix**: Add `started_at`, `completed_at`, `status`, `error`, `metadata` (JSON) fields to `PipelineLog` model

### MEDIUM Priority

2. **Queue Depth Not Monitored**
   - **Issue**: Document claims PipelineMonitor tracks "queue depth per stage" - no implementation found
   - **Impact**: Cannot detect pipeline bottlenecks
   - **Fix**: Add Redis-backed queue depth tracking per stage in `pipeline_monitor.py`

3. **Source Health Correlation Not Tracked**
   - **Issue**: Document claims "Source health correlation" in PipelineMonitor - no implementation found
   - **Impact**: Cannot correlate pipeline failures to source issues
   - **Fix**: Add source health metrics correlation in pipeline monitoring

4. **Circuit Breaker Recovery Timeout Mismatch**
   - **Issue**: Document says 30s half-open, actual is 60s
   - **Impact**: Slightly longer failover latency than documented
   - **Fix**: Update document or `services/llm/__init__.py` line 22 to use 30.0

### LOW Priority

5. **Degradation Count Threshold Documentation**
   - **Issue**: Document shows degrade to review at 1 failure for disabled stages - actual uses `degradation_count >= 2`
   - **Impact**: Minor doc inconsistency
   - **Fix**: Update degradation table in document to show actual 2-failure threshold

6. **Retry Delay Variation Not Documented**
   - **Issue**: Document says fixed backoff (30s, 60s, 120s) - actual uses per-stage delays and Celery exponential backoff
   - **Impact**: Users may expect uniform retry behavior
   - **Fix**: Document actual per-stage retry delays

---

## Improvement Opportunities

1. **Complete PipelineLog Schema**
   - Add missing timestamp fields for stage start/end tracking
   - Add error and metadata JSON fields for richer logging

2. **Implement Queue Depth Monitoring**
   - Track pending articles per stage in Redis
   - Add `get_queue_depth_stats()` function to `pipeline_monitor.py`

3. **Add Source-Pipeline Correlation**
   - Track which sources produce failing articles
   - Join source health data with pipeline failure rates

4. **Align Circuit Breaker Configuration**
   - Verify 30s vs 60s is intentional
   - Document the recovery timeout choice

5. **Stage Duration Metrics Enhancement**
   - Currently tracks p95/p99 via histogram but no utility functions
   - Add `get_stage_duration_stats()` utility for percentiles

---

## Action Items

| Priority | Item | Owner |
|----------|------|-------|
| HIGH | Add missing fields to PipelineLog model: `started_at`, `completed_at`, `status`, `error`, `metadata` | Backend |
| MEDIUM | Implement queue depth tracking in pipeline_monitor.py | Backend |
| MEDIUM | Implement source health correlation in pipeline_monitor.py | Backend |
| MEDIUM | Verify and align circuit breaker recovery timeout (30s vs 60s) | Architecture |
| LOW | Update architecture document degradation table for 2-failure threshold | Documentation |
| LOW | Document per-stage retry delays in architecture | Documentation |
| LOW | Add `get_stage_duration_stats()` utility for p95/p99 calculations | Backend |
