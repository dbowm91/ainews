# Utils Module Verification & Improvement Plan

**Date:** 2026-05-07
**Architecture Document:** `architecture/utils.md`
**Current State vs Documentation:** PARTIAL - Several items implemented by previous review, many still missing

---

## Executive Summary

The `architecture/utils.md` document describes a utils module with 7 files and ~20 functions. After the previous architecture review (commit 8945c5b), some fixes were applied:
- ✅ `is_valid_url` added to `utils/url.py`
- ✅ `get_domain` added to `utils/url.py`
- ❌ `utils/text.py` still has wrong contents (XML escaping vs text processing)
- ❌ `utils/datetime.py`, `hash.py`, `html.py`, `security.py`, `ipc.py` still MISSING

**Completion:** ~30% of documented utils functions exist.

---

## Verification of Claims

### File Inventory Status

| Claimed File | Status | Actual Contents |
|--------------|--------|------------------|
| `utils/url.py` | ✅ IMPLEMENTED | `normalize_url`, `normalize_title`, `TRACKING_PARAMS`, `is_valid_url`, `get_domain` |
| `utils/text.py` | ❌ WRONG CONTENTS | Documented: `truncate`, `sanitize_html`, `extract_hashtags`<br>Actual: `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data` (XML escaping for LLM prompts) |
| `utils/datetime.py` | ❌ MISSING | Documented functions in `services/date_utils.py` |
| `utils/hash.py` | ❌ MISSING | Script exists at `scripts/hash_password.py` but no utils module |
| `utils/html.py` | ❌ MISSING | No implementation found |
| `utils/security.py` | ❌ MISSING | Token functions scattered inline; TOTP in `services/totp.py` |
| `utils/ipc.py` | ❌ MISSING | No implementation found |

---

## Function-Level Verification

### URL Utilities (`utils/url.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `normalize_url` | ✅ VERIFIED | Works correctly; strips www, sorts query params, removes tracking params |
| `is_valid_url` | ✅ VERIFIED | Added in commit 8945c5b (H-15); wrapper around `services.url.validate_url_safe` |
| `get_domain` | ✅ VERIFIED | Added in commit 8945c5b (H-15); extracts domain with www stripping |

### Text Utilities (`utils/text.py`)

| Function | Status | Notes |
|----------|--------|-------|
| `truncate` | ❌ NOT IMPLEMENTED | Similar `truncate_for_log` exists in `constants.py:108` |
| `sanitize_html` | ❌ NOT IMPLEMENTED | No implementation found |
| `extract_hashtags` | ❌ NOT IMPLEMENTED | No implementation found |
| `esc_xml_text` | ✅ ACTUAL | Current content - XML text escaping for LLM prompts |
| `esc_xml_attr` | ✅ ACTUAL | Current content - XML attribute escaping for LLM prompts |
| `escape_prompt_data` | ✅ ACTUAL | Current content - recursive dict escaping for LLM prompts |

**Issue:** The `utils/text.py` module serves a legitimate purpose (XML escaping) but doesn't match architecture docs. This is a **content mismatch**, not a bug.

### DateTime Utilities

| Function | Status | Location |
|----------|--------|----------|
| `parse_date` | ❌ NOT IMPLEMENTED | No implementation found |
| `format_date` | ✅ EXISTS | `services/date_utils.py:6` - human-readable formatting ("2 hours ago") |
| `time_ago` | ✅ EXISTS | Same function as `format_date` - implements "time ago" logic |

**Issue:** DateTime utilities are in `services/` not `utils/`. Violates architecture layering.

### Security Utilities

| Function | Status | Location |
|----------|--------|----------|
| `generate_token` | ⚠️ FRAGMENTED | Inline `secrets.token_urlsafe(32)` throughout codebase |
| `verify_token` | ⚠️ PARTIAL | `services/totp.py:11` - TOTP verification, not general-purpose |
| `constant_time_compare` | ❌ NOT IMPLEMENTED | No general-purpose implementation found |
| `hash_password` | ✅ EXISTS | `scripts/hash_password.py:77` - uses werkzeug `generate_password_hash` |
| `verify_password` | ✅ EXISTS | `scripts/hash_password.py:79` - uses werkzeug `check_password_hash` |

**Issue:** Password hashing exists only in a script, not as a reusable utility. Token generation is inline.

### HTML Utilities

