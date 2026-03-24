from __future__ import annotations
import abc
import logging
from dataclasses import dataclass
from typing import Any, Optional, TypeVar, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int = 0


_PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {}


def register_provider(provider_type: str):
    def decorator(cls):
        _PROVIDER_REGISTRY[provider_type] = cls
        return cls
    return decorator


def get_provider_class(provider_type: str) -> type[BaseLLMProvider]:
    if provider_type not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise KeyError(f"No LLM provider for '{provider_type}'. Available: {available}")
    return _PROVIDER_REGISTRY[provider_type]


class BaseLLMProvider(abc.ABC):
    default_model: str = ""

    def __init__(self, provider_id: str, config: dict):
        self.provider_id = provider_id
        self.config = config

    @abc.abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Basic chat completion, returns raw text."""
        ...

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: Type[T],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        """Chat with structured output, returns validated Pydantic model."""
        schema = response_model.model_json_schema()
        resp = self._chat_with_schema(
            messages, response_model, model, system, temperature, max_tokens, schema
        )
        return response_model.model_validate_json(resp)

    @abc.abstractmethod
    def _chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model: Type[T],
        model: Optional[str],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
    ) -> str:
        """Provider-specific schema-guided chat, returns raw JSON string."""
        ...

    def health_check(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "status": "unknown"}
