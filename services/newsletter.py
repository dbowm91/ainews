import logging
from datetime import datetime, timedelta, timezone
from html import escape

import redis.exceptions
from pydantic import BaseModel, Field
from sqlalchemy.orm import joinedload

from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError

from services.utils import parse_article_headline

logger = logging.getLogger(__name__)


class SubjectLine(BaseModel):
    subject: str = Field(description="Catchy, engaging email subject line for a tech news newsletter")


def generate_newsletter_html(
    articles: list,
    title: str,
    site_url: str = "",
    date_str: str = "",
    executive_summary: str = "",
    unsubscribe_url: str = "",
) -> str:
    """Generate email-safe newsletter HTML from a list of articles."""
    from urllib.parse import quote

    summary_html = ""
    if executive_summary:
        paragraphs = executive_summary.split("\n\n")
        para_parts = []
        for p in paragraphs:
            p = p.strip()
            if p:
                para_parts.append(
                    f'<p style="color:#333;font-size:14px;line-height:1.7;margin:0 0 12px 0;">{escape(p)}</p>',
                )
        para_html = "".join(para_parts)
        if para_html:
            summary_html = f"""
        <tr>
          <td style="padding:8px 32px 24px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f7ff;border:1px solid #d0e3f7;border-radius:6px;">
              <tr><td style="padding:20px 24px;">
                {para_html}
              </td></tr>
            </table>
          </td>
        </tr>"""

    items_parts = []
    for i, article in enumerate(articles, 1):
        headline, tldr = parse_article_headline(article, fallback_headline="Untitled")
        trackable_link = f"{site_url}/track/newsletter-click/{article.id}"
        category = article.category or ""
        safe_headline = escape(headline)
        safe_category = escape(category)
        safe_tldr = escape(tldr)

        items_parts.append(f"""
        <tr>
          <td style="padding:16px 0;border-bottom:1px solid #eaeaea;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="40" style="font-family:monospace;font-size:18px;color:#888;font-weight:700;vertical-align:top;padding-right:12px;">{i}.</td>
                <td>
                  <a href="{quote(trackable_link, safe=":/.?=&#")}" style="color:#111;font-size:16px;font-weight:600;text-decoration:none;line-height:1.3;">{safe_headline}</a>
                  {'<br><span style="font-family:monospace;font-size:11px;color:#888;text-transform:uppercase;">' + safe_category + "</span>" if category else ""}
                  <p style="color:#555;font-size:14px;line-height:1.5;margin:6px 0 0 0;">{safe_tldr}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>""")
    items_html = "".join(items_parts)

    if unsubscribe_url:
        unsub = unsubscribe_url.replace("{site_url}", site_url)
        safe_unsub = escape(unsub, quote=True)
        unsub_link = f'<a href="{safe_unsub}" style="color:#888;text-decoration:none;">unsubscribe</a>'
    else:
        unsub_link = '<span style="color:#888;">unsubscribe link unavailable</span>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;">
        <tr>
          <td style="padding:24px 32px;background:#0d1117;color:#fff;">
            <span style="font-family:monospace;font-size:20px;font-weight:700;">ainews<span style="color:#58a6ff;">//</span></span>
            <span style="font-family:monospace;font-size:12px;color:#888;margin-left:8px;">{date_str}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 8px 32px;">
            <h1 style="font-size:20px;font-weight:700;color:#111;margin:0;">{escape(title)}</h1>
          </td>
        </tr>
        {summary_html}
        <tr>
          <td style="padding:8px 32px 24px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {items_html}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
            <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
              condensed by agents &middot;
              <a href="{site_url}" style="color:#58a6ff;text-decoration:none;">ainews//</a> &middot;
              {unsub_link}
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _generate_newsletter(
    title: str,
    articles_filter,
    site_url: str = "",
    max_articles: int = 10,
    hours: int = 24,
    executive_summary: str = "",
) -> tuple[str, str, int]:
    """Generate a newsletter with custom article filter.

    Args:
        title: Title for the newsletter (used in HTML)
        articles_filter: Callable that takes a SQLAlchemy query and returns filtered query
        site_url: Base URL for article links
        max_articles: Maximum number of articles to include
        hours: Lookback window in hours
        executive_summary: Optional executive summary text

    Returns:
        Tuple of (html, subject, article_count)
    """
    from constants import PipelineStatus
    from models import Article

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    base_query = Article.query.filter(
        Article.pipeline_status == PipelineStatus.DONE,
        Article.created_at >= cutoff,
    ).options(joinedload(Article.source), joinedload(Article.tags))
    query = articles_filter(base_query)
    articles = query.order_by(Article.impact_score.desc()).limit(max_articles).all()

    if not articles:
        logger.warning("%s newsletter has no articles, skipping generation", title)
        return "", "", 0

    date_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
    generated_subject = _generate_subject_line(articles)
    subject = f"ainews// — {escape(generated_subject)} — {date_str}"
    newsletter_html = generate_newsletter_html(
        articles,
        title,
        site_url,
        date_str,
        executive_summary=executive_summary,
    )
    return newsletter_html, subject, len(articles)


