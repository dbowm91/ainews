from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from adapters.base import BaseSourceAdapter, RawItem, register_adapter
from schemas.source import RSSConfig
from utils.url import validate_url_safe

from .session import SSRFSafeSession


def _validate_feed(feed: Any) -> bool:
    """Check feed has required elements."""
    if not feed or not feed.get("entries"):
        return False
    return True


def _scrape_feed_fallback(url: str, session: requests.Session, timeout: int = 15) -> list[dict[str, Any]]:
    """Extract items from HTML page using BeautifulSoup when feed parsing fails."""
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    items = []
    for item in soup.select("item, entry, article"):
        title_el = item.select_one("title")
        link_el = item.select_one("link")
        if title_el and link_el:
            items.append({
                "title": title_el.get_text(strip=True),
                "link": link_el.get("href", link_el.get_text(strip=True)),
            })
    return items


@register_adapter("rss")
class RSSAdapter(BaseSourceAdapter):
    config_class = RSSConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = SSRFSafeSession()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def close(self):
        self._session.close()

    def fetch(self) -> list[Any]:
        cfg = self.adapter_config
        validate_url_safe(cfg.feed_url)
        headers = {
            "User-Agent": cfg.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        }
        resp = self._session.get(
            cfg.feed_url, headers=headers, timeout=cfg.request_timeout
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if not _validate_feed(feed):
            return _scrape_feed_fallback(cfg.feed_url, self._session, cfg.request_timeout)
        return feed.entries[: cfg.max_items]  # type: ignore[no-any-return]

    def parse_item(self, raw: Any) -> Optional[RawItem]:
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        url = raw.get("link", "")

        # Date
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            ts = getattr(raw, attr, None)
            if ts:
                published = datetime(*ts[:6], tzinfo=timezone.utc)  # type: ignore[misc]
                break

        # Content: prefer full content, fall back to summary
        content = ""
        if raw.get("content"):
            content = raw.content[0].get("value", "")
        elif raw.get("summary"):
            content = raw.summary

        text = ""
        if content:
            text = BeautifulSoup(content, "html.parser").get_text(
                separator=" ", strip=True
            )

        # Author
        author = raw.get("author")
        if not author and raw.get("authors"):
            author = raw["authors"][0].get("name")

        return RawItem(
            source_id=self.source_id,
            external_id=self._hash_ext_id(url, title),
            title=title,
            url=url,
            author=author,
            published_at=published,
            text_content=self._truncate(text),
            raw_score=0.0,
            raw_metadata={
                "tags": [t["term"] for t in raw.get("tags", []) if t.get("term")],
            },
        )
