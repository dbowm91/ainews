from __future__ import annotations
import abc
import logging
from dataclasses import dataclass
from typing import Any, Optional, TypeVar, Type

from pydantic import BaseModel

from services.provider_base import BaseProvider, ProviderManager

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int = 0


class BaseLLMProvider(BaseProvider, abc.ABC):
    default_model: str = ""

    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)

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

    def _build_messages(
        self, messages: list[dict], system: Optional[str]
    ) -> list[dict]:
        """Build message list with optional system prompt prepended."""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend(messages)
        return result


# Shared provider manager for LLM providers
_manager = ProviderManager("llm")

# Backward-compatible module-level exports
_PROVIDER_REGISTRY = _manager._registry
register_provider = _manager.register


def get_provider_class(provider_type: str) -> type[BaseLLMProvider]:
    return _manager.get_class(provider_type)
