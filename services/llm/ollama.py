import json
import logging
import time
import uuid
from typing import Any, Iterator, Optional, cast

import httpx
from constants import DEFAULT_LLM_TIMEOUT_SECONDS
from schemas.common import resolve_env_vars
from services.circuit_breaker import circuit_protected
from services.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    ToolCall,
    ToolCallingResponse,
    ToolDefinition,
    register_provider,
)
from services.llm.errors import make_error_handler
from services.url import validate_url_safe

from schemas.llm import OllamaConfig

logger = logging.getLogger(__name__)

_HTTPX_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


def _handle_ollama_error(e: Exception) -> Exception:
    """Convert ollama SDK exceptions to our custom exceptions."""
    from ollama import ResponseError

    return make_error_handler(
        "Ollama",
        rate_limit_exc=(ResponseError,),
        auth_exc=type(None),
        timeout_exc=(ConnectionError, TimeoutError),
    )(e)


@register_provider("ollama")
class OllamaProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OllamaConfig(**self.config)
        self.host = cfg.host
        # Ollama normally runs on the operator's own machine. A provider
        # declared local may therefore live on loopback or a private
        # network, which the SSRF guard blocks by design.
        validate_url_safe(self.host, allow_private=cfg.local)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens

    def _create_client(self):
        import ollama

        http_client = httpx.Client(limits=_HTTPX_LIMITS, timeout=DEFAULT_LLM_TIMEOUT_SECONDS)
        return ollama.Client(host=self.host, timeout=DEFAULT_LLM_TIMEOUT_SECONDS, client=http_client)

    def _extract_text(self, resp, return_thinking: bool = False) -> str:
        message: dict[str, Any] = resp.get("message", {})
        content: str = message.get("content", "")
        if not content and return_thinking:
            thinking: str = message.get("thinking", "")
            if thinking:
                return thinking
        return content or ""

    @circuit_protected("llm_ollama")
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
        t0 = time.monotonic()
        try:
            resp = self.client.chat(
                model=model,
                messages=msgs,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except (httpx.HTTPError, ImportError, ConnectionError,
                TimeoutError, ValueError) as e:
            raise _handle_ollama_error(e) from e
        latency_ms = (time.monotonic() - t0) * 1000
        prompt_tokens = resp.get("prompt_eval_count", 0)
        eval_tokens = resp.get("eval_count", 0)
        return LLMResponse(
            text=self._extract_text(resp),
            model=model,
            tokens_used=prompt_tokens + eval_tokens,
            input_tokens=prompt_tokens,
            output_tokens=eval_tokens,
            cached_tokens=0,
            latency_ms=latency_ms,
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
        return cast(LLMResponse, self._retry_with_backoff(
            self._do_chat, model,
            messages=messages, system=system, temperature=temperature, max_tokens=max_tokens, **kwargs,
        ))

    @circuit_protected("llm_ollama")
    def chat_streaming(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> Iterator[str]:
        model = model or self.default_model
        msgs = self._build_messages(messages, system)
        try:
            stream = self.client.chat(
                model=model,
                messages=msgs,
                options={"temperature": temperature, "num_predict": max_tokens},
                stream=True,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
        except (KeyboardInterrupt, SystemExit):
            raise
        except (httpx.HTTPError, ImportError, ConnectionError,
                TimeoutError, ValueError) as e:
            raise _handle_ollama_error(e) from e

    @circuit_protected("llm_ollama")
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
        except (KeyboardInterrupt, SystemExit):
            raise
        except (httpx.HTTPError, ImportError, ConnectionError,
                TimeoutError, ValueError) as e:
            raise _handle_ollama_error(e) from e
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
        return cast(str, self._retry_with_backoff(
            self._do_chat_with_schema, model,
            messages=messages, response_model=response_model, system=system,
            temperature=temperature, max_tokens=max_tokens, schema=schema,
        ))

    @circuit_protected("llm_ollama")
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
        except (KeyboardInterrupt, SystemExit):
            raise
        except (httpx.HTTPError, ImportError, ConnectionError,
                TimeoutError, ValueError) as e:
            raise _handle_ollama_error(e) from e
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
        return cast(tuple[Any, Any], self._retry_with_backoff(
            self._do_call_api_with_tools, model,
            messages=messages, tools=tools, tool_choice=tool_choice,
            temperature=temperature, max_tokens=max_tokens,
        ))

    def _extract_text_and_tool_calls(
        self, response: Any,
    ) -> tuple[str, list[ToolCall]]:
        msg = response.get("message", {})
        content = msg.get("content", "")
        tool_calls_raw = msg.get("tool_calls") or []
        tool_calls = []
        for _i, tc in enumerate(tool_calls_raw):
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
                ),
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
            messages, tools, tool_choice, model, system, temperature, max_tokens, max_iterations,
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
        except (KeyboardInterrupt, SystemExit):
            raise
        except (httpx.HTTPError, ImportError, ConnectionError,
                TimeoutError, ValueError) as e:
            converted = _handle_ollama_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}

