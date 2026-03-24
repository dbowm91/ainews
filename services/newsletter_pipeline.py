import json
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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


DEFAULT_READER_SYSTEM_PROMPT = (
    "You are a news analyst reading today's top tech stories. "
    "Identify the major themes, highlights, and connections across articles.\n\n"
    "INSTRUCTIONS:\n"
    "1. Read each article's headline and summary carefully.\n"
    "2. Identify 2-4 major themes that span multiple articles.\n"
    "3. Call out 3-5 individual stories that stand out.\n"
    "4. Note any patterns or connections between articles.\n"
)

DEFAULT_NEWSLETTER_WRITER_SYSTEM_PROMPT = (
    "You are a newsletter writer. Write an executive summary for today's "
    "tech news in a Smart Brevity-inspired style.\n\n"
    "STYLE:\n"
    "1. Start with a short, punchy greeting — set the tone immediately.\n"
    "2. Weave highlights naturally into a tight narrative.\n"
    "3. Reference specific articles by headline where relevant.\n"
    "4. Keep it 3-4 paragraphs max. Every sentence must earn its place.\n"
    "5. End with a brief forward-looking teaser — what to watch next.\n"
    "6. Tone: smart, direct, slightly informal. Like a sharp colleague\n"
    "   catching you up over coffee.\n"
)

DEFAULT_NEWSLETTER_EDITOR_SYSTEM_PROMPT = (
    "You are an editor reviewing a newsletter executive summary.\n\n"
    "CHECKLIST:\n"
    "1. Tone — sharp and smart, not robotic or fluffy.\n"
    "2. Brevity — cut anything that doesn't inform. Tighten every sentence.\n"
    "3. Flow — smooth transitions between topics.\n"
    "4. Accuracy — verify article references are correct.\n"
    "5. Length — 3-4 paragraphs max.\n"
    "Return the corrected summary in the same JSON format."
)


def _get_nl_role_config(role: str):
    from schemas.pipeline import get_role_config
    return get_role_config(f"newsletter_pipeline.{role}")


def get_reader_system_prompt() -> str:
    rc = _get_nl_role_config("reader")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_READER_SYSTEM_PROMPT


def get_newsletter_writer_system_prompt() -> str:
    rc = _get_nl_role_config("writer")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_NEWSLETTER_WRITER_SYSTEM_PROMPT


def get_newsletter_editor_system_prompt() -> str:
    rc = _get_nl_role_config("editor")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_NEWSLETTER_EDITOR_SYSTEM_PROMPT


def build_reader_prompt(articles, topic_context: str) -> str:
    parts = [f"TOPIC CONTEXT: {topic_context}", "", "TODAY'S ARTICLES:"]
    for i, article in enumerate(articles, 1):
        headline, tldr = _parse_article(article)
        category = article.category or ""
        parts.append(f"{i}. [{category}] {headline}")
        if tldr:
            parts.append(f"   {tldr[:200]}")
    parts.append("")
    parts.append("Analyze these articles. Identify themes, highlights, and connections.")
    return "\n".join(parts)


def build_writer_prompt(brief_json: str, topic_context: str) -> str:
    return (
        f"TOPIC CONTEXT: {topic_context}\n\n"
        f"NEWS ANALYSIS:\n{brief_json}\n\n"
        f"Write an executive summary for today's newsletter. "
        f"Be welcoming and contextual. Reference specific articles by headline. "
        f"Keep it 3-4 paragraphs, sharp and direct."
    )


def build_editor_prompt(summary_json: str) -> str:
    return (
        f"DRAFT EXECUTIVE SUMMARY:\n{summary_json}\n\n"
        f"Review and improve this summary. "
        f"Ensure sharp tone, smooth flow, correct article references, and brevity. "
        f"Return the corrected version in the same format."
    )


def _parse_article(article):
    from services.utils import parse_article_headline
    return parse_article_headline(article, fallback_headline="Untitled")


def generate_executive_summary(articles, topic_key="main") -> str:
    """Generate executive summary using reader -> writer -> editor pipeline."""
    from schemas.pipeline import load_pipeline_config
    from services.limiter import get_limiter
    from services.llm import get_provider_for_role

    config = load_pipeline_config()
    nlp = config.newsletter_pipeline

    if topic_key == "main":
        topic_context = "ainews// — autonomous tech news condensation — AI, privacy, security, programming, hardware"
    else:
        from schemas.topic import load_topics
        topics = load_topics().topics
        topic_def = topics.get(topic_key)
        topic_name = topic_def.display_name if topic_def else topic_key
        topic_desc = topic_def.description if topic_def else ""
        topic_context = f"ainews// — {topic_name}: {topic_desc}"

    limiter = get_limiter()
    brief_json = json.dumps({"themes": [], "highlights": [], "connections": []})
    summary_json = json.dumps({"summary": ""})

    # Reader
    if nlp.reader.enabled:
        try:
            provider, model, max_tokens = get_provider_for_role("newsletter_pipeline.reader")
            if limiter.acquire(nlp.reader.provider, model, nlp.reader.concurrency, nlp.reader.timeout_seconds):
                try:
                    prompt = build_reader_prompt(articles, topic_context)
                    brief = provider.chat_structured(
                        messages=[{"role": "user", "content": prompt}],
                        response_model=NewsletterBrief,
                        model=model,
                        system=get_reader_system_prompt(),
                        temperature=nlp.reader.temperature,
                        max_tokens=max_tokens,
                    )
                    brief_json = brief.model_dump_json()
                finally:
                    limiter.release(nlp.reader.provider, model)
        except Exception as e:
            logger.error(f"Reader failed: {e}")

    # Writer
    if nlp.writer.enabled:
        try:
            provider, model, max_tokens = get_provider_for_role("newsletter_pipeline.writer")
            if limiter.acquire(nlp.writer.provider, model, nlp.writer.concurrency, nlp.writer.timeout_seconds):
                try:
                    prompt = build_writer_prompt(brief_json, topic_context)
                    result = provider.chat_structured(
                        messages=[{"role": "user", "content": prompt}],
                        response_model=ExecutiveSummary,
                        model=model,
                        system=get_newsletter_writer_system_prompt(),
                        temperature=nlp.writer.temperature,
                        max_tokens=max_tokens,
                    )
                    summary_json = result.model_dump_json()
                finally:
                    limiter.release(nlp.writer.provider, model)
            else:
                return ""
        except Exception as e:
            logger.error(f"Writer failed: {e}")
            return ""
    else:
        return ""

    # Editor
    if nlp.editor.enabled:
        try:
            provider, model, max_tokens = get_provider_for_role("newsletter_pipeline.editor")
            if limiter.acquire(nlp.editor.provider, model, nlp.editor.concurrency, nlp.editor.timeout_seconds):
                try:
                    prompt = build_editor_prompt(summary_json)
                    result = provider.chat_structured(
                        messages=[{"role": "user", "content": prompt}],
                        response_model=ExecutiveSummary,
                        model=model,
                        system=get_newsletter_editor_system_prompt(),
                        temperature=nlp.editor.temperature,
                        max_tokens=max_tokens,
                    )
                    return result.summary
                finally:
                    limiter.release(nlp.editor.provider, model)
            else:
                try:
                    return json.loads(summary_json).get("summary", "")
                except Exception:
                    return ""
        except Exception as e:
            logger.error(f"Editor failed: {e}")
            try:
                return json.loads(summary_json).get("summary", "")
            except Exception:
                return ""
    else:
        try:
            return json.loads(summary_json).get("summary", "")
        except Exception:
            return ""
