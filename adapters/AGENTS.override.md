# Adapters Agent Context

## Adapter Types
- **RSSAdapter:** Creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`. Independent session management.
- **APIAdapter:** Uses shared global session from `get_crawl_session()`. Does NOT have pagination support yet.
- **WebAdapter:** Uses shared global session from `get_crawl_session()`.

## SSRFSafeRedirectHandler
- Uses thread-local storage for `_redirect_count` to prevent cross-request accumulation.
- Validates redirects: blocks internal IPs, private hostnames, and scheme-relative URLs (`//evil.com`).
- Blocklist check happens at redirect time, not just initial validation.

## APIAdapter Implementation Notes
The `APIAdapter` in `adapters/api.py`:
- Does NOT have pagination support - only makes single requests to `list_url`
- Supports these filter operations: `equals`, `min`, `exists`
- Does NOT support `contains` operation
- Only supports Bearer token authentication (no API key header support)
- Uses `list_items_path` and `list_method` (NOT `item_path`)

## Authentication
- APIAdapter only supports Bearer token authentication.
- No API key header support (e.g., `X-Api-Key`) implemented yet.

## Session Independence
- RSSAdapter creates its own session - BY DESIGN for different session management requirements.
- APIAdapter and WebAdapter share global session from `get_crawl_session()`.

## Config Loading
Config is loaded via `adapters/base.py:46`:
```python
if self.config_class and source_config.config:
    self.adapter_config = self.config_class(**source_config.config)
```
The config_class varies by adapter type (RSSConfig, APIConfig, WebConfig).