# Utils Module Verification & Improvement Plan

## Verification Results

### File Inventory

| Claimed File | Status | Actual Location |
|-------------|--------|-----------------|
| `utils/url.py` | DISCREPANCY | Exists but missing `is_valid_url`, `get_domain`; has `normalize_url`, `normalize_title` |
| `utils/text.py` | DISCREPANCY | Exists but has completely different functions (`esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`) |
| `utils/datetime.py` | MISSING | Does not exist; functions are in `services/date_utils.py` |
| `utils/hash.py` | MISSING | Does not exist |
| `utils/html.py` | MISSING | Does not exist |
| `utils/security.py` | MISSING | Does not exist |
| `utils/ipc.py` | MISSING | Does not exist |

### Function Verification

#### URL Utilities (`utils/url.py`)

| Claimed | Status | Notes |
|---------|--------|-------|
| `normalize_url` | VERIFIED | Exists in `utils/url.py` |
| `is_valid_url` | DISCREPANCY | Function does not exist; SSRF validation is in `services/url.py` as `validate_url_safe` |
| `get_domain` | MISSING | Function does not exist anywhere |

#### Text Utilities (`utils/text.py`)

| Claimed | Status | Notes |
|---------|--------|-------|
| `truncate` | DISCREPANCY | Similar function `truncate_for_log` exists in `constants.py`, not `utils/text.py` |
| `sanitize_html` | MISSING | No implementation found |
| `extract_hashtags` | MISSING | No implementation found |

#### DateTime Utilities

| Claimed | Status | Notes |
|---------|--------|-------|
| `parse_date` | MISSING | No implementation found |
| `format_date` | DISCREPANCY | Exists in `services/date_utils.py` but not in `utils/` |
| `time_ago` | DISCREPANCY | Functionality exists in `services/date_utils.py` but under `format_date` |

#### Security Utilities

| Claimed | Status | Notes |
|---------|--------|-------|
| `generate_token` | DISCREPANCY | Exists as inline `secrets.token_urlsafe(32)` in routes, not as utility function |
| `verify_token` | DISCREPANCY | Exists in `services/totp.py` but is TOTP-specific, not general purpose |
| `constant_time_compare` | MISSING | No implementation found |
| `hash_password` | MISSING | No implementation found |
| `verify_password` | MISSING | No implementation found |

#### HTML Utilities

| Claimed | Status | Notes |
|---------|--------|-------|
| `strip_tags` | MISSING | No implementation found |
| `linkify` | MISSING | No implementation found |
| `extract_text` | MISSING | No implementation found |

#### Hash Utilities

| Claimed | Status | Notes |
|---------|--------|-------|
| `generate_hash` | MISSING | No implementation found |
| `verify_hash` | MISSING | No implementation found |

---

## Bug Findings

### Critical

1. **Architecture Document Lacks Accuracy**
   - The `architecture/utils.md` document describes a `utils/` module that largely does not exist
   - 6 of 7 files are missing or have wrong contents
   - This document appears to be aspirational rather than actual

2. **SSRF Protection Location Wrong**
   - Document claims `is_valid_url` is in `utils/url.py`
   - Actually implemented as `validate_url_safe` in `services/url.py`
   - SSRF validation has proper blocking of private IPs, DNS rebinding protection, DNS caching
   - **Positive**: Actual SSRF implementation is robust, just in wrong location per doc

### High

3. **Pure Function Violations in `services/url.py`**
   - `validate_url_safe` is NOT a pure function despite being in a "utils-style" service
   - Global state: `_dns_cache`, `_dns_cache_lock`, `_dns_executor`
   - DNS cache with TTL introduces non-deterministic behavior
   - Thread pool executor is shared state

4. **No `get_domain` Utility**
   - Many places may need domain extraction
   - Document claims it exists but it does not
   - Could lead to inconsistent domain extraction logic

### Medium

5. **`utils/text.py` Wrong Contents**
   - Document claims `truncate`, `sanitize_html`, `extract_hashtags`
   - Actual functions are `esc_xml_text`, `esc_xml_attr`, `escape_prompt_data`
   - These are valid utilities but different purpose (XML escaping for LLM prompts)

