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

## Text Utilities (`text.py`)

```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on words"""

def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags from content"""

def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text"""

def esc_xml_text(text: str) -> str:
    """Escape text for XML element content"""

def esc_xml_attr(text: str) -> str:
    """Escape text for XML attribute value"""

def escape_prompt_data(data: dict) -> dict:
    """Escape dict values for prompt injection prevention"""
```

## DateTime Utilities (`datetime.py`)

```python
def parse_date(date_str: str) -> datetime | None:
    """Parse various date formats"""

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
    """Generate cryptographically secure random token"""

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
    Raises UnsafeURLError if URL is invalid or unsafe.
    """

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication (strip tracking params, lowercase)"""

def normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching"""

TRACKING_PARAMS: set[str]
    """Set of tracking parameter names to strip from URLs"""

def clear_dns_cache() -> None:
    """Clear the DNS resolution cache"""

class UnsafeURLError(ValueError):
    """Raised when URL fails SSRF checks"""
```

## Design Principles

1. **Pure functions**: Most functions are pure, but `validate_url_safe()` and related DNS functions in `url.py` perform DNS resolution with caching using global state (`_dns_cache`, `_dns_executor`, `_TTLCache`). These are intentionally not pure for performance.
2. **Minimal dependencies**: Only standard library + very common packages
3. **Comprehensive validation**: Input checking with clear errors
4. **Type hints**: Full typing for better IDE support
5. **Testable**: Easy to unit test without mocking complex systems
6. **URL validation layering**: `services/url.py` contains a config-aware version of URL validation (reads `get_config_with_default`). Adapters should import from `utils/url.py` per clean layering. The duplication is intentional.

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
