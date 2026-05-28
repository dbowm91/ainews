# LLM Providers

The `services/llm/` package implements a multi-provider LLM architecture with automatic fallback, circuit breakers, and retry logic.

## Architecture

```
services/llm/
├── __init__.py       # Provider registry, get_provider_for_role(), fallback chain
├── base.py           # BaseLLMProvider, LLMResponse, ToolDefinition, ToolCall
├── openai.py         # OpenAI + OpenAI-compatible (DeepSeek, Groq, OpenRouter, xAI, etc.)
├── anthropic.py      # Anthropic Claude (native API)
├── gemini.py         # Google Gemini (native API)
├── ollama.py         # Local Ollama models
├── errors.py         # Error classification (AuthError, RateLimitError, etc.)
├── types.py          # LLM response types
└── json_utils.py     # JSON parsing for structured LLM output
```

## Provider Base Class

All providers implement `BaseLLMProvider` from `services/llm/base.py`:

```python
class BaseLLMProvider(ABC):
    default_model: str = ""

    @property
    def client(self) -> Any:
        """Lazy-loaded provider-specific client"""

    @abstractmethod
    def _create_client(self) -> Any: ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse: ...

    @abstractmethod
    def chat_streaming(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> Iterator[str]: ...

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_model: Type[BaseModel],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> BaseModel: ...

    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition],
        tool_choice: Optional[str] = None,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        max_iterations: int = 5,
    ) -> ToolCallingResponse: ...
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `chat()` | Plain text completions |
| `chat_structured()` | Pydantic-validated output via `response_model` |
| `chat_with_tools()` | Tool/function calling with iteration loop |
| `chat_streaming()` | Streaming text output |
| `health_check()` | Provider readiness probe |

## ToolDefinition Dataclass

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)
    # NOTE: No `cached` field exists on ToolDefinition
```

## Provider Implementations

### OpenAI-Compatible (`openai.py`)

Handles all providers using the OpenAI API format:
- OpenAI, DeepSeek, Groq, OpenRouter, xAI, TogetherAI, Fireworks, Cerebras, ZAI, MiniMax, OpenCode

```python
class OpenAIProvider(BaseLLMProvider):
    def _create_client(self) -> openai.OpenAI:
        return openai.OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)

    def chat(self, messages, model=None, system=None, ...):
        # Formats as OpenAI messages API call
        # Handles tool calling via OpenAI function calling format
```

### Anthropic (`anthropic.py`)

Native Anthropic API with Claude-specific message formatting:

```python
class AnthropicProvider(BaseLLMProvider):
    def _create_client(self) -> anthropic.Anthropic:
        return anthropic.Anthropic(api_key=self.config.api_key)

    def chat(self, messages, model=None, system=None, ...):
        # Formats as Anthropic Messages API
        # System message passed as separate `system` parameter
```

### Gemini (`gemini.py`)

Google Gemini with native API:

```python
class GeminiProvider(BaseLLMProvider):
    def _create_client(self) -> genai.Client:
        return genai.Client(api_key=self.config.api_key)
```

### Ollama (`ollama.py`)

Local Ollama models via OpenAI-compatible endpoint:

```python
class OllamaProvider(BaseLLMProvider):
    def _create_client(self) -> openai.OpenAI:
        return openai.OpenAI(base_url="http://localhost:11434/v1")
```

## Provider Registry

Providers are registered in `providers.yaml` and loaded via `services/llm/__init__.py`:

```python
# services/llm/__init__.py

def get_provider_for_role(role: str) -> Tuple[BaseLLMProvider, str, int, str]:
    """Get LLM provider configured for a specific pipeline role.
    Returns (provider, model, max_tokens, provider_id).
    Integrates circuit breaker - skips providers with open circuits."""

def get_provider_chain() -> Generator[Tuple[BaseLLMProvider, str, int, str], None, None]:
    """Yield (provider, model, max_tokens, provider_id) tuples for enabled providers.
    Dynamic - determined by providers.yaml config order, filtering out open circuits."""
```

### Provider Resolution

1. Read `pipeline.yaml` to get provider/model for the role
2. Look up provider config in `providers.yaml`
3. Create provider instance (lazy-loaded singleton)
4. Check circuit breaker state
5. Return provider or fall through to next in chain

## Fallback Chain

The fallback chain is **dynamic** — determined by enabled providers in `providers.yaml` configuration order:

