# Implementation Plan - Deferred Items

**Date:** April 28, 2026
**Status:** Complete - All actionable items implemented. Remaining items are intentionally deferred.

---

## Completed Items

| Item | Description | Completion Date |
|------|-------------|-----------------|
| B3 | ShareConfig validation on save | April 28, 2026 |
| CSP `unsafe-inline` removal | Move inline handlers to external JS with nonce | April 28, 2026 |
| Audit logging for admin actions | Implemented - AuditLog model, `log_admin_action()`, 36+ usages | April 28, 2026 |
| Redis max_connections env var | `REDIS_MAX_CONNECTIONS` env var (default 100/20) | April 28, 2026 |
| Static analysis (mypy) | Added mypy config to pyproject.toml | April 28, 2026 |
| Pagination accessibility | Added ARIA labels to pagination nav | April 28, 2026 |
| Pipeline throughput counters | Added throughput tracking to pipeline_monitor.py | April 28, 2026 |
| CSP inline styles | Moved inline styles to external CSS (D4) | April 28, 2026 |

## Deferred Items

The following items are intentionally deferred. Do not implement without further analysis.

| Item | Description | Reason |
|------|-------------|--------|
| D1 | Degradation routing threshold change | Current `>= 2` behavior is intentional design. Changing to `> 0` may cause review queue overflow. Needs stakeholder input. |
| CSS architecture refactor | Intentional duplication | `critical.css` must work standalone for first-paint performance. See AGENTS.md CSS module architecture section. |
| Session cookie `__Secure-` prefix | Requires HTTPS in all environments | Local dev must also use HTTPS. Consider when forcing HTTPS everywhere. |
| HSTS `include_subdomains` | May break subdomains | Only add if certain no subdomains will be added later. |
| Redis-backed sessions | Current cookie sessions adequate | Cookie sessions work fine for single-server deployment. |
| Pipeline query parallelization | Do NOT parallelize | <1% savings, not worth complexity. |
| JS bundling | Not needed | ~8KB total footprint, bundling adds complexity with no benefit. |
| CSS token sync (critical.css) | Working as intended | Shared tokens match; missing tokens are below-the-fold. |
| Queue depth backpressure | Significant new feature | Needs design discussion and stakeholder input. |

---

## Verification Commands

```bash
# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Specific affected tests
.venv/bin/python -m pytest tests/test_safe_href_filter.py tests/test_response_cache.py tests/test_pipeline_monitor.py tests/test_cost_tracker.py -v
```

*Last updated: April 28, 2026*