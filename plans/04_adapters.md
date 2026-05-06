# Adapters Architecture Verification & Improvement Plan

**Date:** 2026-05-06  
**Type:** Architecture Review  
**Status:** Draft

---

## Executive Summary

Reviewed `architecture/adapters.md` against the actual codebase. Found **5 verified claims**, **4 discrepancies**, and **7 bugs** including 1 critical syntax error that would prevent import.

---

## Verification Results

### File Inventory
| Claim | Status | Notes |
|-------|--------|-------|
| `base.py` exists | VERIFIED | ✅ Present |
| `rss.py` exists | VERIFIED | ✅ Present |
| `api.py` exists | VERIFIED | ✅ Present |
| `web.py` exists | VERIFIED | ✅ Present |
| `session.py` exists | VERIFIED | ✅ Present |

### BaseSourceAdapter
| Claim | Status | Notes |
|-------|--------|-------|
| `fetch` abstract method | VERIFIED | ✅ Line 48-49 |
| `parse_item` abstract method | VERIFIED | ✅ Line 51-52 |
| `fetch_and_parse` method | VERIFIED | ✅ Line 54-67 |
| Registry decorator | VERIFIED | ✅ `register_adapter` exists (line 21-26) |

### Registry
| Claim | Status | Notes |
|-------|--------|-------|
| `SOURCE_ADAPTERS` registry | DISCREPANCY | Registry is named `_ADAPTER_REGISTRY` (line 18). Not exported as `SOURCE_ADAPTERS`. |
| `get_adapter_class()` function | VERIFIED | ✅ Present (line 29-33) |

### RSSAdapter
| Claim | Status | Notes |
|-------|--------|-------|
| Uses feedparser | VERIFIED | ✅ Line 44 |
| BeautifulSoup fallback | DISCREPANCY | BeautifulSoup is used for HTML→text extraction (line 71), NOT as fallback for malformed feeds as claimed |
| Feed validation | DISCREPANCY | No feed validation logic found |
| Atom feed support | VERIFIED | feedparser handles Atom |

### APIAdapter
| Claim | Status | Notes |
|-------|--------|-------|
| JSONPath field extraction | VERIFIED | `_resolve_path()` supports `$.path.to.field` (line 136-152) |
| Pagination support | VERIFIED | Has `item_url` pattern for fetching individual items (line 44-54) |
| Auth headers | DISCREPANCY | Document claims "Bearer, API key headers" but no explicit auth header injection found |

### WebAdapter
| Claim | Status | Notes |
|-------|--------|-------|
| CSS selectors | VERIFIED | Uses BeautifulSoup `select()` |
| Pagination | VERIFIED | `_scrape_listing()` handles pagination (line 136-167) |
| **Syntax corruption** | **CRITICAL** | Line 36: `u/a` is corrupted text, would cause `NameError` at runtime |

### SSRF Protection
| Claim | Status | Notes |
|-------|--------|-------|
| Blocks `javascript:` URLs | VERIFIED | `validate_url_safe()` only allows http/https |
| Blocks `data:` URLs | VERIFIED | Same as above |
| Blocks internal IPs | VERIFIED | `_BLOCKED_NETWORKS` list in services/url.py |
| `SSRFSafeRedirectHandler` class | VERIFIED | Present in session.py |

---

## Bug Findings

### Critical (Must Fix)

#### C-1: Syntax Corruption in web.py (HIGH)
**File:** `adapters/web.py` line 36  
**Issue:** Corrupted syntax: `u/a if u/a != "AINwsBot/1.0" else USER_AGENTS[index]`  
**Impact:** Module would fail to import with `NameError: name 'u' is not defined`  
**Fix:** Replace line 35-37 with proper ternary:
```python
self._session.headers["User-Agent"] = (
    ua if ua != "AINewsBot/1.0" else USER_AGENTS[index]
)
```

#### C-2: Clean Layering Violation - base.py imports from services
**File:** `adapters/base.py` line 80  
**Issue:** `match_topics()` imports `from services.trend_detector import classify`  
**Impact:** Adapters layer depends on services layer, violating architecture rules  
**Fix:** Move `classify` function to `utils/` or accept topic matching is a valid adapter responsibility that should use pure functions

### High

