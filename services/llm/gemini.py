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


def _handle_gemini_error(e: Exception) -> Exception:
    """Convert Google Gemini SDK exceptions to our custom exceptions."""
    from google.genai.errors import ClientError

    return make_error_handler(
        "Gemini",
        rate_limit_exc=(ClientError,),
        auth_exc=(),
        timeout_exc=(ConnectionError, TimeoutError),
    )(e)


@register_provider("gemini")
class GeminiProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = GeminiConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens

    def _create_client(self):
        from google import genai

        return genai.Client(
            api_key=self.config.get("api_key"),
            http_options={"timeout": 120},
        )

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
        contents, system_instruction = self._build_contents(messages, system)
        resp = self.client.models.generate_content(
            model=model,
            contents=contents,
            system_instruction=system_instruction,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        usage = resp.usage_metadata
        tokens_used = usage.total_token_count if usage else 0
        return LLMResponse(
            text=resp.text or "",
            model=model,
            tokens_used=tokens_used,
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
        contents, system_instruction = self._build_contents(messages, system)
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
        return resp.text or "{}"

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
        all_messages = list(messages)
        contents, system_instruction = self._build_contents(all_messages, None)
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
        resp = self.client.models.generate_content(**call_kwargs)
        if not resp.candidates:
            raise RuntimeError(f"Gemini returned no candidates for model {model}")
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
        candidate = response.candidates[0]
        content_parts = candidate.content.parts
        text_content = ""
        tool_calls = []
        for part in content_parts:
            if hasattr(part, "text") and part.text:
                text_content += part.text
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                fn_args = {}
                if hasattr(fc, "args") and fc.args:
                    fn_args = fc.args
                tool_calls.append(
                    ToolCall(
                        id=fc.id or "",
                        name=fc.name,
                        arguments=fn_args,
                    )
                )
        return text_content, tool_calls

    def _format_tool_result(self, tool_call: ToolCall, result_content: str) -> dict:
        return {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "response": {"result": result_content},
                    }
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
