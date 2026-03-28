# Deferred Items from Plan.md

These items from phases 6-9 were deferred due to time constraints and complexity. They should be addressed in future work.

## Phase 6: Observability

### 6.1 Request Correlation IDs
**Problem:** No correlation IDs for tracking requests across Flask, Celery, and logs.
**Impact:** Medium - helps with debugging distributed issues.
**Deferred because:** Requires changes to Flask middleware, Celery task metadata, and logging configuration. More complex than other phases.

### 6.2 Enhanced Logging (JSON + Request Timing)
**Problem:** Missing structured JSON logging option, user context in admin logs, request timing.
**Impact:** Medium - improves observability and debugging.
**Deferred because:** Requires JSONFormatter implementation, request timing middleware, and user context integration.

### 6.3 Celery Worker Health Check
**Problem:** `/health` checks DB and Redis but not Celery workers.
**Impact:** Medium - workers could be dead while Flask reports healthy.
**Deferred because:** Requires adding `celery.control.inspect()` to health check endpoint.

## Phase 7: Maintainability & Cleanup

### 7.1 Extract Common Newsletter Logic
**Problem:** `generate_main_newsletter` and `generate_topic_newsletter` share ~80% code.
**Impact:** Medium - reduces duplication.
**Deferred because:** Requires refactoring two functions into a shared private method.

### 7.2 Hardcoded Download Timeout
**Problem:** `DOWNLOAD_TIMEOUT=30` is hardcoded in content_extractor.py.
**Impact:** Low - configurable via environment variable would be nice.
**Deferred because:** Simple change but low priority.

### 7.3 Missing Type Hints on Key Services
**Problem:** `services/url.py`, `services/prompts.py`, `services/utils.py` missing type hints.
**Impact:** Low - improves code quality but not critical.
**Deferred because:** Time-consuming for limited immediate benefit.

## Phase 8: Testing

### 8.1 XML Escaping Tests
**Problem:** `esc_xml_text()` and `esc_xml_attr()` have no tests enforcing usage.
**Impact:** Medium - ensures XML safety.
**Deferred because:** Requires creating new test file.

### 8.2 URL Validation Test Coverage
**Problem:** Edge cases untested (localhost with port, mixed case, public URLs with ports).
**Impact:** Medium - ensures URL validation correctness.
**Deferred because:** Requires adding test cases to existing test file.

### 8.3 Auth Lockout Tests
**Problem:** No explicit tests for login lockout behavior.
**Impact:** Medium - ensures security mechanism works correctly.
**Deferred because:** Requires creating new test file with Redis mocking.

### 8.4 Concurrent Access Tests
**Problem:** No tests for concurrent access patterns in ConfigCache, metrics singleton.
**Impact:** Medium - ensures thread safety.
**Deferred because:** Requires threading test patterns.

### 8.5 Migration Testing
**Problem:** Tests use `db.create_all()` but production uses Flask-Migrate.
**Impact:** Medium - catches migration-specific issues.
**Deferred because:** Requires CI integration or dedicated migration test.

## Phase 9: Optional / Low ROI

### 9.1 Cost Tracking
**Problem:** LLM token usage not persisted or aggregated.
**Impact:** Low - optional feature with limited ROI given pricing changes.
**Deferred because:** Requires DB schema changes, new service, and admin endpoint.

### 9.2 Metrics Endpoint (Prometheus Format)
**Problem:** `services/metrics.py` exists but may not expose Prometheus format.
**Impact:** Low - existing JSON endpoint may be sufficient.
**Deferred because:** Requires verifying current implementation and potentially adding Prometheus exposition.

### 9.3 Rate Limit Configuration Review
**Problem:** Default rate limit is 200/minute — very high for a news site.
**Impact:** Low - could enable scraping but not critical.
**Deferred because:** Simple env var change but low priority.

## Summary

**Deferred items:** 13 out of 19 remaining items (phases 6-9)
**Primary reasons:** Time constraints, complexity, and lower priority compared to completed phases 4-5.
**Next steps:** These should be prioritized based on actual production needs and observability gaps.