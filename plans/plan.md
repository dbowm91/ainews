# AINews Implementation Plan

**Status:** COMPLETED (2026-05-22)
**Last Updated:** 2026-05-22

All items from architecture review have been completed. See git history for details.

---

## Completion Summary

All items from the consolidated implementation plan (created 2026-05-22) have been completed across 4 waves:

| Wave | Items | Commit |
|------|-------|--------|
| Wave 1 (CRIT) | SUB-1, TASK-1, SERVICE-1 | `b60aca9`, `b054081` |
| Wave 2 (HIGH) | MODELS-1, MODELS-2, OVERVIEW-1, SCHEMA-1, SCHEMA-2, ROUTES-1, ADPT-1 | `88ee46e` |
| Wave 3 (MED) | UTIL-1, SUB-2-SUB-6, MODELS-3, TASK-3, SCHEMA-3-5 | `dc176ca`, `ec2f45a`, `47f8063`, `5f9e445` |
| Wave 4 (LOW) | ADPT-3 | `9f28d65` |

### Verification Fixes (2026-05-22)
- OVERVIEW-1: Add FTS5+vector similarity comment to hybrid provider
- ROUTES-2: Increase dashboard cache TTL from 60s to 180s  
- SERVICE-5: Add explanatory comment for TYPE_CHECKING import
- MODELS-4: Simplify Source.created_at lambda to use direct imports

**Total commits:** `cae3f1b`

---

## Verified Items

The following items were verified as already correct or already fixed:

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| SSRF redirect counter | `adapters/session.py:47-49` | FIXED | Counter decrements before raising UnsafeURLError |
| Duplicate except block | `schemas/common.py` | FIXED | File is 97 lines, no duplicate block |
| _should_route_to_review export | `tasks/pipeline.py:26` | FIXED | Re-export with noqa comment |
| track_share_click JSON | `routes/public/links.py:125` | FIXED | Returns `{"success": True}` |
| Chain escaping | `services/subagent/chain.py` | FIXED | Uses escape_prompt_data |
| utils/url.py docstring | `utils/url.py:1-5` | FIXED | Now clarifies impure DNS functions |
| Session key | `routes/admin/__init__.py:76` | FIXED | Uses `user_agent` not `ua` |
| SubagentChainStep/Config | `schemas/pipeline.py:107-117` | VERIFIED | Correctly located in schemas/pipeline.py |
| RawItem schema | `schemas/item.py` | VERIFIED | Exists and documented |
| trafilatura failure | `adapters/web.py:119-120` | VERIFIED | Only logs warning |
| request_delay per-article | `adapters/web.py:174-175` | VERIFIED | Per-article delay confirmed |
| Dashboard cache TTL | `routes/admin/dashboard.py:188` | VERIFIED | 180 seconds (increased from 60s) |
| updated_at index | `models/article.py:48` | VERIFIED | Inline index |
| TrendMemory index name | `models/context.py:49` | VERIFIED | ix_trend_memory_topic_importance |
| Source.source_key constraint | `architecture/models.md:118` | VERIFIED | Documented |
| Provider chain iteration | `services/llm/__init__.py:57-97` | VERIFIED | Generator pattern documented |
| TrendMemory semantic search | `services/trend_memory.py:414-430` | VERIFIED | 500 limit confirmed |
| retry_max=20 selector | `tasks/select.py:202` | VERIFIED | Aggressive retry behavior documented |

### Known Issues (Not Fixed but Acceptable)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| raw_token_hash security | `routes/admin/api_tokens.py:43-45` | ACCEPTABLE | Field stores unhashed hash; not displayed externally |
| Limiter release fallback | `tasks/pipeline.py:436-437` | ACCEPTABLE | `provider_id or rc.provider` pattern correctly handles None case |

---

*Plan consolidated from architecture review findings - 2026-05-22*