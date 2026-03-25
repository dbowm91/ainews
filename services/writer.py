from pydantic import BaseModel, Field
from typing import Optional
import logging

from services.prompts import esc_xml_text

logger = logging.getLogger(__name__)


class CitationItem(BaseModel):
    title: str
    url: str
    author: Optional[str] = None
    type: str = "article"  # article, web, db


class OriginalAttribution(BaseModel):
    source: str
    author: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None


class CondensedArticle(BaseModel):
    headline: str = Field(description="Catchy but accurate headline")
    tldr: str = Field(description="One-sentence summary for busy readers")
    why_it_matters: str = Field(
        default="",
        description="1-2 sentences on why this matters to the reader. Connect to a bigger trend or consequence.",
    )
    body: str = Field(
        description=(
            "The full condensed article. Write in a clear, engaging style "
            "for a tech-savvy audience. Include context from external sources. "
            "Use markdown formatting."
        )
    )
    key_points: list[str] = Field(
        description="3-5 bullet points of the most important takeaways"
    )
    what_to_watch: str = Field(
        default="",
        description="Forward-looking indicator: what happens next, a key date, or why this story isn't over.",
    )
    citations: list[CitationItem] = Field(
        description="All sources referenced in the article"
    )
    original_attribution: OriginalAttribution
    tags: list[str] = Field(
        default_factory=list,
        description="1-3 concise tags describing the article's specific topics (lowercase, hyphenated)",
    )


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
) -> str:
    # User-controlled content wrapped in XML tags to separate from instructions
    return (
        "<input_data>\n"
        f"  <topics>{esc_xml_text(', '.join(topics))}</topics>\n"
        f"  <original_title>{esc_xml_text(title)}</original_title>\n"
        f"  <research_brief>\n{esc_xml_text(research_brief)}\n  </research_brief>\n"
        "</input_data>\n\n"
        f"Write a condensed news article based on this research brief. "
        f"Include all key facts, quotes with attribution, and external context. "
        f"Include 'why_it_matters' (why this is significant) and "
        f"'what_to_watch' (what happens next or what to monitor). "
        f"Limit key_points to {max_key_points} items. "
        f"Reference external sources and related articles from the brief in the body text. "
        f"List all citations used."
    )
