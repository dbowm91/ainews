# Models Review Plan

Review the `models/` package and [models.md](../architecture/models.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual model implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Layer Violations**: Models should not import from services

## Key Files

- `models/article.py` - Article model with pipeline_status
- `models/source.py` - Source model with health tracking
- `models/newsletter.py` - Newsletter, Subscriber, ArticleMetric
- `models/pipeline.py` - PipelineRun, PipelineLog, ArticleVersion
- `models/context.py` - TopicNote, TrendMemory
- `models/webhook.py` - Webhook, WebhookEvent
- `models/auth.py` - ApiToken, AdminUser
- `models/tag.py` - Tag, article_tags

## Known Issues to Verify

- `TrendMemory.embedding` is Text (not vector type) - confirm implementation
- `Source.adapter_config` never implemented - verify field exists
- `AdminUser.ip_binding` and `user_agent_hash` not implemented - verify

## Review Checklist

- [ ] Verify Article model fields: title, url, source_id, content, summary, pipeline_status, impact_score, published_at, created_at
- [ ] Verify Source model fields: name, source_type, consecutive_failures, consecutive_successes, last_crawled
- [ ] Verify PipelineRun and PipelineLog relationships
- [ ] Verify TrendMemory fields: topic, signal, embedding, source_articles
- [ ] Verify indexes on frequently queried columns
- [ ] Verify AdminUser TOTP and backup codes implementation
- [ ] Verify many-to-many relationships: Article-Tag, Newsletter-Article, Newsletter-Subscriber

## Output

Save findings to `plans/models_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found