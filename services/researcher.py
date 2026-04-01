from pydantic import BaseModel, Field
from typing import Optional
import logging

from services.prompts import esc_xml_text

logger = logging.getLogger(__name__)


class ExternalSource(BaseModel):
    title: str
    url: str
    snippet: str


class KeyClaim(BaseModel):
    claim: str
    source: str  # "source_article" or URL
    confidence: str  # high/medium/low


class DirectQuote(BaseModel):
    quote: str
    attribution: str  # Who said it
    source_url: Optional[str] = None


class RelatedArticle(BaseModel):
    title: str
    category: str
    summary_snippet: str  # First 200 chars of our summary
    created_at: str


class ResearchBrief(BaseModel):
    source_summary: str = Field(description="TL;DR of the source article")
    key_claims: list[KeyClaim] = Field(
        description="Factual claims with source attribution"
    )
    direct_quotes: list[DirectQuote] = Field(
        default=[], description="Verbatim quotes from the article"
    )
    external_sources: list[ExternalSource] = Field(
        default=[], description="Additional web sources found during research"
    )
    related_articles: list[RelatedArticle] = Field(
        default=[], description="Related articles from our database"
    )
    context_notes: str = Field(
        default="",
        description="Additional context, background, or significance",
    )
    newsworthiness: str = Field(description="Why this matters to a tech audience")
    impact_score: int = Field(
        ge=0,
        le=100,
        description=(
            "Impact score 0-100 reflecting: importance of subject matter, "
            "original article popularity, research findings significance, "
            "community excitement, and engagement potential. "
            "0-25: niche/minor. 26-50: notable. 51-75: significant. 76-100: major/breaking."
        ),
    )


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
                f"</article>"
            )
        parts.append("</related_articles>")
        parts.append("")

    parts.append(
        "Compile a comprehensive research brief using all available information. "
        "Include external context where relevant. Attribute all claims to their sources."
    )

    return "\n".join(parts)
