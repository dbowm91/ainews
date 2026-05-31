# Services Module

The `services/` package contains business logic, LLM interactions, and third-party service wrappers. **Services should NOT import from adapters** (clean layering).

## Architecture

```
services/
├── provider_base.py         # BaseProvider, ProviderManager (provider registry)
├── llm/                     # LLM provider implementations
│   ├── base.py              # BaseLLMProvider, LLMResponse, ToolDefinition
│   ├── anthropic.py         # Anthropic Claude provider
│   ├── openai.py            # OpenAI-compatible provider
│   ├── gemini.py            # Google Gemini provider
│   ├── ollama.py            # Ollama local provider
│   ├── errors.py            # Error classification (AuthError, RateLimitError, etc.)
│   ├── types.py             # Type definitions
│   └── json_utils.py        # JSON extraction helpers
├── subagent/                # Tool-enabled LLM agents
├── search/                  # Search provider implementations
│   └── session.py           # Shared requests.Session with SSRF-safe redirect handler
├── article_parser.py        # Article content parsing
├── article_validation.py    # Article quality validation
├── article_fallback.py      # Fallback content extraction
├── researcher.py            # Article research logic
├── writer.py                # Article writing logic
├── editor.py                # Article editing logic
├── content_extractor.py    # trafilatura + readability extraction
├── crawling.py             # Crawling utilities
├── trend_detector.py        # Trend detection logic
├── embeddings.py            # Embedding generation
├── newsletter_pipeline.py   # Newsletter orchestration
├── pipeline_monitor.py      # Pipeline health monitoring
├── pipeline_degradation.py  # Graceful degradation logic
├── pipeline_failure.py      # Failure handling
├── pipeline_utils.py        # Pipeline utilities
├── circuit_breaker.py       # Circuit breaker for provider fallback
├── context_service.py       # Context management
├── related.py               # Related article finding
├── trend_memory.py          # Trend memory operations
├── email.py                 # SMTP email delivery
├── webhooks.py              # Webhook dispatch
├── cache.py                 # Redis caching (ResponseCache L1+L2)
├── limiter.py               # Redis-based rate limiting (ModelLimiter)
├── cost_tracker.py          # LLM cost tracking
└── ...                      # Additional modules (see `ls services/` for full list; includes health.py, totp.py, prompts.py, url.py, topic_gap.py, stage_cost.py, source_intelligence.py, quality_report.py, alerts.py, config_utils.py, config_unified.py, audit.py, subscribers.py, redis_utils.py, task_security.py, timeout.py, etc.)
```

## LLM Provider System

### Provider Base (`llm/base.py`)

Abstract base class defining the interface. Inherits from `BaseProvider` (`services/provider_base.py`) which provides `provider_id` and `config` fields:

```python
class BaseLLMProvider(BaseProvider, abc.ABC):
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
reader (extracts themes/highlights/connections via NewsletterBrief schema) → writer (generates ExecutiveSummary) → editor (reviews and improves with attribution/citation check)
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

Redis-based concurrency limiter using pub/sub. Provider/model-aware — each provider+model combination has independent concurrency slots:

```python
class ModelLimiter:
    def acquire(self, provider_id: str, model: str, max_concurrent: int, timeout: int = 300) -> bool:
        """Acquire a slot for the given provider/model. Blocks until available or timeout."""

    def release(self, provider_id: str, model: str, timeout: int = 300) -> None:
        """Release the slot for the given provider/model."""

    def get_active(self, provider_id: str, model: str) -> int | None:
        """Get count of active slots for the given provider/model."""

    def cleanup_stale_slots(self) -> None:
        """Remove slots with expired TTL."""

    def is_healthy(self) -> bool:
        """Check if Redis is available for slot management."""
