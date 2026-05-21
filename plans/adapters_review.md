# Adapters Module Architecture Review

## Summary of Verified Claims

| Claim | Status | Notes |
|-------|--------|-------|
| File inventory (5 files) | VERIFIED | All files exist: base.py, rss.py, api.py, web.py, session.py |
| Adapter pattern with @register_adapter | VERIFIED | `SOURCE_ADAPTERS` registry at adapters/base.py:18-20 |
| BaseSourceAdapter abstract methods | VERIFIED | `fetch()` and `parse_item()` at lines 50-54 |
| SOURCE_ADAPTERS registry | VERIFIED | `_ADAPTER_REGISTRY` with public alias at line 20 |
| RSSAdapter with feedparser + BeautifulSoup | VERIFIED | rss.py uses feedparser, falls back to BeautifulSoup |
| APIAdapter JSONPath extraction | VERIFIED | `_resolve_path()` at api.py:176-192 |
| WebAdapter CSS selectors | VERIFIED | Uses ListingConfig and ArticleSelectors from schemas |
| SSRFSafeRedirectHandler with thread-local counter | VERIFIED | Uses `_thread_local` at session.py:13,31-35 |
| SSRF via validate_url_safe from utils/url | VERIFIED | All adapters import from utils/url.py, not services/url.py |
| Error handling: network errors return [] | VERIFIED | All adapters return empty list on network failure |
| Error handling: parse errors skip items | VERIFIED | fetch_and_parse() catches ValueError/KeyError/AttributeError |
| Rate limiting: exponential backoff | VERIFIED | web.py:181 uses `2**attempt * 5 + jitter` |
| Source config via `config` field | VERIFIED | SourceConfig.config validated against adapter schemas |

---

## Discrepancies & Issues

### CRIT-1: SSRFSafeRedirectHandler Re-raises Without Decrementing Counter

**File**: `adapters/session.py:42,47-48`

**Issue**: When a redirect is blocked by SSRF protection, the redirect count is incremented BEFORE validation, but the exception is re-raised without any decrement. This means a single blocked redirect consumes one of the 30 allowed redirects.

```python
self._redirect_count += 1                      # line 42
if self._redirect_count > self._max_redirects:
    raise requests.exceptions.TooManyRedirects  # line 43-44
try:
    validate_url_safe(location)                # line 46
except UnsafeURLError:
    raise                                      # line 47-48 - count NOT decremented
```

**Impact**: An attacker could trigger 30 SSRF-blocked redirects and then succeed on the 31st redirect to a private IP (since counter is exhausted).

**Fix**: Decrement count when re-raising UnsafeURLError, or move increment after successful validation.

---

### CRIT-2: javascript: and data: Schemes Not Blocked by Scheme Validation

**File**: `adapters/session.py` (SSRFSafeRedirectHandler)

**Issue**: The docstring at `architecture/adapters.md:137-138` claims:
> "Non-http/https schemes (javascript:, data:, etc.) via scheme validation"

But `SSRFSafeRedirectHandler` does NOT validate schemes at all - it only calls `validate_url_safe(location)` which checks scheme in `utils/url.py:253`:
```python
if parsed.scheme not in ("http", "https"):
    raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
```

So `javascript:` and `data:` ARE blocked by `validate_url_safe` calling `urlparse` and checking scheme. The issue is the docstring says the blocking is "via scheme validation" in the redirect handler specifically, when in fact it's blocked by the upstream `validate_url_safe()` call.

**Impact**: Documentation is technically accurate but misleading - the redirect handler doesn't do scheme validation itself.

---

### CRIT-3: APIAdapter item_url Limit Applies After item Fetch

**File**: `adapters/api.py:63-69`

**Issue**: The document doesn't mention that when `item_url` is configured:
1. First, `all_items` is populated from the list endpoint (up to `max_items`)
2. Then, individual items are fetched via `item_url` for each item in `all_items[:cfg.max_items]`
3. The returned list may have FEWER than `max_items` items due to failed fetches

```python
if cfg.item_url and all_items:
    fetched = []
    for item_id in all_items[: cfg.max_items]:  # Iterates up to max_items
        item = self._fetch_item(item_id)
        if item:
            fetched.append(item)
    return fetched  # May be < max_items if some fetches fail
```

**Impact**: Users expecting exactly `max_items` articles may get fewer without error indication.

---

### MED-1: Inconsistent Session Management Between Adapters

**Files**: `adapters/rss.py:47-52` vs `adapters/api.py:22-23` vs `adapters/web.py:35`

**Issue**: The architecture document notes that RSSAdapter "creates its own `requests.Session`" while APIAdapter and WebAdapter "share the global session". This is VERIFIED but poorly documented.

- **RSSAdapter**: Creates own session at `rss.py:47`, mounts retry adapter, sets redirect handler
- **APIAdapter**: Uses `get_crawl_session()` - global singleton
- **WebAdapter**: Uses `get_crawl_session()` - global singleton

**Impact**: Unexpected behavior when switching between adapter types (different session state, different retry behavior).

---

### MED-2: Rate Limiter Not Session-Scoped

**File**: `adapters/session.py:57-75`

**Issue**: `get_crawl_session()` creates a global singleton session with a global `SSRFSafeRedirectHandler`. The redirect counter is thread-local (good), but the handler instance is shared across ALL requests globally.

**Impact**: While thread-local storage fixes the per-request counter issue, the handler's `_max_redirects = 30` is hardcoded and cannot be configured per-source.

---

### MED-3: APIAdapter auth_header Bearer Token Handling is Correct But Documentation is Ambiguous

