import hashlib
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from adapters.base import BaseSourceAdapter, RawItem, register_adapter
from schemas.source import WebConfig
from services.url import normalize_url

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


@register_adapter("web")
class WebAdapter(BaseSourceAdapter):
    config_class = WebConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        ua = self.adapter_config.user_agent
        self._session.headers["User-Agent"] = ua if ua != "AINewsBot/1.0" else random.choice(USER_AGENTS)
        self._session.headers.update({
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def fetch(self) -> list[Any]:
        cfg = self.adapter_config
        article_urls = self._scrape_listing(cfg.listing_url)
        logger.info(f"[{self.source_id}] Found {len(article_urls)} article links")

        articles = []
        for url in article_urls:
            try:
                soup = self._polite_get(url)
                if soup:
                    articles.append((soup, url))
            except Exception as e:
                logger.warning(f"[{self.source_id}] Failed to scrape {url}: {e}")
        return articles

    def parse_item(self, raw: Any) -> Optional[RawItem]:
        soup, source_url = raw if isinstance(raw, tuple) else (raw, None)
        cfg = self.adapter_config
        acfg = cfg.article

        title = self._text(soup, acfg.title_selector)
        if not title:
            return None

        # URL: use source_url from listing, fallback to meta tags
        url = source_url
        if not url:
            canonical = soup.select_one("link[rel='canonical']")
            if canonical and canonical.get("href"):
                url = canonical["href"]
            og_url = soup.select_one("meta[property='og:url']")
            if not url and og_url:
                url = og_url.get("content")

        author = self._text(soup, acfg.author_selector)

        # Date extraction
        published = None
        if acfg.date_selector:
            dt_str = self._attr(soup, acfg.date_selector, acfg.date_attribute or "datetime")
            if not dt_str:
                dt_str = self._text(soup, acfg.date_selector)
            if dt_str:
                published = self._parse_date(dt_str)

        # Body text
        body = None
        if acfg.body_selector:
            body_el = soup.select_one(acfg.body_selector)
            if body_el:
                body = body_el.get_text(separator=" ", strip=True)
        # Fallback: use trafilatura on the full HTML
        from constants import MIN_CONTENT_LENGTH
        if not body or len(body) < MIN_CONTENT_LENGTH:
            try:
                import trafilatura
                html_str = str(soup)
                extracted = trafilatura.extract(html_str)
                if extracted and len(extracted) >= MIN_CONTENT_LENGTH:
                    body = extracted
            except Exception:
                pass

        ext_id = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16] if url else hashlib.sha256(title.encode()).hexdigest()[:16]

        return RawItem(
            source_id=self.source_id,
            external_id=ext_id,
            title=title,
            url=url,
            author=author,
            published_at=published,
            text_content=body[:3000] if body else None,
            raw_score=0.0,
            raw_metadata={"source_url": url},
        )

    def _get_match_text(self, item: RawItem) -> str:
        parts = [item.title]
        if item.text_content:
            parts.append(item.text_content[:500])
        return " ".join(parts)

    def _scrape_listing(self, url: str, depth: int = 0) -> list[str]:
        cfg = self.adapter_config
        pag = cfg.listing.pagination

        if pag.enabled and depth >= pag.max_pages:
            return []

        soup = self._polite_get(url)
        if not soup:
            return []

        card_sel = cfg.listing.card_selector
        link_sel = cfg.listing.link_selector
        link_attr = cfg.listing.link_attribute

        urls = []
        for card in soup.select(card_sel):
            link_el = card.select_one(link_sel)
            if not link_el:
                continue
            href = link_el.get(link_attr)
            if href:
                urls.append(urljoin(cfg.base_url, href))

        # Pagination
        if pag.enabled and pag.next_link_selector and depth < pag.max_pages:
            next_el = soup.select_one(pag.next_link_selector)
            if next_el and next_el.get("href"):
                next_url = urljoin(cfg.base_url, next_el["href"])
                urls.extend(self._scrape_listing(next_url, depth + 1))

        return urls

    def _polite_get(self, url: str) -> Optional[BeautifulSoup]:
        cfg = self.adapter_config
        delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
        time.sleep(delay)

        for attempt in range(cfg.max_retries):
            try:
                resp = self._session.get(url, timeout=15)
                if resp.status_code == 429:
                    wait = 2 ** attempt * 5 + random.uniform(0, 2)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "lxml")
            except requests.RequestException as e:
                logger.warning(f"[{self.source_id}] Request failed ({attempt+1}): {e}")
                time.sleep(2 ** attempt)
        return None

    @staticmethod
    def _text(soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        if not selector:
            return None
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None

    @staticmethod
    def _attr(soup: BeautifulSoup, selector: Optional[str], attr: str) -> Optional[str]:
        if not selector:
            return None
        el = soup.select_one(selector)
        return el.get(attr) if el else None

    @staticmethod
    def _parse_date(dt_str: str) -> Optional[datetime]:
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None
