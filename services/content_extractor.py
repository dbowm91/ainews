import concurrent.futures
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import trafilatura
import urllib3
from bs4 import BeautifulSoup
from readability import Document

logger = logging.getLogger(__name__)

CONTENT_EXTRACTOR_WORKERS = int(
    os.environ.get("CONTENT_EXTRACTOR_WORKERS", "8"),
)
_CONTENT_EXTRACTOR = ThreadPoolExecutor(
    max_workers=CONTENT_EXTRACTOR_WORKERS,
    thread_name_prefix="content_extract",
)


class ExtractionStatus(Enum):
    SUCCESS = "success"
    PAYWALL = "paywall"
    EMPTY = "empty"
    FETCH_ERROR = "fetch_error"


@dataclass
class ExtractionResult:
    url: str
    text: Optional[str]
    title: Optional[str]
    author: Optional[str]
    status: ExtractionStatus
    content_length: int = 0


PAYWALL_INDICATORS = [
    "subscribe to continue",
    "sign in to read",
    "this article is for subscribers",
    "metered paywall",
    "become a member",
    "unlock this article",
]


def _detect_paywall(html: str) -> bool:
    lower = html.lower()
    return any(ind in lower for ind in PAYWALL_INDICATORS)


def _fetch_with_timeout(url: str, timeout: int = 30) -> str | None:
    cfg = trafilatura.settings.use_config()
    cfg.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(timeout))
    try:
        return trafilatura.fetch_url(url, config=cfg)
    except (urllib3.exceptions.HTTPError, ValueError, Exception):
        logger.warning("Content fetch failed for %s", url)
        return None


def extract_article(url: str) -> ExtractionResult:
    from services.config_unified import MIN_CONTENT_LENGTH
    from services.url import UnsafeURLError, validate_url_safe

    try:
        validate_url_safe(url)
    except UnsafeURLError as e:
        logger.warning("Blocked unsafe URL %s: %s", url, e)
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    timeout = int(os.environ.get("CONTENT_EXTRACTOR_TIMEOUT", "30"))
    try:
        future = _CONTENT_EXTRACTOR.submit(_fetch_with_timeout, url, timeout)
        downloaded = future.result(timeout=timeout + 5)
    except (concurrent.futures.TimeoutError, TimeoutError):
        future.cancel()
        logger.warning("Content extraction timeout for %s", url)
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)
    except (ImportError, ConnectionError, TimeoutError,
            ValueError, AttributeError) as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    if not downloaded:
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    paywall = _detect_paywall(downloaded)

    result = trafilatura.bare_extraction(downloaded, url=url, with_metadata=True)
    if result and result.get("text") and len(result["text"]) >= MIN_CONTENT_LENGTH:
        return ExtractionResult(
            url=url,
            text=result["text"],
            title=result.get("title"),
            author=result.get("author"),
            status=(ExtractionStatus.PAYWALL if paywall else ExtractionStatus.SUCCESS),
            content_length=len(result["text"]),
        )

    try:
        doc = Document(downloaded)
        soup = BeautifulSoup(doc.summary(), "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if len(text) >= MIN_CONTENT_LENGTH:
            return ExtractionResult(
                url=url,
                text=text,
                title=doc.title(),
                author=None,
                status=ExtractionStatus.SUCCESS,
                content_length=len(text),
            )
    except (ImportError, ConnectionError, TimeoutError,
            ValueError, AttributeError) as e:
        logger.debug("Readability fallback failed for %s: %s", url, e)

    return ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)