**File**: `adapters/api.py:164-168`

**Issue**: The architecture document at line 89 says:
> "Auth header injection (Bearer token only — API key in custom headers NOT supported)"

The code at lines 164-168 shows:
```python
if cfg.api_key:
    if cfg.auth_header:
        headers[cfg.auth_header] = f"Bearer {cfg.api_key}"
    else:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
```

This DOES support custom auth_header values (e.g., `X-Api-Key` would be set to `Bearer <token>`). The documentation claim that "API key in custom headers NOT supported" seems to mean "API key values are not used directly in custom headers" (they're always wrapped in Bearer), which is accurate but unclear.

**Impact**: Documentation could be clearer about what "NOT supported" means here.

---

### MED-4: WebAdapter Trafilatura ImportError Handling Incomplete

**File**: `adapters/web.py:112-122`

**Issue**: When trafilatura is not installed, the code logs a warning but continues with potentially low-quality content:

```python
if not body or len(body) < MIN_CONTENT_LENGTH:
    try:
        import trafilatura
        ...
    except ImportError:
        logger.warning("trafilatura not installed...")  # Warning only, no fallback
```

**Impact**: Articles may be stored with minimal content if trafilatura is missing and CSS selectors extract little text. No alert to operators that content extraction failed.

---

### LOW-1: APIAdapter Pagination Missing from Documented Example

**File**: `adapters/api.py`

**Issue**: The architecture document shows an API source example but doesn't include pagination configuration in the YAML example. The reader cannot see how to configure pagination.

**Impact**: Low - pagination is documented elsewhere in schemas/source.py but not shown in adapter documentation example.

---

## Security Concerns

### SEC-1: SSRF Protection Depends on External DNS Resolution

**File**: `utils/url.py:201-240`

**Issue**: `validate_url_safe()` performs DNS resolution to check for DNS rebinding attacks. This is correct and necessary, but:
1. DNS resolution adds latency (up to 10s timeout per URL)
2. DNS caches are global and can be poisoned (mitigated by short TTL of 5 seconds)
3. If DNS resolver fails open (returns safe IPs on error), SSRF protection fails

**Impact**: Performance bottleneck when crawling many URLs, potential security gap if DNS is compromised.

---

### SEC-2: Global Session Shares State Across Requests

**File**: `adapters/session.py:57-75`

**Issue**: `get_crawl_session()` returns a global singleton. The session's headers are modified per-adapter (e.g., `api.py:23` sets User-Agent, `web.py:36-40` sets User-Agent). These modifications affect the global session state.

**Impact**: Race conditions possible if multiple crawlers run concurrently with different User-Agent requirements.

---

## Performance Concerns

### PERF-1: WebAdapter Request Delay is Per-URL Not Per-Page

**File**: `adapters/web.py:174-175`

**Issue**: `request_delay_min/max` is applied per-article URL fetch, not per listing page. When scraping 50 articles from one listing page, delays accumulate sequentially.

```python
for url in article_urls:  # Each URL
    soup = self._polite_get(url)  # Sleeps delay_min to delay_max between each
```

**Impact**: Slow crawling when many articles per source. Batch processing or concurrent fetching could be faster.

---

### PERF-2: RSSAdapter Retry Uses Global Session

**File**: `adapters/rss.py:47-52`

**Issue**: The retry configuration in RSSAdapter is session-scoped but uses hardcoded values:
```python
retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
```

Cannot configure via sources.yaml.

---

## Recommendations

| Priority | Issue | Recommendation | File:Line |
|----------|-------|----------------|-----------|
| CRIT | Redirect counter not decremented on blocked redirect | Fix: decrement counter on UnsafeURLError or move increment after validation | session.py:42-48 |
| CRIT | javascript:/data: scheme blocking unclear | Clarify doc: scheme blocking happens in validate_url_safe, not redirect handler | architecture/adapters.md:137 |
| CRIT | item_url returns fewer items than max_items | Document this behavior or ensure consistent count | api.py:63-69 |
| MED | Inconsistent session management | Document session ownership per adapter type clearly | architecture/adapters.md |
| MED | WebAdapter trafilatura ImportError | Log error-level warning, consider flagging article | web.py:119-120 |
| MED | auth_header documentation unclear | Clarify: custom headers get Bearer token, not raw API key | architecture/adapters.md:89 |
| LOW | Global session header modifications | Document that API/Web adapter headers modify shared session | adapters/session.py |
| LOW | Request delay per article | Consider batch delay or document current behavior | web.py:174-175 |
| LOW | Pagination not in example YAML | Add pagination config to API source example | architecture/adapters.md:154-160 |

---

## Bug Summary

| Bug | File | Line | Description |
|-----|------|------|-------------|
| BUG-1 | adapters/session.py | 42,47-48 | Redirect counter incremented before validation, not decremented on UnsafeURLError re-raise |
| BUG-2 | adapters/api.py | 63-69 | item_url fetch can return fewer than max_items without indication |
| BUG-3 | adapters/web.py | 119-120 | trafilatura missing logs only warning, no operator alert |

---

## Verified Layering

**Claim**: Adapters must NOT import from services.

**Verification**: Only one mention of "services" in adapters:
- `adapters/base.py:113` - Comment explaining why `_classify_topics` is defined in adapters

No actual imports from services layer. **VERIFIED CORRECT**.

**Services importing from adapters**: Verified via grep - `services/crawling.py:13` uses `TYPE_CHECKING` block for `RawItem` import. **CORRECT** - this is the proper pattern for type hints only.