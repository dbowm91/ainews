# Utils Module

The `utils/` package contains pure utility functions with minimal dependencies.

## File Inventory

| File | Functions | Purpose |
|------|-----------|---------|
| `url.py` | `validate_url_safe`, `UnsafeURLError` | URL validation with SSRF protection |
| `text.py` | `truncate`, `sanitize_html`, `extract_hashtags`, `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` | Text processing and XML escaping |
| `datetime.py` | `parse_date`, `format_date`, `time_ago` | Date/time parsing and formatting |
| `hash.py` | `generate_hash`, `verify_hash` | Hashing utilities |
| `html.py` | `strip_tags`, `linkify`, `extract_text` | HTML processing |
| `security.py` | `generate_token`, `constant_time_compare` | Security utilities |
| `__init__.py` | — | Package init |

## Text Utilities (`text.py`)

```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on word boundaries."""

def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags from content"""

def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text"""

def esc_xml_text(text: str) -> str:
    """Escape text for XML element content"""

def esc_xml_attr(text: str) -> str:
    """Escape text for XML attribute value"""

def escape_prompt_data(data: dict) -> dict:
    """Escape dict values for prompt injection prevention.
    Handles strings, nested dicts, and lists (escapes string items recursively)."""
```

**Two different truncate() functions:**

1. `utils/text.py:truncate()` - Word-boundary truncation. Breaks on word boundaries, finds last space before limit, appends suffix. Used for general text truncation.

2. `adapters/base.py:BaseSourceAdapter._truncate()` - Simple slicing. Returns `text[:limit]` for non-empty input, `None` for empty. Used for adapter text truncation where word boundaries don't matter.

## DateTime Utilities (`datetime.py`)

```python
def parse_date(date_str: str) -> datetime | None:
    """Parse various date formats.

    Handles ISO 8601, RFC 2822, and other common formats.
    Naive datetimes (without timezone info) automatically get UTC
    appended via dt.replace(tzinfo=timezone.utc) to ensure consistent
    timezone handling throughout the application.
    """

def format_date(dt: datetime) -> str:
    """Format datetime as human-readable relative or absolute date.

    Returns 'just now', 'X minutes ago', 'X hours ago', 'yesterday',
    'X days ago', '%b %d' (same year), or '%b %d, %Y' (different year).
    """

def time_ago(dt: datetime) -> str:
    """Alias for format_date() - return human-readable time difference"""
```

## Security Utilities (`security.py`)

```python
def generate_token(length: int = 32) -> str:
    """Generate cryptographically secure random token.
    `length` is the number of random bytes (not characters); output uses
    URL-safe base64 encoding so the resulting string is ~33% longer."""

def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (timing attack prevention)"""
```

## HTML Utilities (`html.py`)

```python
def strip_tags(html: str) -> str:
    """Remove all HTML tags"""

def linkify(text: str) -> str:
    """Convert URLs to clickable links"""

def extract_text(html: str) -> str:
    """Extract readable text from HTML (uses trafilatura fallback)"""
```

## Hash Utilities (`hash.py`)

```python
def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash of data"""

def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool:
    """Verify hash matches data"""
```

## URL Utilities (`url.py`)

```python
def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP addresses.

    Performs DNS resolution to check for SSRF attempts via DNS rebinding.
    Returns the validated URL string.
    Raises UnsafeURLError for all invalid URL cases: empty URL, unsupported
    scheme, missing hostname, DNS resolution failure, or blocked IP address.
    UnsafeURLError inherits from ValueError, so callers can catch either type.
    """

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication (strip tracking params, lowercase)"""

def normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching"""

TRACKING_PARAMS: set[str]
    """Set of tracking parameter names to strip from URLs (14 params)"""

def clear_dns_cache() -> None:
    """Clear the DNS resolution cache"""

class UnsafeURLError(ValueError):
    """Raised when URL fails SSRF checks"""

The 14 tracked parameters are: `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `utm_id`, `fbclid`, `gclid`, `ref`, `source`, `mc_cid`, `mc_eid`, `twclid`, `yclid`. These are stripped during URL normalization to prevent deduplication issues with tracking-heavy URLs.
```

**Test coverage**: URL parser edge cases (credentials, host confusion, IPv6 brackets, trailing dots, percent-encoding, decimal/octal/hex IPv4 forms) are tested in `tests/test_url_security.py`.

## Design Principles

1. **Pure functions**: Most functions are pure, but `validate_url_safe()` and related DNS functions in `url.py` perform DNS resolution with caching using global state (`_dns_cache`, `_dns_executor`, `_TTLCache`). These are intentionally not pure for performance.
2. **Thread-safety**: `_TTLCache` (`utils/url.py:138`) uses a `threading.Lock` to protect all `get`/`set`/`clear` operations. The global `_dns_cache` singleton is initialized with double-checked locking via `_dns_cache_lock` (`utils/url.py:185-196`).
3. **Minimal dependencies**: Only standard library + very common packages
4. **Comprehensive validation**: Input checking with clear errors
5. **Type hints**: Full typing for better IDE support
6. **Testable**: Easy to unit test without mocking complex systems
7. **URL validation layering**: `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py` unchanged. Only `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` are duplicated in `services/url.py` — these copies add config support by reading `DNS_CACHE_TTL` and `DNS_CACHE_MAX` via `get_config_with_default()` (see `services/url.py:60-63`), whereas `utils/url.py` uses hardcoded constants (`_DNS_CACHE_TTL = 5`, `_DNS_CACHE_MAX = 1024`). Adapters should import from `utils/url.py` per clean layering.

## __all__ exports

The `utils/url.py` module exports a mix of functions, constants, and exception classes via `__all__`:

```python
__all__ = [
    "normalize_url",      # Function
    "normalize_title",    # Function
    "TRACKING_PARAMS",    # Constant (set of tracking parameter names)
    "UnsafeURLError",      # Exception class
    "validate_url_safe",  # Function
    "clear_dns_cache",     # Function
]
```

This mixed export pattern (functions + types) is intentional to support `from utils.url import *` style imports while documenting what's available.

## Empty __init__.py

The `utils/__init__.py` file is intentionally empty (0 bytes) because:
- `utils/` is not a proper Python package with submodules to export
- Each utility module (`url.py`, `text.py`, etc.) is imported directly when needed
- No top-level `from utils import *` pattern is used in the codebase

This is a deliberate design choice, not an oversight or incomplete implementation.
