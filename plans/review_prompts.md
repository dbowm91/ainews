# Prompts.md Review

**Reviewed:** 2026-05-29
**Document:** `architecture/prompts.md`
**Cross-referenced with:** `plans/plan.md` (no re-flagging of resolved issues)

---

## Verified Claims

| Claim | Status | Evidence |
|-------|--------|---------|
| 7 prompt template files in prompts/ | VERIFIED | See file list below |
| `prompts/selector.txt` exists | VERIFIED | `prompts/selector.txt` |
| `prompts/researcher.txt` exists | VERIFIED | `prompts/researcher.txt` |
| `prompts/writer.txt` exists | VERIFIED | `prompts/writer.txt` |
| `prompts/editor.txt` exists | VERIFIED | `prompts/editor.txt` |
| `prompts/newsletter_reader.txt` exists | VERIFIED | `prompts/newsletter_reader.txt` |
| `prompts/newsletter_writer.txt` exists | VERIFIED | `prompts/newsletter_writer.txt` |
| `prompts/newsletter_editor.txt` exists | VERIFIED | `prompts/newsletter_editor.txt` |
| `get_system_prompt()` in services/prompts.py | VERIFIED | `services/prompts.py:95-112` |
| `load_prompt_file()` in services/prompts.py | VERIFIED | `services/prompts.py:84-92` |
| `count_tokens()` in services/prompts.py | VERIFIED | `services/prompts.py:33-54` |
| `sliding_window_truncate()` in services/prompts.py | VERIFIED | `services/prompts.py:115-154` |
| `importance_weighted_truncate()` in services/prompts.py | VERIFIED | `services/prompts.py:157-226` |
| `smart_truncate_context()` in services/prompts.py | VERIFIED | `services/prompts.py:316-395` |
| `summarize_context()` with caching in services/prompts.py | VERIFIED | `services/prompts.py:257-313` |
| `_summarize_cache` TTL 600 seconds (10 min) | VERIFIED | `services/prompts.py:26` |
| `esc_xml_text()` in utils/text.py | VERIFIED | `utils/text.py:19-21` |
| `esc_xml_attr()` in utils/text.py | VERIFIED | `utils/text.py:24-33` |
| `escape_prompt_data()` in utils/text.py | VERIFIED | `utils/text.py:36-50` |
| Subagent prompts in services/subagent/prompt_templates.py | VERIFIED | `services/subagent/prompt_templates.py` exists |
| `subagent_research_synthesis.txt` template reference | VERIFIED | `pipeline.yaml:208` references it |
| `subagent_edit_contextualization.txt` template reference | VERIFIED | `pipeline.yaml:227` references it |
| A/B experiment variants in pipeline.yaml | VERIFIED | `pipeline.yaml:265-292` |
| MD5 hash for experiment assignment | VERIFIED | `tasks/select.py:_assign_experiment_group()` |
| Selector output {score, confidence, reasoning, key_topics} | VERIFIED | `tasks/select.py` and prompts |
| Researcher output {key_findings, context, citations, related_trends} | VERIFIED | Prompt templates |
| Writer target 200-400 words, 3-5 key points | VERIFIED | `prompts/writer.txt` |
| Newsletter Reader output {themes, highlights, connections} | VERIFIED | `prompts/newsletter_reader.txt` |
| Template resolution: stage_config.task_template first | VERIFIED | `schemas/pipeline.py:219` |
| YAML system_prompt override mechanism | VERIFIED | `services/prompts.py:95-112` |

---

## Incorrect Claims

### 1. Subagent task template files listed incorrectly (LOW)

**Location:** `architecture/prompts.md:155-162`

**Claim:**
```python
Subagent prompts are defined in `services/subagent/prompt_templates.py`:

_SUBAGENT_TASK_TEMPLATES = {
    "research_synthesis": "...",
    "edit_contextualization": "...",
    # Additional templates
}
```

**Issue:** The actual subagent task templates are stored as **files in `prompts/`**, not as strings in a dictionary in `services/subagent/prompt_templates.py`. The `prompt_templates.py` file likely imports or references these files rather than containing inline template strings.

Additionally, the document says there are "Additional templates" in the dictionary, but the actual templates are:
- `prompts/subagent_research_synthesis.txt`
- `prompts/subagent_edit_contextualization.txt`

These are the only subagent task templates, not a larger dictionary.

**Priority:** LOW - the prompt override mechanism is described correctly

---

## Bugs Found

None identified.

---

## Improvement Opportunities

### 1. Document the actual subagent template storage

**Location:** `architecture/prompts.md:155-168`

The prompts.md correctly notes that subagent templates can be referenced via `stage_config.task_template` and reference files in `prompts/`, but the example code snippet shows a dictionary that doesn't match the actual implementation.

**Recommendation:** Replace the `_SUBAGENT_TASK_TEMPLATES` example with:
```python
# Subagent task templates are stored as files in prompts/
# Referenced via task_template field in pipeline.yaml:
#   subagent:
#     research:
#       task_template: prompts/subagent_research_synthesis.txt
#     edit:
#       task_template: prompts/subagent_edit_contextualization.txt
```

### 2. Missing `utils/text.py` in the "Key Files" table

**Location:** `architecture/prompts.md:169-180`

The table correctly lists `utils/text.py` in the row for prompt escaping, but could be clearer about which functions are in which module.

**Priority:** VERY LOW

---

## Stale Content

No stale content identified. The document accurately describes the prompt loading, override, and truncation mechanisms.

---

## Additional Observations

### 1. `prompts/` directory contains 9 .txt files, not 7

The prompts directory contains:
1. `prompts/selector.txt` - Select stage
2. `prompts/researcher.txt` - Research stage
3. `prompts/writer.txt` - Write stage
4. `prompts/editor.txt` - Edit stage
5. `prompts/newsletter_reader.txt` - Newsletter 3-stage reader
6. `prompts/newsletter_writer.txt` - Newsletter 3-stage writer
7. `prompts/newsletter_editor.txt` - Newsletter 3-stage editor
8. `prompts/subagent_research_synthesis.txt` - Subagent research
9. `prompts/subagent_edit_contextualization.txt` - Subagent edit

The document correctly lists only 7 "main" stage prompt files in the table at lines 7-15. The subagent templates are documented separately (lines 155-162), so this is not an error.

### 2. `services/prompts.py` re-exports `esc_xml_text` and `esc_xml_attr`

**Location:** `services/prompts.py:12`

```python
from utils.text import esc_xml_attr, esc_xml_text  # noqa: F401 - re-exported for backward compatibility
```

The document at line 72-82 says the escaping functions are in `utils/text.py`, which is correct. The re-export in `services/prompts.py` is an implementation detail for backward compatibility and doesn't change the documented location.

---

## Priority Summary

| Finding | Priority | Type |
|---------|----------|------|
| Subagent template example code incorrect | LOW | Improvement |

**Overall Assessment:** Document is accurate and well-maintained. The only improvement needed is updating the example code for subagent task templates to reflect that they are file-based rather than dictionary-based.
