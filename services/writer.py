import logging

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (  # noqa: F401
    CitationItem,
    CondensedArticle,
    OriginalAttribution,
)
from services.prompts import esc_xml_text

logger = logging.getLogger(__name__)


def get_writer_system_prompt() -> str:
    from schemas.pipeline import get_role_config
    from services.prompts import get_system_prompt

    rc = get_role_config("writer")
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
        f"List all citations used."
    )

    return "".join(parts)
