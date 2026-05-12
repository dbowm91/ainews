# Services Review Plan

Review the `services/` package and [services.md](../architecture/services.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual service implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Layer Violations**: Services must NOT import from adapters

## Key Areas

### LLM Provider System (`services/llm/`)

- `base.py` - BaseLLMProvider abstract class
- `anthropic.py`, `openai.py`, `gemini.py`, `ollama.py` - Provider implementations
- `circuit_breaker.py` - Circuit breaker pattern
- `cost_tracker.py` - Cost tracking per provider

### Pipeline Services

- `researcher.py` - Research stage
- `writer.py` - Writing stage
- `editor.py` - Editing stage
- `newsletter_pipeline.py` - Newsletter orchestration (3-stage: reader→writer→editor)

### Infrastructure Services

- `limiter.py` - Redis-based rate limiting with slots
- `email.py` - SMTP pool for newsletter delivery
- `webhooks.py` - HMAC-SHA256 signatures, encrypted secrets
- `cache.py` - Redis caching

### Context & Trend Services

- `trend_memory.py` - Embedding-based semantic trend tracking
- `related.py` - Related article finding

### Content Extraction

- `content_extractor.py` - trafilatura primary, readability fallback

## Review Checklist

- [ ] Verify clean layering: services/ does NOT import from adapters/
- [ ] Verify LLM provider base class interface: chat(), chat_streaming(), chat_structured(), chat_with_tools()
- [ ] Verify circuit breaker states: Closed→Open→Half-Open
- [ ] Verify rate limiter: acquire(), release(), is_available(), always release in finally
- [ ] Verify newsletter_pipeline 3-stage: reader→writer→editor
- [ ] Verify cost tracking: tokens used, cost per model, budgets
- [ ] Verify trend memory: propose(), consolidate(), search()

## Output

Save findings to `plans/services_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found