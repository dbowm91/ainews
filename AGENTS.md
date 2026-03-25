# AGENTS.md

Conventions for AI coding agents working in this codebase.

## Run before committing

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

## Key conventions

### LLM prompt building

All externally-sourced content (article text, titles, URLs, web search results) must be XML-delimited and escaped before embedding in LLM prompts. Use the shared helpers in `services/prompts.py`:

```python
from services.prompts import esc_xml_text, esc_xml_attr

# Text content inside XML tags
f"<title>{esc_xml_text(title)}</title>"

# Values inside XML attributes
f"<citation title='{esc_xml_attr(c.get('title', ''))}' />"
```

### URL fetching

All outbound HTTP requests must validate URLs against private IP ranges via `services/url.py:validate_url_safe()` to prevent SSRF. Catch `UnsafeURLError` to handle blocked URLs gracefully.

### Database transactions

Wrap `db.session.commit()` in try/except with `db.session.rollback()` in the except block. Never leave commits unguarded in route handlers.

### Environment variables

Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders in config. It returns an empty string (not the raw placeholder) for missing vars, with deduplicated warnings.

### Rate limiting

`ModelLimiter` in `services/limiter.py` fails closed on Redis errors — returns `False` to deny slots when Redis is unavailable. This is intentional for LLM pipeline stages.

### ASGI deployment

`run.py` exports `WsgiToAsgi(flask_app)` as the module-level `app` variable for granian. Flask remains WSGI internally; the adapter runs it in a thread pool behind granian's async event loop. Do not remove the `WsgiToAsgi` wrapper — granian and systemd are configured for `--interface asgi`.
