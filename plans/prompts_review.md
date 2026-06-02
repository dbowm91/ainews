# Prompts Architecture Review

## Summary
Overall health: **Good with minor discrepancies**. The prompt system is well-implemented and documented, with a few inaccuracies in line references and one content drift issue between file and inline templates.

## Verified Claims

### Prompt Templates (9 files - ALL EXIST)
- `prompts/selector.txt` - EXISTS
- `prompts/researcher.txt` - EXISTS
- `prompts/writer.txt` - EXISTS
- `prompts/editor.txt` - EXISTS
- `prompts/newsletter_reader.txt` - EXISTS
- `prompts/newsletter_writer.txt` - EXISTS
- `prompts/newsletter_editor.txt` - EXISTS
- `prompts/subagent_research_synthesis.txt` - EXISTS
- `prompts/subagent_edit_contextualization.txt` - EXISTS

### Prompt Loading Functions
- `get_system_prompt(role, yaml_prompt)` at `services/prompts.py:140-157` - **VERIFIED**: Checks yaml_prompt first, falls back to file
- `load_prompt_file(name)` at `services/prompts.py:131-137` - **VERIFIED**: Uses mtime-based LRU cache

### Context Truncation
- `count_tokens()` at `services/prompts.py:35-56` - **VERIFIED**: tiktoken with char fallback
- `_budget_tokens()` at `services/prompts.py:274-299` - **VERIFIED**: Uses sliding_window_truncate internally
- `summarize_context()` at `services/prompts.py:302-358` - **VERIFIED**: SHA-256 cache key of first 500 chars + max_tokens + temperature

### Prompt Escaping
- `esc_xml_text()` at `utils/text.py:19-21` - **VERIFIED**
- `esc_xml_attr()` at `utils/text.py:24-33` - **VERIFIED**
- `escape_prompt_data()` at `utils/text.py:36-50` - **VERIFIED**
- Used by `runner.py`, `chain.py`, and `subagent/utils.py` - **VERIFIED**

### Override Mechanism
- `system_prompt` in pipeline.yaml overrides file - **VERIFIED** at `services/prompts.py:150-151`

### A/B Experiments
- 70/15/15 distribution - **VERIFIED** at `tasks/select.py:36-43`
- MD5 hash assignment - **VERIFIED** at `tasks/select.py:33-34`
- writer/editor check `experiment_group` - **VERIFIED** at `services/writer.py:23-30` and `services/editor.py:23-30`

### Template Resolution Order
1. `stage_config.task_template` - **VERIFIED** at `services/subagent/runner.py:31-34`
2. `_SUBAGENT_TASK_TEMPLATES` fallback - **VERIFIED** at `services/subagent/runner.py:35`

### Newsletter Brief Schema
- `{themes, highlights, connections}` output - **VERIFIED** at `schemas/llm_responses.py:142-148`

## Discrepancies Found

- **Claim**: "Cache key is SHA-256 of first 500 chars + max_tokens + temperature" at `architecture/prompts.md:69`
- **Reality**: Cache key is `SHA-256 of first 500 chars + max_tokens + temperature` - This is correct
- **Location**: `services/prompts.py:321`
- **Suggested fix**: No fix needed - line reference was for context, not precision

- **Claim**: "10-minute TTL, `services/prompts.py:25-26`" at `architecture/prompts.md:68`
- **Reality**: TTL constant `_SUMMARIZE_CACHE_TTL = 600` is at line 28, not 25-26
- **Severity**: Minor
- **Location**: `architecture/prompts.md:68`
- **Suggested fix**: Change to `services/prompts.py:28`

- **Claim**: "Output: `{key_findings, context, citations, related_trends}`" at `architecture/prompts.md:109`
- **Reality**: Actual ResearchBrief schema at `schemas/llm_responses.py:53-79` has: `source_summary`, `key_claims`, `direct_quotes`, `external_sources`, `related_articles`, `context_notes`, `newsworthiness`, `impact_score`
- **Severity**: Minor
- **Location**: `architecture/prompts.md:109` vs `schemas/llm_responses.py:53-79`
- **Suggested fix**: Update doc to describe actual schema fields, or use generic description like "Research brief with claims, quotes, context, and impact score"

- **Claim**: "Target: 200-400 words, 3-5 key points" at `architecture/prompts.md:117`
- **Reality**: `prompts/writer.txt` says "BODY — 3-5 tight paragraphs" (not "key points") and contains no explicit word count target
- **Severity**: Minor
- **Location**: `prompts/writer.txt:7` vs `architecture/prompts.md:117`
- **Suggested fix**: Update doc to say "Target: 3-5 tight paragraphs" (or check if word count is specified elsewhere)

- **Claim**: "prompts/subagent_edit_contextualization.txt ... Review the draft in light of the research brief, topic notes, and related articles."
- **Reality**: File says: "Review the draft in light of the research brief, topic notes, and related articles."
- **Inline template** at `services/subagent/prompt_templates.py:40` says: "Review the draft in light of the research brief, topic notes, related articles, and trend memory."
- **Severity**: Minor
- **Location**: `prompts/subagent_edit_contextualization.txt:17` vs `services/subagent/prompt_templates.py:40`
- **Suggested fix**: Update file to match inline template (add "and trend memory")

## Bugs Identified

- **Bug**: Content drift between `prompts/subagent_edit_contextualization.txt` and inline template
- **Location**: `prompts/subagent_edit_contextualization.txt:17` vs `services/subagent/prompt_templates.py:40`
- **Impact**: If a user edits the .txt file but the inline template is used as fallback, behavior diverges. Also confusing for documentation.
- **Suggested fix**: Synchronize the two - either keep both identical or clarify when each is used

## Improvement Opportunities

- **Improvement**: The `prompts/` cache uses mtime-based invalidation but `_summarize_cache` uses time-based TTL only (no mtime). If a prompt file changes, summarize_context results may be stale.
- **Location**: `services/prompts.py:86-126` (PromptFileCache) vs `services/prompts.py:316-358` (_summarize_cache)
- **Benefit**: Ensure cached summaries reflect current prompt templates

- **Improvement**: The `_SUBAGENT_TASK_TEMPLATES` dict at `services/subagent/prompt_templates.py:7-43` duplicates content from `prompts/subagent_*.txt` files. This creates maintenance burden and drift risk.
- **Location**: `services/subagent/prompt_templates.py`
- **Benefit**: Eliminate duplication by loading from files directly

## Stale Items Found

None - all documented features exist and are implemented.

## Recommendations

1. **High Priority**: Sync `prompts/subagent_edit_contextualization.txt` with inline template to include "and trend memory" in the review instruction
2. **Low Priority**: Fix line reference in `architecture/prompts.md:68` from "25-26" to "28"
3. **Low Priority**: Consider loading subagent templates from files by default (eliminating the duplicate inline `_SUBAGENT_TASK_TEMPLATES` dict)
4. **Informational**: The summarize_context cache is independent of prompt file cache - no action needed but be aware of this behavior