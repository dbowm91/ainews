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

## URL Utilities (`url.py`)

```python
def validate_url_safe(url: str) -> bool:
    """Check if URL is safe for fetching (SSRF protection)"""
    # Raises UnsafeURLError if blocked
    # Blocks internal IPs, private hostnames
    # Validates scheme (http/https only)

class UnsafeURLError(Exception):
    """Raised when URL fails SSRF checks"""
```

## Text Utilities (`text.py`)

```python
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on words"""

def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags and attributes"""

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
    # RFC 2822, ISO 8601, common formats

def format_date(dt: datetime, format: str = "%Y-%m-%d") -> str:
    """Format datetime to string"""

def time_ago(dt: datetime) -> str:
    """Return human-readable time difference"""
    # "2 hours ago", "3 days ago"
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
    """Extract readable text from HTML"""
    # Uses trafilatura fallback
```

## Hash Utilities (`hash.py`)

```python
def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash of data"""

def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool:
    """Verify hash matches data"""
```

## Design Principles

1. **Pure functions**: No side effects, no global state
2. **Minimal dependencies**: Only standard library + very common packages
3. **Comprehensive validation**: Input checking with clear errors
4. **Type hints**: Full typing for better IDE support
5. **Testable**: Easy to unit test without mocking complex systems