```

**Important**: Always release slots in a `finally` block to avoid leaks. Use `provider_id or rc.provider` and `model or rc.model` as fallbacks when releasing on early return paths.

### Email (`email.py`)

`SMTPConnectionPool` class at `services/email.py:13` provides connection pooling:

```python
class SMTPConnectionPool:
    """Pool of reusable SMTP connections."""
    def __init__(self, pool_size: int = 5): ...
    def get_connection(self) -> smtplib.SMTP: ...
    def return_connection(self, server: smtplib.SMTP): ...
    def close_all(self): ...
    def _is_healthy(self, server) -> bool: ...
    def _compute_cfg_hash(self, cfg: dict) -> str: ...
```

The pool is thread-safe and detects config changes (host, port, user, password, from_addr, use_tls) to reset pool on change. Unhealthy connections are automatically replaced. A global `_smtp_pool` singleton is created on first use via `_get_smtp_pool()`.

Module-level functions for email sending:

```python
def send_newsletter_email(email: str, subject: str, html_content: str, unsubscribe_url: str) -> None:
    """Send newsletter with connection pooling"""

def send_verification_email(email: str, newsletter_type: str, verification_url: str, unsubscribe_url: str, site_name: str) -> None:
    """Send subscription verification email"""

def send_welcome_email(email: str, newsletter_type: str, unsubscribe_url: str, site_name: str) -> None:
    """Send welcome email"""
```

### Webhooks (`webhooks.py`)

Event notifications with security features:

- **HMAC-SHA256 signatures** with timestamp replay protection
- **Encrypted secrets** at rest
- **Retry logic** with exponential backoff
- **Event tracking** via `WebhookEvent` model

## Context & Trend Services

### Trend Memory (`trend_memory.py`)

Embedding-based semantic trend tracking. **Note**: This module uses module-level functions, not a class:

```python
def propose_trend_memory(article: Article, engagement_data: dict | None = None) -> SubagentResponse:
    """Post-finalization LLM extraction of high-signal entries"""

def get_memory_for_topics(topics, min_importance=1, max_age_days=None) -> list[TrendMemory]:
    """Retrieve valid memory entries filtered by topic, tier, and freshness"""

def consolidate_all_topics() -> dict[str, int]:
    """Run consolidation across all topics with high-importance entries"""

def purge_expired() -> int:
    """Delete all expired trend memory entries"""
```

### Related Articles (`related.py`)

Finds related articles by topics and content similarity.

## Content Extraction

### Content Extractor (`content_extractor.py`)

Primary: `trafilatura` for main content extraction
Fallback: `readability` for article parsing
If both fail: Returns `ExtractionStatus.EMPTY` (no content extracted)

## Search Providers

Located in `services/search/`:

```
services/search/
├── __init__.py           # Provider registry
├── base.py              # SearchResult dataclass, abstract base
├── duckduckgo.py        # DuckDuckGo provider (default/enabled)
├── google.py            # Google provider (disabled, requires API key)
├── searxng.py           # SearxNG provider (disabled, self-hosted)
├── hybrid.py            # Hybrid provider (enabled - FTS5 + vector similarity)
├── session.py           # Shared requests.Session with SSRF-safe redirect handler
└── sqlite_fts.py        # SQLite FTS provider (internal article search)
```

| Provider | File | Status |
|----------|------|--------|
| DuckDuckGo | `duckduckgo.py` | Default, enabled |
| Google | `google.py` | Disabled (requires API key) |
| SearxNG | `searxng.py` | Disabled (self-hosted) |
| Hybrid | `hybrid.py` | Enabled (FTS5 + vector similarity) |
| SQLite FTS | `sqlite_fts.py` | Internal article search |
| Session | `session.py` | Shared connection pool with SSRF-safe redirects |

**Note:** DeepSeek is not a search provider. DeepSeek is only referenced as a regex pattern (`r"\bdeepseek\b"`) in `services/trend_detector.py` for detecting AI topic trends.

## Known Layering Exceptions

The following imports represent intentional deviations from clean layering:

- `services/crawling.py` imports from `adapters.base` (TYPE_CHECKING only, for type hints)
- `services/subagent/tools.py` imports from `models` and `extensions`
- `schemas/common.py` imports from `services.config_cache`
- `tasks/crawl.py` imports from `adapters.base`

These are documented and accepted - do not "fix" them.
