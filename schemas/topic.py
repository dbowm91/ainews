from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import BASE_DIR, cached_config_with_mtime, load_yaml_file


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
    raw = load_yaml_file(p)
    return TopicsConfig(**raw)


def load_topics(path: str | Path = BASE_DIR / "topics.yaml") -> TopicsConfig:
    return cached_config_with_mtime(
        key="topics",
        loader_fn=lambda: _load_topics_from_file(path),
        config_path=Path(path),
    )


def get_topic_keys(path: str | Path = BASE_DIR / "topics.yaml") -> list[str]:
    return list(load_topics(path).topics.keys())


def get_topic_colors(path: str | Path = BASE_DIR / "topics.yaml") -> dict[str, str]:
    return {k: v.color for k, v in load_topics(path).topics.items()}