6. **Security Utilities Fragmented**
   - `generate_token` is inlined in multiple places (`secrets.token_urlsafe(32)`)
   - `verify_token` exists but is TOTP-specific in `services/totp.py`
   - No central security utility module

### Low

7. **DateTime Logic in Two Places**
   - `services/date_utils.py` has `format_date`
   - `app.py` has `format_date_filter` (Jinja filter)
   - Potential for divergence

8. **No `utils/` Package Docstring**
   - `utils/__init__.py` is empty
   - No documentation of what belongs in utils

---

## Improvement Opportunities

### 1. Align Architecture Document with Reality

**Option A**: Update `architecture/utils.md` to reflect actual state
**Option B**: Implement missing utilities to match document

Recommendation: **Option B** - The architecture document describes a well-designed utils layer that would improve code organization.

### 2. Implement Missing Utils

| File | Functions to Add |
|------|------------------|
| `utils/url.py` | Add `is_valid_url()` wrapper that calls `services.url.validate_url_safe`, add `get_domain()` |
| `utils/text.py` | Add `truncate()`, `sanitize_html()`, `extract_hashtags()` |
| `utils/datetime.py` | Create with `parse_date()`, `format_date()`, `time_ago()` (move from services) |
| `utils/security.py` | Create with `generate_token()`, `constant_time_compare()`, `hash_password()`, `verify_password()` |
| `utils/html.py` | Create with `strip_tags()`, `linkify()`, `extract_text()` |
| `utils/hash.py` | Create with `generate_hash()`, `verify_hash()` |
| `utils/ipc.py` | Document as "no plans" or implement if needed |

### 3. Clean Up Service/Utils Boundary

- Move pure date utilities from `services/date_utils.py` to `utils/datetime.py`
- The SSRF validation should stay in `services/url.py` (requires network I/O)
- Consider moving `services/totp.py` security functions to `utils/security.py`

### 4. Add Utils Package Documentation

```python
# utils/__init__.py
"""Pure utility functions with minimal dependencies.

This package should contain only pure functions with no side effects.
For utilities requiring I/O (network, filesystem, etc.), use services/.
"""
```

### 5. Standardize Token Generation

- Create `utils/security.py::generate_token()` as single implementation
- Replace inline `secrets.token_urlsafe(32)` calls throughout codebase

---

## Action Items

| Priority | Item | Owner |
|----------|------|-------|
| P0 | Update `architecture/utils.md` to accurately reflect current state | Architecture |
| P1 | Implement `utils/url.py::is_valid_url()` as wrapper for `services.url.validate_url_safe` | Core |
| P1 | Implement `utils/url.py::get_domain()` function | Core |
| P2 | Implement `utils/text.py::truncate()`, `sanitize_html()`, `extract_hashtags()` | Core |
| P2 | Move `services/date_utils.py` content to `utils/datetime.py` | Core |
| P2 | Create `utils/security.py` with `generate_token()`, `constant_time_compare()`, `hash_password()`, `verify_password()` | Core |
| P3 | Implement `utils/html.py::strip_tags()`, `linkify()`, `extract_text()` | Core |
| P3 | Implement `utils/hash.py::generate_hash()`, `verify_hash()` | Core |
| P3 | Standardize all token generation to use `utils/security.py::generate_token()` | Refactor |
| P3 | Add package docstring to `utils/__init__.py` | Documentation |

---

## Summary

The architecture document at `architecture/utils.md` describes a utils layer that is **~85% unimplemented**. The actual `utils/` directory contains only 2 files with partial functionality. Many claimed functions are scattered across `services/`, `routes/`, and `constants.py`.

**Key Positive Finding**: The actual SSRF protection in `services/url.py` is well-implemented with proper DNS caching, private IP blocking, and DNS rebinding prevention. It just needs to be exposed through the `utils/` interface as documented.

**Recommended Approach**: Complete the utils layer implementation to match the architecture document, which will improve code organization and make the documented interface actually available.
