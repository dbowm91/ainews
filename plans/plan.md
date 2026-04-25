# Consolidated Implementation Plan

**Created:** April 25, 2026
**Last Updated:** April 25, 2026
**Status:** IN PROGRESS -- Majority completed in Waves 1-4, remaining items in Wave 5

---

## Wave 1 Summary (COMPLETED)

| Item | Status | Notes |
|------|--------|-------|
| A.1 Precompile Regex | ✅ Done | Already implemented in `services/llm/base.py` |
| A.2 Silent Exception Logging | ✅ Done | Already has logging |
| A.3 Subagent Thread Pool | ✅ Done | Already configurable via `SUBAGENT_WORKERS` |
| A.4 Cost Pricing | ✅ Done | All providers already have pricing |
| A.5 Search Clear Button | ✅ Done | Already implemented |
| A.6 Base Font Size | ✅ Done | Already 15px |
| A.7 Date Format | ✅ Done | Already `format_date` filter |
| A.8 Beat Schedule Reload | ✅ Done | Already calls `Config.reload_beat_schedule()` |
| A.9 traced_stage | ✅ Done | Already wired in `run_stage()` |
| A.10 Threshold Config | ✅ Done | Already configurable |

---

## Deferred Items (Do Not Implement Without Explicit Direction)

| Item | Reason |
|------|--------|
| Newsletter subagent chain | Lower priority |
| Trend memory admin UI | Nice-to-have |
| Public API rate limiting | AGENTS.md says don't add `@limiter.limit()` |
| Pagination cursor-based | Works for current scale |
| Global LLM circuit breaker | Per-provider sufficient |
| Batch duplicate detection | Current approach sufficient |
| Redis pool segregation | Hasn't hit limits |
| CSS minification | CDN handles gzip |
| Announcement banner | Only if needed |
| Tool expansion/validation | Low ROI |
| Admin route fragmentation | Current split acceptable |
| Tool registry auto-init | Optional |
| Input/output token separation | Requires provider changes |
| Provider logprobs confidence | Complex, not universal |
| Ollama tool-calling | Not all models support |
| Full editor with tools | Higher effort |
| Persistent DuckDuckGo instance | Rate limits make pooling less impactful |

---

## Testing Requirements

### Before any changes:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q --tb=short
```

### After each batch:
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Some LLM adapter tests may have pre-existing failures unrelated to code changes (per AGENTS.md).

---

## Rollback Methods

| Change | Rollback Method |
|--------|----------------|
| Precompiled regex | Remove constants, revert to inline `re.search()` |
| Type hints | Remove `-> Response` annotations |
| Database index (model only) | Remove `index=True` from model |
| Logging additions | Revert logger calls |
| Session pooling | Remove session import, revert to `requests.get()` |
| Duplicate limit | Revert to hardcoded `limit(1000)` |
| Subagent workers | Remove env var, revert to `max_workers=8` |
| Cost pricing | Remove pricing entries |
| State machine | Revert to direct assignment |
| Docker Compose | Remove `docker-compose.yml` |
| CI/CD pipeline | Remove `.github/workflows/` |
| Secret rotation | Remove fallback env vars |
| Audit category | Drop column via migration |

---

## Sub-agent Assignment Recommendations

| Sub-agent | Items | Estimated Time |
|-----------|-------|---------------|
| **Performance** | A.1 (regex), A.2 (logging), A.3 (thread pool), A.4 (cost pricing) | 30 min |
| **UX** | A.5 (search clear), A.6 (font size), A.7 (date format) | 40 min |
| **Infra-small** | A.8 (beat reload), A.9 (traced_stage), A.10 (threshold config) | 35 min |
| **Testing** | B.1 (mock fixes), B.2 (test helpers) | 60 min |
| **Performance-2** | B.3 (session pooling), B.4 (dup limit), B.5 (index) | 45 min |
| **Newsletter** | B.6 (dead letter retry), B.7 (trend memory split) | 45 min |
| **Security** | B.8 (secret rotation), B.9 (audit logging), B.10 (size limits) | 80 min |
| **Architecture** | B.11 (state machine), B.12 (docker), B.13 (CI/CD) | 105 min |
| **Agent-harness** | C.1 (tools), C.2 (fallback), C.3 (context), C.4 (quality gates), C.5 (type hints) | 195 min |
| **Advanced** | D.1-D.5 (advanced features) | 180 min |
| **Docs** | D.6-D.8 (documentation) | 100 min |

---

*Consolidated April 25, 2026*
