import json
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

logger = logging.getLogger(__name__)


def _handle_ollama_error(e: Exception) -> Exception:
    """Convert ollama SDK exceptions to our custom exceptions."""
    from services.llm.errors import handle_provider_error
    from ollama import ResponseError

    return handle_provider_error(
        e,
        "Ollama",
        rate_limit_exc=(ResponseError,),
        auth_exc=(),
        timeout_exc=(ConnectionError, TimeoutError),
    )


@register_provider("ollama")
class OllamaProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OllamaConfig(**self.config)
        self.host = cfg.host
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client = None
        self._client_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    import ollama

                    self._client = ollama.Client(host=self.host, timeout=120)
        return self._client

    def _extract_text(self, resp) -> str:
        message = resp.get("message", {})
        content = message.get("content")
        if not content:
            thinking = message.get("thinking")
            if thinking:
                return thinking
        return content or ""

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
            resp = self.client.chat(
                model=model,
                messages=msgs,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
        except Exception as e:
            raise _handle_ollama_error(e) from e
        return LLMResponse(
            text=self._extract_text(resp),
            model=model,
            tokens_used=resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0),
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
            resp = self.client.chat(
                model=model,
                messages=msgs,
                format=schema,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
        except Exception as e:
            raise _handle_ollama_error(e) from e
        return self._extract_text(resp)

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
            all_messages.insert(0, {"role": "system", "content": system})

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
                raise _handle_ollama_error(e) from e

            msg = resp.get("message", {})
            content = msg.get("content", "")

            if content:
                all_messages.append({"role": "assistant", "content": content})

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return ToolCallingResponse(
                    text=content or "",
                    model=model,
                    tool_calls=[],
                    tokens_used=resp.get("prompt_eval_count", 0)
                    + resp.get("eval_count", 0),
                )

            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                fn_args = tc.get("function", {}).get("arguments", {})
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args)

                all_messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [tc],
                    }
                )

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
                        "role": "tool",
                        "content": result_content,
                    }
                )

        return ToolCallingResponse(
            text="",
            model=model,
            tool_calls=[],
            tokens_used=0,
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
