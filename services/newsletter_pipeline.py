import json
import logging

import redis.exceptions

from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (
    ExecutiveSummary,
    NewsletterBrief,
)

logger = logging.getLogger(__name__)


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
    from utils.text import esc_xml_text
    from services.utils import parse_article_headline

    parts = [f"TOPIC CONTEXT: {topic_context}", "", "TODAY'S ARTICLES:"]
    for i, article in enumerate(articles, 1):
        headline, tldr = parse_article_headline(article, fallback_headline="Untitled")
        category = article.category or ""
        parts.append(f"{i}. [{esc_xml_text(category)}] {esc_xml_text(headline)}")
        if tldr:
            parts.append(f"   {esc_xml_text(tldr[:200])}")
    parts.append("")
    parts.append(
        "Analyze these articles. Identify themes, highlights, and connections.",
    )
    return "\n".join(parts)


def build_writer_prompt(brief_json: str, topic_context: str) -> str:
    from utils.text import esc_xml_text

    return (
        f"TOPIC CONTEXT: {topic_context}\n\n"
        f"NEWS ANALYSIS:\n{esc_xml_text(brief_json)}\n\n"
        f"Write an executive summary for today's newsletter. "
        f"Be welcoming and contextual. Reference specific articles by headline. "
        f"Keep it 3-4 paragraphs, sharp and direct."
    )


def build_editor_prompt(summary_json: str) -> str:
    from utils.text import esc_xml_text

    return (
        f"DRAFT EXECUTIVE SUMMARY:\n{esc_xml_text(summary_json)}\n\n"
        f"Review and improve this summary. "
        f"Ensure sharp tone, smooth flow, correct article references, and brevity. "
        f"Return the corrected version in the same format."
    )


def _run_pipeline_stage(
    role: str,
    stage_config,
    metrics,
    limiter,
    llm_call,
    fallback_stages: list,
):
    """Run a single pipeline stage with acquire/release/fallback pattern.

    Args:
        role: Stage name (reader/writer/editor) for logging and metrics.
        stage_config: The stage's config (nlp.reader/writer/editor).
        metrics: Metrics collector.
        limiter: ModelLimiter instance.
        llm_call: Callable(provider, model, max_tokens) that returns the LLM result.
        fallback_stages: List to append to on failure.

    Returns:
        (result, success) tuple. result is the LLM output or None on failure.
    """
    from services.llm import get_provider_for_role

    try:
        provider, model, max_tokens, provider_id = get_provider_for_role(
            f"newsletter_pipeline.{role}",
        )
        if limiter.acquire(
            provider_id,
            model,
            stage_config.concurrency,
            stage_config.timeout_seconds,
        ):
            try:
                result = llm_call(provider, model, max_tokens)
                return result, True
            finally:
                limiter.release(
                    provider_id, model, stage_config.timeout_seconds,
                )
        else:
            metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": role})
            fallback_stages.append(role)
            return None, False
    except (ImportError, KeyError, AttributeError, redis.exceptions.RedisError,
            AuthError, ProviderServerError, ProviderTimeoutError,
            ConnectionError, ValueError) as e:
        logger.error("%s failed: %s", role, e)
        metrics.counter_inc("newsletter.pipeline_fallback", labels={"stage": role})
        fallback_stages.append(role)
        return None, False


def _get_topic_context(topic_key):
    if topic_key == "main":
        return "ainews// — autonomous tech news condensation — AI, privacy, security, programming, hardware"
    from schemas.topic import load_topics
    topics = load_topics().topics
    topic_def = topics.get(topic_key)
    topic_name = topic_def.display_name if topic_def else topic_key
    topic_desc = topic_def.description if topic_def else ""
    return f"ainews// — {topic_name}: {topic_desc}"


def _handle_reader_fallback(brief_json, metrics, fallback_stages):
    try:
        brief_data = json.loads(brief_json)
        if not brief_data.get("themes") and not brief_data.get("highlights"):
            logger.error("Reader stage produced empty brief")
            metrics.counter_inc(
                "newsletter.pipeline_empty_stage", labels={"stage": "reader"},
            )
            if "reader" not in fallback_stages:
                fallback_stages.append("reader")
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse brief JSON for fallback check", exc_info=True,
        )
    return fallback_stages


