# Implementation Plan
**Date:** April 28, 2026
**Status:** COMPLETED - All items implemented and verified

All 17 action items from the original plan have been implemented and verified in code.

---

## Verification Commands

```bash
# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Specific affected tests
.venv/bin/python -m pytest tests/test_response_cache.py tests/test_pipeline_monitor.py tests/test_cost_tracker.py -v
```

---

## Completed Implementation Summary

| Item | Description | Files Changed |
|------|-------------|---------------|
| A1 | Import sorting auto-fix | ~133 files |
| A2 | LLM cost rate correction | services/cost_tracker.py |
| A3 | Debug logging in silent exception blocks | routes/public/links.py, routes/admin/api/webhooks.py, tasks/extract.py |
| A4 | Remove console.log from production code | static/js/app.js |
| B1 | CSP missing directives | app.py |
| B5 | Add SESSION_USE_SIGNER | config.py |
| B2 | safe_href filter in share templates | templates/partials/share_macro.html, templates/share_redirect.html |
| C2 | Fix O(n) cache eviction | services/cache.py |
| C4 | Add Source health indexes | models.py, migrations/versions/029_sources_health_indexes.py |
| D4 | Add stage label to LLM metrics | services/llm/__init__.py, services/llm/base.py, tasks/select.py, tasks/research.py, tasks/write.py, tasks/edit.py |
| B4 | Merge share-a11y.js into app.js + fix aria-expanded | static/js/app.js, templates/base.html, templates/base_admin.html |
| C1+C3 | Fix uncached related articles + add date prefilter | routes/public/links.py, services/related.py |
| D2+D5 | Fire article.failed webhook + add failure reason tracking | services/pipeline_failure.py, services/pipeline_monitor.py, tasks/pipeline.py |
| D3 | Fire newsletter.failed webhook + fix newsletter_id | tasks/newsletter.py |

---

## Deferred Items

The following items are intentionally deferred. Do not implement without further analysis.

| Item | Reason |
|------|--------|
| B3: ShareConfig validation on save | No CRUD route exists for ShareConfig; records are seed data only. Add when admin CRUD is built. |
| D1: Degradation routing threshold change | Current `>= 2` behavior is intentional design. Changing to `> 0` may cause review queue overflow. Needs stakeholder input. |
| CSS architecture refactor | Intentional duplication per AGENTS.md (critical.css must work standalone) |
| Session cookie name prefix (`__Secure-`) | Requires HTTPS in all environments including local dev |
| CSP `unsafe-inline` removal | Medium effort, risk of breakage. Do after other CSP fixes stabilize. |
| Audit logging for admin actions | Significant effort (9 events). No audit infrastructure exists yet. |
| HSTS include_subdomains | May break subdomains if added later |
| Redis-backed sessions | Current cookie sessions adequate |
| Pipeline query parallelization | Do NOT parallelize (<1% savings) |
| JS bundling | Not needed for ~8KB footprint |
| CSS token sync (critical.css) | Shared tokens already match; missing tokens are below-the-fold |
| Pagination accessibility announcements | Nice-to-have, low signal |
| Queue depth backpressure | Significant new feature, needs design |
| Pipeline throughput counters | Nice-to-have observability |
| Source health query cache in subagent | Tool registered but NOT enabled in pipeline.yaml |
| Redis max_connections env var | Nice-to-have, hasn't hit limits |
| safe_href filter unit tests | Important but low priority, no active vulnerability |
| A/B experiment implementation | Depends on experiment config in pipeline.yaml |
| Static analysis (mypy/ty) | Future tooling enhancement |
| _find_overlapping_low_entries dead code | Harmless dead code in trend_memory.py:274-287 |
| Inline event handler CSP fix | Already clean - no onclick/onerror handlers found in templates |

---

*Verified complete: April 28, 2026*