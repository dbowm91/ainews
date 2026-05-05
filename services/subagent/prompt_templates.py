"""Subagent prompt templates - loaded from files or from inline defaults."""

from pathlib import Path

__all__ = ["SUBAGENT_TASK_TEMPLATES", "load_prompt_template"]

_SUBAGENT_TASK_TEMPLATES = {
    "research_synthesis": """<source_article>
  <title>{title}</title>
  <body>{body}</body>
</source_article>

<web_results>
{web_results}
</web_results>

Synthesize the external sources into a coherent summary that supplements the source article.
Focus on facts, context, and perspectives not already covered in the source article.
Return your synthesis as a concise paragraph.""",
    "edit_contextualization": """<draft_article>
{draft}
</draft_article>

<research_brief>
{brief}
</research_brief>

<topic_notes>
{topic_notes}
</topic_notes>

<related_articles>
{related_articles}
</related_articles>

<trend_memory>
{trend_memory}
</trend_memory>

Review the draft in light of the research brief, topic notes, related articles, and trend memory.
Identify gaps in context, missing attribution, or claims that need additional support.
Return a concise contextualization that addresses what the editor should know.""",
}

SUBAGENT_TASK_TEMPLATES = _SUBAGENT_TASK_TEMPLATES


def load_prompt_template(path: str) -> str | None:
    """Load a prompt template from a file path."""
    from schemas.pipeline import BASE_DIR

    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / p
    if p.exists():
        return p.read_text()
    return None