import logging
import random
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from adapters.base import BaseSourceAdapter, RawItem, register_adapter
from adapters.session import get_crawl_session
from schemas.source import WebConfig
from utils.url import UnsafeURLError, validate_url_safe

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 200

# User-Agent strings - intentionally long for authenticity
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
        self._session = get_crawl_session()
        ua = self.adapter_config.user_agent
        if ua == "AINwsBot/1.0":
            ua = USER_AGENTS[secrets.randbelow(len(USER_AGENTS))]
        self._headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def close(self):
        pass

    def fetch(self) -> list[Any]:
        cfg = self.adapter_config
        try:
            validate_url_safe(cfg.listing_url)
        except UnsafeURLError as e:
            logger.error("[%s] Unsafe listing URL: %s", self.source_id, e)
            return []
        article_urls = self._scrape_listing(cfg.listing_url)
        logger.info("[%s] Found %s article links", self.source_id, len(article_urls))

        articles = []
        for url in article_urls:
            try:
                soup = self._polite_get(url)
                if soup:
                    articles.append((soup, url))
            except UnsafeURLError as e:
                logger.warning("[%s] Blocked unsafe URL %s: %s", self.source_id, url, e)
            except (ValueError, KeyError, AttributeError) as e: 
                logger.warning("[%s] Failed to scrape %s: %s", self.source_id, url, e)
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
            dt_str = self._attr(
                soup, acfg.date_selector, acfg.date_attribute or "datetime"
            )
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
        if not body or len(body) < MIN_CONTENT_LENGTH:
            try:
                import trafilatura

                html_str = str(soup)
                extracted = trafilatura.extract(html_str)
                if extracted and len(extracted) >= MIN_CONTENT_LENGTH:
                    body = extracted
            except ImportError:
                logger.warning("trafilatura not installed, content extraction unavailable for %s", url)
            except (ValueError, AttributeError) as e:
                logger.warning("Content extraction failed for %s: %s", url, e)

        ext_id = self._hash_ext_id(url, title)

        return RawItem(
            source_id=self.source_id,
            external_id=ext_id,
            title=title,
            url=url,
            author=author,
            published_at=published,
            text_content=self._truncate(body),
            raw_score=0.0,
            raw_metadata={"source_url": url},
        )

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

        urls: list[str] = []
        for card in soup.select(card_sel):
            if len(urls) >= cfg.max_items:
                break
            link_el = card.select_one(link_sel)
            if not link_el:
                continue
            href = link_el.get(link_attr)
            if href:
                urls.append(urljoin(cfg.base_url, href))

        # Pagination
        if pag.enabled and pag.next_link_selector and depth < pag.max_pages and len(urls) < cfg.max_items:
            next_el = soup.select_one(pag.next_link_selector)
            if next_el and next_el.get("href"):
                next_url = urljoin(cfg.base_url, next_el["href"])
                remaining = cfg.max_items - len(urls)
                next_urls = self._scrape_listing(next_url, depth + 1)
                urls.extend(next_urls[:remaining])

        return urls

    def _polite_get(self, url: str) -> Optional[BeautifulSoup]:
        cfg = self.adapter_config
        validate_url_safe(url)
        delay = random.uniform(cfg.request_delay_min, cfg.request_delay_max)
        time.sleep(delay)

        for attempt in range(cfg.max_retries):
            try:
                resp = self._session.get(url, headers=self._headers, timeout=15)
                if resp.status_code == 429:
                    # Note: Retry-After header is not currently respected
                    # Using fixed exponential backoff instead
                    wait = 2**attempt * 5 + random.uniform(0, 2)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "lxml")
            except requests.RequestException as e:
                logger.warning(
                    f"[{self.source_id}] Request failed ({attempt + 1}): {e}"
                )
                time.sleep(2**attempt)
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
        if el is None:
            return None
        val = el.get(attr)
        return str(val) if val is not None else None

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
        logger.warning("Failed to parse date: %s", dt_str)
        return None
