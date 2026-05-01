# Plan 8: AI Agent Harness, Tool Systems, Memory & Pipeline Improvements

**Date:** 2026-05-01  
**Status:** Draft - Ready for Review  
**Priority:** High

---

## Executive Summary

Based on comprehensive deep dives across 7 system components, the ainews codebase has a **solid architectural foundation** with clean abstractions and good resilience patterns. This plan identifies **10 high-impact improvement opportunities** across:

- **AI Agent Harness** (`services/subagent.py`) - Thread safety, code duplication, chain limitations
- **Tool System** (`services/tool_selection.py`) - Unused selectors, missing middleware
- **Trend Memory** (`services/trend_memory.py`) - Keyword-only retrieval, no semantic understanding
- **Pipeline System** (`tasks/pipeline.py`) - Observability gaps, Redis dependency
- **LLM Provider Architecture** - Stable, well-tested, minor gaps
- **Context & Related Articles** - No semantic search, keyword-only matching
- **MCP/RAG Gap** - Missing modern retrieval patterns

**Expected Impact:**
- 30-50% improvement in related article relevance (via semantic search)
- Elimination of 150+ lines of duplicated retry code
- Better pipeline observability with end-to-end tracing
- Foundation for future MCP interoperability

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Assessment](#current-state-assessment)
   - [Architecture Overview](#architecture-overview)
   - [Strengths](#strengths)
   - [Gaps Identified](#gaps-identified)
3. [Detailed Improvement Plan](#detailed-improvement-plan)
   - [Priority 0 (Critical/High-Impact)](#priority-0-criticalhigh-impact---months-1-2)
      - [0.1 Add Vector Embeddings for Articles](#01-add-vector-embeddings-for-articles)
      - [0.2 Implement Hybrid Search (SQL + Vector)](#02-implement-hybrid-search-sql--vector)
      - [0.3 Fix Thread Cancellation in Subagent System](#03-fix-thread-cancellation-in-subagent-system)
   - [Priority 1 (Important/Medium-Impact)](#priority-1-importantmedium-impact---months-2-4)
      - [1.1 Integrate ToolSelector into Pipeline Config](#11-integrate-toolselector-into-pipeline-config)
      - [1.2 Add Semantic Retrieval to Trend Memory](#12-add-semantic-retrieval-to-trend-memory)
      - [1.3 Extract Common Retry Logic in Subagent System](#13-extract-common-retry-logic-in-subagent-system)
      - [1.4 Add Tool Execution Middleware](#14-add-tool-execution-middleware)
   - [Priority 2 (Nice-to-Have/Low-Impact)](#priority-2-nice-to-havelow-impact---months-4-6)
      - [2.1 Enhance Pipeline Observability with Trace IDs](#21-enhance-pipeline-observability-with-trace-ids)
      - [2.2 Add Memory Decay for High-Importance Entries](#22-add-memory-decay-for-high-importance-entries)
      - [2.3 MCP Server Wrapper (Optional Interoperability)](#23-mcp-server-wrapper-optional-interoperability)
4. [Implementation Roadmap](#implementation-roadmap)
5. [File Change Summary](#file-change-summary)
6. [Success Metrics](#success-metrics)
7. [Risks & Mitigations](#risks--mitigations)
8. [Next Steps](#next-steps)

---

## Current State Assessment

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Pipeline System                        │
│  Crawl → Select → Research → Write → Edit → Review       │
│  - Redis distributed locks (fail-closed)                  │
│  - Circuit breakers with provider fallback chain           │
│  - Graceful degradation at each stage                    │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              AI Agent Harness (Subagent)                   │
│  - run_subagent() - basic structured output               │
│  - run_subagent_with_tools() - tool calling (5 iterations)│
│  - run_subagent_chain() - multi-step (no tool support)    │
│  - 9 built-in tools (context, search, memory)            │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Knowledge Retrieval                         │
│  - Topic Notes (manual, exact match)                      │
│  - Trend Memory (LLM-judged, topic match, TTL expiry)   │
│  - Related Articles (tag overlap + keyword scoring)         │
│  - NO vector embeddings or semantic search                 │
└─────────────────────────────────────────────────────────────┘
```

### Strengths

| Area | Strength |
|------|----------|
| **Pipeline Resilience** | Circuit breakers with Redis distribution, provider fallback chain |
| **Graceful Degradation** | Each stage has degradation path, `degradation_count` tracking |
| **LLM Provider System** | Clean adapter pattern, 4 providers + 8+ OpenAI-compatible |
| **Trend Memory** | LLM-as-judge pattern, importance tiers, TTL expiration |
| **Tool Definitions** | Structured `ToolDefinition` dataclass, callable functions |
| **Security** | AST-based condition evaluation (no `eval()`), XML escaping |

### Gaps Identified

| Area | Gap | Impact |
|------|-----|--------|
| **Semantic Search** | No vector embeddings, all keyword-based | HIGH - Missed relationships |
| **Subagent Thread Safety** | `future.cancel()` doesn't stop LLM calls | HIGH - Resource leaks |
| **Tool Selectors** | `StageAwareToolSelector` implemented but NEVER USED | MEDIUM - Unused infrastructure |
| **Code Duplication** | 3 retry loops × 30 lines each in subagent.py | MEDIUM - Maintenance burden |
| **Chain Limitations** | `run_subagent_chain()` uses `chat()`, not `chat_with_tools()` | MEDIUM - Limits chain capabilities |
| **Pipeline Observability** | No end-to-end tracing, fragmented metrics | MEDIUM - Debugging difficulty |
| **Memory Retrieval** | Exact topic match only, no semantic understanding | MEDIUM - Limits memory utility |
| **MCP Interoperability** | No MCP server implementation | LOW - Nice-to-have for now |

---

## Detailed Improvement Plan

### Priority 0 (Critical/High-Impact) - Months 1-2

#### 0.1 Add Vector Embeddings for Articles

**Problem:** All article retrieval is keyword-based (FTS5, tag overlap, title keywords). Two articles about "quantum computing" with different tags won't be found as related.

**Solution:** Add vector embeddings using `sentence-transformers` for semantic search.

**Files to Modify:**
- `models.py` - Add embedding columns to Article model
- `migrations/versions/` - New migration for embedding columns
- `services/embeddings.py` - New file for embedding generation
- `services/related.py` - Add semantic search function

**Implementation:**

```python
# models.py addition
class Article(db.Model):
    # ... existing fields ...
    embedding = db.Column(db.LargeBinary)  # 768-dim float32 = 3072 bytes
    embedding_model = db.Column(db.String(50))  # Track model version
    embedding_updated_at = db.Column(db.DateTime)
```

```python
# services/embeddings.py (new file)
"""Lightweight embedding service using sentence-transformers."""
from __future__ import annotations

import logging
from numpy import asarray, float32, norm
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Model cache - lazy load
_model_cache: dict[str, any] = {}


def get_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    """Get or load embedding model (cached)."""
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", model_name)
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> bytes:
    """Generate embedding for text, return as bytes."""
    model = get_embedding_model(model_name)
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.astype(float32).tobytes()


def cosine_similarity(vec1_bytes: bytes, vec2_bytes: bytes) -> float:
    """Compute cosine similarity between two embedding byte strings."""
    v1 = asarray(vec1_bytes, dtype=float32)
    v2 = asarray(vec2_bytes, dtype=float32)
    dot = v1 @ v2
    return dot / (norm(v1) * norm(v2) + 1e-8)


def batch_embed_articles(limit: int = 100) -> int:
    """Embed articles that don't have embeddings yet."""
    from models import Article
    from extensions import db
    
    articles = Article.query.filter(
        Article.embedding.is_(None),
        Article.final_article.isnot(None)
    ).limit(limit).all()
    
    count = 0
    for article in articles:
        try:
            text = article.final_article or article.draft_article or ""
            if len(text) < 50:
                continue
            article.embedding = embed_text(text[:5000])  # First 5k chars
            article.embedding_model = "all-MiniLM-L6-v2"
            article.embedding_updated_at = datetime.now(timezone.utc)
            count += 1
        except (ImportError, RuntimeError) as e:
            logger.error("Failed to embed article %s: %s", article.id, e)
            
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
        
    return count
```

**Migration:**

```python
# migrations/versions/XXX_add_article_embeddings.py
"""Add embedding columns to articles table."""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('articles', sa.Column('embedding', sa.LargeBinary(), nullable=True))
    op.add_column('articles', sa.Column('embedding_model', sa.String(50), nullable=True))
    op.add_column('articles', sa.Column('embedding_updated_at', sa.DateTime(), nullable=True))
    op.create_index('ix_articles_embedding_model', 'articles', ['embedding_model'])

def downgrade():
    op.drop_index('ix_articles_embedding_model')
    op.drop_column('articles', 'embedding_updated_at')
    op.drop_column('articles', 'embedding_model')
    op.drop_column('articles', 'embedding')
```

---

#### 0.2 Implement Hybrid Search (SQL + Vector)

**Problem:** Related article search misses semantic relationships. Current scoring uses tag overlap (weight 2.0), title keywords (weight 0.5), and category matching (weight 3.0), but can't find articles about the same concept with different tags/keywords.

**Solution:** Combine existing SQL-based search with vector similarity search using Reciprocal Rank Fusion (RRF).

**Files to Modify:**
- `services/related.py` - Add `find_related_articles_hybrid()` function
- `tasks/research.py` - Use hybrid search in research stage

**Implementation:**

```python
# services/related.py addition
from services.embeddings import cosine_similarity, embed_text


def find_related_articles_hybrid(article, limit: int = 5, vector_weight: float = 0.5) -> list[dict]:
    """Find related articles using hybrid search (SQL + vector)."""
    # 1. Get SQL-based candidates (current approach)
    sql_results = find_related_articles(article, limit=20)
    
    # 2. Get vector similarity results
    vector_results = []
    if article.embedding or article.original_title:
        vector_results = _vector_search_similar(article, limit=20)
    
    # 3. Merge and rerank with RRF
    if vector_results:
        merged = _reciprocal_rank_fusion(sql_results, vector_results, k=60)
        return merged[:limit]
    
    return sql_results[:limit]


def _vector_search_similar(article, limit: int = 20) -> list[dict]:
    """Find articles with similar embeddings."""
    from models import Article
    
    if article.embedding:
        query_vec = article.embedding
    else:
        # Generate embedding from title
        query_vec = embed_text(article.original_title or "")
    
    candidates = []
    # Note: For production, use FAISS or similar for efficient ANN search
    # This is a brute-force approach for <10k articles
    for candidate in Article.query.filter(
        Article.embedding.isnot(None),
        Article.id != article.id,
        Article.pipeline_status == "DONE"
    ).limit(1000):
        sim = cosine_similarity(query_vec, candidate.embedding)
        if sim > 0.6:  # Similarity threshold
            candidates.append({
                "id": candidate.id,
                "title": candidate.original_title,
                "score": sim,
                "method": "vector"
            })
    
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:limit]


def _reciprocal_rank_fusion(results_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Merge multiple result lists using RRF."""
    scores = {}
    article_data = {}
    
    for results in results_lists:
        for rank, item in enumerate(results, start=1):
            article_id = item["id"]
            if article_id not in scores:
                scores[article_id] = 0
                article_data[article_id] = item
            
            scores[article_id] += 1.0 / (k + rank)
    
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [article_data[a_id] for a_id in sorted_ids]
```

---

#### 0.3 Fix Thread Cancellation in Subagent System

**Problem:** `future.cancel()` in ThreadPoolExecutor only works if the task hasn't started. LLM calls that timeout may continue running in the background, wasting resources.

**Solution:** Switch to ProcessPoolExecutor with signal handling OR add timeout monitoring that marks tasks as "orphaned" and ignores late responses.

**Files to Modify:**
- `services/subagent.py` - Replace ThreadPoolExecutor, add timeout handling

**Implementation Option A (Recommended - Simpler):**

```python
# services/subagent.py modification
import signal
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError

# Replace ThreadPoolExecutor with ProcessPoolExecutor
SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "4"))  # Reduced for process overhead
_subagent_executor = ProcessPoolExecutor(max_workers=SUBAGENT_WORKERS)

# Wrap LLM calls to handle SIGTERM in subprocess
def _call_with_timeout_and_signal(provider_id, model, stage, messages, response_model, system, temperature, max_tokens):
    """LLM call wrapper that handles timeout signals."""
    import signal
    from services.llm import get_provider_by_id
    from services.llm.base import ProviderTimeoutError
    
    def timeout_handler(signum, frame):
        raise ProviderTimeoutError("Subagent timed out (signal)")
    
    signal.signal(signal.SIGTERM, timeout_handler)
    signal.signal(signal.SIGALRM, timeout_handler)  # For alarm-based timeout
    
    provider = get_provider_by_id(provider_id)
    with traced_llm_call(provider=provider_id, model=model, stage=stage):
        return provider.chat_structured(
            messages=messages,
            response_model=response_model,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
```

**Implementation Option B (Alternative - Monitoring):**

```python
# Add orphaned task tracking
_orphaned_tasks: set[str] = set()

def run_subagent(...):
    # ... existing code ...
    
    task_id = f"subagent_{article_id}_{task_type}_{time.time()}"
    
    def _call_with_timeout():
        # Check if task was orphaned before starting
        if task_id in _orphaned_tasks:
            raise ProviderTimeoutError("Task orphaned")
        result = provider.chat_structured(...)
        # Check if task was orphaned during execution
        if task_id in _orphaned_tasks:
            raise ProviderTimeoutError("Task orphaned during execution")
        return result
    
    try:
        future = _subagent_executor.submit(_call_with_timeout)
        result = future.result(timeout=stage_config.timeout_seconds)
    except FuturesTimeoutError:
        _orphaned_tasks.add(task_id)  # Mark as orphaned
        future.cancel()
        # ... rest of timeout handling ...
```

---

### Priority 1 (Important/Medium-Impact) - Months 2-4

#### 1.1 Integrate ToolSelector into Pipeline Config

**Problem:** `StageAwareToolSelector` and `KeywordToolSelector` are implemented in `services/tool_selection.py` but NEVER USED. The codebase only uses the `tool_names` parameter in `initialize_tool_registry()`.

**Solution:** Integrate selectors into `pipeline.yaml` configuration and update `initialize_tool_registry()` callers.

**Files to Modify:**
- `pipeline.yaml` - Add `tool_selector` config blocks
- `schemas/pipeline.py` - Add `ToolSelectorConfig` model
- `services/subagent.py` - Update `initialize_tool_registry()` and callers

**Implementation:**

```yaml
# pipeline.yaml addition
subagent:
  research:
    enabled: true
    tool_selector:
      type: "stage_aware"  # or "keyword"
      tool_names: ["web_search", "context_notes", "related_articles", "get_source_health"]
    # ... rest of config ...
  edit:
    enabled: true
    tool_selector:
      type: "keyword"
      keyword_map:
        "trend": ["get_trend_memory"]
        "context": ["context_notes", "related_articles"]
      default_tools: ["context_notes"]
    # ... rest of config ...
```

```python
# schemas/pipeline.py addition
class ToolSelectorConfig(BaseModel):
    """Configuration for tool selection strategy."""
    type: str = Field(..., description="Selector type: 'stage_aware' or 'keyword'")
    tool_names: list[str] = Field(default_factory=list)
    keyword_map: dict[str, list[str]] = Field(default_factory=dict)
    default_tools: list[str] = Field(default_factory=list)


class SubagentStageConfig(BaseModel):
    # ... existing fields ...
    tool_selector: Optional[ToolSelectorConfig] = None  # NEW FIELD
```

```python
# services/subagent.py modification
def _get_tools_for_stage(
    stage_config: SubagentStageConfig,
    context: dict[str, Any] | None = None,
) -> list[ToolDefinition]:
    """Get tools using selector if configured, else fall back to tool_names."""
    if stage_config.tool_selector:
        selector_type = stage_config.tool_selector.type
        
        if selector_type == "keyword":
            selector = KeywordToolSelector(
                keyword_map=stage_config.tool_selector.keyword_map,
                default_tools=stage_config.tool_selector.default_tools,
            )
        else:  # stage_aware
            selector = StageAwareToolSelector(stage_config.tool_selector.tool_names)
        
        return initialize_tool_registry(selector=selector, context=context)
    
    # Fallback to current behavior
    return initialize_tool_registry(tool_names=stage_config.tools)
```

---

#### 1.2 Add Semantic Retrieval to Trend Memory

**Problem:** `get_memory_for_topics()` uses exact topic string matching. "AI" won't match "Artificial Intelligence" or "LLM developments".

**Solution:** Add semantic search capability to trend memory using embeddings.

**Files to Modify:**
- `models.py` - Add embedding column to TrendMemory model
- `services/trend_memory.py` - Add `get_memory_semantic()` function
- `migrations/versions/` - New migration

**Implementation:**

```python
# models.py addition
class TrendMemory(db.Model):
    # ... existing fields ...
    embedding = db.Column(db.LargeBinary)  # Optional embedding for semantic search
    embedding_model = db.Column(db.String(50))
```

```python
# services/trend_memory.py addition
from services.embeddings import embed_text, cosine_similarity


def get_memory_for_topics_semantic(
    topics: list[str],
    min_importance: int = 1,
    max_age_days: Optional[int] = None,
    use_semantic: bool = True,
) -> list[TrendMemory]:
    """Retrieve memory using both exact and semantic matching."""
    # 1. Exact match (current behavior)
    exact_results = get_memory_for_topics(topics, min_importance, max_age_days)
    
    if not use_semantic or not topics:
        return exact_results
    
    # 2. Semantic match
    try:
        query_embedding = embed_text(", ".join(topics))
        semantic_results = _semantic_memory_search(query_embedding, min_importance, max_age_days)
        
        # 3. Merge and deduplicate
        return _merge_memory_entries(exact_results, semantic_results)
    except (ImportError, RuntimeError):
        # Embeddings not available, return exact results
        return exact_results


def _semantic_memory_search(
    query_emb: bytes,
    min_importance: int,
    max_age_days: Optional[int],
    threshold: float = 0.6,
) -> list[TrendMemory]:
    """Find memory entries with similar topic embeddings."""
    query = TrendMemory.query.filter(
        TrendMemory.embedding.isnot(None)
    )
    
    if min_importance > 1:
        query = query.filter(TrendMemory.importance >= min_importance)
    
    now = datetime.now(timezone.utc)
    query = query.filter(
        (TrendMemory.expires_at.is_(None)) | (TrendMemory.expires_at > now)
    )
    
    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        query = query.filter(TrendMemory.created_at >= cutoff)
    
    results = []
    for entry in query.limit(100):
        sim = cosine_similarity(query_emb, entry.embedding)
        if sim >= threshold:
            results.append(entry)
    
    return sorted(results, key=lambda x: x.created_at, reverse=True)


def _merge_memory_entries(
    exact: list[TrendMemory],
    semantic: list[TrendMemory],
) -> list[TrendMemory]:
    """Merge exact and semantic results, deduplicate by ID."""
    seen_ids = set()
    merged = []
    
    for entry in exact + semantic:
        if entry.id not in seen_ids:
            seen_ids.add(entry.id)
            merged.append(entry)
    
    return sorted(merged, key=lambda x: (-x.importance, -x.created_at.timestamp()))
```

---

#### 1.3 Extract Common Retry Logic in Subagent System

**Problem:** `run_subagent()`, `run_subagent_with_tools()`, and `run_subagent_chain()` have nearly identical retry loops (~30 lines each, 150+ lines total duplicated).

**Solution:** Extract common retry logic into a shared helper function.

**Files to Modify:**
- `services/subagent.py` - Add `_execute_with_retry()` helper, refactor 3 functions

**Implementation:**

```python
# services/subagent.py addition
def _execute_with_retry(
    func: Callable,
    timeout_seconds: int,
    max_retries: int,
    retry_delay: float,
    stage: str,
    task_type: str,
    article_id: int | None = None,
    metrics_labels: dict | None = None,
) -> tuple[Any, bool, list[str]]:
    """Execute function with retry, timeout, and metrics.
    
    Returns:
        Tuple of (result, used_fallback, fallback_stages)
    """
    import random
    from time import time as now
    
    if metrics_labels is None:
        metrics_labels = {"stage": stage, "task_type": task_type}
    
    last_exc = None
    used_fallback = False
    fallback_stages = []
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                delay = min(
                    1.0 * (2 ** attempt) + random.uniform(0, 0.5),
                    retry_delay,
                )
                time.sleep(delay)
            
            future = _subagent_executor.submit(func)
            try:
                result = future.result(timeout=timeout_seconds)
                return result, False, []
            except FuturesTimeoutError:
                future.cancel()
                logger.warning(
                    "Subagent %s/%s timed out after %ss",
                    stage,
                    task_type,
                    timeout_seconds,
                )
                raise ProviderTimeoutError(
                    f"Subagent timed out after {timeout_seconds}s"
                )
                
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < max_retries:
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    retry_delay,
                    e,
                )
                continue
            break
        except (AuthError, ProviderServerError) as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed with non-retryable error: %s",
                stage,
                task_type,
                e,
            )
            return None, True, [stage]
        except Exception as e:
            last_exc = e
            logger.error(
                "Subagent %s/%s unexpected error: %s — using fallback",
                stage,
                task_type,
                e,
            )
            return None, True, [stage]
    
    # All retries exhausted
    get_metrics().counter_inc("subagent.failure", labels=metrics_labels)
    log_pipeline_event(
        stage="subagent",
        event="subagent.failure",
        article_id=article_id,
        task_type=task_type,
        stage_name=stage,
        error=str(last_exc) if last_exc else None,
    )
    return None, True, [stage]
```

Then refactor `run_subagent()` to use this helper (similar for other two functions).

---

#### 1.4 Add Tool Execution Middleware

**Problem:** Tool functions are called directly without observability hooks for logging, metrics, validation, or error handling standardization.

**Solution:** Add a middleware system for tool execution.

**Files to Modify:**
- `services/subagent.py` - Add `ToolExecutionMiddleware` class, integrate into tool calling

**Implementation:**

```python
# services/subagent.py addition
class ToolExecutionMiddleware:
    """Middleware for tool execution with logging, metrics, and error handling."""
    
    def __init__(self):
        self._pre_hooks: list[Callable] = []
        self._post_hooks: list[Callable] = []
        self._error_hooks: list[Callable] = []
    
    def register_pre_hook(self, hook: Callable[[str, dict], None]):
        """Register hook called before tool execution."""
        self._pre_hooks.append(hook)
    
    def register_post_hook(self, hook: Callable[[str, dict, str, float], None]):
        """Register hook called after tool execution (with duration)."""
        self._post_hooks.append(hook)
    
    def register_error_hook(self, hook: Callable[[str, dict, Exception], None]):
        """Register hook called on tool execution error."""
        self._error_hooks.append(hook)
    
    def execute(self, tool: ToolDefinition, args: dict) -> str:
        """Execute tool with middleware."""
        from services.metrics import get_metrics
        import time
        
        # Pre-execution hooks
        for hook in self._pre_hooks:
            try:
                hook(tool.name, args)
            except Exception as e:
                logger.warning("Pre-hook failed for %s: %s", tool.name, e)
        
        start = time.time()
        try:
            if tool.fn is None:
                result = f"Error: Tool {tool.name} has no callable function"
            else:
                result = str(tool.fn(**args))
            
            duration = time.time() - start
            
            # Post-execution hooks
            for hook in self._post_hooks:
                try:
                    hook(tool.name, args, result, duration)
                except Exception as e:
                    logger.warning("Post-hook failed for %s: %s", tool.name, e)
            
            # Metrics
            get_metrics().histogram_observe(
                "subagent.tool_duration_seconds",
                duration,
                labels={"tool": tool.name},
            )
            
            return esc_xml_text(result)
            
        except Exception as e:
            # Error hooks
            for hook in self._error_hooks:
                try:
                    hook(tool.name, args, e)
                except Exception as hook_e:
                    logger.warning("Error-hook failed for %s: %s", tool.name, hook_e)
            
            logger.error("Tool %s failed: %s", tool.name, e)
            return esc_xml_text(f"Error: {e}")


# Global middleware instance
_tool_middleware = ToolExecutionMiddleware()


def get_tool_middleware() -> ToolExecutionMiddleware:
    """Get the global tool middleware instance."""
    return _tool_middleware
```

Then update `chat_with_tools()` in `services/llm/base.py` to use middleware:

```python
# In services/llm/base.py chat_with_tools() method
from services.subagent import get_tool_middleware

middleware = get_tool_middleware()

# Replace direct tool execution:
# result_content = esc_xml_text(str(fn(**fn_args)))
# With:
result_content = middleware.execute(tool_def, fn_args)
```

---

### Priority 2 (Nice-to-Have/Low-Impact) - Months 4-6

#### 2.1 Enhance Pipeline Observability with Trace IDs

**Problem:** Failures are logged separately across stages, no end-to-end tracing for debugging pipeline issues.

**Solution:** Add trace ID propagation through all pipeline stages.

**Files to Modify:**
- `services/pipeline_utils.py` - Add trace ID management
- `tasks/pipeline.py` - Propagate trace ID in `run_stage()`
- `services/logging_utils.py` - Add trace ID to log context

**Implementation:**

```python
# services/pipeline_utils.py addition
import uuid
import contextvars

_trace_id_var = contextvars.ContextVar("trace_id", default=None)


def set_trace_id(trace_id: str | None = None) -> str:
    """Set or generate trace ID for current context."""
    if trace_id is None:
        trace_id = str(uuid.uuid4())
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str | None:
    """Get current trace ID."""
    return _trace_id_var.get()


# In run_stage() - tasks/pipeline.py
def run_stage(...):
    from services.pipeline_utils import set_trace_id, get_trace_id
    
    # Get or generate trace ID
    if task_self and hasattr(task_self, "request"):
        headers = getattr(task_self.request, "headers", None) or {}
        trace_id = headers.get("trace_id")
        if trace_id:
            set_trace_id(trace_id)
    
    if not get_trace_id():
        set_trace_id()
    
    trace_id = get_trace_id()
    logger.info("Starting stage %s for article %s (trace_id=%s)", stage, article_id, trace_id)
    
    # Pass trace_id to all subcalls (LLM calls, tool calls, etc.)
    # This requires updating log_pipeline_event, traced_llm_call, etc.
```

---

#### 2.2 Add Memory Decay for High-Importance Entries

**Problem:** HIGH importance trend memory entries never expire (TTL = None). This could lead to stale information persisting indefinitely.

**Solution:** Add a very long TTL (1 year) for HIGH entries instead of "never expires", allowing eventual cleanup while preserving long-term memory.

**Files to Modify:**
- `services/trend_memory.py` - Modify `_ttl_for_importance()` for HIGH tier

**Implementation:**

```python
# services/trend_memory.py modification
def _ttl_for_importance(importance: int) -> Optional[datetime]:
    config = _get_config()
    if importance == MemoryImportance.LOW:
        return datetime.now(timezone.utc) + timedelta(days=config.ttl_days_low)
    if importance == MemoryImportance.MEDIUM:
        return datetime.now(timezone.utc) + timedelta(days=config.ttl_days_medium)
    
    # HIGH: Very long TTL (1 year) instead of never
    # This allows eventual cleanup while preserving long-term memory
    return datetime.now(timezone.utc) + timedelta(days=365)
```

Optionally, add a "staleness" check in `get_memory_for_topics()`:

```python
def get_memory_for_topics(...):
    # ... existing query ...
    
    # For HIGH importance entries older than 1 year, add a "stale" warning
    now = datetime.now(timezone.utc)
    for entry in entries:
        if entry.importance == MemoryImportance.HIGH:
            age_days = (now - entry.created_at).days
            if age_days > 365:
                entry.signal = f"[STALE - {age_days} days old] " + entry.signal
    
    return entries
```

---

#### 2.3 MCP Server Wrapper (Optional Interoperability)

**Problem:** Tools defined in `services/subagent.py` can't be used by external MCP clients (Claude Desktop, Cursor, VS Code, etc.)

**Solution:** Create optional MCP server wrappers for interoperability. **Only implement if needed** (team growth, external tool sharing).

**Files to Create:**
- `mcp_servers/ainews_content.py` - MCP server for content tools
- `mcp_servers/ainews_memory.py` - MCP server for memory tools

**Implementation:**

```python
# mcp_servers/ainews_content.py
"""MCP server exposing ainews content tools."""
from mcp import MCPServer
from mcp.types import Tool, TextContent

server = MCPServer("ainews-content")


@server.tool()
def get_article(article_id: int) -> str:
    """Get article by ID."""
    from models import Article
    
    article = Article.query.get(article_id)
    if not article:
        return f"Article {article_id} not found"
    
    return {
        "id": article.id,
        "title": article.original_title,
        "body": article.final_article or article.draft_article,
        "status": article.pipeline_status,
    }


@server.tool()
def search_articles(query: str, limit: int = 5) -> list[dict]:
    """Search articles using FTS5."""
    from models import Article
    
    results = Article.search(query).limit(limit).all()
    return [
        {"id": r.id, "title": r.original_title}
        for r in results
    ]


@server.tool()
def get_related_articles(article_id: int, limit: int = 5) -> list[dict]:
    """Get related articles for a given article."""
    from models import Article
    from services.related import find_related_articles_dicts
    
    article = Article.query.get(article_id)
    if not article:
        return []
    
    return find_related_articles_dicts(article.topics or [], article_id, limit)


if __name__ == "__main__":
    server.run()
```

---

## Implementation Roadmap

```
Phase 1: Foundation (Months 1-2)
├── 0.1 Add vector embeddings (P0)
│   ├── Create services/embeddings.py
│   ├── Add columns to Article model
│   ├── Create migration
│   └── Batch embed existing articles
├── 0.2 Implement hybrid search (P0)
│   ├── Add find_related_articles_hybrid()
│   └── Integrate into research stage
└── 0.3 Fix thread cancellation (P0)
    ├── Replace ThreadPoolExecutor with ProcessPoolExecutor
    └── Add timeout signal handling

Phase 2: Integration (Months 3-4)
├── 1.1 Integrate ToolSelector into pipeline (P1)
│   ├── Add ToolSelectorConfig to schemas/pipeline.py
│   ├── Update pipeline.yaml with selector configs
│   └── Refactor initialize_tool_registry() callers
├── 1.2 Add semantic memory retrieval (P1)
│   ├── Add embedding column to TrendMemory model
│   ├── Implement get_memory_for_topics_semantic()
│   └── Update edit stage to use semantic retrieval
└── 1.3 Extract common retry logic (P1)
    ├── Create _execute_with_retry() helper
    └── Refactor 3 subagent functions

Phase 3: Observability & Polish (Months 5-6)
├── 1.4 Add tool execution middleware (P1)
│   ├── Create ToolExecutionMiddleware class
│   └── Integrate into chat_with_tools()
├── 2.1 Enhance pipeline tracing (P2)
│   ├── Add trace ID propagation
│   └── Update logging to include trace_id
└── 2.2 Add memory decay for HIGH entries (P2)
    └── Modify _ttl_for_importance() for 1-year TTL

Phase 4: Optional (Months 6+)
└── 2.3 MCP server wrapper (P2)
    ├── Create mcp_servers/ directory
    ├── Implement ainews-content server
    └── Implement ainews-memory server
```

---

## File Change Summary

| Priority | Change | Files Modified | New Files |
|----------|-------|----------------|-----------|
| P0 | Vector embeddings | `models.py`, `services/related.py` | `services/embeddings.py`, migration |
| P0 | Hybrid search | `services/related.py`, `tasks/research.py` | - |
| P0 | Thread cancellation | `services/subagent.py` | - |
| P1 | ToolSelector integration | `schemas/pipeline.py`, `services/subagent.py`, `pipeline.yaml` | - |
| P1 | Semantic memory | `models.py`, `services/trend_memory.py` | migration |
| P1 | Common retry logic | `services/subagent.py` | - |
| P1 | Tool middleware | `services/subagent.py`, `services/llm/base.py` | - |
| P2 | Pipeline tracing | `tasks/pipeline.py`, `services/pipeline_utils.py`, `services/logging_utils.py` | - |
| P2 | Memory decay | `services/trend_memory.py` | - |
| P2 | MCP server | - | `mcp_servers/ainews_content.py`, `mcp_servers/ainews_memory.py` |

---

## Success Metrics

| Improvement | Metric | Target |
|-------------|--------|--------|
| Vector embeddings | Related article relevance score (human eval) | >75% relevant |
| Hybrid search | Click-through rate on related articles | +30% |
| Thread cancellation | Orphaned task count | 0 |
| ToolSelector integration | Selector usage in pipeline | 100% (replace tool_names) |
| Common retry logic | Lines of duplicated code | -150 lines |
| Tool middleware | Tool execution visibility (metrics) | 100% coverage |
| Pipeline tracing | Mean time to debug pipeline failure | -50% |
| Semantic memory | Memory hit rate for related topics | +40% |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Embedding model size (~90MB for all-MiniLM-L6-v2) | Increased memory usage | Use lazy loading, document requirement |
| ProcessPoolExecutor overhead | Slower subagent execution | Reduce SUBAGENT_WORKERS, benchmark |
| Semantic search latency | Slower related article queries | Limit candidates, use FAISS for >10k articles |
| Breaking changes to tool system | Pipeline disruption | Feature flag selector usage, gradual rollout |
| Migration complexity (embeddings) | Deployment issues | Test migration on staging, have rollback plan |

---

## Next Steps

1. **Review this plan** with the team
2. **Prioritize Phase 1 items** based on business needs
3. **Create feature branches** for each Priority 0 item
4. **Write tests** before implementation (TDD)
5. **Run lint and pytest** after each change (per AGENTS.md)

---

**Plan Status:** Ready for implementation pending team review.
