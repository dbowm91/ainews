# LLM Context Summarization: Best Practices Research

**Date:** April 2026  
**Purpose:** Research context overflow handling for ainews pipeline system

---

## Executive Summary

Context overflow is the single most common failure mode in production LLM systems. The core challenge: finite context windows vs. unbounded conversation/tool result accumulation. Production systems (2024-2025) converge on three strategies:

1. **Threshold-based summarization** (most common) - compress at ~70-85% occupancy
2. **Sliding window with sticky facts** (production default) - keep recent verbatim + extracted key facts
3. **Hierarchical/recursive summarization** (for very long contexts) - chunk → summarize → merge

For ainews specifically, the pipeline architecture (select→research→write→edit stages) means context accumulates across stages. Recommended approach: hybrid summary buffer with stage-aware retention.

---

## 1. How Production LLM Systems Handle Context Overflow

### 1.1 LangChain / LangGraph

**Mechanism:** `SummarizationMiddleware` + conversation memory classes

Key components:
- `ConversationSummaryMemory` - summarizes conversation as it grows (logarithmic token growth)
- `ConversationTokenBufferMemory` - keeps last N tokens verbatim
- `ConversationSummaryBufferMemory` - hybrid: keeps recent buffer + summarizes older
- `trim_messages` utility - LangGraph's state reducer for selective message retention

LangChain's 2025 approach (Deep Agents):
- Triggers at 85% of model's `max_input_tokens`
- Keeps 10% tokens as recent context reserve
- Uses model profiles to determine per-model thresholds
- Tool call results >20K tokens offloaded to filesystem with preview
- Supports autonomous agent-triggered compaction (agent decides when to compact)

```python
# LangChain pattern
from langchain.memory import ConversationSummaryBufferMemory
memory = ConversationSummaryBufferMemory(
    llm=chat,
    max_token_limit=16000,
    return_messages=True
)
```

### 1.2 AutoGen (Microsoft)

**Mechanism:** Compression agent + message filtering

From GitHub issue #156 (2023):
- Two modes: `TERMINATE` (stop before error) vs `COMPRESS` (call compression agent)
- Compression agent summarizes previous messages
- Message filtering: remove failed tool calls, keep reasoning traces
- Manual: user can trigger `/compact` command

Recent (2025): More mature message list management with retrieval-based history (retrieve relevant messages based on current query vs. simple truncation).

### 1.3 CrewAI

**Mechanism:** Auto-summarization with task-level context reuse

- Automatic context passing between tasks
- `max_tokens` parameter limits individual agent turns
- No hard limit enforcement on cumulative team context
- Warning: Large agent teams with deep task chains can still exceed token budgets

CrewAI pattern:
```python
from crewai import Agent, Task, Crew
# Context managed automatically per task
# Manual monitoring needed for multi-agent workflows
```

### 1.4 Claude Code / Anthropic

**Mechanism:** Server-side compaction (beta) + client-side token budget

- Auto-compact at 95% context usage (Claude Code)
- Server-side compaction: automatic summarization of earlier conversation parts
- Context-aware models (Sonnet 4.5+): trained to use token budget throughout conversation
- Returns validation error (vs silent truncation) when context exceeded (Sonnet 3.7+)

Key insight: "Context rot" - accuracy degrades as token count grows even before hitting limits.

---

## 2. Tradeoffs: Summarization Approaches

### 2.1 Naive Truncation (Sliding Window)

**How it works:** Keep most recent N messages/tokens, discard older

**Pros:**
- Simple to implement
- Predictable token budget
- Low latency (no additional LLM call)
- Works for short conversations

**Cons:**
- "Amnesia" - lose critical early context (user name, preferences, prior decisions)
- "Lost in the middle" - quality degrades even before hitting limits
- No semantic understanding of what's important
- 82% failure rate when filling context to 95% of limit

**Best practice:** Reserve 20% headroom - effective context is ~80% of advertised limit

```python
# Sliding window pattern
messages = conversation[-max_messages:]  # Keep last N messages
```

### 2.2 Summary Extraction via LLM

**How it works:** Call LLM to compress older messages into summary

**Pros:**
- Preserves key information in compressed form
- Better than pure truncation for long conversations
- Extensible: can extract structured facts vs free-form summary

**Cons:**
- Additional LLM call (cost + latency)
- Summary quality varies - can lose nuance or introduce hallucinations
- Recursive hallucination risk: summarizing summaries compounds errors

**Best practice:** Use for conversations >30K tokens; keep recent 40-50% verbatim

