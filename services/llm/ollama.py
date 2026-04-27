import json
import logging
import uuid
from typing import Any, Optional

from constants import DEFAULT_LLM_TIMEOUT_SECONDS
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


def _handle_ollama_error(e: Exception) -> Exception:
    """Convert ollama SDK exceptions to our custom exceptions."""
    from ollama import ResponseError

    return make_error_handler(
        "Ollama",
        rate_limit_exc=(ResponseError,),
        auth_exc=(),
        timeout_exc=(ConnectionError, TimeoutError),
    )(e)


@register_provider("ollama")
class OllamaProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OllamaConfig(**self.config)
        self.host = cfg.host
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens

    def _create_client(self):
        import ollama

        return ollama.Client(host=self.host, timeout=DEFAULT_LLM_TIMEOUT_SECONDS)

    def _extract_text(self, resp, return_thinking: bool = False) -> str:
        message = resp.get("message", {})
        content = message.get("content")
        if not content and return_thinking:
            thinking = message.get("thinking")
            if thinking:
                return thinking
        return content or ""

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
        msgs = self._build_messages(messages, system)
        try:
            resp = self.client.chat(
                model=model,
                messages=msgs,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
        except Exception as e:
            raise _handle_ollama_error(e)
        return LLMResponse(
            text=self._extract_text(resp),
            model=model,
            tokens_used=resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0),
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
            self._do_chat, model,
            messages=messages, system=system, temperature=temperature, max_tokens=max_tokens, **kwargs
        )

    def _do_chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
        model: Optional[str] = None,
    ) -> str:
        model = model or self.default_model
        msgs = self._build_messages(messages, system)
        try:
            resp = self.client.chat(
                model=model,
                messages=msgs,
                format=schema,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
        except Exception as e:
            raise _handle_ollama_error(e)
        return self._extract_text(resp)

    def _chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
        model: Optional[str] = None,
    ) -> str:
        return self._retry_with_backoff(
            self._do_chat_with_schema, model,
            messages=messages, response_model=response_model, system=system,
            temperature=temperature, max_tokens=max_tokens, schema=schema,
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
            "options": {"temperature": temperature, "num_predict": max_tokens},
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
        try:
            resp = self.client.chat(**call_kwargs)
        except Exception as e:
            raise _handle_ollama_error(e)
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
            self._do_call_api_with_tools, model,
            messages=messages, tools=tools, tool_choice=tool_choice,
            temperature=temperature, max_tokens=max_tokens,
        )

    def _extract_text_and_tool_calls(
        self, response: Any
    ) -> tuple[str, list[ToolCall]]:
        msg = response.get("message", {})
        content = msg.get("content", "")
        tool_calls_raw = msg.get("tool_calls") or []
        tool_calls = []
        for i, tc in enumerate(tool_calls_raw):
            fn = tc.get("function", {})
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}
            tool_calls.append(
                ToolCall(
                    id=f"ollama_{uuid.uuid4().hex[:12]}",
                    name=fn.get("name", ""),
                    arguments=fn_args,
                )
            )
        return content, tool_calls

    def _format_tool_result(self, tool_call: ToolCall, result_content: str) -> dict:
        return {
            "role": "tool",
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
            result = self.client.list()
            return {
                "provider": self.provider_id,
                "status": "ok",
                "model": self.default_model,
                "available_models": [m.model for m in result.models],
            }
        except Exception as e:
            converted = _handle_ollama_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}


# Re-export for backward compatibility
from schemas.llm import OllamaConfig  # noqa: E402
