import copy
import json
import logging
import time
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
from services.llm.errors import (
    ProviderResponseIncompleteError,
    RateLimitError as CustomRateLimitError,
    make_error_handler,
)
from services.llm.httpx_transport import create_httpx_client
from services.url import validate_url_safe

from schemas.llm import OpenAIConfig

logger = logging.getLogger(__name__)

_HTTPX_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)

# A local endpoint that needs no credential still has to satisfy the OpenAI
# SDK, which refuses to construct a client without an API key.
_LOCAL_PLACEHOLDER_KEY = "local-no-key-required"


def _make_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Pydantic schema for OpenAI-compatible strict JSON mode.

    OpenAI-compatible endpoints require every object to explicitly disallow
    additional properties and require every declared property. Optional Pydantic
    fields are represented as nullable unions, so making their keys required
    still permits the model to return ``null`` while keeping the schema strict.
    """
    strict_schema = copy.deepcopy(schema)

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(strict_schema)
    return strict_schema


def _message_text(message: Any) -> str:
    """Return the assistant text carried by a chat-completion message.

    A reasoning model spends part of its token budget thinking and can put
    the answer in ``reasoning_content`` while leaving ``content`` empty --
    especially when ``max_tokens`` is small. Treating that as an empty
    response makes the provider look broken, so fall back to the reasoning
    text when there is no ordinary content.
    """
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return content if isinstance(content, str) else ""


def _handle_openai_error(e: Exception) -> Exception:
    """Convert OpenAI SDK exceptions to our custom exceptions."""
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        RateLimitError,
    )

    if isinstance(e, RateLimitError):
        retry_after = None
        if hasattr(e, "headers") and e.headers:
            retry_after = e.headers.get("retry-after")
        elif hasattr(e, "response") and e.response and hasattr(e.response, "headers"):
            retry_after = e.response.headers.get("retry-after")
        return CustomRateLimitError(str(e), retry_after=retry_after)

    return make_error_handler(
        "OpenAI",
        rate_limit_exc=(RateLimitError,),
        auth_exc=AuthenticationError,
        timeout_exc=(APITimeoutError, APIConnectionError),
    )(e)


@register_provider("openai")
class OpenAIProvider(BaseLLMProvider):
    supports_reasoning_effort = True

    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OpenAIConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self.is_local = cfg.local
        self.reasoning_effort = cfg.reasoning_effort
        self.timeout_seconds = cfg.timeout_seconds
        self.retry_attempts = cfg.retry_attempts
        # A provider declared local may live on loopback or a private
        # network -- a local inference server, for instance. The SSRF guard
        # blocks those addresses by design, so it is relaxed for a provider
        # the operator has explicitly marked local. Everything else about
        # the URL is still checked.
        validate_url_safe(cfg.base_url, allow_private=cfg.local)
        self._client_kwargs = {
            # The OpenAI SDK refuses to start without a credential. A local
            # endpoint that needs none still gets a placeholder, which it
            # ignores; the point is that the request is made at all.
            "api_key": cfg.api_key or _LOCAL_PLACEHOLDER_KEY,
            "base_url": cfg.base_url,
            "timeout": self.timeout_seconds,
            # BaseLLMProvider owns transient retries. Disable the SDK's nested
            # retries so one request cannot silently multiply the stage budget.
            "max_retries": 0,
        }
        if cfg.headers:
            self._client_kwargs["default_headers"] = cfg.headers

    def _create_client(self):
        from openai import OpenAI

        http_client = create_httpx_client(
            limits=_HTTPX_LIMITS,
            timeout=self._client_kwargs.get("timeout", DEFAULT_LLM_TIMEOUT_SECONDS),
        )
        return OpenAI(**self._client_kwargs, http_client=http_client)

    @circuit_protected("llm_openai")
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
            resp = self.client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ImportError, httpx.HTTPError, ConnectionError,
                TimeoutError, ValueError, Exception) as e:
            raise _handle_openai_error(e) from e
        latency_ms = (time.monotonic() - t0) * 1000
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        input_toks = resp.usage.prompt_tokens if resp.usage else 0
        output_toks = resp.usage.completion_tokens if resp.usage else 0
        cached_toks = getattr(resp.usage, "cached_tokens", 0) or 0
        choice = resp.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            raise ProviderResponseIncompleteError(
                f"OpenAI-compatible provider {self.provider_id} reached the output limit",
                finish_reason=finish_reason,
            )
        content = _message_text(choice.message)
        if not content.strip():
            raise ProviderResponseIncompleteError(
                f"OpenAI-compatible provider {self.provider_id} returned empty content"
            )
        return LLMResponse(
            text=content,
            model=model,
            tokens_used=input_toks + output_toks,
            input_tokens=input_toks,
            output_tokens=output_toks,
            cached_tokens=cached_toks,
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

    @circuit_protected("llm_openai")
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
            response = self.client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if not (isinstance(text, str) and text.strip()):
                    text = getattr(delta, "reasoning_content", None)
                if isinstance(text, str) and text:
                    yield text
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ImportError, httpx.HTTPError, ConnectionError,
                TimeoutError, ValueError, Exception) as e:
            raise _handle_openai_error(e) from e

    @circuit_protected("llm_openai")
    def _do_chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        model = model or self.default_model
        msgs = self._build_messages(messages, system)
        strict_schema = _make_strict_json_schema(schema)
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                **({"reasoning_effort": reasoning_effort or self.reasoning_effort}
                   if reasoning_effort or self.reasoning_effort else {}),
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        "schema": strict_schema,
                    },
                },
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ImportError, httpx.HTTPError, ConnectionError,
                TimeoutError, ValueError, Exception) as e:
            raise _handle_openai_error(e) from e
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        choice = resp.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            raise ProviderResponseIncompleteError(
                f"OpenAI-compatible provider {self.provider_id} reached the structured output limit",
                finish_reason=finish_reason,
            )
        # Some OpenAI-compatible reasoning models put their completed JSON in
        # reasoning_content. Only accept that fallback after a normal stop;
        # length-terminated responses were rejected above, and the JSON is
        # still parsed and validated by chat_structured before use.
        content = _message_text(choice.message)
        if not content.strip():
            raise ProviderResponseIncompleteError(
                f"OpenAI-compatible provider {self.provider_id} returned empty "
                f"structured content (finish_reason={finish_reason or 'unknown'})",
                finish_reason=finish_reason,
            )
        return content

    def _chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        return cast(str, self._retry_with_backoff(
            self._do_chat_with_schema, model,
            messages=messages, response_model=response_model, system=system,
            temperature=temperature, max_tokens=max_tokens, schema=schema,
            reasoning_effort=reasoning_effort,
        ))

    @circuit_protected("llm_openai")
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
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ImportError, httpx.HTTPError, ConnectionError,
                TimeoutError, ValueError, Exception) as e:
            raise _handle_openai_error(e) from e
        if not resp.choices:
            raise RuntimeError(f"OpenAI returned empty choices for model {model}")
        return resp.choices[0].message, resp

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
        msg = response
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn_args = tc.function.arguments
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        fn_args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=fn_args,
                    ),
                )
        return _message_text(msg), tool_calls

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
            messages, tools, tool_choice, model, system, temperature, max_tokens, max_iterations,
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
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ImportError, httpx.HTTPError, ConnectionError,
                TimeoutError, ValueError, Exception) as e:  # noqa: BLE001 - APIError is base for all OpenAI SDK errors
            converted = _handle_openai_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}

