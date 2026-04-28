# Implementation Plan - Deferred Items

**Date:** April 28, 2026
**Status:** Complete - All actionable items verified. Deferred items are intentionally not implemented.

**Last Verified:** April 28, 2026 - All 8 completed items verified in code.

---

## Verified Complete (April 28, 2026)

| Item | Description | Verification |
|------|-------------|--------------|
| B3 | ShareConfig validation on save | routes/admin/shares.py:81-98 (all fields validated) |
| CSP `unsafe-inline` removal | Inline handlers to external JS with nonce | webhooks.html:94, articles_table.html:81, base_admin.html:15,19 |
| Audit logging for admin actions | AuditLog model, log_admin_action(), 37 usages | services/audit.py, 37 usages across admin routes |
| Redis max_connections env var | `REDIS_MAX_CONNECTIONS` env var | extensions.py:107 (100), config_cache.py:250 (20) |
| Static analysis (mypy) | mypy config in pyproject.toml | pyproject.toml:65-75, Python 3.12 target |
| Pagination accessibility | ARIA labels in pagination nav | templates/partials/pagination.html:3-22 |
| Pipeline throughput counters | record_throughput(), get_throughput_stats() | services/pipeline_monitor.py:141,164 |
| CSP inline styles | Skeleton styles in external CSS | static/css/articles.css:1195-1233 |

---

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
| JS bundling | Not needed | ~16KB custom JS total footprint (~67KB with htmx), bundling adds complexity with no benefit. |
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