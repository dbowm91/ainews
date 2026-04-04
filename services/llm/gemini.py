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


def _handle_gemini_error(e: Exception) -> Exception:
    """Convert Google Gemini SDK exceptions to our custom exceptions."""
    from google.genai.errors import ClientError
    from services.llm.errors import handle_provider_error

    return handle_provider_error(
        e,
        "Gemini",
        rate_limit_exc=(ClientError,),
        auth_exc=(),
        timeout_exc=(ConnectionError, TimeoutError),
    )


@register_provider("gemini")
class GeminiProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = GeminiConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client = None
        self._client_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from google import genai

                    self._client = genai.Client(
                        api_key=self.config.get("api_key"),
                        http_options={"timeout": 120},
                    )
        return self._client

    def _build_contents(
        self, messages: list[dict[str, str]], system: Optional[str]
    ) -> tuple[list[dict], Any]:
        """Build Gemini contents format with optional system instruction."""
        contents = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append(
                {
                    "role": role,
                    "parts": [{"text": msg["content"]}],
                }
            )
        system_instruction = None
        if system:
            system_instruction = {"parts": [{"text": system}]}
        return contents, system_instruction

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
        contents, system_instruction = self._build_contents(messages, system)
        try:
            resp = self.client.models.generate_content(
                model=model,
                contents=contents,
                system_instruction=system_instruction,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
        except Exception as e:
            raise _handle_gemini_error(e) from e
        usage = resp.usage_metadata
        tokens_used = usage.total_token_count if usage else 0
        return LLMResponse(
            text=resp.text or "",
            model=model,
            tokens_used=tokens_used,
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
        contents, system_instruction = self._build_contents(messages, system)
        try:
            resp = self.client.models.generate_content(
                model=model,
                contents=contents,
                system_instruction=system_instruction,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
        except Exception as e:
            raise _handle_gemini_error(e) from e
        return resp.text or "{}"

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
        contents, system_instruction = self._build_contents(all_messages, system)

        tool_call_map: dict[str, tuple[str, Callable]] = {}
        for tool in tools:
            if hasattr(tool, "fn") and callable(tool.fn):
                tool_call_map[tool.name] = (tool.name, tool.fn)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            call_kwargs: dict[str, Any] = {
                "model": model,
                "contents": contents,
                "generation_config": {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            }
            if system_instruction:
                call_kwargs["system_instruction"] = system_instruction
            if tools:
                call_kwargs["tools"] = [
                    {
                        "function_declarations": [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.parameters,
                            }
                            for tool in tools
                        ]
                    }
                ]

            try:
                resp = self.client.models.generate_content(**call_kwargs)
            except Exception as e:
                raise _handle_gemini_error(e) from e

            if not resp.candidates:
                raise RuntimeError(f"Gemini returned no candidates for model {model}")

            candidate = resp.candidates[0]
            content_parts = candidate.content.parts

            text_content = ""
            function_calls = []
            for part in content_parts:
                if hasattr(part, "text") and part.text:
                    text_content += part.text
                if hasattr(part, "function_call") and part.function_call:
                    function_calls.append(part.function_call)

            if not function_calls:
                usage = resp.usage_metadata
                tokens_used = usage.total_token_count if usage else 0
                return ToolCallingResponse(
                    text=text_content,
                    model=model,
                    tool_calls=[],
                    tokens_used=tokens_used,
                )

            for fc in function_calls:
                fn_name = fc.name
                fn_args = {}
                if hasattr(fc, "args") and fc.args:
                    fn_args = fc.args
                fc_id = fc.id or ""

                tool_call_msg = {
                    "role": "model",
                    "parts": [
                        {
                            "function_call": {
                                "id": fc_id,
                                "name": fn_name,
                                "args": fn_args,
                            }
                        }
                    ],
                }
                contents.append(tool_call_msg)

                result_content = ""
                if fn_name in tool_call_map:
                    try:
                        _, fn = tool_call_map[fn_name]
                        result_content = str(fn(**fn_args))
                    except Exception as e:
                        result_content = f"Error: {e}"
                else:
                    result_content = f"Unknown tool: {fn_name}"

                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "id": fc_id,
                                    "name": fn_name,
                                    "response": {"result": result_content},
                                }
                            }
                        ],
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
            result = self.client.models.list()
            return {
                "provider": self.provider_id,
                "status": "ok",
                "model": self.default_model,
                "available_models": [m.name for m in result.models[:10]],
            }
        except Exception as e:
            converted = _handle_gemini_error(e)
            return {"provider": self.provider_id, "status": f"error: {converted}"}


from schemas.llm import GeminiConfig  # noqa: E402
