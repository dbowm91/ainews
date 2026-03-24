from pydantic import BaseModel, Field
from typing import Optional
import logging

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
    newsworthiness: str = Field(
        description="Why this matters to a tech audience"
    )
    impact_score: int = Field(
        ge=0, le=100,
        description=(
            "Impact score 0-100 reflecting: importance of subject matter, "
            "original article popularity, research findings significance, "
            "community excitement, and engagement potential. "
            "0-25: niche/minor. 26-50: notable. 51-75: significant. 76-100: major/breaking."
        ),
    )


DEFAULT_RESEARCHER_SYSTEM_PROMPT = (
    "You are a tech research analyst. Your job is to compile a comprehensive "
    "research brief for a news article.\n\n"
    "INSTRUCTIONS:\n"
    "1. Extract all key factual claims from the source article.\n"
    "2. Identify direct quotes with proper attribution.\n"
    "3. Use the provided external sources and related articles to add context.\n"
    "4. Explain why this matters to a tech-savvy audience.\n"
    "5. Be precise with names, dates, numbers, and attributions.\n"
    "6. Rate each claim's confidence as high/medium/low.\n"
    "7. Provide an impact score (0-100) based on:\n"
    "   - Importance of the subject matter to the tech community\n"
    "   - Popularity/engagement signals of the original article\n"
    "   - Significance of research findings and external context\n"
    "   - Community excitement and discussion level\n"
    "   - Potential lasting impact on the industry\n"
    "   Scale: 0-25 niche/minor, 26-50 notable, 51-75 significant, 76-100 major/breaking.\n"
)


def get_researcher_system_prompt() -> str:
    from schemas.pipeline import get_role_config
    rc = get_role_config("researcher")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_RESEARCHER_SYSTEM_PROMPT


def build_research_prompt(
    title: str,
    extracted_text: str,
    original_url: str,
    author: str,
    topics: list[str],
    web_results: list[dict],
    related_articles: list[dict],
    max_text_length: int = 6000,
) -> str:
    parts = [
        f"SOURCE ARTICLE: {title}",
        f"URL: {original_url}",
        f"AUTHOR: {author}",
        f"TOPICS: {', '.join(topics)}",
        "",
        "ARTICLE TEXT:",
        extracted_text[:max_text_length],
        "",
    ]

    if web_results:
        parts.append("ADDITIONAL WEB SOURCES:")
        for i, wr in enumerate(web_results, 1):
            parts.append(f"{i}. [{wr['title']}]({wr['url']})")
            parts.append(f"   {wr['snippet'][:300]}")
        parts.append("")

    if related_articles:
        parts.append("RELATED ARTICLES FROM OUR DATABASE:")
        for i, ra in enumerate(related_articles, 1):
            parts.append(f"{i}. {ra['title']} ({ra['category']}) - {ra['snippet'][:200]}")
        parts.append("")

    parts.append(
        "Compile a comprehensive research brief using all available information. "
        "Include external context where relevant. Attribute all claims to their sources."
    )

    return "\n".join(parts)
