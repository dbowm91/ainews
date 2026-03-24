import logging
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from services.llm.base import BaseLLMProvider, LLMResponse, register_provider
from schemas.llm import OllamaConfig, _resolve_env_vars

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@register_provider("ollama")
class OllamaProvider(BaseLLMProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, _resolve_env_vars(config))
        cfg = OllamaConfig(**self.config)
        self.host = cfg.host
        self.default_model = cfg.model
        self.max_tokens = cfg.max_tokens
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host)
        return self._client

    def _extract_text(self, resp) -> str:
        content = resp["message"]["content"]
        if not content:
            thinking = resp.get("message", {}).get("thinking")
            if thinking:
                return thinking
        return content

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
        resp = self.client.chat(
            model=model,
            messages=msgs,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
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
        resp = self.client.chat(
            model=model,
            messages=msgs,
            format=schema,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return self._extract_text(resp)

    def _build_messages(
        self, messages: list[dict], system: Optional[str]
    ) -> list[dict]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend(messages)
        return result

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
            return {"provider": self.provider_id, "status": f"error: {e}"}
