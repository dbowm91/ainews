# Review: prompts.md

**Reviewed:** 2026-05-31
**Source:** `architecture/prompts.md`
**Reviewer:** Subagent 4 (Pipeline & Tasks Layer)
**Status:** COMPLETE

---

## Verified Claims

### Prompt Loading Functions
- `get_system_prompt(role, yaml_prompt)` in `services/prompts.py` — VERIFIED (`services/prompts.py:140-157`)
- `load_prompt_file(name)` returns None if not found — VERIFIED (`services/prompts.py:131-137`)

### Override Mechanism
- YAML `system_prompt` takes priority over `.txt` file — VERIFIED (`services/prompts.py:150-154`)

### Context Truncation Functions
- `count_tokens(text, model)` — VERIFIED (`services/prompts.py:36-56`)
- `sliding_window_truncate(text, max_chars, model, ...)` — VERIFIED (`services/prompts.py:160-199`)
- `importance_weighted_truncate(text, max_chars, key_topics)` — VERIFIED (`services/prompts.py:202-271`)
- `smart_truncate_context(text, max_chars, model, ...)` returns `tuple[str, bool]` — VERIFIED (`services/prompts.py:361-440`)
- `summarize_context(text, llm_provider, max_tokens, temperature)` — VERIFIED (`services/prompts.py:302-358`)
- Cache: 10-minute TTL, SHA-256 of first 500 chars — VERIFIED (`services/prompts.py:27-28, 321`)

### Prompt Escaping
- `esc_xml_text(text)` in `utils/text.py` — VERIFIED (`utils/text.py:19-21`)
- `esc_xml_attr(text)` in `utils/text.py` — VERIFIED (`utils/text.py:24-33`)
- `escape_prompt_data(data)` in `utils/text.py` — VERIFIED (`utils/text.py:36-50`)

### Subagent Task Templates
- `_SUBAGENT_TASK_TEMPLATES` in `services/subagent/prompt_templates.py` — VERIFIED (`services/subagent/prompt_templates.py:7-43`)
- Template keys: `research_synthesis`, `edit_contextualization` — VERIFIED (`services/subagent/prompt_templates.py:7-43`)

### Template Resolution Order
- 1. `stage_config.task_template` (YAML) → 2. `_SUBAGENT_TASK_TEMPLATES` fallback — VERIFIED (consistent with `tasks/research.py:74`, `tasks/edit.py:104`)

### A/B Experiment Prompts
- Defined in `pipeline.yaml` `experiments.prompt_variants` — VERIFIED (`tasks/select.py:19-43`, `services/writer.py`, `services/editor.py`)
- Writer and editor check `article.experiment_group` — VERIFIED (`services/writer.py:get_writer_system_prompt()`, `services/editor.py:get_editor_system_prompt()`)

### Stage Prompt Descriptions
- Selector: evaluates article newsworthiness 1-10, threshold score >= 6 with medium/high confidence — VERIFIED (`tasks/select.py:86-94, 126-128`)
- Researcher: builds research brief with web search, related articles, trend memory — VERIFIED (`tasks/research.py:48-178`)
- Writer: Smart Brevity format, 200-400 words — VERIFIED (`tasks/write.py:58-101`)
- Editor: contextualization, validation, quality checks — VERIFIED (`tasks/edit.py:220-363`)
- Newsletter stages: reader, writer, editor — VERIFIED (`tasks/newsletter.py:144-157`)

---

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| 7-18 | "7 prompt template files" | 9 files exist in `prompts/`: selector.txt, researcher.txt, writer.txt, editor.txt, newsletter_reader.txt, newsletter_writer.txt, newsletter_editor.txt, subagent_research_synthesis.txt, subagent_edit_contextualization.txt | MEDIUM |
| 90 | `escape_prompt_data(data: dict) -> dict` in `utils/text.py` | Correct location, but signature says `data: dict` while actual code says `data: dict[str, Any]` | LOW |
| 160-175 | Subagent task templates section says "Template resolution order: 1. stage_config.task_template 2. _SUBAGENT_TASK_TEMPLATES fallback" | Correct, but the section heading implies this is about file-based templates. The `load_prompt_template()` function loads from arbitrary file paths, not from `prompts/` directory. | LOW |

---

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | `escape_prompt_data` is in `utils/text.py` but architecture doc references `_escape_prompt_data` in `services/subagent/runner.py` — the underscore-prefixed name is a backward-compat alias, not the canonical name | `services/subagent/__init__.py:54` | LOW | `_escape_prompt_data = escape_prompt_data` is a re-export. Canonical location is `utils/text.py:36`. |

---

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | Update prompt file count from 7 to 9 — add subagent_research_synthesis.txt and subagent_edit_contextualization.txt to the table | documentation | P1 |
| 2 | Clarify that `_escape_prompt_data` is a backward-compat alias for `escape_prompt_data` | documentation | P2 |
| 3 | Document `_budget_tokens()` function (`services/prompts.py:274-299`) — exists but not in prompts.md | documentation | P2 |
| 4 | Document `max_tokens_for_model()` function (`services/prompts.py:59-79`) — used by truncation functions but not mentioned | documentation | P3 |
| 5 | Note that `load_prompt_template()` in `services/subagent/prompt_templates.py` loads from arbitrary file paths, not just `prompts/` directory | documentation | P3 |

---

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| 7-18 | "7 prompt template files" | 9 files exist (2 subagent templates missing from list) | update |
| 185 | Duplicate entry: `services/subagent/prompt_templates.py` listed twice in Key Files table | Copy-paste error | remove duplicate |

---

## Summary

- Verified: 22 claims
- Incorrect: 3 claims
- Bugs: 1 (HIGH: 0, MEDIUM: 0, LOW: 1)
- Improvements: 5
- Stale items: 2
