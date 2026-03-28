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


def _get_nl_role_config(role: str):
    from schemas.pipeline import get_role_config

    return get_role_config(f"newsletter_pipeline.{role}")


def get_reader_system_prompt() -> str:
    from services.prompts import get_system_prompt

    rc = _get_nl_role_config("reader")
    return get_system_prompt("newsletter_reader", rc.system_prompt)


def get_newsletter_writer_system_prompt() -> str:
    from services.prompts import get_system_prompt

    rc = _get_nl_role_config("writer")
    return get_system_prompt("newsletter_writer", rc.system_prompt)


def get_newsletter_editor_system_prompt() -> str:
    from services.prompts import get_system_prompt

    rc = _get_nl_role_config("editor")
    return get_system_prompt("newsletter_editor", rc.system_prompt)


def build_reader_prompt(articles, topic_context: str) -> str:
    parts = [f"TOPIC CONTEXT: {topic_context}", "", "TODAY'S ARTICLES:"]
    for i, article in enumerate(articles, 1):
        headline, tldr = _parse_article(article)
        category = article.category or ""
        parts.append(f"{i}. [{category}] {headline}")
        if tldr:
            parts.append(f"   {tldr[:200]}")
    parts.append("")
    parts.append(
        "Analyze these articles. Identify themes, highlights, and connections."
    )
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


def generate_executive_summary(articles, topic_key="main") -> dict:
    """Generate executive summary using reader -> writer -> editor pipeline.
    
    Returns a dict with keys:
        summary: The executive summary text
        used_fallback: bool - Whether any stage fell back to defaults
        fallback_stages: list[str] - Which stages fell back
    """
    from schemas.pipeline import load_pipeline_config
    from services.limiter import get_limiter
    from services.llm import get_provider_for_role
    from services.metrics import get_metrics

    metrics = get_metrics()
    config = load_pipeline_config()
    nlp = config.newsletter_pipeline
    
    used_fallback = False
    fallback_stages = []

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
        reader_success = False
        try:
            provider, model, max_tokens = get_provider_for_role(
                "newsletter_pipeline.reader"
            )
            if limiter.acquire(
                nlp.reader.provider,
                model,
                nlp.reader.concurrency,
                nlp.reader.timeout_seconds,
            ):
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
                    reader_success = True
                finally:
                    limiter.release(nlp.reader.provider, model)
        except Exception as e:
            logger.error(f"Reader failed: {e}")
            metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "reader"})
            used_fallback = True
            fallback_stages.append("reader")
        
        if not reader_success:
            # Check if reader produced anything meaningful
            try:
                brief_data = json.loads(brief_json)
                if not brief_data.get("themes") and not brief_data.get("highlights"):
                    raise ValueError("Reader stage produced empty brief")
            except Exception as e:
                logger.error(f"Reader produced empty brief: {e}")
                metrics.counter_inc("newsletter.pipeline_empty_stage", labels={"stage": "reader"})
                used_fallback = True
                if "reader" not in fallback_stages:
                    fallback_stages.append("reader")

    # Writer
    if nlp.writer.enabled:
        writer_success = False
        try:
            provider, model, max_tokens = get_provider_for_role(
                "newsletter_pipeline.writer"
            )
            if limiter.acquire(
                nlp.writer.provider,
                model,
                nlp.writer.concurrency,
                nlp.writer.timeout_seconds,
            ):
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
                    writer_success = True
                finally:
                    limiter.release(nlp.writer.provider, model)
            else:
                # Limiter not available, use fallback
                metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "writer"})
                used_fallback = True
                fallback_stages.append("writer")
                return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages}
        except Exception as e:
            logger.error(f"Writer failed: {e}")
            metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "writer"})
            used_fallback = True
            fallback_stages.append("writer")
            return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages}
        
        if not writer_success:
            return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages}
    else:
        # Writer disabled
        metrics.counter_inc("newsletter.pipeline_disabled", labels={"stage": "writer"})
        return {"summary": "", "used_fallback": True, "fallback_stages": ["writer_disabled"]}

    # Editor
    if nlp.editor.enabled:
        try:
            provider, model, max_tokens = get_provider_for_role(
                "newsletter_pipeline.editor"
            )
            if limiter.acquire(
                nlp.editor.provider,
                model,
                nlp.editor.concurrency,
                nlp.editor.timeout_seconds,
            ):
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
                    return {
                        "summary": result.summary,
                        "used_fallback": used_fallback,
                        "fallback_stages": fallback_stages,
                    }
                finally:
                    limiter.release(nlp.editor.provider, model)
            else:
                # Limiter not available, use fallback
                metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "editor"})
                used_fallback = True
                fallback_stages.append("editor")
                try:
                    summary = json.loads(summary_json).get("summary", "")
                    return {
                        "summary": summary,
                        "used_fallback": True,
                        "fallback_stages": fallback_stages,
                    }
                except Exception:
                    return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages}
        except Exception as e:
            logger.error(f"Editor failed: {e}")
            metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": "editor"})
            used_fallback = True
            fallback_stages.append("editor")
            try:
                summary = json.loads(summary_json).get("summary", "")
                return {
                    "summary": summary,
                    "used_fallback": True,
                    "fallback_stages": fallback_stages,
                }
            except Exception:
                return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages}
    else:
        # Editor disabled
        metrics.counter_inc("newsletter.pipeline_disabled", labels={"stage": "editor"})
        try:
            summary = json.loads(summary_json).get("summary", "")
            return {
                "summary": summary,
                "used_fallback": used_fallback or True,
                "fallback_stages": fallback_stages + ["editor_disabled"],
            }
        except Exception:
            return {"summary": "", "used_fallback": True, "fallback_stages": fallback_stages + ["editor_disabled"]}
