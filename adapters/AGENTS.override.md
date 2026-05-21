# Adapters Agent Context

## Adapter Types
- **RSSAdapter:** Creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`. Independent session management.
- **APIAdapter:** Uses shared global session from `get_crawl_session()`. Does NOT have pagination support yet (MED-11 in plan).
- **WebAdapter:** Uses shared global session from `get_crawl_session()`.

## SSRFSafeRedirectHandler
- Uses thread-local storage for `_redirect_count` to prevent cross-request accumulation.
- Validates redirects: blocks internal IPs, private hostnames, and scheme-relative URLs (`//evil.com`).
- Blocklist check happens at redirect time, not just initial validation.

## APIAdapter Pagination (MED-11 - PENDING)
The `APIAdapter` in `adapters/api.py` currently has NO pagination support. It only makes single requests to `list_url`. Implementation needed:
- Supports pagination via `PaginationConfig` with modes: `next_link`, `query_param`, `none`
- Filter operations: `equals`, `min`, `exists`, `contains`
- Uses `list_items_path` and `list_method` (NOT `item_path`)

## Authentication
- APIAdapter only supports Bearer token authentication.
- No API key header support (e.g., `X-Api-Key`) implemented yet.

## Session Independence
- RSSAdapter creates its own session - BY DESIGN for different session management requirements.
- APIAdapter and WebAdapter share global session from `get_crawl_session()`.