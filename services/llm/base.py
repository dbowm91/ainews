from __future__ import annotations
import abc
import logging
import threading
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
        self._client = None
        self._client_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._create_client()
        return self._client

    @abc.abstractmethod
    def _create_client(self) -> Any:
        """Create and return the provider-specific client instance."""
        ...

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
        from services.metrics import get_metrics

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
            get_metrics().counter_inc(
                "llm.validation_failures",
                labels={"model": model or self.default_model, "provider": self.provider_id},
            )
            if max_validation_retries > 0:
                get_metrics().counter_inc(
                    "llm.validation_retries",
                    labels={"model": model or self.default_model, "provider": self.provider_id},
                )
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
    def _call_api_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Any]:
        """Make the provider-specific API call for chat with tools.

        Returns:
            Tuple of (response, raw_response) where response is provider-specific
            and raw_response can be used for token counting.
        """
        ...

    @abc.abstractmethod
    def _extract_text_and_tool_calls(
        self, response: Any
    ) -> tuple[str, list[ToolCall]]:
        """Extract text content and tool calls from provider response.

        Args:
            response: Provider-specific response object from _call_api_with_tools

        Returns:
            Tuple of (text_content, list_of_tool_calls)
        """
        ...

    @abc.abstractmethod
    def _format_tool_result(
        self, tool_call: ToolCall, result_content: str
    ) -> dict:
        """Format a tool result as a message dict for the provider's message format.

        Args:
            tool_call: The ToolCall that was executed
            result_content: The string result of the function execution

        Returns:
            Provider-specific message dict representing the tool result
        """
        ...

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

        Uses provider-specific _call_api_with_tools, _extract_text_and_tool_calls,
        and _format_tool_result hooks.
        """
        model = model or self.default_model
        all_messages = self._build_messages(messages, system)

        tool_call_map: dict[str, tuple[str, Callable]] = {}
        for tool in tools:
            if hasattr(tool, "fn") and callable(tool.fn):
                tool_call_map[tool.name] = (tool.name, tool.fn)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            response, raw_response = self._call_api_with_tools(
                model=model,
                messages=all_messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            text_content, tool_calls_found = self._extract_text_and_tool_calls(response)

            if text_content:
                all_messages.append({"role": "assistant", "content": text_content})

            if not tool_calls_found:
                tokens_used = 0
                if hasattr(raw_response, "usage"):
                    tokens_used = (
                        getattr(raw_response.usage, "prompt_tokens", 0) or 0
                    ) + (getattr(raw_response.usage, "completion_tokens", 0) or 0)
                elif hasattr(raw_response, "prompt_eval_count"):
                    tokens_used = (
                        getattr(raw_response, "prompt_eval_count", 0) or 0
                    ) + (getattr(raw_response, "eval_count", 0) or 0)
                elif hasattr(raw_response, "usage_metadata"):
                    tokens_used = getattr(
                        raw_response.usage_metadata, "total_token_count", 0
                    ) or 0
                return ToolCallingResponse(
                    text=text_content,
                    model=model,
                    tool_calls=[],
                    tokens_used=tokens_used,
                )

            for tc in tool_calls_found:
                fn_name = tc.name
                fn_args = tc.arguments
                if isinstance(fn_args, str):
                    import json

                    fn_args = json.loads(fn_args)

                result_content = ""
                if fn_name in tool_call_map:
                    try:
                        _, fn = tool_call_map[fn_name]
                        result_content = str(fn(**fn_args))
                    except Exception as e:
                        result_content = f"Error: {e}"
                else:
                    result_content = f"Unknown tool: {fn_name}"

                all_messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": (
                                        tc.arguments
                                        if isinstance(tc.arguments, str)
                                        else tc.arguments
                                    ),
                                },
                            }
                        ],
                    }
                )

                tool_result_msg = self._format_tool_result(tc, result_content)
                all_messages.append(tool_result_msg)

        return ToolCallingResponse(
            text="",
            model=model,
            tool_calls=[],
            tokens_used=0,
        )

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
