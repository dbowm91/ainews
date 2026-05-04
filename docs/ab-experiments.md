# A/B Experiment System

## Overview

The A/B experiment system enables controlled experimentation with different prompt variants for the writing and editing pipeline stages. Articles are deterministically assigned to experiment groups during selection, allowing comparison of article quality and engagement across variants.

## Assignment Logic

Articles are assigned to experiment groups during the `select` stage via `_assign_experiment_group()` in `tasks/select.py`. Assignment uses MD5 hashing for deterministic, reproducible results:

```python
def _assign_experiment_group(article_id: int, salt: str = "") -> str:
    hash_input = f"{article_id}:{salt}:experiment"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    bucket = hash_value % 100
    if bucket < 70:
        return "control"
    elif bucket < 85:
        return "variant_a"
    else:
        return "variant_b"
```

**Split:** 70% control, 15% variant_a, 15% variant_b

## Configuration

Experiment prompts are configured in `pipeline.yaml` under the `experiments:` section:

```yaml
experiments:
  enabled: true
  assignment_salt: "${EXPERIMENT_SALT}"
  prompt_variants:
    writer:
      control: |
        Your control prompt here...
      variant_a: |
        Your variant A prompt here...
      variant_b: |
        Your variant B prompt here...
    editor:
      control: |
        Your control prompt here...
      variant_a: |
        Your variant A prompt here...
      variant_b: |
        Your variant B prompt here...
```

## Variant Selection

During pipeline execution, variant prompts are selected based on `article.experiment_group`:

- `services/writer.py:get_writer_system_prompt(article)` - returns writer variant
- `services/editor.py:get_editor_system_prompt(article)` - returns editor variant

Both fall back to the control prompt if no variant is configured or the article has no assignment.

## Database Column

Articles store their experiment assignment in the `experiment_group` column:

```python
experiment_group = db.Column(db.String(32), nullable=True, index=True)
```

## Use Cases

- **Prompt Optimization:** Test new prompt engineering techniques against control
- **Quality Metrics:** Compare quality scores across variants
- **Engagement Tracking:** Measure click-through and engagement by variant
- **Editorial Voice:** Test different writing styles

## Analysis

Experiment results can be analyzed by filtering articles on `experiment_group` and comparing:
- Quality scores (from `services/quality.py`)
- Engagement metrics (clicks, time on page)
- Pipeline duration and cost

## Disabling Experiments

Set `experiments.enabled: false` in `pipeline.yaml` or omit the `assignment_salt` environment variable to assign all articles to the control group.