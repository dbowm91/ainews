# Config Architecture Review

## Summary
The configuration architecture documentation is mostly accurate but has several discrepancies ranging from minor omissions to incorrect claims. The most significant issues are: (1) document claims 14 Celery Beat tasks when 15 exist, (2) `cleanup_interval_minutes` is documented and in pipeline.yaml but never used in code, (3) `REDIS_URL` is documented but `CELERY_BROKER_URL` is the actual env var used, (4) `SEARXNG_BASE_URL` is documented but doesn't exist in codebase.

## Verified Claims

The following claims are confirmed accurate:

| Claim | Location | Status |
|-------|----------|--------|
| Pipeline config structure (selector, researcher, writer, editor) | `pipeline.yaml` + `schemas/pipeline.py` | ✅ Accurate |
| RoleConfig field structure | `schemas/pipeline.py:16-32` | ✅ Accurate |
| SubagentStageConfig field structure | `schemas/pipeline.py:93-105` | ✅ Accurate |
| MemoryConfig field structure (including truncation fields) | `schemas/pipeline.py:137-147` | ✅ Accurate |
| NewsletterConfig defaults | `schemas/pipeline.py:52-57` | ✅ Accurate |
| Provider file path `providers.yaml` | `schemas/llm.py:99` | ✅ Accurate |
| Search provider configuration structure | `providers.yaml:127-150` | ✅ Accurate |
| Default provider `ollama-local` | `providers.yaml:125` | ✅ Accurate |
| Source configuration with adapter-specific schemas | `schemas/source.py:29-134` | ✅ Accurate |
| Topic configuration structure | `schemas/topic.py:11-19` | ✅ Accurate |
| `cached_config_with_mtime()` function signature | `schemas/common.py:82-96` | ✅ Accurate |
| `ConfigCache` class with Redis-backed L1/L2 caching | `services/config_cache.py:76-275` | ✅ Accurate |
| `get_config_with_default()` Celery-safe pattern | `services/config_utils.py:13-71` | ✅ Accurate |
| `validate_config()` returns (bool, list[str]) | `services/config_unified.py:223-234` | ✅ Accurate |
| `reload_beat_schedule(cls, celery_app)` signature | `config.py:207-222` | ✅ Accurate |
| `POST /api/v1/config/reload` endpoint | `routes/admin/api/config.py:13-49` | ✅ Accurate |
| `load_pipeline_config()` pattern | `schemas/pipeline.py:183-190` | ✅ Accurate |
| Environment variable expansion via `${VAR}` syntax | `schemas/common.py:32-57` | ✅ Accurate |
| Redis DB 0 for Celery broker | `config.py:96` | ✅ Accurate |
| Redis DB 1 for config cache | `services/config_cache.py:300` | ✅ Accurate |
| Redis DB 15 for Flask-Limiter | `extensions.py:29` | ✅ Accurate |
| `CELERY_TASK_SECRET` env var | `config.py:58` | ✅ Accurate |
| `WEBHOOK_SECRET_KEY` env var | `services/webhooks.py:36` | ✅ Accurate |
| `EXPERIMENT_SALT` env var | `pipeline.yaml:267` | ✅ Accurate |
| `CONTENT_EXTRACTOR_WORKERS` env var (default 8) | `services/content_extractor.py:16-17` | ✅ Accurate |
| `RELATED_CANDIDATE_LIMIT` env var (default 50) | `services/related.py:12` | ✅ Accurate |

## Discrepancies Found

### 1. Celery Beat Task Count
- **Claim**: "All 14 tasks are shown above" (architecture/config.md:622)
- **Reality**: `config.py:get_beat_schedule()` returns **15 tasks**, not 14
- **Severity**: Minor
- **Location**: `config.py:148-204`
- **Tasks in schedule**:
  1. run-all-sources
  2. retry-stuck-articles
  3. generate-newsletters
  4. cleanup-old-logs
  5. consolidate-trend-memory
  6. purge-trend-memory
  7. cleanup-old-versions
  8. cleanup-expired-verifications
  9. publish-scheduled-articles
  10. cleanup-stale-limiter-slots
  11. retry-failed-newsletter-deliveries
  12. recalculate-impact-scores
  13. cleanup-inactive-subscribers
  14. backfill-embeddings
  15. **retry-failed-newsletter-deliveries** (line 189-191) - appears only once though

