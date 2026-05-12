# Schemas Review Plan

Review the `schemas/` package and [schemas.md](../architecture/schemas.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual schema implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, or validation issues
4. **Check Field Names**: Verify documented field names match actual Pydantic models

## Key Files

- `schemas/pipeline.py` - PipelineRootConfig, StageConfig (stub), RoleConfig
- `schemas/source.py` - SourceConfig, RSSConfig, APIConfig, WebConfig, PaginationConfig
- `schemas/llm.py` - Provider definitions
- `schemas/llm_responses.py` - SelectionResult, ResearchBrief, CondensedArticle, ExecutiveSummary, NewsletterBrief
- `schemas/tasks.py` - Task input validation
- `schemas/topic.py` - Topic definitions
- `schemas/webhook.py` - WebhookCreate, WebhookResponse

## Known Discrepancies (document in schema)

From architecture doc:
- `StageConfig` is a stub with only `tools: list[str]` - actual config in RoleConfig
- `ExecutiveSummary` has single `summary` field (not 6 separate fields)
- `NewsletterBrief` has `themes: list[str]` (not single string)
- `ResearchBrief.context_notes` (not `context`)
- `KeyClaim` is list[KeyClaim] not list[str]

## Review Checklist

- [ ] Verify StageConfig is stub, actual config in RoleConfig
- [ ] Verify PipelineRootConfig sections: pipeline, newsletter, newsletter_pipeline, subagent, memory, stages, schedule
- [ ] Verify NewsletterConfig fields: max_articles, send_time, timezone, site_url, prep_minutes
- [ ] Verify NewsletterPipelineConfig: reader, writer, editor RoleConfigs
- [ ] Verify SubagentConfig: enabled, default, research, edit, chains
- [ ] Verify MemoryConfig: ttl_days_low, ttl_days_medium, ttl_days_high, consolidation_cooldown_hours
- [ ] Verify SelectionResult fields: selected, score, reason, confidence, key_topics, impact_summary
- [ ] Verify ResearchBrief fields: source_summary, key_claims (list[KeyClaim]), direct_quotes, external_sources, related_articles, context_notes, newsworthiness, impact_score
- [ ] Verify CondensedArticle fields: headline, tldr, body, why_it_matters, key_points, what_to_watch, citations, original_attribution, tags

## Output

Save findings to `plans/schemas_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found