# Services Module

The `services/` package contains business logic, LLM interactions, and third-party service wrappers. **Services should NOT import from adapters** (clean layering).

## Architecture

```
services/
├── llm/                     # LLM provider implementations
│   ├── provider_base.py    # Abstract base class
│   ├── anthropic.py        # Anthropic Claude provider
│   ├── openai.py           # OpenAI-compatible provider
│   ├── gemini.py           # Google Gemini provider
│   ├── ollama.py           # Ollama local provider
├── subagent/               # Tool-enabled LLM agents
├── search/                 # Search provider implementations
├── article_parser.py       # Article content parsing
├── article_validation.py   # Article quality validation
├── article_fallback.py     # Fallback content extraction
├── researcher.py           # Article research logic
├── writer.py               # Article writing logic
├── editor.py               # Article editing logic
├── content_extractor.py   # trafilatura + readability extraction
├── crawling.py            # Crawling utilities
├── trend_detector.py       # Trend detection logic
├── embeddings.py           # Embedding generation
├── newsletter_pipeline.py  # Newsletter orchestration
├── pipeline_monitor.py     # Pipeline health monitoring
├── pipeline_degradation.py # Graceful degradation logic
├── pipeline_failure.py     # Failure handling
├── pipeline_utils.py       # Pipeline utilities
├── context_service.py      # Context management
├── related.py              # Related article finding
├── trend_memory.py         # Trend memory operations
├── email.py                # SMTP email delivery
├── webhooks.py             # Webhook dispatch
├── cache.py                # Redis caching
├── limiter.py              # Redis-based rate limiting
└── cost_tracker.py         # LLM cost tracking
```

## LLM Provider System

### Provider Base (`llm/base.py`)

Abstract base class defining the interface:

```python
class BaseLLMProvider(ABC):
    default_model: str = ""

    @property
    def client(self): ...  # Lazy-loaded provider-specific client

    @abc.abstractmethod
    def _create_client(self) -> Any: ...

    @abc.abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse: ...

    @abc.abstractmethod
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
        tool_choice: Optional[str],
        model: Optional[str],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        max_iterations: int = 5,
    ) -> ToolCallingResponse: ...

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
    ) -> str: ...

    @abc.abstractmethod
    def _call_api_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[ToolDefinition],
        tool_choice: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Any]: ...

    @abc.abstractmethod
    def _extract_text_and_tool_calls(
        self, response: Any,
    ) -> tuple[str, list[ToolCall]]: ...

    @abc.abstractmethod
    def _format_tool_result(
        self, tool_call: ToolCall, result_content: str,
    ) -> dict: ...
```

### Circuit Breaker Pattern

`circuit_breaker.py` implements circuit breaker for provider fallback:

```
Closed (正常) → Open (熔断) → Half-Open (半开)
     │              │              │
     └── 失败计数 ──→ │              │
                     └── 超时后 ──→ │
                                 └── 成功 → Closed
```

### Cost Tracking

`cost_tracker.py` tracks LLM usage per provider:

- Tokens used (prompt/completion)
- Cost per model
- Daily/monthly budgets

## Pipeline Services

### Newsletter Pipeline (`newsletter_pipeline.py`)

Orchestrates the 3-stage newsletter generation:

```
reader (extracts key points) → writer (generates summary) → editor (polishes)
```

### Article Processing

| Service | Stage | Responsibility |
|---------|-------|----------------|
| `researcher.py` | `research_article` | Builds research brief with web search + context |
| `writer.py` | `write_article` | Writes condensed article in Smart Brevity format |
| `editor.py` | `edit_article` | Edits + contextualization via subagent tools |

## Subagent System

See [subagent.md](subagent.md) for detailed documentation.

## Infrastructure Services

### Rate Limiter (`limiter.py`)

Redis-based concurrency limiter using pub/sub:

```python
class RateLimiter:
    def acquire(self, slots: int = 1, timeout: float = 30) -> bool:
        """Acquire rate limiter slots"""

    def release(self, slots: int = 1) -> None:
        """Release rate limiter slots"""

    def is_available(self, slots: int = 1) -> bool:
        """Check if slots are available"""
```

**Important**: Always release slots in a `finally` block to avoid leaks.

### Email (`email.py`)

SMTP pool for newsletter delivery:

```python
class EmailService:
    def send_newsletter(self, newsletter: Newsletter, subscribers: list[Subscriber]):
        """Send newsletter with connection pooling"""

    def send_verification(self, subscriber: Subscriber, token: str):
        """Send subscription verification email"""
```

### Webhooks (`webhooks.py`)

Event notifications with security features:

- **HMAC-SHA256 signatures** with timestamp replay protection
- **Encrypted secrets** at rest
- **Retry logic** with exponential backoff
- **Event tracking** via `WebhookEvent` model

## Context & Trend Services

### Trend Memory (`trend_memory.py`)

Embedding-based semantic trend tracking:

```python
class TrendMemoryService:
    def propose(self, article: Article) -> list[TrendMemory]:
        """Propose new trend entries from article"""

    def consolidate(self, timeframe_days: int = 7):
        """Consolidate similar trend entries"""

    def search(self, query: str, limit: int = 5) -> list[TrendMemory]:
        """Semantic search for trend entries"""
```

### Related Articles (`related.py`)

Finds related articles by topics and content similarity.

## Content Extraction

### Content Extractor (`content_extractor.py`)

Primary: `trafilatura` for main content extraction
Fallback: `readability` for article parsing
Final fallback: Raw HTML with boilerplate removal

## Search Providers

Located in `services/search/`:

| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `duckduckgo.py` | Default, enabled |
| Google | `google.py` | Disabled (requires API key) |
| SearxNG | `searxng.py` | Disabled (self-hosted) |
| Hybrid | `hybrid.py` | Enabled (FTS5 + vector similarity) |
| SQLite FTS | `sqlite_fts.py` | Internal article search |