| Function | Status |
|----------|--------|
| `strip_tags` | ❌ NOT IMPLEMENTED |
| `linkify` | ❌ NOT IMPLEMENTED |
| `extract_text` | ❌ NOT IMPLEMENTED |

### Hash Utilities

| Function | Status |
|----------|--------|
| `generate_hash` | ❌ NOT IMPLEMENTED |
| `verify_hash` | ❌ NOT IMPLEMENTED |

---

## Bugs and Issues

### Critical Issues

1. **Architecture Document Lacks Accuracy**
   - The `architecture/utils.md` describes a `utils/` module that is ~70% unimplemented
   - Document should either be updated to reflect reality, or missing modules should be implemented
   - Recommendation: Implement missing utilities to match documented design

### High Priority Issues

2. **Layering Violation: DateTime in Services**
   - `services/date_utils.py` contains pure date formatting functions
   - Should be `utils/datetime.py` per architecture
   - **Reference:** `services/date_utils.py:6`

3. **Layering Violation: URL SSRF in Services**
   - `utils/url.py` has `is_valid_url` that delegates to `services.url.validate_url_safe`
   - The delegation imports from services, creating a services→utils dependency
   - **Reference:** `utils/url.py:86`

4. **Fragmented Token Generation**
   - `secrets.token_urlsafe(32)` used inline in multiple locations:
     - `routes/admin/auth.py` (likely)
     - `models/newsletter.py` (unsubscribe_token)
   - No central `utils/security.py::generate_token()`
   - Creates inconsistency and potential security issues

### Medium Priority Issues

5. **XML Escaping vs Text Processing Mismatch**
   - `utils/text.py` contains XML escaping functions, not the documented `truncate`, `sanitize_html`, `extract_hashtags`
   - The XML escaping is legitimate and used throughout codebase (20+ imports found)
   - **Resolution needed:** Either rename module, update docs, or implement the missing functions alongside existing ones

6. **No `utils/` Package Documentation**
   - `utils/__init__.py` is empty (0 bytes)
   - No docstring explaining what belongs in utils vs services
   - **Reference:** `utils/__init__.py`

### Low Priority Issues

7. **Date Formatting Duplicated**
   - `services/date_utils.py` has `format_date`
   - `app.py:285` has `format_date_filter` (Jinja filter)
   - Potential for divergence if modified independently

---

## Specific Improvement Recommendations

### 1. Implement `utils/datetime.py` (Move from services)

```python
# utils/datetime.py
"""Date/time utilities - pure functions with no external dependencies."""

from datetime import datetime, timezone

def parse_date(date_str: str) -> datetime | None:
    """Parse various date formats (RFC 2822, ISO 8601, common formats)."""
    # Implementation needed
    
def format_date(dt: datetime, format: str = "%Y-%m-%d") -> str:
    """Format datetime to string."""
    # Move from services/date_utils.py
    
def time_ago(dt: datetime) -> str:
    """Return human-readable time difference ('2 hours ago', '3 days ago')."""
    # Move from services/date_utils.py
```

**Reference:** `services/date_utils.py:6-59`

### 2. Implement `utils/text.py` Content Completion

Option A: Add missing functions alongside existing XML escaping:
```python
# Add to utils/text.py
def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on words."""
    
def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags and attributes."""
    
def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text."""
```

Option B: Update architecture doc to reflect actual XML escaping purpose.

**Recommendation:** Option A - implement documented functions to complete the module.

### 3. Create `utils/security.py`

```python
# utils/security.py
"""Security utilities - pure functions for cryptographic operations."""

import secrets

def generate_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(length)

def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (timing attack prevention)."""
    import hmac
    return hmac.compare_digest(a, b)
    
# Note: hash_password/verify_password could use werkzeug or passlib
# but that adds dependency. Consider if these belong in utils or services.
```

**Impact:** Replace scattered inline `secrets.token_urlsafe(32)` calls throughout codebase.

### 4. Create `utils/hash.py`

```python
# utils/hash.py
"""Hashing utilities - pure functions for data hashing."""

import hashlib

def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash of data."""
    
def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool:
    """Verify hash matches data."""
```

### 5. Create `utils/html.py`

