from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

BASE_DIR = Path(__file__).parent.parent


class TopicDef(BaseModel):
    display_name: str
    description: str
    color: str = "blue"
    icon: Optional[str] = None


class TopicsConfig(BaseModel):
    topics: dict[str, TopicDef] = Field(default_factory=dict)


def _load_topics_from_file(path: str | Path) -> TopicsConfig:
    p = Path(path)
    if not p.exists():
        return TopicsConfig(topics={})
    raw = yaml.safe_load(p.read_text()) or {}
    return TopicsConfig(**raw)


def load_topics(path: str | Path = BASE_DIR / "topics.yaml") -> TopicsConfig:
    try:
        from services.config_cache import get_config_cache
        return get_config_cache().get(
            key="topics",
            loader_fn=lambda: _load_topics_from_file(path),
            ttl=300,
        )
    except Exception:
        return _load_topics_from_file(path)


def get_topic_keys(path: str | Path = BASE_DIR / "topics.yaml") -> list[str]:
    return list(load_topics(path).topics.keys())


def get_topic_colors(path: str | Path = BASE_DIR / "topics.yaml") -> dict[str, str]:
    return {k: v.color for k, v in load_topics(path).topics.items()}