```python
# Summary buffer pattern
if total_tokens > threshold:
    older_messages = messages[:-recent_count]
    summary = llm.invoke(f"Summarize this conversation: {older_messages}")
    messages = [summary] + messages[-recent_count:]
```

### 2.3 Hierarchical Summarization (Map-Reduce)

**How it works:** Chunk → summarize each chunk → merge summaries → optionally summarize again

**Pros:**
- Scales to very long contexts (100K+ tokens)
- Preserves per-section detail while providing global view
- Research shows better quality than single-pass summarization for documents

**Cons:**
- Multiple LLM calls (cost scales with log n)
- "Hallucination amplification" - recursive summarization compounds errors
- Context-dependent: needs document structure to chunk effectively
- More complex to implement

**Research insight (ACL 2025):** Context-aware hierarchical merging outperforms zero-shot and basic hierarchical baselines. Key: enrich intermediate summaries with source context (citations, evidence links).

```python
# Hierarchical pattern
# Level 1: chunk-level summaries
chunk_summaries = [llm.summarize(chunk) for chunk in chunks]
# Level 2: merge summaries
final_summary = llm.merge_summaries(chunk_summaries)
```

### 2.4 Comparison Table

| Approach | Tokens | Latency | Quality | Best For |
|----------|--------|---------|---------|----------|
| Sliding Window | O(n) | O(1) | Low | Short tasks, simple bots |
| Summary Buffer | O(n) | O(1) | Medium | Long conversations |
| Hierarchical | O(n log n) | O(log n) | High | Long documents, deep pipelines |
| Retrieval-based | O(n) | O(k) | High | Questions about past context |

---

## 3. Prompting Techniques for Summarizing Long Context

### 3.1 Core Principles

1. **Place instructions at beginning or end** - Models attend less to middle context
2. **Use delimiters** - `### Instruction` / `### Context` / `### Output`
3. **Be specific about format** - JSON, bullet points, paragraph
4. **Specify length constraints** - "3 sentences" vs "brief summary"
5. **Lead the output** - Start with expected first word/format
6. **State what to do, not what not to do** - Positive instructions work better

### 3.2 Effective Prompt Structures

**For conversation summarization:**
```
### Instruction
Summarize the conversation below into a concise summary that preserves:
- Key decisions or commitments made
- Important facts about the user's needs/preferences
- Any unresolved questions or pending items
Output as JSON: {"summary": "...", "key_facts": [...], "pending": [...]}

### Conversation
{messages}

### Output
```

**For tool result compression:**
```
### Instruction
Extract the essential information from this tool output. Keep:
- Final results/answers
- Error messages if present
- Key metrics or data points
Discard: intermediate steps, debugging info, verbose logging

### Tool Output
{output}

### Summary
```

**For hierarchical merge:**
```
### Instruction
Merge these section summaries into a coherent overall summary.
Preserve: key findings, contradictions between sections, important details
Format: {overview paragraph} followed by {key points as bullet list}

### Section Summaries
{summaries}

### Merged Summary
```

### 3.3 Best Practices from Production Systems

- **Anthropic**: Give explicit structural context (what document is, role, extraction goal) vs expecting model to infer
- **OpenAI**: Put extraction instructions AFTER document content for complex tasks
- **Retrieval order matters**: Place most relevant chunks at start or end, not middle
- **Contradiction instruction**: "Surface contradictions rather than silently resolve them"
- **Temperature = 0** for factual extraction tasks

---

## 4. Validating Summary Quality

### 4.1 LLM-as-Judge Approaches

**RAGAS Framework** (Reference-free evaluation):
- **Faithfulness**: Does summary contain hallucinations? (LLM judges claims)
- **Answer Relevancy**: Does summary address the intended questions?
- **Context Precision**: Are retrieved chunks relevant? (for RAG scenarios)
- **Context Recall**: Was all needed information captured? (needs ground truth)

**Key insight**: Faithfulness and answer relevancy are reference-free, enabling production monitoring without human labels.

### 4.2 Validation Strategies

**1. Self-reflection prompts:**
```
### Instruction
Evaluate this summary for:
1. Factual accuracy (does it match source?)
2. Completeness (did it miss key points?)
3. Coherence (is it logically consistent?)
Rate each 1-5 and explain any issues.

### Summary
{summary}

### Source
{source}
```

**2. Question generation + answer matching:**
- Generate questions from summary
- Answer questions from source
- Compare answers for consistency

