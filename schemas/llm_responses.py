"""Pydantic schemas for LLM pipeline response validation.

All models used by `chat_structured()` across pipeline stages are defined here
to avoid scattering response schemas across service modules.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Selector stage ──────────────────────────────────────────────────────────


class SelectionResult(BaseModel):
    selected: bool
    score: int = Field(ge=1, le=10)
    reason: str
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")


# ── Researcher stage ────────────────────────────────────────────────────────


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


# ── Writer stage ────────────────────────────────────────────────────────────


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


# ── Newsletter pipeline ─────────────────────────────────────────────────────


class NewsletterBrief(BaseModel):
    themes: list[str] = Field(description="Major themes across the selected articles")
    highlights: list[str] = Field(description="Most notable individual stories")
    connections: list[str] = Field(
        default_factory=list,
        description="Patterns or threads connecting multiple articles",
    )


class ExecutiveSummary(BaseModel):
    summary: str = Field(
        description=(
            "3-4 paragraph executive summary. Sharp, slightly informal tone. "
            "Lead with the most important takeaway. "
            "Reference specific articles where relevant."
        )
    )


# ── Subagent responses ──────────────────────────────────────────────────────


class SubagentResponse(BaseModel):
    synthesis: str = Field(description="Synthesized output from the subagent")
    used_fallback: bool = Field(
        default=False,
        description="Whether a fallback response was used due to subagent failure",
    )
    fallback_stages: list[str] = Field(
        default=[],
        description="Which stages used fallback responses",
    )


class ResearchSynthesisResponse(BaseModel):
    synthesis: str = Field(description="Synthesized summary of web research results")


class EditContextualizationResponse(BaseModel):
    synthesis: str = Field(
        description="Contextualization notes for the editor about gaps, attribution, and claims needing support"
    )


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class ToolResult(BaseModel):
    id: str
    name: str
    content: str


class ToolCallingResponse(BaseModel):
    text: str
    model: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_used: int = 0
