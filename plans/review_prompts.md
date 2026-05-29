# Review: prompts.md

**Reviewed:** 2026-05-29
**Status:** COMPLETE

---

## Verified Claims

- **All 7 documented prompt template files exist** — `prompts/selector.txt`, `prompts/researcher.txt`, `prompts/writer.txt`, `prompts/editor.txt`, `prompts/newsletter_reader.txt`, `prompts/newsletter_writer.txt`, `prompts/newsletter_editor.txt`
- **`get_system_prompt(role, yaml_prompt)` exists** — `services/prompts.py:95-112`
- **`load_prompt_file(name)` exists** — `services/prompts.py:84-92`
- **Override mechanism: YAML `system_prompt` takes priority** — `services/prompts.py:105-106` (checks `yaml_prompt` first, falls back to file)
- **`count_tokens(text, model)` exists** — `services/prompts.py:33-54`
- **`sliding_window_truncate(text, max_chars, model)` exists** — `services/prompts.py:115-154`
- **`importance_weighted_truncate(text, max_chars, key_topics)` exists** — `services/prompts.py:157-226`
- **`smart_truncate_context(text, max_chars, model, llm_provider)` returns `tuple[str, bool]`** — `services/prompts.py:316-395`
- **`summarize_context(text, llm_provider, max_tokens, temperature)` exists** — `services/prompts.py:257-313`
- **`esc_xml_text(text)` exists** — `utils/text.py:19-21`
- **`esc_xml_attr(text)` exists** — `utils/text.py:24-33`
- **`escape_prompt_data(data)` exists** — `utils/text.py:36-50`
- **`_SUBAGENT_TASK_TEMPLATES` dict exists** — `services/subagent/prompt_templates.py:7-43`
- **Template keys `research_synthesis` and `edit_contextualization` exist** — `services/subagent/prompt_templates.py:8,20`
- **A/B experiment prompt variants in `pipeline.yaml`** — `pipeline.yaml:265-292`
- **`_assign_experiment_group()` in `tasks/select.py`** — `tasks/select.py:19-43`
- **Selector prompt evaluates newsworthiness** — `prompts/selector.txt` exists, `tasks/select.py:85-94` builds the prompt
- **Researcher prompt builds research brief** — `prompts/researcher.txt` exists
- **Writer prompt creates Smart Brevity format** — `prompts/writer.txt` exists
- **Editor prompt polishes and contextualizes** — `prompts/editor.txt` exists
- **Newsletter prompts exist** — `prompts/newsletter_reader.txt`, `prompts/newsletter_writer.txt`, `prompts/newsletter_editor.txt`
- **Subagent templates referenced from `pipeline.yaml`** — `pipeline.yaml:208` (`task_template: prompts/subagent_research_synthesis.txt`), `pipeline.yaml:227` (`task_template: prompts/subagent_edit_contextualization.txt`)

## Incorrect Claims

1. **Prompt escaping functions located in `utils/text.py` per documentation** — `prompts.md:72-83`
   - Priority: **LOW**
   - The documentation shows the functions as `# utils/text.py` at line 73. The functions do exist in `utils/text.py` as documented. However, `services/prompts.py:12` re-exports them (`from utils.text import esc_xml_attr, esc_xml_text  # noqa: F401 - re-exported for backward compatibility`). The documentation is technically correct but could note the re-export for consumers who import from `services.prompts`.

2. **"Used by `services/subagent/runner.py`, `services/subagent/chain.py`, and `services/subagent/utils.py`"** — `prompts.md:85`
   - Priority: **LOW**
   - The documentation claims the escaping functions are used by three specific subagent modules. Without exhaustively searching all imports, this claim is plausible but unverified. The functions are used in prompt construction throughout the codebase.

## Bugs Found

1. **No bugs found in the prompts system code itself.**
   - The prompt loading, override, escaping, and truncation functions are well-implemented with proper error handling, caching (`@lru_cache` on `count_tokens` and `load_prompt_file`), and fallback behavior.

## Improvement Opportunities

1. **Document the 2 additional subagent prompt template files** — `prompts.md` Prompt Templates table
   - Priority: **MEDIUM**
   - Two additional prompt template files exist in `prompts/` that aren't documented:
     - `prompts/subagent_research_synthesis.txt`
     - `prompts/subagent_edit_contextualization.txt`
   These are referenced by `pipeline.yaml` via `task_template` and loaded by `services/subagent/prompt_templates.py:load_prompt_template()`. They should be added to the Prompt Templates table.

2. **Document `load_prompt_template()` function** — `services/subagent/prompt_templates.py:48-57`
   - Priority: **MEDIUM**
   - `services/subagent/prompt_templates.py` defines `load_prompt_template(path)` which loads templates from file paths. This function is part of the template resolution chain but isn't documented in `prompts.md`. It's used when `stage_config.task_template` is set in `pipeline.yaml`.

3. **Document the template resolution order more accurately** — `prompts.md:165-167`
   - Priority: **MEDIUM**
   - The documented resolution order says:
     1. `stage_config.task_template` (from pipeline.yaml, can reference files in `prompts/`)
     2. `_SUBAGENT_TASK_TEMPLATES` fallback in `subagent.py`
   
   The actual flow is:
   1. `stage_config.task_template` → `load_prompt_template()` in `services/subagent/prompt_templates.py:48-57`
   2. Falls back to `_SUBAGENT_TASK_TEMPLATES` dict in `services/subagent/prompt_templates.py:7-43`
   
   The documentation references `subagent.py` which doesn't exist as a standalone module — the templates are in `services/subagent/prompt_templates.py`.

4. **Document `importance_weighted_truncate` regex caching** — `prompts.md:58-59`
   - Priority: **LOW**
   - `services/prompts.py:190-193` caches compiled regex patterns in `_regex_cache` for performance. This optimization detail isn't documented but is relevant for understanding the function's behavior under repeated calls.

5. **Document `smart_truncate_context` config dependencies** — `prompts.md:61-62`
   - Priority: **LOW**
   - `smart_truncate_context()` at `services/prompts.py:346-395` loads config from `pipeline.yaml` via `load_pipeline_config()` to get `truncation_llm_enabled`, `truncation_llm_threshold`, `truncation_llm_max_tokens`, and `truncation_llm_temperature`. The function signature shows these as optional parameters but doesn't document that they default to pipeline config values.

## Stale Content

1. **Template resolution references "subagent.py"** — `prompts.md:167`
   - Priority: **MEDIUM**
   - The documentation says `_SUBAGENT_TASK_TEMPLATES` fallback is in `subagent.py`. The actual location is `services/subagent/prompt_templates.py:7-43`. There is no standalone `subagent.py` file in the services directory.

2. **Subagent task templates description is incomplete** — `prompts.md:157-163`
   - Priority: **LOW**
   - The documentation shows `_SUBAGENT_TASK_TEMPLATES` with only `research_synthesis` and `edit_contextualization` keys plus a comment `# Additional templates`. The actual dict at `services/subagent/prompt_templates.py:7-43` contains only these two keys — there are no additional templates. The comment implies more exist.
