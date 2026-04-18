import json
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


def _handle_openai_error(e: Exception) -> Exception:
    """Convert OpenAI SDK exceptions to our custom exceptions."""
    from openai import (
        RateLimitError,
        AuthenticationError,
        APITimeoutError,
        APIConnectionError,
    )

    return make_error_handler(
        "OpenAI",
        rate_limit_exc=(RateLimitError,),
        auth_exc=AuthenticationError,
        timeout_exc=(APITimeoutError, APIConnectionError),
    )(e)


@register_provider("openai")
class OpenAIProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OpenAIConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client_kwargs = {
            "api_key": cfg.api_key,
            "base_url": cfg.base_url,
            "timeout": 120.0,
        }

    def _create_client(self):
        from openai import OpenAI

        return OpenAI(**self._client_kwargs)

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
        msgs = self._build_messages(messages, system)
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            raise _handle_openai_error(e)
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            model=model,
            tokens_used=(
                (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)
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
        msgs = self._build_messages(messages, system)
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        "schema": schema,
                    },
                },
            )
        except Exception as e:
            raise _handle_openai_error(e)
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        return resp.choices[0].message.content or "{}"

    def _call_api_with_tools(
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
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            call_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        if tool_choice:
            call_kwargs["tool_choice"] = (
                {"type": "function", "function": {"name": tool_choice}}
                if tool_choice != "auto"
                else "auto"
            )
        try:
            resp = self.client.chat.completions.create(**call_kwargs)
        except Exception as e:
            raise _handle_openai_error(e)
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        return resp.choices[0].message, resp

    def _extract_text_and_tool_calls(
        self, response: Any
    ) -> tuple[str, list[ToolCall]]:
        msg = response
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn_args = tc.function.arguments
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args)
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=fn_args,
                    )
                )
        return msg.content or "", tool_calls

    def _format_tool_result(self, tool_call: ToolCall, result_content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result_content,
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
            models = self.client.models.list()
            return {
                "provider": self.provider_id,
                "status": "ok",
                "model": self.default_model,
                "available_models": [m.id for m in models.data[:10]],
            }
        except Exception as e:
            converted = _handle_openai_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}


# Re-export for backward compatibility
from schemas.llm import OpenAIConfig  # noqa: E402
