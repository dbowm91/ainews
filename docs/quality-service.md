# Quality Service

The quality service (`services/quality.py`) provides content quality assessment infrastructure for articles in the pipeline.

## Purpose

The quality service evaluates article content quality using both lightweight heuristic signals and LLM-based assessment. It integrates with the pipeline to compute quality scores and route failed articles to `review` status for manual inspection.

## Data Structures

### `QualityScore`
A dataclass holding quality assessment scores:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `groundedness` | float | 0-1 | Factual alignment with sources |
| `coherence` | float | 0-1 | Logical flow and readability |
| `completeness` | float | 0-1 | Coverage of key points |
| `safety` | float | 0-1 | Absence of harmful content |
| `overall` | float | 0-1 | Average of all dimensions (auto-computed) |

**Methods:**
- `passes_threshold(threshold: float = 0.7) -> bool`: Returns True if overall score meets threshold

## Classes

### `QualityAssessor` (Abstract Base)
Base class for quality assessment implementations.

**Methods:**
- `assess(content, sources=None, context=None) -> QualityScore`: Abstract method for quality assessment

### `LLMQualityAssessor`
LLM-based quality assessment using the LLM-as-judge pattern.

**Initialization:**
- `model`: Optional model override
- `provider_id`: Optional provider ID

**Methods:**
- `assess(content, sources=None, context=None) -> QualityScore`: Uses LLM to evaluate content quality

**Configuration:**
- Uses `get_provider_for_role("editor")` by default
- Prompts LLM with sources and content
- Parses JSON response for dimension scores
- Falls back to neutral scores (0.5) on failure

**Internal Methods:**
- `_format_sources(sources)`: Formats up to 5 sources for the prompt
- `_build_assessment_prompt(content, sources_text, context)`: Builds the evaluation prompt
- `_parse_response(text)`: Parses LLM JSON response into QualityScore

## Functions

### `detect_hallucination(content: str, sources: list[dict]) -> list[str]`
Detects potential hallucinations by checking factual claims against source material.

**Returns:** List of suspicious claims (max 5) that don't appear to be grounded in sources.

**Algorithm:**
- Extracts sentences from content
- For each sentence with 5+ words, checks if key words (length > 4) appear in source text
- Returns sentences where key words don't match any source

### `lightweight_quality_signals(content: str, sources: list[dict] | None = None) -> QualityScore`
Fast heuristic quality assessment without LLM calls.

**Dimensions:**
- `groundedness`: Based on source attribution and citation markers
- `coherence`: Based on sentence structure and transition words
- `completeness`: Based on content length (100-600+ words)
- `safety`: Basic keyword filtering for harmful patterns

**Internal Helpers:**
- `_assess_groundedness(content, sources) -> float`: Checks if source titles appear in content
- `_assess_coherence(content) -> float`: Scores based on sentence count and transition words
- `_assess_completeness(content) -> float`: Scores based on word count
- `_assess_safety(content) -> float`: Checks for harmful patterns (kill, bomb, terrorist, hate speech, etc.)

## Pipeline Integration

The quality service runs after the edit stage:
- Quality scores are computed via `build_quality_report()` in `tasks/edit.py`
- Reports are persisted to the `quality_reports` table via `persist_quality_report()`
- Articles failing quality gates are routed to `review` status for manual inspection

## Configuration Options

Currently, the quality service uses these defaults:
- **LLM Model**: Uses editor role provider (typically `gpt-4o-mini` or equivalent)
- **Max Tokens**: 512 for LLM assessment
- **Assessment Threshold**: 0.7 (used with `passes_threshold()`)
- **Source Limit**: 5 sources formatted for LLM prompt
- **Content Truncation**: 2000 chars sent to LLM

## Usage Example

```python
from services.quality import lightweight_quality_signals, LLMQualityAssessor

# Fast heuristic assessment
score = lightweight_quality_signals(article_content, sources)
if score.passes_threshold(0.7):
    print("Quality check passed")

# LLM-based assessment
assessor = LLMQualityAssessor()
score = assessor.assess(article_content, sources)
print(f"Overall quality: {score.overall}")
```
