# Search Services Conventions

Contextual conventions for agents working in the `services/search/` directory.

## ThreadPoolExecutor Pattern

Blocking I/O uses ThreadPoolExecutor to avoid blocking Celery workers. Applied in `searxng.py`, `google.py`, `duckduckgo.py`. Module-level singleton executor with `submit()` + `future.result(timeout=N)`.