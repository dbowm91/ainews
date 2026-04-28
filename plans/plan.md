# Implementation Plan - Deferred Items

**Date:** April 28, 2026
**Status:** COMPLETED - All actionable items done. Remaining items are intentionally deferred.

All 14 original implementation items (A1-A4, B1-B5, C1-C4, D1-D5) have been implemented and verified.

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
| Audit logging for admin actions | Significant effort (9 events) | No audit infrastructure exists yet. Needed for compliance in production. |
| HSTS `include_subdomains` | May break subdomains | Only add if certain no subdomains will be added later. |
| Redis-backed sessions | Current cookie sessions adequate | Cookie sessions work fine for single-server deployment. |
| Pipeline query parallelization | Do NOT parallelize | <1% savings, not worth complexity. |
| JS bundling | Not needed | ~8KB total footprint, bundling adds complexity with no benefit. |
| CSS token sync (critical.css) | Working as intended | Shared tokens match; missing tokens are below-the-fold. |
| Pagination accessibility announcements | Nice-to-have | Low signal for current user base. |
| Queue depth backpressure | Significant new feature | Needs design discussion and stakeholder input. |
| Pipeline throughput counters | Nice-to-have observability | Current success/failure counters are more actionable. |
| Source health query cache in subagent | Tool registered, not enabled | Registered in `services/subagent.py:282-289`. Enable by adding `get_source_health` to `tools:` in `pipeline.yaml` subagent config. |
| Redis max_connections env var | Nice-to-have | Hardcoded values (100 general, 20 config cache) are reasonable. Hasn't hit limits. |
| A/B experiment implementation | Depends on experiment config | Requires `pipeline.yaml` experiment configuration first. |
| Static analysis (mypy/ty) | Future tooling enhancement | Add when team is ready to adopt type checking. |
| Inline event handler CSP fix | Already clean | No `onclick`/`onerror` handlers found in public templates. Admin templates have some (deferred with CSP `unsafe-inline` removal). |

---

## Completed Items (Archived)

The following items have been implemented and verified:

| Item | Description | Files Changed |
|------|-------------|---------------|
| A1 | Import sorting auto-fix | ~133 files |
| A2 | LLM cost rate correction | services/cost_tracker.py |
| A3 | Debug logging in silent exception blocks | routes/public/links.py, routes/admin/api/webhooks.py, tasks/extract.py |
| A4 | Remove console.log from production code | static/js/app.js |
| B1 | CSP missing directives | app.py |
| B2 | safe_href filter in share templates | templates/partials/share_macro.html, templates/share_redirect.html |
| B4 | Merge share-a11y.js into app.js + fix aria-expanded | static/js/app.js, templates/base.html, templates/base_admin.html |
| B5 | Add SESSION_USE_SIGNER | config.py |
| C1+C3 | Fix uncached related articles + add date prefilter | routes/public/links.py, services/related.py |
| C2 | Fix O(n) cache eviction | services/cache.py |
| C4 | Add Source health indexes | models.py, migrations/versions/029_sources_health_indexes.py |
| D2+D5 | Fire article.failed webhook + add failure reason tracking | services/pipeline_failure.py, services/pipeline_monitor.py, tasks/pipeline.py |
| D3 | Fire newsletter.failed webhook + fix newsletter_id | tasks/newsletter.py |
| D4 | Add stage label to LLM metrics | services/llm/__init__.py, services/llm/base.py, tasks/select.py, tasks/research.py, tasks/write.py, tasks/edit.py |
| safe_href filter unit tests | Test coverage for security filter | tests/test_safe_href_filter.py |
| Remove _find_overlapping_low_entries | Dead code cleanup | services/trend_memory.py |

---

## Verification Commands

```bash
# Full lint check
.venv/bin/ruff check . --exclude .venv

# Run tests
.venv/bin/python -m pytest tests/ -x -q

# Specific affected tests
.venv/bin/python -m pytest tests/test_response_cache.py tests/test_pipeline_monitor.py tests/test_cost_tracker.py tests/test_safe_href_filter.py -v
```

*Last updated: April 28, 2026*
