from pydantic import BaseModel, Field
from typing import Optional
import logging

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


DEFAULT_WRITER_SYSTEM_PROMPT = (
    "You are a professional tech news writer. Write condensed articles "
    "inspired by the Smart Brevity format — short, scannable, high-signal.\n\n"
    "STRUCTURE:\n"
    "1. HEADLINE — Short, punchy, accurate. No clickbait.\n"
    "2. TL;DR — One bold sentence that captures the essence. The busy-reader hook.\n"
    "3. WHY IT MATTERS — 1-2 sentences on why this is significant to the reader.\n"
    "   Connect the story to a bigger trend or consequence.\n"
    "4. BODY — 3-5 tight paragraphs. Lead with the most important fact.\n"
    "   Use clear, direct prose. No filler, no throat-clearing, no fluff.\n"
    "   Attribute every claim to a source. Include context from external sources.\n"
    "   Write in markdown with paragraphs, not bullet lists.\n"
    "5. WHAT TO WATCH — Forward-looking: what happens next, what to monitor,\n"
    "   a key date, or why this story isn't over.\n\n"
    "STYLE RULES:\n"
    "- Sentences should be short and punchy. Vary rhythm.\n"
    "- Use technical terms accurately. Assume the reader knows the basics.\n"
    "- No opinions or speculation. Factual only.\n"
    "- Include inline references to external sources in the body text.\n"
    "- Reference related articles from the research brief where relevant.\n"
)


def get_writer_system_prompt() -> str:
    from schemas.pipeline import get_role_config
    rc = get_role_config("writer")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_WRITER_SYSTEM_PROMPT


def build_writer_prompt(
    title: str,
    topics: list[str],
    research_brief: str,
    max_key_points: int = 5,
) -> str:
    return (
        f"TOPICS: {', '.join(topics)}\n"
        f"ORIGINAL TITLE: {title}\n\n"
        f"RESEARCH BRIEF:\n{research_brief}\n\n"
        f"Write a condensed news article based on this research brief. "
        f"Include all key facts, quotes with attribution, and external context. "
        f"Include 'why_it_matters' (why this is significant) and "
        f"'what_to_watch' (what happens next or what to monitor). "
        f"Limit key_points to {max_key_points} items. "
        f"Reference external sources and related articles from the brief in the body text. "
        f"List all citations used."
    )
