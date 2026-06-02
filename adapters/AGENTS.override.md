# Adapters Agent Context

## Adapter Types
- **RSSAdapter:** Creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`. Independent session management.
- **APIAdapter:** Uses shared global session from `get_crawl_session()`. Has pagination support via `PaginationConfig`.
- **WebAdapter:** Uses shared global session from `get_crawl_session()`.

## SSRFSafeRedirectHandler
- Uses thread-local storage for `_redirect_count` to prevent cross-request accumulation.
- Validates redirects: blocks internal IPs, private hostnames, and scheme-relative URLs (`//evil.com`).
- Blocklist check happens at redirect time, not just initial validation.
- **Known Bug:** `__call__` at `adapters/session.py:54` returns the original request object instead of a redirect-modified request. The redirect URL is validated but the return value is misleading. Works in practice due to requests library internals. Fix: should return a new `PreparedRequest` with the redirect URL set, or `None` to skip.

## APIAdapter Implementation Notes
The `APIAdapter` in `adapters/api.py`:
- Has pagination support via `PaginationConfig` (added in MED-11):
  - `next_link` type: extracts next URL from JSON response via JSONPath
  - `query_param` type: increments page/offset query param
  - `none` type: disables pagination
  - Respects `max_pages` limit (default 3) and `max_items` limit across all pages
- Supports filter operations: `equals`, `min`, `exists`, `contains`
- Only supports Bearer token authentication (no API key header support)
- Uses `list_items_path` and `list_method` (NOT `item_path`)

## Authentication
- APIAdapter only supports Bearer token authentication.
- No API key header support (e.g., `X-Api-Key`) implemented yet.

## Session Independence
- RSSAdapter creates its own session - BY DESIGN for different session management requirements.
- APIAdapter and WebAdapter share global session from `get_crawl_session()`.
- APIAdapter and WebAdapter implement `close()` as no-ops (empty pass). They do NOT close the shared global session because doing so would break other adapters using the same session.
- RSSAdapter closes its own session in `close()`.

## Config Loading
Config is loaded via `adapters/base.py:46`:
```python
if self.config_class and source_config.config:
    self.adapter_config = self.config_class(**source_config.config)
```
The config_class varies by adapter type (RSSConfig, APIConfig, WebConfig).