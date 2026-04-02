import logging
from typing import Any, Optional

from schemas.common import resolve_env_vars
from services.llm.base import BaseLLMProvider, LLMResponse, register_provider

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

    @property
    def client(self):
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
        return LLMResponse(
            text=resp.text or "",
            model=model,
            tokens_used=0,
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