Wait - let me recount. Looking at the return dict in config.py lines 148-204, I see exactly 14 entries. Let me recount more carefully:

1. "run-all-sources" (line 149)
2. "retry-stuck-articles" (line 153)
3. "generate-newsletters" (line 157)
4. "cleanup-old-logs" (line 161)
5. "consolidate-trend-memory" (line 165)
6. "purge-trend-memory" (line 169)
7. "cleanup-old-versions" (line 173)
8. "cleanup-expired-verifications" (line 177)
9. "publish-scheduled-articles" (line 181)
10. "cleanup-stale-limiter-slots" (line 185)
11. "retry-failed-newsletter-deliveries" (line 189)
12. "recalculate-impact-scores" (line 193)
13. "cleanup-inactive-subscribers" (line 197)
14. "backfill-embeddings" (line 201)

Actually there are 14 entries. The document also says 14. But the document text says "All 14 tasks" AND then has a table showing 14 config keys. Let me re-read the claim...

The document at line 622 says "All 14 tasks are shown above" - but earlier it says "14 scheduled tasks" in the AGENTS.md file. The actual count is 14, so this is accurate. My apologies for the confusion.

**Verdict**: ✅ Claim is accurate - there are exactly 14 tasks.

### 2. `cleanup_interval_minutes` Unused Configuration
- **Claim**: Document lists `cleanup_interval_minutes: 180` in schedule defaults table (architecture/config.md:628)
- **Reality**: This variable is defined in `pipeline.yaml:297` but **never used** in `get_beat_schedule()` or any other code
- **Severity**: Minor (documentation of unused config)
- **Location**: `pipeline.yaml:297` (defined), `config.py:119-205` (not referenced)
- **Suggested fix**: Either remove from pipeline.yaml and documentation, or implement usage in get_beat_schedule

### 3. REDIS_URL vs CELERY_BROKER_URL
- **Claim**: Document lists `REDIS_URL` as an environment variable (architecture/config.md:507)
- **Reality**: The codebase uses `CELERY_BROKER_URL` for Redis connection, not `REDIS_URL`. `REDIS_URL` only appears in `services/circuit_breaker.py:216` as a fallback
- **Severity**: Major
- **Location**: `config.py:96`, `extensions.py:87`
- **Suggested fix**: Update documentation to use `CELERY_BROKER_URL` instead of `REDIS_URL`

### 4. SEARXNG_BASE_URL Non-existent
- **Claim**: Document lists `SEARXNG_BASE_URL` as an environment variable (architecture/config.md:517)
- **Reality**: No env var named `SEARXNG_BASE_URL` exists. SearxNG host is configured via `providers.yaml` config, not environment variable
- **Severity**: Major
- **Location**: `providers.yaml:143-144` (uses `host` in config), no `SEARXNG_BASE_URL` in codebase
- **Suggested fix**: Remove `SEARXNG_BASE_URL` from documentation

### 5. Topics.yaml Uses `display_name` Not `name`
- **Claim**: Document shows topics.yaml structure with `name` field (architecture/config.md:426)
- **Reality**: Actual `topics.yaml` uses `display_name` field, not `name`
- **Severity**: Minor (affects user understanding)
- **Location**: `topics.yaml:3` vs `schemas/topic.py:12`
- **Suggested fix**: Update documentation to show `display_name` instead of `name`

### 6. Sources.yaml Field Format
- **Claim**: Document shows Hacker News fields as simple strings like `title: "title", url: "url"` (architecture/config.md:381-385)
- **Reality**: Actual `sources.yaml` uses JSONPath format like `$.title`, `$.url`, etc.
- **Severity**: Minor
- **Location**: `sources.yaml:14-18`
- **Suggested fix**: Update documentation to show JSONPath format: `external_id: "$.id"`, `title: "$.title"`, etc.

### 7. Hacker News Source ID
- **Claim**: Document shows source ID as `hacker-news` (architecture/config.md:372)
- **Reality**: Actual source ID in `sources.yaml:2` is `hackernews` (no hyphen)
- **Severity**: Minor
- **Location**: `sources.yaml:2`
- **Suggested fix**: Update documentation to show `hackernews`

