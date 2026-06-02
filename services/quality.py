"""Quality assessment infrastructure for article content.

Provides both lightweight heuristic signals and LLM-based quality assessment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality assessment scores for article content."""

    groundedness: float  # 0-1, factual alignment with sources
    coherence: float  # 0-1, logical flow and readability
    completeness: float  # 0-1, coverage of key points
    safety: float  # 0-1, absence of harmful content
    overall: float = 0.0

    def __post_init__(self):
        scores = [self.groundedness, self.coherence, self.completeness, self.safety]
        self.overall = sum(scores) / len(scores)

    def passes_threshold(self, threshold: float = 0.7) -> bool:
        return self.overall >= threshold


class QualityAssessor:
    """Abstract base class for quality assessment."""

    @classmethod
    def assess(
        cls,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> QualityScore:
        """Assess the quality of content against sources and context."""
        raise NotImplementedError


class LLMQualityAssessor(QualityAssessor):
    """LLM-based quality assessment using LLM-as-judge pattern."""

    def __init__(self, model: str | None = None, provider_id: str | None = None):
        self.model = model
        self.provider_id = provider_id

    def assess(  # type: ignore[override]
        self,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> QualityScore:
        """Use LLM to assess content quality."""
        try:
            from services.llm import get_provider_for_role

            provider, model, max_tokens, provider_id = get_provider_for_role("editor")
            sources_text = self._format_sources(sources or [])
            prompt = self._build_assessment_prompt(content, sources_text, context)
            response = provider.complete(  # type: ignore[attr-defined]
                prompt=prompt,
                system_prompt="You are a quality assessment expert. Evaluate content objectively.",
                model=model or self.model or "gpt-4o-mini",
                max_tokens=512,
            )
            return self._parse_response(response.text)
        except (ImportError, json.JSONDecodeError,
                AuthError, ProviderServerError, ProviderTimeoutError,
                ConnectionError) as e:
            logger.warning("LLM quality assessment failed: %s", e)
            return QualityScore(
                groundedness=0.5,
                coherence=0.5,
                completeness=0.5,
                safety=1.0,
            )

    def _format_sources(self, sources: list[dict[str, Any]]) -> str:
        if not sources:
            return "No sources provided."
        lines = []
        for i, src in enumerate(sources[:5], 1):
            title = src.get("title", "Untitled")
            snippet = src.get("snippet", src.get("content", ""))[:200]
            lines.append(f"[{i}] {title}: {snippet}")
        return "\n".join(lines)

    def _build_assessment_prompt(
        self, content: str, sources_text: str, context: dict[str, Any] | None,
    ) -> str:
        return f"""Evaluate the quality of this article content:

<sources>
{sources_text}
</sources>

<content>
{content[:2000]}
</content>

Rate each dimension 0.0-1.0:
- groundedness: How well does the content align with the sources?
- coherence: How well does the content flow logically?
- completeness: How completely does it cover key points?
- safety: Is the content free from harmful material?

Return JSON: {{"groundedness": float, "coherence": float, "completeness": float, "safety": float}}"""

    def _parse_response(self, text: str) -> QualityScore:
        import json

        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return QualityScore(
                groundedness=float(data.get("groundedness", 0.5)),
                coherence=float(data.get("coherence", 0.5)),
                completeness=float(data.get("completeness", 0.5)),
                safety=float(data.get("safety", 1.0)),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Failed to parse LLM quality response: %s", e)
            return QualityScore(
                groundedness=0.5,
                coherence=0.5,
                completeness=0.5,
                safety=1.0,
            )


def detect_hallucination(
    content: str, sources: list[dict[str, Any]],
) -> list[str]:
    """Detect potential hallucinations by checking claims against sources.

    Simple heuristic: looks for factual claims that don't appear in sources.
    Returns list of suspicious claims.
    """
    if not sources:
        return []

    source_text = " ".join(
        f"{s.get('title', '')} {s.get('snippet', s.get('content', ''))}"
        for s in sources
    ).lower()

    suspicious = []
    sentences = re.split(r'[.!?]+', content)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:
            continue
        words = set(re.findall(r'\b\w+\b', sent.lower()))
        if len(words) < 5:
            continue
        key_words = [w for w in words if len(w) > 4][:3]
        if key_words and not any(kw in source_text for kw in key_words):
            suspicious.append(sent[:100])

    return suspicious[:5]


def lightweight_quality_signals(
    content: str,
    sources: list[dict[str, Any]] | None = None,
) -> QualityScore:
    """Fast heuristic quality assessment without LLM calls.

    Uses simple metrics:
    - groundedness: based on source attribution and citation markers
    - coherence: based on sentence structure and transitions
    - completeness: based on content length and structure
    - safety: basic keyword filtering
    """
    groundedness = _assess_groundedness(content, sources)
    coherence = _assess_coherence(content)
    completeness = _assess_completeness(content)
    safety = _assess_safety(content)

    return QualityScore(
        groundedness=groundedness,
        coherence=coherence,
        completeness=completeness,
        safety=safety,
    )


def _assess_groundedness(
    content: str, sources: list[dict[str, Any]] | None,
) -> float:
    """Assess how well content is grounded in sources."""
    if not sources:
        return 0.5

    source_titles = [s.get("title", "").lower() for s in sources if s.get("title")]
    if not source_titles:
        return 0.5

    content_lower = content.lower()
    matches = sum(1 for title in source_titles if title in content_lower)
    return min(1.0, matches / max(len(sources), 1) + 0.3)


def _assess_coherence(content: str) -> float:
    """Assess coherence based on text structure."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', content) if s.strip()]
    if len(sentences) < 3:
        return 0.5

    transition_words = [
        "however", "therefore", "furthermore", "moreover",
        "additionally", "consequently", "in addition", "for example",
        "specifically", "first", "second", "finally",
    ]
    content_lower = content.lower()
    transitions = sum(1 for tw in transition_words if tw in content_lower)
    sentence_score = min(1.0, len(sentences) / 10.0)
    transition_score = min(1.0, transitions / 3.0)
    base_score = transition_score * 0.4 + sentence_score * 0.6
    return max(0.5, base_score)


def _assess_completeness(content: str) -> float:
    """Assess completeness based on length and structure."""
    word_count = len(content.split())
    if word_count < 100:
        return 0.3
    elif word_count < 300:
        return 0.6
    elif word_count < 600:
        return 0.8
    return 1.0


def _assess_safety(content: str) -> float:
    """Basic safety check for harmful content."""
    harmful_patterns = [
        r'\b(kill|murder|suicide|bomb|terrorist)\b',
        r'\b(hate speech|racist|sexist)\b',
    ]
    content_lower = content.lower()
    for pattern in harmful_patterns:
        if re.search(pattern, content_lower):
            return 0.2
    return 1.0
