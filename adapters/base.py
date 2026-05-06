from __future__ import annotations

import abc
import hashlib
import logging
from typing import Any, ClassVar, Optional

from schemas.item import RawItem
from schemas.source import SourceConfig
from utils.url import normalize_url

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 3000
MATCH_TEXT_PREVIEW_LENGTH = 500


_ADAPTER_REGISTRY: dict[str, type[BaseSourceAdapter]] = {}

SOURCE_ADAPTERS = _ADAPTER_REGISTRY


def register_adapter(source_type: str):
    def decorator(cls):
        _ADAPTER_REGISTRY[source_type] = cls
        return cls

    return decorator


def get_adapter_class(source_type: str) -> type[BaseSourceAdapter]:
    if source_type not in _ADAPTER_REGISTRY:
        available = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        raise KeyError(f"No adapter for '{source_type}'. Available: {available}")
    return _ADAPTER_REGISTRY[source_type]


class BaseSourceAdapter(abc.ABC):
    config_class: ClassVar = None

    def __init__(self, source_config: SourceConfig):
        self.source_config = source_config
        self.source_id = source_config.id
        self.topic_config = source_config.topics
        if self.config_class and source_config.config:
            self.adapter_config = self.config_class(**source_config.config)
        else:
            self.adapter_config = None

    @abc.abstractmethod
    def fetch(self) -> list[Any]: ...

    @abc.abstractmethod
    def parse_item(self, raw: Any) -> Optional[RawItem]: ...

    def fetch_and_parse(self) -> list[RawItem]:
        raw_items = self.fetch()
        parsed = []
        for raw in raw_items:
            try:
                item = self.parse_item(raw)
                if item is not None:
                    parsed.append(item)
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning("[%s] Parse error: %s", self.source_id, e)
        logger.info(
            f"[{self.source_id}] Fetched {len(raw_items)}, parsed {len(parsed)}"
        )
        return parsed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        """Release resources. Override in subclasses that hold sessions."""
        pass

    def match_topics(self, item: RawItem) -> RawItem:
        text = self._get_match_text(item)
        matched = _classify_topics(text)
        included = [
            t for t in matched if t in self.topic_config.include or t == "other"
        ]
        item.topics = included or ["other"]
        return item

    def _get_match_text(self, item: RawItem) -> str:
        """Build text for topic matching. Override for custom matching."""
        parts = [item.title]
        if item.text_content:
            parts.append(item.text_content[:MATCH_TEXT_PREVIEW_LENGTH])
        return " ".join(parts)

    @staticmethod
    def _hash_ext_id(url: str = None, title: str = None) -> str:
        """Generate a stable external ID from URL or title."""
        source = normalize_url(url) if url else (title or "")
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    @staticmethod
    def _truncate(text: Optional[str], limit: int = MAX_TEXT_LENGTH) -> Optional[str]:
        """Truncate text to limit, returning None for empty input."""
        return text[:limit] if text else None


def _classify_topics(title: str, text: str = "") -> list[str]:
    """Classify topics from title/text using regex patterns.

    This is a pure function with no external dependencies, defined here
    to avoid layering violations (adapters should not import from services).
    """
    import re

    _PATTERNS = {
        "ai": [
            r"\bai\b", r"\bartificial intelligence\b", r"\bmachine learning\b",
            r"\bllm\b", r"\bgpt\b", r"\bclaude\b", r"\bgemini\b", r"\bopenai\b",
            r"\bdeep learning\b", r"\bneural net", r"\btransformer", r"\blanguage model\b",
            r"\bdeepseek\b", r"\bllama\b", r"\bmistral\b", r"\bembedding\b", r"\bfine.?tun",
        ],
        "privacy": [
            r"\bprivacy\b", r"\bsurveillance\b", r"\bencrypt", r"\bgdpr\b",
            r"\btracking\b", r"\bdata breach\b", r"\btor\b", r"\bvpn\b",
        ],
        "security": [
            r"\bcve-\d", r"\bvulnerabilit", r"\bexploit\b", r"\bmalware\b",
            r"\bransomware\b", r"\bzero.?day\b", r"\bcybersec",
        ],
        "programming": [
            r"\brust\b", r"\bpython\b", r"\bgolang\b", r"\bjavascript\b",
            r"\btypescript\b", r"\bc\+\+\b", r"\bopen.?source\b", r"\bgithub\b",
        ],
        "hardware": [
            r"\bgpu\b", r"\bchip\b", r"\bsemiconductor\b", r"\bnvidia\b",
            r"\bamd\b", r"\bapple\b",
        ],
    }
    compiled = {k: [re.compile(p, re.I) for p in pats] for k, pats in _PATTERNS.items()}
    combined = f"{title} {text}".lower()
    matched = [
        topic for topic, pats in compiled.items()
        if any(p.search(combined) for p in pats)
    ]
    return matched or ["other"]