**3. Sampling + human review:**
- Spot-check 5-10% of summaries
- Track quality drift over time
- Establish SLOs (e.g., 90% faithfulness score)

**4. Downstream task validation:**
- Does summary preserve accuracy on downstream tasks?
- For ainews: does summarized article context still produce accurate write/edit outputs?

### 4.3 Metrics to Track

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Faithfulness | Hallucination rate | >0.9 |
| Conciseness | Summary length vs source | <30% |
| Coverage | Key points retained | >80% |
| Consistency | Summary quality variance | <10% drift |
| Compression latency | Time to summarize | <2s |

---

## 5. Recommendations for ainews Pipeline

### 5.1 Context Accumulation Pattern in ainews

The pipeline has unique characteristics:
- **Stage-dependent context**: Select stage sees different context than write/edit
- **Accumulating artifacts**: Each stage produces outputs that feed next
- **Document-level context**: Article being processed is the primary context
- **Tool outputs**: Research stage produces fetched content, embeddings

### 5.2 Recommended Approach: Hybrid Summary Buffer

**Architecture:**
```
┌─────────────────────────────────────────────┐
│           Context Window                    │
├─────────────────────────────────────────────┤
│  System Prompt (fixed, ~2K tokens)         │
├─────────────────────────────────────────────┤
│  Stage State (current stage + artifacts)   │
│  - Keep full context for active stage      │
├─────────────────────────────────────────────┤
│  Recent Buffer (last 8K tokens verbatim)   │
│  - Preserve recent tool outputs, reasoning │
├─────────────────────────────────────────────┤
│  Summary of Prior Stages (compressed)      │
│  - Each completed stage: 1-2 sentence brief│
├─────────────────────────────────────────────┤
│  Current Request (~4K tokens reserved)    │
└─────────────────────────────────────────────┘
```

**Implementation:**

1. **Token budget allocation:**
   - System prompt: 3K (fixed)
   - Active stage context: 60K (keep full)
   - Recent buffer: 8K
   - Stage summaries: 4K
   - Request reserve: 4K
   - Headroom: 2K

2. **Trigger policy:**
   - Soft cap: 70% occupancy → warn
   - Hard cap: 85% occupancy → compress
   - Emergency: 95% occupancy → aggressive trim + retry

3. **Compression strategy by stage:**
   - **Crawl**: Summarize URLs fetched, keep raw URLs
   - **Select**: Summarize article metadata, keep titles/urls
   - **Research**: Summarize research findings, keep key citations
   - **Write**: Full context preserved, stage summary for prior stages
   - **Edit**: Full context for edit task, prior stages summarized

4. **Sticky facts extraction:**
   - Extract: source URLs, key claims, entity names, article metadata
   - Persist across compression rounds

### 5.3 Monitoring & Observability

Add to pipeline metrics:
- `context_tokens_used` - current context size
- `compression_triggered` - count by trigger type
- `compression_latency_ms` - time for summarization
- `summary_quality_score` - faithfulness (LLM-judged, sampled)
- `stage_context_rot` - how much prior stage context retained

**SLOs:**
- P95 latency increase from compression <500ms
- Compression trigger rate <10% of pipeline runs
- Summary faithfulness >0.85

### 5.4 Quick Wins (Implement First)

1. **Token counting** - Add token estimator to all LLM calls
2. **Soft limits** - Warn at 70% context, don't auto-compress yet
3. **Stage summary** - Each stage produces 1-2 sentence brief of prior work
4. **Sticky facts** - Extract key metadata, persist separately

### 5.5 Later (If Needed)

1. **Full summarization** - When regular context exceeds 80K tokens
2. **Hierarchical** - If single-stage summarization quality degrades
3. **RAG for history** - If downstream tasks frequently need prior stage context

---

## Appendix: Key Sources

- LangChain Context Engineering (2025): https://docs.langchain.com/oss/python/deepagents/context-engineering
- AutoGen Compression (GitHub #156): https://github.com/microsoft/autogen/issues/156
- ACL 2025 Hierarchical Summarization: https://aclanthology.org/2025.findings-acl.289/
- RAGAS Framework: https://docs.ragas.io/en/latest/howtos/applications/align-llm-as-judge/
- Context Window Management Production (Tanuj Garg, 2026): https://tanujgarg.com/blog/llm-context-window-management-production
- Anthropic Context Windows: https://docs.anthropic.com/en/docs/build-with-claude/context-windows
- DeadEnds Research (2023): https://deadends.dev/llm/context-window-overflow-silent-truncation/