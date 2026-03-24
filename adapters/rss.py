import hashlib
from datetime import datetime, timezone
from time import mktime
from typing import Any, Optional

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from adapters.base import BaseSourceAdapter, RawItem, register_adapter
from schemas.source import RSSConfig
from services.url import normalize_url


@register_adapter("rss")
class RSSAdapter(BaseSourceAdapter):
    config_class = RSSConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def fetch(self) -> list[Any]:
        cfg = self.adapter_config
        headers = {
            "User-Agent": cfg.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        }
        resp = self._session.get(cfg.feed_url, headers=headers, timeout=cfg.request_timeout)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return feed.entries[:cfg.max_items]

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
                published = datetime(*ts[:6], tzinfo=timezone.utc)
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

        # External ID: hash the normalized URL
        ext_id = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16] if url else hashlib.sha256(title.encode()).hexdigest()[:16]

        # Author
        author = raw.get("author")
        if not author and raw.get("authors"):
            author = raw["authors"][0].get("name")

        return RawItem(
            source_id=self.source_id,
            external_id=ext_id,
            title=title,
            url=url,
            author=author,
            published_at=published,
            text_content=text[:3000] if text else None,
            raw_score=0.0,
            raw_metadata={
                "tags": [t["term"] for t in raw.get("tags", []) if t.get("term")],
            },
        )

    def _get_match_text(self, item: RawItem) -> str:
        parts = [item.title]
        if item.text_content:
            parts.append(item.text_content[:500])
        return " ".join(parts)
