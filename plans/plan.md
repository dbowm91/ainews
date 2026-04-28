# Implementation Plan - Deferred Items

**Date:** April 28, 2026
**Status:** Active - All implementation complete. Only intentionally deferred items remain.

---

## Deferred Items

The following items are intentionally deferred. Do not implement without further analysis.

| Item | Description | Reason |
|------|-------------|--------|
| B3 | ShareConfig validation on save | No CRUD route exists for ShareConfig; records are seed data only. Add when admin CRUD is built. |
| D1 | Degradation routing threshold change | Current `>= 2` behavior is intentional design. Changing to `> 0` may cause review queue overflow. Needs stakeholder input. |
| CSS architecture refactor | Intentional duplication | `critical.css` must work standalone for first-paint performance. See AGENTS.md CSS module architecture section. |
| Session cookie `__Secure-` prefix | Requires HTTPS in all environments | Local dev must also use HTTPS. Consider when forcing HTTPS everywhere. |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage | Inline handlers exist in admin templates (`onclick=`). Requires moving to external JS + nonce implementation. |
| Audit logging for admin actions | Significant effort (9 events) | AuditLog model and `log_admin_action()` exist in `services/audit.py`. Full audit trail infrastructure deferred until compliance review. |
| HSTS `include_subdomains` | May break subdomains | Only add if certain no subdomains will be added later. |
| Redis-backed sessions | Current cookie sessions adequate | Cookie sessions work fine for single-server deployment. |
| Pipeline query parallelization | Do NOT parallelize | <1% savings, not worth complexity. |
| JS bundling | Not needed | ~8KB total footprint, bundling adds complexity with no benefit. |
| CSS token sync (critical.css) | Working as intended | Shared tokens match; missing tokens are below-the-fold. |
| Pagination accessibility announcements | Nice-to-have | Low signal for current user base. |
| Queue depth backpressure | Significant new feature | Needs design discussion and stakeholder input. |
| Pipeline throughput counters | Nice-to-have observability | Current success/failure counters are more actionable. |
| Redis max_connections env var | Nice-to-have | Hardcoded values (100 general, 20 config cache) are reasonable. Hasn't hit limits. |
| Static analysis (mypy/ty) | Future tooling enhancement | Add when team is ready to adopt type checking. |
| Inline event handler CSP fix | Already clean | No `onclick`/`onerror` handlers found in public templates. Admin templates have some (deferred with CSP `unsafe-inline` removal). |

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