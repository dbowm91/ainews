# Milestone C.2: Content Extractor Integration

## Objective

Refactor article/content extraction so untrusted URLs are fetched only by the first-party safe fetch client. Extraction libraries such as trafilatura may parse already-fetched HTML, but must not perform network I/O for untrusted input.

## Problem

The unsafe pattern is:

```python
validate_url_safe(url)
html = trafilatura.fetch_url(url)
```

That pattern validates one URL state and then delegates the actual request to trafilatura, which can independently resolve DNS, follow redirects, and connect to a different destination. Milestone C must replace this with:

```python
result = safe_fetch_url(url)
article = extract_from_html(result.text, final_url=result.final_url)
```

## Affected files

Likely files:

- `services/content_extractor.py`
- `services/article.py`
- `adapters/web.py`
- `tasks/research.py`
- `tasks/crawl.py`
- any route or service that accepts arbitrary URLs for preview/import/fetch
- `tests/test_content_extractor_safe_fetch.py`
- `tests/test_tasks_research_new.py`
- `tests/test_services_article.py`
- `docs/security.md`
- `AGENTS.md`

## Integration design

### Step 1: Inventory all untrusted network fetches

Search for:

- `trafilatura.fetch_url`
- `requests.get`
- `httpx.get`
- `urlopen`
- `urllib.request`
- `aiohttp`
- `feedparser.parse(` with URL input
- functions named `fetch`, `extract`, `crawl`, `preview`, `import`, `readability`, `scrape`

Classify each call site:

- untrusted URL fetch: must use safe fetch client.
- trusted internal service call: document why safe fetch is not required.
- local file/config load: not in scope.

### Step 2: Refactor `services/content_extractor.py`

Split the module into two layers:

1. Fetching layer: `safe_fetch_url(url)`.
2. Extraction layer: pure parsing/extraction from HTML/text bytes.

Suggested API:

```python
def extract_article(url: str) -> ExtractedArticle:
    result = safe_fetch_url(url)
    return extract_article_from_html(
        result.text,
        source_url=url,
        final_url=result.final_url,
        content_type=result.content_type,
    )


def extract_article_from_html(
    html: str,
    *,
    source_url: str | None = None,
    final_url: str | None = None,
    content_type: str | None = None,
) -> ExtractedArticle:
    ...
```

Use trafilatura extraction APIs that accept HTML/text input. Do not call trafilatura network APIs.

### Step 3: Preserve extraction behavior

Maintain current output fields as much as possible:

- title,
- text/body,
- author,
- published date,
- source URL,
- final URL if new field is available,
- language,
- metadata,
- extraction confidence/fallback status if present.

If current callers expect `None` rather than exceptions on fetch failures, either preserve that behavior at the boundary or update callers/tests consistently. Prefer raising typed exceptions inside the safe fetch layer and converting to pipeline statuses at task boundaries.

### Step 4: Update task/crawler call sites

For crawlers and research tasks:

- Use safe fetch for webpage/article URLs.
- Keep feed fetching under review: RSS/Atom feed URLs are also untrusted network inputs and should use the safe fetch client or a feed-specific safe fetch wrapper.
- Ensure task logs distinguish fetch failure, unsafe URL rejection, extraction failure, and empty content.

### Step 5: Avoid double-fetching

If a crawl adapter already fetched feed/item HTML safely, pass the fetched HTML into extraction rather than fetching the URL again. Add optional `html` or `fetched` arguments where useful.

### Step 6: Error handling

Map safe-fetch exceptions to existing domain outcomes:

- `UnsafeFetchError`: mark URL/source/article as rejected/unsafe; do not retry aggressively.
- `FetchTimeoutError`: retry according to transient retry policy.
- `FetchTooLargeError`: fail terminally or with low retry count.
- `FetchContentTypeError`: terminal extraction failure.
- upstream 5xx: retry according to existing source failure policy.
- 4xx: terminal or low retry count.

Avoid hiding `UnsafeFetchError` as a generic extraction failure; security rejections should be visible in logs/metrics.

## Tests

Add content-extractor integration tests with mocks/local servers:

- `extract_article()` calls `safe_fetch_url()` exactly once.
- `extract_article()` does not call `trafilatura.fetch_url()`.
- `extract_article_from_html()` works with static HTML and performs no network calls.
- Safe fetch result final URL is propagated into extraction metadata if supported.
- Unsafe URL rejection is surfaced distinctly.
- Oversize/timeout/content-type errors are handled by task/caller boundary.
- Existing tests for article extraction still pass after refactor.

Suggested monkeypatch guard:

```python
def fail_fetch_url(*args, **kwargs):
    raise AssertionError("trafilatura.fetch_url must not be called")
monkeypatch.setattr(trafilatura, "fetch_url", fail_fetch_url)
```

## Regression checks

Search after implementation:

```bash
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes tests
```

Any remaining direct network call must be either removed, routed through safe fetch, or documented as trusted/internal with a test.

## Acceptance criteria

- Untrusted content extraction uses safe fetch client.
- Extraction libraries do not perform network I/O for untrusted URLs.
- Existing extraction behavior remains functionally equivalent for normal public HTML pages.
- Security errors are distinguishable from normal extraction failures.
- Tests enforce that `trafilatura.fetch_url()` is not used for untrusted URLs.

## Handoff cautions

- Be careful with RSS/feed parsing libraries; many can fetch URLs directly if passed a URL. Prefer passing fetched bytes/text.
- Do not regress article quality by dropping useful metadata extraction; feed HTML into trafilatura extraction APIs correctly.
- Avoid broad `except Exception` blocks that hide unsafe URL rejection.
