---
name: utils-modules
description: "Utils modules for the ainews codebase — text processing, datetime, security, hashing, HTML utilities. Use these instead of duplicating functionality in services."
---

## Utils Modules Overview

The `utils/` package contains pure utility functions with minimal dependencies. These should be used instead of duplicating functionality in services.

## Available Modules

### `utils/text.py` - Text Processing
```python
from utils.text import (
    esc_xml_text,        # Escape text for XML embedding in LLM prompts
    esc_xml_attr,        # Escape value for XML attribute embedding
    escape_prompt_data,  # Recursively escape dict values for XML
    truncate,            # Truncate text to length on word boundary
    sanitize_html,        # Remove dangerous HTML tags/attributes
    extract_hashtags,     # Extract #hashtags from text
)
```

### `utils/datetime.py` - Date/Time Utilities
```python
from utils.datetime import (
    parse_date,    # Parse RFC 2822, ISO 8601, common formats to datetime
    format_date,   # Human-readable relative/absolute date ("2 hours ago")
    time_ago,      # Alias for format_date
)
```

### `utils/security.py` - Security Utilities
```python
from utils.security import (
    generate_token,         # Cryptographically secure random token
    constant_time_compare,  # Timing-attack safe string comparison
)
```

### `utils/hash.py` - Hashing Utilities
```python
from utils.hash import (
    generate_hash,  # Generate hash of data (default sha256)
    verify_hash,    # Verify hash matches data
)
```

### `utils/html.py` - HTML Processing
```python
from utils.html import (
    strip_tags,   # Remove all HTML tags
    linkify,      # Convert URLs to clickable links
    extract_text, # Extract readable text (uses trafilatura fallback)
)
```

### `utils/url.py` - URL Safety (SSRF Protection)
```python
from utils.url import (
    validate_url_safe,  # Validate URL is safe for fetching (blocks internal IPs)
    UnsafeURLError,     # Exception raised for unsafe URLs
)
```

## Design Principles

1. **Pure functions**: No side effects, no global state
2. **Minimal dependencies**: Only standard library + very common packages
3. **Comprehensive validation**: Input checking with clear errors
4. **Type hints**: Full typing for better IDE support

## Migration Note

Date utilities previously existed in `services/date_utils.py`. The canonical location is now `utils/datetime.py`. The `services/date_utils.py` module is retained for backward compatibility but may be deprecated in the future.