import logging

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (
    CitationItem,
    CondensedArticle,
    OriginalAttribution,
)
from services.prompts import esc_xml_text

logger = logging.getLogger(__name__)


def get_writer_system_prompt(article=None) -> str:
    """Get writer system prompt, optionally using experiment variant.

    Args:
        article: Optional article object with experiment_group attribute.
                 If provided and experiment_group is set, uses the variant prompt.
    """
    from schemas.pipeline import get_config, get_role_config
    from services.prompts import get_system_prompt

    rc = get_role_config("writer")
    config = get_config()

    # Check for experiment variant
    if article and hasattr(article, 'experiment_group') and article.experiment_group:
        experiments = config.get("experiments", {})
        if experiments.get("enabled", False):
            prompt_variants = experiments.get("prompt_variants", {})
            writer_variants = prompt_variants.get("writer", {})
            variant_prompt = writer_variants.get(article.experiment_group)
            if variant_prompt:
                return get_system_prompt("writer", variant_prompt)

    return get_system_prompt("writer", rc.system_prompt)


def build_writer_prompt(
    title: str,
    topics: list[str],
    research_brief: str,
    max_key_points: int = 5,
    trend_memory: str = "",
) -> str:
    # User-controlled content wrapped in XML tags to separate from instructions
    parts = [
        "<input_data>\n",
        f"  <topics>{esc_xml_text(', '.join(topics))}</topics>\n",
        f"  <original_title>{esc_xml_text(title)}</original_title>\n",
        f"  <research_brief>\n{esc_xml_text(research_brief)}\n  </research_brief>\n",
    ]

    if trend_memory:
        parts.append("  <editor_memory>\n")
        parts.append(esc_xml_text(trend_memory))
        parts.append("\n  </editor_memory>\n")

    parts.append("</input_data>\n\n")

    parts.append(
        f"Write a condensed news article based on this research brief. "
        f"Include all key facts, quotes with attribution, and external context. "
        f"Include 'why_it_matters' (why this is significant) and "
        f"'what_to_watch' (what happens next or what to monitor). "
        f"Limit key_points to {max_key_points} items. "
        f"Reference external sources and related articles from the brief in the body text. "
        f"List all citations used.",
    )

    return "".join(parts)
