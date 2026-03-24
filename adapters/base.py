from __future__ import annotations
import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, ClassVar

from schemas.source import SourceConfig, TopicMatchConfig

logger = logging.getLogger(__name__)


@dataclass
class RawItem:
    source_id: str
    external_id: str
    title: str
    url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    text_content: Optional[str] = None
    raw_score: float = 0.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)


_ADAPTER_REGISTRY: dict[str, type[BaseSourceAdapter]] = {}


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
    def fetch(self) -> list[Any]:
        ...

    @abc.abstractmethod
    def parse_item(self, raw: Any) -> Optional[RawItem]:
        ...

    def fetch_and_parse(self) -> list[RawItem]:
        raw_items = self.fetch()
        parsed = []
        for raw in raw_items:
            try:
                item = self.parse_item(raw)
                if item is not None:
                    parsed.append(item)
            except Exception as e:
                logger.warning(f"[{self.source_id}] Parse error: {e}")
        logger.info(f"[{self.source_id}] Fetched {len(raw_items)}, parsed {len(parsed)}")
        return parsed

    def match_topics(self, item: RawItem) -> RawItem:
        from services.trend_detector import classify
        text = self._get_match_text(item)
        matched = classify(text)
        included = [t for t in matched if t in self.topic_config.include or t == "other"]
        item.topics = included or ["other"]
        return item

    def _get_match_text(self, item: RawItem) -> str:
        return item.title
