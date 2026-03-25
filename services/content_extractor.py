import trafilatura
from readability import Document
from bs4 import BeautifulSoup
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


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


def extract_article(url: str) -> ExtractionResult:
    from constants import MIN_CONTENT_LENGTH
    from services.url import validate_url_safe, UnsafeURLError

    try:
        validate_url_safe(url)
    except UnsafeURLError as e:
        logger.warning(f"Blocked unsafe URL {url}: {e}")
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    try:
        cfg = trafilatura.settings.use_config()
        cfg.set("DEFAULT", "DOWNLOAD_TIMEOUT", "30")
        downloaded = trafilatura.fetch_url(url, config=cfg)
    except Exception as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    if not downloaded:
        return ExtractionResult(url, None, None, None, ExtractionStatus.FETCH_ERROR)

    paywall = _detect_paywall(downloaded)

    # Primary: trafilatura
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

    # Fallback: readability
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
    except Exception as e:
        logger.debug(f"Readability fallback failed for {url}: {e}")

    return ExtractionResult(url, None, None, None, ExtractionStatus.EMPTY)