def generate_executive_summary(articles, topic_key="main") -> dict:
    """Generate executive summary using reader -> writer -> editor pipeline.

    Returns a dict with keys:
        summary: The executive summary text
        used_fallback: bool - Whether any stage fell back to defaults
        fallback_stages: list[str] - Which stages fell back
    """
    from schemas.pipeline import load_pipeline_config
    from services.limiter import get_limiter
    from services.metrics import get_metrics

    metrics = get_metrics()
    config = load_pipeline_config()
    nlp = config.newsletter_pipeline

    used_fallback = False
    fallback_stages: list[str] = []

    topic_context = _get_topic_context(topic_key)

    limiter = get_limiter()
    brief_json = json.dumps({"themes": [], "highlights": [], "connections": []})
    summary_json = json.dumps({"summary": ""})

    # Reader
    if nlp.reader.enabled:

        def reader_llm_call(provider, model, max_tokens):
            prompt = build_reader_prompt(articles, topic_context)
            return provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=NewsletterBrief,
                model=model,
                system=get_reader_system_prompt(),
                temperature=nlp.reader.temperature,
                max_tokens=max_tokens,
            )

        brief, reader_success = _run_pipeline_stage(
            "reader", nlp.reader, metrics, limiter, reader_llm_call, fallback_stages,
        )
        if reader_success:
            brief_json = brief.model_dump_json()
        else:
            used_fallback = True
            fallback_stages = _handle_reader_fallback(brief_json, metrics, fallback_stages)

    # Writer
    if nlp.writer.enabled:

        def writer_llm_call(provider, model, max_tokens):
            prompt = build_writer_prompt(brief_json, topic_context)
            return provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=ExecutiveSummary,
                model=model,
                system=get_newsletter_writer_system_prompt(),
                temperature=nlp.writer.temperature,
                max_tokens=max_tokens,
            )

        result, writer_success = _run_pipeline_stage(
            "writer", nlp.writer, metrics, limiter, writer_llm_call, fallback_stages,
        )
        if writer_success:
            summary_json = result.model_dump_json()
        else:
            return {
                "summary": "",
                "used_fallback": True,
                "fallback_stages": fallback_stages,
            }
    else:
        metrics.counter_inc("newsletter.pipeline_disabled", labels={"stage": "writer"})
        return {
            "summary": "",
            "used_fallback": True,
            "fallback_stages": ["writer_disabled"],
        }

    # Editor
    if nlp.editor.enabled:

        def editor_llm_call(provider, model, max_tokens):
            prompt = build_editor_prompt(summary_json)
            return provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=ExecutiveSummary,
                model=model,
                system=get_newsletter_editor_system_prompt(),
                temperature=nlp.editor.temperature,
                max_tokens=max_tokens,
            )

        result, editor_success = _run_pipeline_stage(
            "editor", nlp.editor, metrics, limiter, editor_llm_call, fallback_stages,
        )
        if editor_success:
            return {
                "summary": result.summary,
                "used_fallback": used_fallback,
                "fallback_stages": fallback_stages,
            }
        else:
            used_fallback = True
            try:
                summary = json.loads(summary_json).get("summary", "")
                return {
                    "summary": summary,
                    "used_fallback": True,
                    "fallback_stages": fallback_stages,
                }
            except json.JSONDecodeError as e:
                logger.debug("Failed to parse summary JSON for fallback: %s", e)
                return {
                    "summary": "",
                    "used_fallback": True,
                    "fallback_stages": fallback_stages,
                }
    else:
        metrics.counter_inc("newsletter.pipeline_disabled", labels={"stage": "editor"})
        try:
            summary = json.loads(summary_json).get("summary", "")
            return {
                "summary": summary,
                "used_fallback": True,
                "fallback_stages": fallback_stages + ["editor_disabled"],
            }
        except json.JSONDecodeError as e:
            logger.debug("Failed to get editor result for fallback: %s", e)
            return {
                "summary": "",
                "used_fallback": True,
                "fallback_stages": fallback_stages + ["editor_disabled"],
            }
