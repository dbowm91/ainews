import logging

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (
    DirectQuote,
    ExternalSource,
    KeyClaim,
    RelatedArticle,
    ResearchBrief,
)
from services.prompts import esc_xml_text

logger = logging.getLogger(__name__)


def get_researcher_system_prompt() -> str:
    from schemas.pipeline import get_role_config
    from services.prompts import get_system_prompt

    rc = get_role_config("researcher")
    return get_system_prompt("researcher", rc.system_prompt)


def build_research_prompt(
    title: str,
    extracted_text: str,
    original_url: str,
    author: str,
    topics: list[str],
    web_results: list[dict],
    related_articles: list[dict],
    max_text_length: int = 6000,
    web_synthesis: str = "",
    topic_notes: str = "",
    trend_memory: str = "",
) -> str:
    # User-controlled content is wrapped in XML tags to separate from instructions
    parts = [
        "<source_article>",
        f"  <title>{esc_xml_text(title)}</title>",
        f"  <url>{esc_xml_text(original_url)}</url>",
        f"  <author>{esc_xml_text(author)}</author>",
        f"  <topics>{esc_xml_text(', '.join(topics))}</topics>",
        "  <body>",
        esc_xml_text(extracted_text[:max_text_length]),
        "  </body>",
        "</source_article>",
        "",
    ]

    if topic_notes:
        parts.append("<topic_notes>")
        parts.append(esc_xml_text(topic_notes))
        parts.append("</topic_notes>")
        parts.append("")

    if trend_memory:
        parts.append("<editor_memory>")
        parts.append(esc_xml_text(trend_memory))
        parts.append("</editor_memory>")
        parts.append("")

    if web_synthesis:
        parts.append("<external_sources_synthesis>")
        parts.append(esc_xml_text(web_synthesis))
        parts.append("</external_sources_synthesis>")
        parts.append("")

    if web_results:
        parts.append("<external_sources>")
        for i, wr in enumerate(web_results, 1):
            parts.append(f"  <source index='{i}'>")
            parts.append(f"    <title>{esc_xml_text(wr['title'])}</title>")
            parts.append(f"    <url>{esc_xml_text(wr['url'])}</url>")
            parts.append(f"    <snippet>{esc_xml_text(wr['snippet'][:300])}</snippet>")
            parts.append("  </source>")
        parts.append("</external_sources>")
        parts.append("")

    if related_articles:
        parts.append("<related_articles>")
        for i, ra in enumerate(related_articles, 1):
            parts.append(
                f"  <article index='{i}'>"
                f"{esc_xml_text(ra['title'])} ({esc_xml_text(ra['category'])}) - "
                f"{esc_xml_text(ra['snippet'][:200])}"
                f"</article>",
            )
        parts.append("</related_articles>")
        parts.append("")

    parts.append(
        "Compile a comprehensive research brief using all available information. "
        "Include external context where relevant. Attribute all claims to their sources.",
    )

    return "\n".join(parts)