#### H-1: Registry Name Mismatch
**File:** `adapters/base.py` line 18  
**Issue:** Document claims `SOURCE_ADAPTERS` but actual is `_ADAPTER_REGISTRY`  
**Fix:** Either update document or add alias `SOURCE_ADAPTERS = _ADAPTER_REGISTRY` for compatibility

#### H-2: RSSAdapter Missing Malformed Feed Fallback
**File:** `adapters/rss.py`  
**Issue:** Document claims fallback to requests+BeautifulSoup for malformed feeds, but no such fallback exists  
**Fix:** Implement `_scrape_feed()` fallback method or update document

#### H-3: web.py imports from services.config_unified
**File:** `adapters/web.py` line 109  
**Issue:** `from services.config_unified import MIN_CONTENT_LENGTH` violates layering  
**Fix:** Define `MIN_CONTENT_LENGTH` as a constant in adapters or accept as a config injection

### Medium

#### M-1: APIAdapter Missing Explicit Auth Headers
**File:** `adapters/api.py`  
**Issue:** Document claims "Bearer token, API key headers" but no explicit auth injection  
**Fix:** Implement auth header support in APIAdapter or update document

#### M-2: Missing Feed Validation in RSSAdapter
**File:** `adapters/rss.py`  
**Issue:** Document lists "Feed validation and normalization" but no validation code found  
**Fix:** Add validation or remove from document

#### M-3: RSSAdapter Has No Malformed Feed Fallback
**File:** `adapters/rss.py`  
**Issue:** `fetch()` only uses feedparser, no BeautifulSoup fallback for malformed feeds  
**Fix:** Implement `_scrape_feed()` method or update document

### Low

#### L-1: Missing `__all__` in adapters/__init__.py
**File:** `adapters/__init__.py`  
**Issue:** No explicit exports  
**Fix:** Add `__all__ = ["RSSAdapter", "APIAdapter", "WebAdapter", "get_adapter_class"]`

#### L-2: session.py Uses Module-Level Global State
**File:** `adapters/session.py`  
**Issue:** `_CRAWL_SESSION` global with lazy initialization  
**Fix:** Acceptable pattern but could be documented

---

## Improvement Opportunities

### I-1: Extract URL Validation to Utils
`validate_url_safe()` is in `services/url.py` but used by adapters. Per Wave 2.1 directive to keep utils pure, consider:
- Moving core IP blocking logic to `utils/url.py`  
- Keeping DNS resolution in `services/url.py`

### I-2: Standardize Adapter Configuration
- All adapters use different config patterns (RSSConfig, APIConfig, WebConfig)
- Consider base config schema

### I-3: Document Error Handling Patterns
Document claims "consistent error handling" but implementations vary:
- RSSAdapter: uses `raise_for_status()` + exceptions
- APIAdapter: catches `RequestException` in `_fetch_item()` only  
- WebAdapter: catches multiple exception types, returns empty list on failure

### I-4: Add Type Annotations
Several methods lack return type annotations:
- `parse_item()` returns `Optional[RawItem]`
- `_resolve_path()` returns `Any`

---

## Action Items

| Priority | Item | Owner | Estimate |
|----------|------|-------|----------|
| P0 | Fix web.py syntax corruption (line 35-37) | Agent | 5 min |
| P0 | Remove services import from base.py match_topics() | Agent | 15 min |
| P1 | Add `SOURCE_ADAPTERS` alias in base.py | Agent | 2 min |
| P1 | Implement RSS malformed feed fallback or update doc | Agent | 30 min |
| P1 | Move services.config_unified import to constant in web.py | Agent | 5 min |
| P2 | Add explicit auth headers support in APIAdapter | Agent | 20 min |
| P2 | Add feed validation in RSSAdapter | Agent | 15 min |
| P3 | Add `__all__` exports to adapters/__init__.py | Agent | 2 min |
| TBD | Document error handling standardization | Agent | 1 hour |

---

## Files Reviewed

- `/home/sugarwookie/projects/ainews/architecture/adapters.md`
- `/home/sugarwookie/projects/ainews/adapters/base.py`
- `/home/sugarwookie/projects/ainews/adapters/rss.py`
- `/home/sugarwookie/projects/ainews/adapters/api.py`
- `/home/sugarwookie/projects/ainews/adapters/web.py`
- `/home/sugarwookie/projects/ainews/adapters/session.py`
- `/home/sugarwookie/projects/ainews/adapters/__init__.py`
- `/home/sugarwookie/projects/ainews/services/url.py`
