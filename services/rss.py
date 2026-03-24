import logging
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring, indent

logger = logging.getLogger(__name__)


def generate_rss_feed(
    articles: list,
    title: str,
    description: str,
    site_url: str = "",
) -> str:
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = site_url
    SubElement(channel, "description").text = description
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "lastBuildDate").text = _format_date(
        datetime.now(timezone.utc)
    )

    for article in articles:
        item = SubElement(channel, "item")

        headline, tldr = _parse_final_article(article)

        title_text = headline or article.original_title or "Untitled"
        SubElement(item, "title").text = title_text

        link = f"{site_url}/article/{article.id}"
        SubElement(item, "link").text = link
        SubElement(item, "guid").text = link

        SubElement(item, "description").text = tldr or ""

        if article.original_published_at:
            SubElement(item, "pubDate").text = _format_date(
                article.original_published_at
            )
        elif article.created_at:
            SubElement(item, "pubDate").text = _format_date(article.created_at)

        if article.category:
            SubElement(item, "category").text = article.category

        if article.original_author:
            SubElement(item, "author").text = article.original_author

    indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        rss, encoding="unicode"
    )


def generate_sitemap(articles: list, site_url: str = "") -> str:
    urlset = Element(
        "urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
    )

    # Homepage
    url_el = SubElement(urlset, "url")
    SubElement(url_el, "loc").text = site_url
    SubElement(url_el, "changefreq").text = "hourly"
    SubElement(url_el, "priority").text = "1.0"

    # Topic pages
    from schemas.topic import load_topics
    topics = load_topics().topics
    for topic_key in topics:
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = f"{site_url}/topic/{topic_key}"
        SubElement(url_el, "changefreq").text = "hourly"
        SubElement(url_el, "priority").text = "0.8"

    # Articles
    for article in articles:
        url_el = SubElement(urlset, "url")
        SubElement(url_el, "loc").text = f"{site_url}/article/{article.id}"
        if article.created_at:
            SubElement(url_el, "lastmod").text = article.created_at.strftime(
                "%Y-%m-%d"
            )
        SubElement(url_el, "changefreq").text = "weekly"
        SubElement(url_el, "priority").text = "0.6"

    indent(urlset, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        urlset, encoding="unicode"
    )


def _parse_final_article(article) -> tuple[str, str]:
    from services.utils import parse_article_headline
    return parse_article_headline(article, include_summary=True)


def _format_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S") + " GMT"