```python
# utils/html.py
"""HTML processing utilities."""

import re

def strip_tags(html: str) -> str:
    """Remove all HTML tags."""
    
def linkify(text: str) -> str:
    """Convert URLs to clickable links."""
    
def extract_text(html: str) -> str:
    """Extract readable text from HTML (uses trafilatura fallback)."""
    # This may need trafilatura dependency - consider if it belongs in utils or adapters
```

### 6. Document `utils/ipc.py` Status

Either:
- Implement if Redis pub/sub helpers are needed as pure utilities
- Update `architecture/utils.md` to mark as "not planned"

### 7. Fix `is_valid_url` Layering

Current `utils/url.py:80-92` imports from services:
```python
def is_valid_url(url: str) -> bool:
    from services.url import validate_url_safe  # Services import from utils - layering violation
```

**Options:**
1. Move validation logic into `utils/url.py` as a pure function (but it needs DNS resolution - not pure)
2. Accept the delegation as a thin wrapper and document the exception
3. Create a proper adapter pattern

**Recommendation:** Option 2 - document that `is_valid_url` is a thin wrapper that legitimately imports from services due to SSRF protection requirements.

### 8. Add Package Docstring to `utils/__init__.py`

```python
"""Pure utility functions with minimal dependencies.

This package should contain only pure functions with no side effects.
For utilities requiring I/O (network, filesystem, etc.), use services/.

Design Principles:
1. Pure functions: No side effects, no global state
2. Minimal dependencies: Only standard library + very common packages
3. Comprehensive validation: Input checking with clear errors
4. Type hints: Full typing for better IDE support
5. Testable: Easy to unit test without mocking complex systems
"""
```

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | Update `architecture/utils.md` to reflect actual state | Low | Documentation accuracy |
| P1 | Implement `utils/datetime.py` (move from services) | Medium | Layering compliance |
| P2 | Implement `utils/text.py` missing functions (`truncate`, `sanitize_html`, `extract_hashtags`) | Medium | Feature completeness |
| P3 | Create `utils/security.py` with `generate_token`, `constant_time_compare` | Medium | Code consistency |
| P3 | Create `utils/hash.py` with `generate_hash`, `verify_hash` | Low | Feature completeness |
| P3 | Create `utils/html.py` with `strip_tags`, `linkify`, `extract_text` | Medium | Feature completeness |
| P3 | Document or implement `utils/ipc.py` | Low | Documentation |
| P3 | Add docstring to `utils/__init__.py` | Low | Documentation |
| P3 | Standardize token generation throughout codebase | Medium | Security consistency |

---

## Tests to Add

| Function | Test File | Coverage Needed |
|----------|-----------|------------------|
| `get_domain` | `tests/test_url.py` | Existing tests don't cover `get_domain` |
| `truncate` | `tests/test_text.py` (new) | Word boundary breaking |
| `sanitize_html` | `tests/test_text.py` (new) | Dangerous tag removal |
| `extract_hashtags` | `tests/test_text.py` (new) | Hashtag extraction |
| `generate_hash` | `tests/test_hash.py` (new) | Hash generation and verification |
| `constant_time_compare` | `tests/test_security.py` (new) | Timing attack prevention |

---

## Summary

The `utils/` module is significantly under-implemented compared to the architecture document:

| Metric | Value |
|--------|-------|
| Files documented | 7 |
| Files existing | 2 (url, text) |
| Functions documented | ~20 |
| Functions implemented | ~6 (30%) |

**Key Positive Finding:** URL utilities are now complete with SSRF protection properly exposed via `utils/url.py`. The XML escaping functions in `utils/text.py` are well-designed and heavily used throughout the codebase.

**Path Forward:** Either implement missing utilities to match the documented design, or update `architecture/utils.md` to accurately reflect what exists. Given the utility of the documented design, implementing missing pieces is recommended.

---

## References

- Architecture doc: `/home/sugarwookie/projects/ainews/architecture/utils.md`
- Existing URL utils: `/home/sugarwookie/projects/ainews/utils/url.py`
- Existing text utils: `/home/sugarwookie/projects/ainews/utils/text.py`
- Date utils (wrong location): `/home/sugarwookie/projects/ainews/services/date_utils.py`
- SSRF validation (in services): `/home/sugarwookie/projects/ainews/services/url.py`
- Password hashing script: `/home/sugarwookie/projects/ainews/scripts/hash_password.py`
- Previous review: `/home/sugarwookie/projects/ainews/plans/09_utils.md` (outdated after fixes)
