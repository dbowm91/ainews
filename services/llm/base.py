from __future__ import annotations
import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar, Type

from pydantic import BaseModel

from services.provider_base import BaseProvider, ProviderManager

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int = 0


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    id: str
    name: str
    content: str


@dataclass
class ToolCallingResponse:
    text: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
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
        max_validation_retries: int = 1,
    ) -> T:
        """Chat with structured output, returns validated Pydantic model."""
        schema = response_model.model_json_schema()
        resp = self._chat_with_schema(
            messages, response_model, model, system, temperature, max_tokens, schema
        )
        try:
            return response_model.model_validate_json(resp)
        except Exception as e:
            logger.warning(
                "Validation failed for %s: %s. Raw response: %s",
                response_model.__name__,
                e,
                resp[:500] if resp else "(empty)",
            )
            if max_validation_retries > 0:
                retry_messages = list(messages)
                retry_messages.append(
                    {
                        "role": "user",
                        "content": f"Your previous response failed validation: {e}. Please correct and try again.",
                    }
                )
                resp = self._chat_with_schema(
                    retry_messages,
                    response_model,
                    model,
                    system,
                    temperature,
                    max_tokens,
                    schema,
                )
                return response_model.model_validate_json(resp)
            raise

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

    @abc.abstractmethod
    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        model: Optional[str],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        max_iterations: int = 5,
    ) -> ToolCallingResponse:
        """Chat with tool/function calling support.

        Provider handles the conversation loop (tool call -> execute -> continue)
        up to max_iterations.
        """
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
