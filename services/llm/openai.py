import logging
from typing import Any, Optional

from schemas.common import resolve_env_vars
from services.llm.base import BaseLLMProvider, LLMResponse, register_provider
from services.llm.errors import handle_provider_error

logger = logging.getLogger(__name__)


def _handle_openai_error(e: Exception) -> Exception:
    """Convert OpenAI SDK exceptions to our custom exceptions."""
    from openai import (
        RateLimitError,
        AuthenticationError,
        APITimeoutError,
        APIConnectionError,
    )

    return handle_provider_error(
        e,
        "OpenAI",
        rate_limit_exc=(RateLimitError,),
        auth_exc=AuthenticationError,
        timeout_exc=(APITimeoutError, APIConnectionError),
    )


@register_provider("openai")
class OpenAIProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, resolve_env_vars(config))
        cfg = OpenAIConfig(**self.config)
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client = None
        self._client_kwargs = {
            "api_key": cfg.api_key,
            "base_url": cfg.base_url,
        }

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(**self._client_kwargs)
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