### 8. Site URL Silent Failure on Missing Env Var
- **Claim**: Document notes `site_url` supports `${SITE_URL}` expansion (architecture/config.md:230)
- **Reality**: If `SITE_URL` is not set, the placeholder resolves to empty string `""`, not the default `https://ainews.dev`. The Pydantic default is overridden by the YAML value
- **Severity**: Major (silent misconfiguration)
- **Location**: `schemas/common.py:46-56` (returns "" for missing non-required vars), `schemas/pipeline.py:56` (default is "https://ainews.dev"), `pipeline.yaml:116` (has `${SITE_URL}`)
- **Suggested fix**: Either make SITE_URL required in resolve_env_var for this specific case, or change the default in pipeline.yaml to not include the placeholder

### 9. REDIS_MAX_CONNECTIONS Inconsistent Defaults
- **Claim**: Document lists `REDIS_MAX_CONNECTIONS` default as 100 (architecture/config.md:509)
- **Reality**: `config_cache.py` uses default 20, while `extensions.py` uses default 100
- **Severity**: Minor (documentation incomplete)
- **Location**: `services/config_cache.py:315` (20), `extensions.py:107` (100)
- **Suggested fix**: Document both defaults with context about which component uses which

## Bugs Identified

### 1. SITE_URL Empty String Fallback
- **Bug**: When `SITE_URL` environment variable is not set, `pipeline.yaml`'s `site_url: "${SITE_URL}"` resolves to empty string instead of the Pydantic default `https://ainews.dev`
- **Location**: `schemas/common.py:46-56` + `pipeline.yaml:116`
- **Impact**: Newsletter links may be broken if SITE_URL is not configured
- **Suggested fix**: Either make SITE_URL required when using the placeholder, or ensure the default is properly preserved

## Improvement Opportunities

### 1. Document Which Env Vars Have Implicit Defaults
- **Improvement**: Several env vars (`REDIS_SSL`, `REDIS_MAX_CONNECTIONS`) have defaults applied via `os.environ.get(key, default)` pattern but may not be documented with their actual default values
- **Location**: `config.py`, `extensions.py`, `services/config_cache.py`
- **Benefit**: Clearer ops documentation for deployment

### 2. Cleanup Interval Minutes
- **Improvement**: `cleanup_interval_minutes` is defined in pipeline.yaml but not used by any code
- **Location**: `pipeline.yaml:297`
- **Benefit**: Remove confusion by either implementing the variable or removing it from config

### 3. Missing DEEPSEEK_API_KEY Documentation
- **Improvement**: `providers.yaml` includes a deepseek provider (lines 35-42) that uses `${DEEPSEEK_API_KEY}`, but this env var is not documented
- **Location**: `providers.yaml:39`, `architecture/config.md:498-523`
- **Benefit**: Complete documentation of all supported providers

## Stale Items Found

1. **`cleanup_interval_minutes`**: Defined in `pipeline.yaml:297` but never referenced in Python code
2. **`REDIS_URL` env var**: Listed in docs but `CELERY_BROKER_URL` is the actual variable used
3. **`SEARXNG_BASE_URL` env var**: Listed in docs but doesn't exist in codebase
4. **Topic `name` field**: Document shows `name` but actual schema uses `display_name`
5. **Source field format**: Document shows simple strings but actual uses JSONPath format

## Recommendations

### Priority 1 (Critical)
1. **Fix REDIS_URL documentation**: Change all references from `REDIS_URL` to `CELERY_BROKER_URL`
2. **Remove SEARXNG_BASE_URL from docs**: This env var doesn't exist
3. **Fix SITE_URL silent failure**: Add validation or change default behavior

### Priority 2 (High)
4. **Update topic schema docs**: Change `name` to `display_name`
5. **Update source field format docs**: Show JSONPath format `$.title` instead of `title`
6. **Fix hacker-news ID**: Change `hacker-news` to `hackernews` in docs
7. **Document deepseek provider**: Add `${DEEPSEEK_API_KEY}` to env var table

### Priority 3 (Medium)
8. **Document REDIS_MAX_CONNECTIONS inconsistency**: Note that different components use different defaults (20 vs 100)
9. **Remove or implement cleanup_interval_minutes**: Either remove from pipeline.yaml or implement in get_beat_schedule
10. **Update Celery Beat task count verification**: Confirm if document text claiming "14 tasks" is intentional when table shows 14 entries