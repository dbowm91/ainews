# Prompts System

The `prompts/` directory contains LLM prompt templates used by pipeline stages. Pipeline YAML config can override these with custom prompts.

## Prompt Templates

| File | Stage | Purpose |
|------|-------|---------|
| `prompts/selector.txt` | Select | Score article newsworthiness 1-10 |
| `prompts/researcher.txt` | Research | Build comprehensive research brief |
| `prompts/writer.txt` | Write | Write condensed Smart Brevity article |
| `prompts/editor.txt` | Edit | Polish and contextualize article |
| `prompts/newsletter_reader.txt` | Newsletter | Extract themes from articles |
| `prompts/newsletter_writer.txt` | Newsletter | Generate newsletter summary |
| `prompts/newsletter_editor.txt` | Newsletter | Review newsletter for quality |

## Prompt Loading

```python
# services/prompts.py

def get_system_prompt(stage: str) -> str:
    """Load system prompt for a pipeline stage.
    Checks pipeline.yaml system_prompt override first,
    then falls back to prompts/*.txt file."""

def load_prompt_file(filename: str) -> str:
    """Load prompt template from prompts/ directory."""
```

### Override Mechanism

In `pipeline.yaml`, each role can specify a custom `system_prompt`:

```yaml
pipeline:
  writer:
    provider: ollama-local
    model: qwen3:8b
    system_prompt: |
      You are a tech news writer. Your task is to write a concise,
      impactful article in Smart Brevity format...
```

If `system_prompt` is set, it takes priority over the `prompts/*.txt` file.

## Context Truncation

LLM prompts can grow large. `services/prompts.py` provides token budgeting:

```python
def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Estimate token count for text."""

def sliding_window_truncate(text: str, max_tokens: int) -> str:
    """Truncate text to max_tokens using sliding window."""

def importance_weighted_truncate(text: str, max_tokens: int) -> str:
    """Truncate while preserving most important content."""

def smart_truncate_context(context: str, max_tokens: int) -> str:
    """LLM-powered summarization fallback for context truncation."""

def summarize_context(context: str, max_tokens: int) -> str:
    """Summarize context using LLM with caching."""
```

## Prompt Escaping

All prompt data is auto-escaped to prevent XML injection:

```python
# utils/text.py
def esc_xml_text(text: str) -> str:
    """Escape text for XML element content.
    Handles <, >, &, ", ' characters."""

def esc_xml_attr(text: str) -> str:
    """Escape text for XML attribute values."""

def escape_prompt_data(data: dict) -> dict:
    """Recursively escape dict values for prompt injection prevention."""
```

Used by `services/subagent.py:_escape_prompt_data()` before template resolution.

## Stage Prompts

### Selector (`selector.txt`)

Evaluates article newsworthiness:
- Input: Article title, URL, extracted text, source info
- Output: `{score, confidence, reasoning, key_topics}`
- Threshold: score >= 6 with medium/high confidence → proceed

### Researcher (`researcher.txt`)

Builds research context:
- Input: Article content, web search results, related articles, topic notes, trend memory
- Output: `{key_findings, context, citations, related_trends}`
- Uses subagent tools: `web_search`, `related_articles`, `get_trend_memory`

### Writer (`writer.txt`)

Creates condensed article:
- Input: Research brief, source article
- Output: Smart Brevity format (hook → context → key points → implications)
- Target: 200-400 words, 3-5 key points

### Editor (`editor.txt`)

Polishes and contextualizes:
- Input: Draft article, research brief, contextualization (from subagent), topic notes, trend memory
- Output: Final edited article with proper attribution
- Validates: schema validation + quality checks

### Newsletter Reader (`newsletter_reader.txt`)

Extracts themes from articles:
- Input: List of article summaries
- Output: `{themes, highlights, connections}`

### Newsletter Writer (`newsletter_writer.txt`)

Generates newsletter summary:
- Input: Reader output, article list
- Output: Executive summary text

### Newsletter Editor (`newsletter_editor.txt`)

Reviews newsletter:
- Input: Draft newsletter
- Output: Polished newsletter with attribution check

## A/B Experiment Prompts

In `pipeline.yaml` under `experiments`, prompt variants can be defined:

```yaml
experiments:
  enabled: true
  prompt_variants:
    writer:
      control: "Standard writer prompt..."
      variant_a: "Alternative writer prompt with different emphasis..."
    editor:
      control: "Standard editor prompt..."
      variant_a: "Alternative editor prompt..."
```

Articles are assigned to experiment groups (control/variant_a/variant_b) via deterministic MD5 hash in `tasks/select.py:_assign_experiment_group()`. The writer/editor check `article.experiment_group` and select the appropriate prompt variant.

## Subagent Task Templates

Subagent prompts are defined in `services/subagent/prompt_templates.py`:

```python
_SUBAGENT_TASK_TEMPLATES = {
    "research_synthesis": "...",
    "edit_contextualization": "...",
    # Additional templates
}
```

Template resolution order:
1. `stage_config.task_template` (from pipeline.yaml, can reference files in `prompts/`)
2. `_SUBAGENT_TASK_TEMPLATES` fallback in `subagent.py`

## Key Files

| File | Purpose |
|------|---------|
| `prompts/*.txt` | Stage-specific prompt templates |
| `services/prompts.py` | `get_system_prompt()`, `load_prompt_file()`, token counting, truncation |
| `utils/text.py` | `esc_xml_text()`, `esc_xml_attr()`, `escape_prompt_data()` |
| `services/subagent/prompt_templates.py` | Subagent task prompt templates |
| `services/subagent/prompt_templates.py` | Template rendering |
| `pipeline.yaml` | `system_prompt` overrides, experiment variants |
| `services/researcher.py` | Research prompt assembly with XML tags |
| `services/writer.py` | Writer prompt assembly with experiment support |
| `services/editor.py` | Editor prompt assembly with contextualization |