```python
def get_provider_chain() -> list[str]:
    """Returns enabled providers in config order, filtering out those with open circuits."""
    chain = []
    for provider_id, config in providers_config.items():
        if config.enabled and not circuit_breaker.is_open(provider_id):
            chain.append(provider_id)
    return chain
```

If the primary provider fails, the system falls through to the next provider in the chain until one succeeds.

## Circuit Breaker

Each provider has a circuit breaker (`services/circuit_breaker.py`):

```
Closed (normal) ──5 failures──→ Open (blocking) ──60s timeout──→ Half-Open
     ↑                              │                              │
     └────────── success ───────────┘──── success ─────────────────┘
                                      └── failure ──→ Open
```

- **Closed**: Normal operation, failures counted
- **Open**: All requests rejected immediately (no LLM call made)
- **Half-Open**: After recovery timeout, one test request allowed
- **Metrics**: Emits circuit state changes to `services/metrics.py`

## Retry with Backoff

`BaseLLMProvider._retry_with_backoff()` retries on transient errors:

```python
def _retry_with_backoff(self, func, model, *args, **kwargs):
    """Retry with exponential backoff + jitter.
    Uses class constants: RETRY_MAX_ATTEMPTS=3, RETRY_BASE_DELAY=1.0, RETRY_MAX_DELAY=30.0
    Retries on: RateLimitError, ProviderTimeoutError, ProviderServerError
    Does NOT retry: AuthError, CircuitOpenError
    Uses server Retry-After header when available
    """
```

| Error Type | Retryable | Behavior |
|------------|-----------|----------|
| `RateLimitError` | Yes | Uses `retry_after` header or exponential backoff |
| `ProviderTimeoutError` | Yes | Exponential backoff |
| `ProviderServerError` | Yes | Exponential backoff |
| `AuthError` | No | Immediate failure (prevents infinite auth loops) |
| `CircuitOpenError` | No | Handled by fallback chain |

## Error Classification

`services/llm/errors.py` defines provider error types. `CircuitOpenError` is defined in `services/circuit_breaker.py` and imported into the LLM package:

```python
# services/llm/errors.py
class AuthError(Exception): ...           # Invalid API key/credentials
class RateLimitError(Exception): ...      # Rate limit exceeded (may have retry_after)
class ProviderServerError(Exception): ...  # 5xx server errors
class ProviderTimeoutError(Exception): ... # Request timeout

# services/circuit_breaker.py
class CircuitOpenError(Exception): ...    # Circuit breaker is open
```

## Structured Output

`chat_structured()` uses `_extract_json()` helper to handle markdown-wrapped JSON from Ollama:

```python
def chat_structured(self, messages, response_model, ...):
    """Returns Pydantic model from LLM output."""
    # 1. Include schema in prompt for models without native structured output
    # 2. Call _chat_with_schema() for provider-specific formatting
    # 3. Parse JSON response
    # 4. Validate against response_model
    # 5. Retry up to 2 times on validation failure
```

## Timeouts

All LLM providers use `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` from `constants.py`:

```python
# constants.py
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
```

Provider files should import and use this constant rather than hardcoding values.

## LLM Stage Metrics

`record_provider_success(provider_id, model, tokens_used, stage="")` accepts optional `stage` parameter:

```python
# When stage is provided, metrics include stage label
llm.calls.labels(provider=provider_id, model=model, stage=stage).inc()
llm.tokens.labels(provider=provider_id, model=model, stage=stage).inc(tokens_used)
```

All pipeline tasks pass `stage=` parameter (select, research, write, edit).

## Cost Tracking

`services/cost_tracker.py` tracks LLM usage per provider:

```python
def get_cost_summary() -> dict:
    """Return daily/monthly usage and cost per provider."""
```

## Key Files

| File | Purpose |
|------|---------|
| `services/llm/__init__.py` | Provider registry, `get_provider_for_role()`, `get_provider_chain()` |
| `services/llm/base.py` | `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`, `ToolCall` |
| `services/llm/openai.py` | OpenAI-compatible providers |
| `services/llm/anthropic.py` | Anthropic Claude |
| `services/llm/gemini.py` | Google Gemini |
| `services/llm/ollama.py` | Local Ollama |
| `services/llm/errors.py` | Error classification |
| `services/llm/json_utils.py` | JSON parsing for LLM responses |
| `providers.yaml` | Provider configuration (16 providers) |
| `pipeline.yaml` | Per-role provider/model assignments |
| `services/circuit_breaker.py` | Circuit breaker implementation |
| `services/cost_tracker.py` | Token usage tracking |
| `constants.py` | `DEFAULT_LLM_TIMEOUT_SECONDS` |