def _generate_subject_line(articles, topic_context: str = "") -> str:
    """Generate an engaging newsletter subject line using LLM.

    Args:
        articles: List of Article objects with headlines
        topic_context: Optional topic context string

    Returns:
        Subject line string, or fallback "Top Stories" on failure
    """
    from services.limiter import get_limiter
    from services.llm import get_provider_for_role
    from utils.text import esc_xml_text

    headlines = []
    for article in articles[:10]:
        headline, _ = parse_article_headline(article, fallback_headline="Untitled")
        category = article.category or ""
        headlines.append(f"- [{esc_xml_text(category)}] {esc_xml_text(headline)}")

    headlines_text = "\n".join(headlines)

    prompt = (
        f"TOPIC CONTEXT: {topic_context or 'ainews// — autonomous tech news condensation'}\n\n"
        f"HEADLINES:\n{headlines_text}\n\n"
        f"Generate a catchy, engaging email subject line (under 60 characters) "
        f"that makes readers want to open this newsletter. "
        f"Be specific and intriguing, not generic. Do not use 'Top Stories' or similar."
    )

    try:
        provider, model, max_tokens, provider_id = get_provider_for_role(
            "newsletter_pipeline.writer",
        )
        limiter = get_limiter()
        if limiter.acquire(provider_id, model, 1, 120):
            try:
                result = provider.chat_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=SubjectLine,
                    model=model,
                    system="You are an expert email marketing copywriter specializing in tech news.",
                    temperature=0.7,
                    max_tokens=max_tokens,
                )
                return result.subject
            finally:
                limiter.release(provider_id, model, 120)
    except (ImportError, redis.exceptions.RedisError,
            AuthError, ProviderServerError, ProviderTimeoutError,
            ConnectionError, ValueError) as e:
        logger.warning("LLM subject line generation failed: %s", e)

    return "Top Stories"


def generate_main_newsletter(
    site_url: str = "",
    max_articles: int = 10,
    hours: int = 24,
    executive_summary: str = "",
) -> tuple[str, str, int]:
    """Generate the main newsletter. Returns (html, subject, article_count)."""
    from models import Article

    def filter_main(query):
        return query.filter(Article.impact_score > 0)

    return _generate_newsletter(
        title="Top Stories",
        articles_filter=filter_main,
        site_url=site_url,
        max_articles=max_articles,
        hours=hours,
        executive_summary=executive_summary,
    )


def generate_topic_newsletter(
    topic_key: str,
    site_url: str = "",
    max_articles: int = 10,
    hours: int = 24,
    executive_summary: str = "",
) -> tuple[str, str, int]:
    """Generate a topic-specific newsletter. Returns (html, subject, article_count)."""
    from models import Article
    from schemas.topic import load_topics

    topics = load_topics().topics
    topic_def = topics.get(topic_key)
    topic_name = topic_def.display_name if topic_def else topic_key

    def filter_topic(query):
        return query.filter(Article.category == topic_key)

    return _generate_newsletter(
        title=topic_name,
        articles_filter=filter_topic,
        site_url=site_url,
        max_articles=max_articles,
        hours=hours,
        executive_summary=executive_summary,
    )


def generate_personalized_newsletter(
    subscriber_preferences: dict,
    site_url: str = "",
    max_articles: int = 10,
    hours: int = 24,
    executive_summary: str = "",
) -> tuple[str, str, int]:
    """Generate a personalized newsletter based on subscriber topic preferences.

    Args:
        subscriber_preferences: Dict with 'topics' key containing list of topic keys
        site_url: Base URL for article links
        max_articles: Maximum number of articles to include
        hours: Lookback window in hours
        executive_summary: Optional executive summary text

    Returns:
        Tuple of (html, subject, article_count)
    """
    from models import Article
    from schemas.topic import load_topics

    topics = load_topics().topics
    preferred_topics = subscriber_preferences.get("topics", [])

    if not preferred_topics:
        return generate_main_newsletter(
            site_url=site_url,
            max_articles=max_articles,
            hours=hours,
            executive_summary=executive_summary,
        )

    def filter_preferred(query):
        return query.filter(
            Article.impact_score > 0,
            Article.category.in_(preferred_topics),
        )

    topic_names = [
        topics.get(t).display_name if topics.get(t) else t for t in preferred_topics
    ]
    title = "Your Personalized: " + ", ".join(topic_names[:3])

    return _generate_newsletter(
        title=title,
        articles_filter=filter_preferred,
        site_url=site_url,
        max_articles=max_articles,
        hours=hours,
        executive_summary=executive_summary,
    )