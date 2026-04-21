import logging
from typing import Any, Optional

from schemas.common import resolve_env_vars
from services.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    ToolCall,
    ToolCallingResponse,
    ToolDefinition,
    register_provider,
)
from services.llm.errors import make_error_handler

logger = logging.getLogger(__name__)


def _handle_anthropic_error(e: Exception) -> Exception:
    """Convert Anthropic SDK exceptions to our custom exceptions."""
    from anthropic import (
        RateLimitError,
        AuthenticationError,
        APITimeoutError,
        APIConnectionError,
    )

    return make_error_handler(
        "Anthropic",
        rate_limit_exc=(RateLimitError,),
        auth_exc=AuthenticationError,
        timeout_exc=(APITimeoutError, APIConnectionError),
    )(e)


@register_provider("anthropic")
class AnthropicProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = AnthropicConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._api_key = cfg.api_key
        self._timeout = 120.0

    def _create_client(self):
        from anthropic import Anthropic

        return Anthropic(api_key=self._api_key, timeout=self._timeout)

    def _do_chat(
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
        resp = self.client.messages.create(**call_kwargs)
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

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        return self._retry_with_backoff(
            self._do_chat, messages, model, system, temperature, max_tokens, **kwargs
        )

    def _do_chat_with_schema(
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
            "output_format": {"type": "json_schema", "schema": schema},
        }
        if system:
            call_kwargs["system"] = system
        resp = self.client.beta.messages.create(**call_kwargs)
        if not resp.content:
            raise RuntimeError(f"Anthropic returned empty content for model {model}")
        return resp.content[0].text

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
        return self._retry_with_backoff(
            self._do_chat_with_schema,
            messages, response_model, model, system, temperature, max_tokens, schema,
        )

    def _do_call_api_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Any]:
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
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
        resp = self.client.messages.create(**call_kwargs)
        if not resp.content:
            raise RuntimeError(f"Anthropic returned empty content for model {model}")
        return resp, resp

    def _call_api_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Any]:
        return self._retry_with_backoff(
            self._do_call_api_with_tools,
            model, messages, tools, tool_choice, temperature, max_tokens,
        )

    def _extract_text_and_tool_calls(
        self, response: Any
    ) -> tuple[str, list[ToolCall]]:
        text_content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )
        return text_content, tool_calls

    def _format_tool_result(self, tool_call: ToolCall, result_content: str) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result_content,
                }
            ],
        }

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
        return super().chat_with_tools(
            messages, tools, tool_choice, model, system, temperature, max_tokens, max_iterations
        )

    def health_check(self) -> dict[str, Any]:
        try:
            self.client.messages.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
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
