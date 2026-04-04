import logging
import threading
from typing import Any, Callable, Optional

from schemas.common import resolve_env_vars
from services.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    ToolCallingResponse,
    ToolDefinition,
    register_provider,
)
from services.llm.errors import handle_provider_error

logger = logging.getLogger(__name__)


def _handle_anthropic_error(e: Exception) -> Exception:
    """Convert Anthropic SDK exceptions to our custom exceptions."""
    from anthropic import (
        RateLimitError,
        AuthenticationError,
        APITimeoutError,
        APIConnectionError,
    )

    return handle_provider_error(
        e,
        "Anthropic",
        rate_limit_exc=(RateLimitError,),
        auth_exc=AuthenticationError,
        timeout_exc=(APITimeoutError, APIConnectionError),
    )


@register_provider("anthropic")
class AnthropicProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = AnthropicConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client = None
        self._client_lock = threading.Lock()
        self._api_key = cfg.api_key

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from anthropic import Anthropic

                    self._client = Anthropic(api_key=self._api_key)
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        model = model or self.default_model
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            call_kwargs["system"] = system
        try:
            resp = self.client.messages.create(**call_kwargs)
        except Exception as e:
            raise _handle_anthropic_error(e)
        if not resp.content:
            raise RuntimeError(f"Anthropic returned empty content for model {model}")
        return LLMResponse(
            text=resp.content[0].text,
            model=model,
            tokens_used=(
                (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
                if resp.usage
                else 0
            ),
        )

    def _chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model,
        model: Optional[str],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
    ) -> str:
        model = model or self.default_model
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "betas": ["structured-outputs-2025-11-13"],
            "output_format": {"type": "json_schema", "schema": schema},
        }
        if system:
            call_kwargs["system"] = system
        try:
            resp = self.client.beta.messages.create(**call_kwargs)
        except Exception as e:
            raise _handle_anthropic_error(e)
        if not resp.content:
            raise RuntimeError(f"Anthropic returned empty content for model {model}")
        return resp.content[0].text

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
        model = model or self.default_model
        all_messages = list(messages)
        if system:
            system_instruction = system
        else:
            system_instruction = None

        tool_call_map: dict[str, tuple[str, Callable]] = {}
        for tool in tools:
            if hasattr(tool, "fn") and callable(tool.fn):
                tool_call_map[tool.name] = (tool.name, tool.fn)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            call_kwargs: dict[str, Any] = {
                "model": model,
                "messages": all_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                call_kwargs["tools"] = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.parameters,
                    }
                    for t in tools
                ]
            if system_instruction:
                call_kwargs["system"] = system_instruction

            try:
                resp = self.client.messages.create(**call_kwargs)
            except Exception as e:
                raise _handle_anthropic_error(e)

            if not resp.content:
                raise RuntimeError(
                    f"Anthropic returned empty content for model {model}"
                )

            text_content = ""
            tool_use_results = []
            for block in resp.content:
                if block.type == "text":
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_use_results.append(block)

            if not tool_use_results:
                return ToolCallingResponse(
                    text=text_content,
                    model=model,
                    tool_calls=[],
                    tokens_used=(
                        (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
                        if resp.usage
                        else 0
                    ),
                )

            for block in tool_use_results:
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                all_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": "",
                            }
                        ],
                    }
                )

                result_content = ""
                if tool_name in tool_call_map:
                    try:
                        _, fn = tool_call_map[tool_name]
                        result_content = str(fn(**tool_input))
                    except Exception as e:
                        result_content = f"Error: {e}"
                else:
                    result_content = f"Unknown tool: {tool_name}"

                all_messages[-1]["content"][0]["content"] = result_content

        return ToolCallingResponse(
            text="",
            model=model,
            tool_calls=[],
            tokens_used=0,
        )

    def health_check(self) -> dict[str, Any]:
        try:
            self.client.messages.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return {
                "provider": self.provider_id,
                "status": "ok",
                "model": self.default_model,
            }
        except Exception as e:
            converted = _handle_anthropic_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}


# Re-export for backward compatibility
from schemas.llm import AnthropicConfig  # noqa: E402
