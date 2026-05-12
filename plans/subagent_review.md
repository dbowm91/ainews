# Subagent Review Plan

Review the `services/subagent/` package and [subagent.md](../architecture/subagent.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual subagent implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
4. **Check Tool System**: Verify tool registry, chain system, middleware, runner

## Key Files

- `services/subagent/registry.py` - _TOOL_REGISTRY with cached tool definitions
- `services/subagent/tools.py` - Tool implementations
- `services/subagent/runner.py` - run_subagent() and run_subagent_with_tools()
- `services/subagent/chain.py` - Multi-step subagent chains with conditions
- `services/subagent/conditions.py` - AST-based condition evaluation
- `services/subagent/prompt_templates.py` - Task prompt templates
- `services/subagent/middleware.py` - LoggingMiddleware, TimingMiddleware

## Known Issues to Verify

- run_subagent signature: run_subagent(task_type, stage, prompt_data, response_model, article_id)
- Not the documented run_subagent(task, context, tools, model)

## Tool Registry

Built-in tools:
- get_topic_note - Fetch editor note for a topic
- context_notes - Get topic notes for multiple topics
- related_articles - Find related articles by topics
- get_trend_memory - Retrieve trend memory entries
- get_article_by_id - Fetch article by ID
- search_articles - Search articles by query
- get_source_health - Get source status summary
- web_search - External web search
- get_search_provider - Get configured search provider

## Review Checklist

- [ ] Verify tool registry: _TOOL_REGISTRY with cached ToolDefinitions
- [ ] Verify tool implementations: _context_tool_* functions registered in registry
- [ ] Verify runner: run_subagent() and run_subagent_with_tools() entry points
- [ ] Verify retry with exponential backoff in runner
- [ ] Verify task revocation checking: stops if Celery task revoked
- [ ] Verify tool-calling loop: execute tools in parallel, add results to messages, max iterations
- [ ] Verify chain system: SubagentChainConfig with steps and conditions
- [ ] Verify condition evaluation via AST from conditions.py
- [ ] Verify middleware: ToolMiddleware base, LoggingMiddleware, TimingMiddleware
- [ ] Verify configuration from pipeline.yaml: subagent.enabled, tools, max_iterations, tool_timeout

## Output

Save findings to `plans/subagent_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found