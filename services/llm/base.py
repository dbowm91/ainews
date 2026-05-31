from __future__ import annotations

import abc
import json
import logging
import random
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from constants import DEFAULT_LLM_TIMEOUT_SECONDS
from services.circuit_breaker import CircuitOpenError
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError, RateLimitError
from services.llm.json_utils import extract_json
from utils.text import esc_xml_text
from services.provider_base import BaseProvider, ProviderManager
from services.tracing import get_current_trace_id

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BatchError(Exception):
    def __init__(self, errors: list[Optional[Exception]], results: list):
        self.errors = errors
        self.results = results
        failed = sum(1 for e in errors if e is not None)
        super().__init__(f"{failed}/{len(errors)} calls failed")


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    id: str
    name: str
    content: str


@dataclass
class ToolCallingResponse:
    text: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0


class BaseLLMProvider(BaseProvider, abc.ABC):
    default_model: str = ""

    RETRY_BASE_DELAY = 1.0
    RETRY_MAX_DELAY = 30.0
    RETRY_MAX_ATTEMPTS = 3

    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)
        self._client = None
        self._client_lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._create_client()
        return self._client

    def _retry_with_backoff(
            self,
            func: Callable[..., T],
            model: str | None,
            *args: Any,
            **kwargs: Any,
        ) -> T:
        """Execute a function with exponential backoff retry on transient errors.

        Args:
            func: The function to call (e.g. self._do_chat)
            model: Model name for failure recording
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            RateLimitError: If rate limited after all retries
            ProviderTimeoutError: If timing out after all retries
            ProviderServerError: If server error after all retries
            AuthError: On first attempt (no retry)
            CircuitOpenError: On first attempt (no retry)
        """
        trace_id = get_current_trace_id()
        last_exc: Optional[Exception] = None
        for attempt in range(self.RETRY_MAX_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except (AuthError, CircuitOpenError):
                raise
            except (RateLimitError, ProviderTimeoutError, ProviderServerError) as e:
                last_exc = e
                if attempt == self.RETRY_MAX_ATTEMPTS - 1:
                    self._record_failure(model or self.default_model or "unknown")
                    break
                if isinstance(e, RateLimitError) and e.retry_after is not None:
                    delay = min(e.retry_after, self.RETRY_MAX_DELAY)
                else:
                    delay = min(
                        random.uniform(0, self.RETRY_BASE_DELAY * (2 ** attempt)),  # noqa: S311
                        self.RETRY_MAX_DELAY,
                    )
                logger.warning(
                    "TraceID=%s: %s attempt %d/%d failed: %s. Retrying in %.1fs.",
                    trace_id,
                    self.provider_id,
                    attempt + 1,
                    self.RETRY_MAX_ATTEMPTS,
                    e,
                    delay,
                )
                time.sleep(delay)
        raise last_exc

    def _record_success(
        self,
        model: str,
        tokens_used: int = 0,
        stage: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        latency_ms: float = 0.0,
        article_id: int | None = None,
    ) -> None:
        from services.llm import record_provider_success
        record_provider_success(
            self.provider_id,
            model,
            tokens_used,
            stage,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            article_id=article_id,
        )

    def _record_failure(self, model: str, stage: str = "", article_id: int | None = None) -> None:
        from services.llm import record_provider_failure
        record_provider_failure(self.provider_id, model, stage, article_id=article_id)

    @abc.abstractmethod
    def _create_client(self) -> Any:
        """Create and return the provider-specific client instance."""
        ...

    @abc.abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Basic chat completion, returns raw text."""
        ...

    @abc.abstractmethod
    def chat_streaming(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream chat completion, yielding text chunks as they arrive."""
        ...

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: Type[T],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        max_validation_retries: int = 2,
        stage: str = "",
    ) -> T:
        """Chat with structured output, returns validated Pydantic model.

        Calls the LLM with a JSON schema derived from ``response_model`` and
        validates the response against that Pydantic model. On validation
        failure the method retries once by appending an error-message to the
        conversation (if ``max_validation_retries > 0``).

        Args:
            messages: Conversation history (list of ``{"role": ..., "content": ...}`` dicts).
            response_model: Pydantic model class (``BaseModel`` subclass) that defines
                the expected output schema. A ``TypeVar`` bound to ``BaseModel`` so the
                return type matches the input model.
            model: Model name override; uses ``self.default_model`` when *None*.
            system: System prompt prepended to the conversation.
            temperature: Sampling temperature (default 0.0).
            max_tokens: Maximum tokens for the LLM response.
            max_validation_retries: How many times to retry after a Pydantic
                ``ValidationError`` / ``json.JSONDecodeError`` / ``ValueError`` /
                ``AttributeError`` / ``ImportError``. Each retry sends the
                validation error and expected schema back to the LLM as a new
                user message. Default ``2`` (first attempt + up to 2 retries).
                Set to ``0`` to disable retries (raise on first failure).
            stage: Tracing stage name used in metrics and logs (e.g. ``"select"``,
                ``"research"``, ``"write"``, ``"edit"``).

        Returns:
            A validated instance of ``response_model``.

        Raises:
            ValidationError: If the LLM response cannot be validated after all
                retries are exhausted.
            json.JSONDecodeError: If the response is not valid JSON after retries.
            ValueError: If JSON extraction fails for structural reasons.
            AttributeError: If the response lacks required attributes.
            ImportError: If a required dependency is missing for extraction.
        """
        from services.metrics import get_metrics

        trace_id = get_current_trace_id()
        schema = response_model.model_json_schema()
        logger.info(
            "TraceID=%s: LLM call to %s (model=%s, stage=%s) - structured output: %s",
            trace_id,
            self.provider_id,
            model or self.default_model,
            stage,
            response_model.__name__,
        )
        t0 = time.monotonic()
        resp = self._chat_with_schema(
            messages, response_model, system, temperature, max_tokens, schema, model,
        )
        latency_ms = (time.monotonic() - t0) * 1000
        try:
            resp = extract_json(resp)
            result = response_model.model_validate_json(resp)
            self._record_success(model or self.default_model, stage=stage, latency_ms=latency_ms)
            logger.info(
                "TraceID=%s: LLM call succeeded for %s (model=%s, stage=%s)",
                trace_id,
                response_model.__name__,
                model or self.default_model,
                stage,
            )
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except (ValidationError, json.JSONDecodeError, ImportError,
                ValueError, AttributeError) as e:
            logger.warning(
                "TraceID=%s: Validation failed for %s: %s. Raw response: %s",
                trace_id,
                response_model.__name__,
                e,
                resp[:500] if resp else "(empty)",
            )
            get_metrics().counter_inc(
                "llm.validation_failures",
                labels={"model": model or self.default_model, "provider": self.provider_id},
            )
            if max_validation_retries > 0:
                get_metrics().counter_inc(
                    "llm.validation_retries",
                    labels={"model": self.default_model, "provider": self.provider_id},
                )
                import json as json_mod
                schema_json = json_mod.dumps(schema, indent=2)
                retry_messages = list(messages)
                retry_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response failed validation: {e}.\n\n"
                            f"Expected JSON format (Pydantic schema):\n{schema_json}\n\n"
                            f"Please respond with valid JSON matching this schema exactly."
                        ),
                    },
                )
                resp = self._chat_with_schema(
                    retry_messages,
                    response_model,
                    system,
                    temperature,
                    max_tokens,
                    schema,
                    model,
                )
                resp = extract_json(resp)
                result = response_model.model_validate_json(resp)
                self._record_success(model or self.default_model, stage=stage, latency_ms=latency_ms)
                return result
            raise

    def chat_structured_batch(
        self,
        requests: list[dict],
        response_model: Type[T],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        max_validation_retries: int = 2,
        stage: str = "",
        max_workers: int = 4,
        timeout: float = DEFAULT_LLM_TIMEOUT_SECONDS,
    ) -> list[T]:
        """Batch chat with structured output using ThreadPoolExecutor.

        Args:
            requests: List of dicts with 'messages' key and optionally 'system'
            response_model: Pydantic model class for structured output
            model: Model name override
            system: Default system prompt
            temperature: Sampling temperature
            max_tokens: Max tokens per call
            max_validation_retries: Validation retries per call
            stage: Tracing stage name
            max_workers: ThreadPoolExecutor max workers (bounded pool)
            timeout: Per-call timeout in seconds

        Returns:
            List of validated Pydantic model instances
        """
        results: list[Optional[T]] = [None] * len(requests)
        errors: list[Optional[Exception]] = [None] * len(requests)

        def _call_one(index: int, req: dict) -> None:
            try:
                msgs = req.get("messages", [])
                sys_prompt = req.get("system") or system
                result = self.chat_structured(
                    messages=msgs,
                    response_model=response_model,
                    model=model,
                    system=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_validation_retries=max_validation_retries,
                    stage=stage,
                )
                results[index] = result
            except (ValidationError, json.JSONDecodeError, ImportError,
                    ValueError, AttributeError, RateLimitError,
                    ProviderTimeoutError, ProviderServerError) as e:
                errors[index] = e
            except (KeyboardInterrupt, SystemExit):
                raise

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = [
                executor.submit(_call_one, i, req)
                for i, req in enumerate(requests)
            ]
            for i, future in enumerate(futures):
                try:
                    future.result(timeout=timeout)
                except FutureTimeoutError:
                    errors[i] = TimeoutError(f"LLM call {i} timed out after {timeout}s")
                except (CancelledError, RuntimeError) as e:
                    if errors[i] is None:
                        errors[i] = e
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if any(e is not None for e in errors):
            raise BatchError(errors, results)
        return results

    @abc.abstractmethod
    def _chat_with_schema(
        self,
        messages: list[dict[str, str]],
        response_model: Type[T],
        model: Optional[str],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        schema: dict,
    ) -> str:
        """Provider-specific schema-guided chat, returns raw JSON string."""
        ...

    @abc.abstractmethod
    def _call_api_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Any]:
        """Make the provider-specific API call for chat with tools.

        Returns:
            Tuple of (response, raw_response) where response is provider-specific
            and raw_response can be used for token counting.
        """
        ...

    @abc.abstractmethod
    def _extract_text_and_tool_calls(
        self, response: Any,
    ) -> tuple[str, list[ToolCall]]:
        """Extract text content and tool calls from provider response.

        Args:
            response: Provider-specific response object from _call_api_with_tools

        Returns:
            Tuple of (text_content, list_of_tool_calls)
        """
        ...

    @abc.abstractmethod
    def _format_tool_result(
        self, tool_call: ToolCall, result_content: str,
    ) -> dict:
        """Format a tool result as a message dict for the provider's message format.

        Args:
            tool_call: The ToolCall that was executed
            result_content: The string result of the function execution

        Returns:
            Provider-specific message dict representing the tool result
        """
        ...

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
        """Chat with tool/function calling support.

        Uses provider-specific _call_api_with_tools, _extract_text_and_tool_calls,
        and _format_tool_result hooks.
        """
        model = model or self.default_model
        all_messages = self._build_messages(messages, system)

        tool_call_map: dict[str, tuple[str, Callable]] = {}
        for tool in tools:
            if hasattr(tool, "fn") and callable(tool.fn):
                tool_call_map[tool.name] = (tool.name, tool.fn)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            response, raw_response = self._call_api_with_tools(
                model=model,
                messages=all_messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            text_content, tool_calls_found = self._extract_text_and_tool_calls(response)

            if text_content:
                all_messages.append({"role": "assistant", "content": text_content})

            if not tool_calls_found:
                tokens_used = 0
                if hasattr(raw_response, "usage"):
                    tokens_used = (
                        getattr(raw_response.usage, "prompt_tokens", 0) or 0
                    ) + (getattr(raw_response.usage, "completion_tokens", 0) or 0)
                elif hasattr(raw_response, "prompt_eval_count"):
                    tokens_used = (
                        getattr(raw_response, "prompt_eval_count", 0) or 0
                    ) + (getattr(raw_response, "eval_count", 0) or 0)
                elif hasattr(raw_response, "usage_metadata"):
                    tokens_used = getattr(
                        raw_response.usage_metadata, "total_token_count", 0,
                    ) or 0
                return ToolCallingResponse(
                    text=text_content,
                    model=model,
                    tool_calls=[],
                    tokens_used=tokens_used,
                )

            for tc in tool_calls_found:
                fn_name = tc.name
                fn_args = tc.arguments
                if isinstance(fn_args, str):
                    import json

                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        fn_args = {}

                result_content = ""
                if fn_name in tool_call_map:
                    try:
                        _, fn = tool_call_map[fn_name]
                        result_content = esc_xml_text(str(fn(**fn_args)))
                    except (KeyboardInterrupt, SystemExit):
                        raise
                    except (KeyError, TypeError, ValueError,
                            AttributeError) as e:
                        result_content = esc_xml_text(f"Error: {e}")
                else:
                    result_content = esc_xml_text(f"Unknown tool: {fn_name}")

                all_messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": (
                                        tc.arguments
                                        if isinstance(tc.arguments, str)
                                        else tc.arguments
                                    ),
                                },
                            },
                        ],
                    },
                )

                tool_result_msg = self._format_tool_result(tc, result_content)
                all_messages.append(tool_result_msg)

        return ToolCallingResponse(
            text="",
            model=model,
            tool_calls=[],
            tokens_used=0,
        )

    def _build_messages(
        self, messages: list[dict], system: Optional[str],
    ) -> list[dict]:
        """Build message list with optional system prompt prepended."""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend(messages)
        return result


# Shared provider manager for LLM providers
_manager = ProviderManager("llm")

# Backward-compatible module-level exports
_PROVIDER_REGISTRY = _manager._registry
register_provider = _manager.register


def get_provider_class(provider_type: str) -> type[BaseLLMProvider]:
    return _manager.get_class(provider_type)