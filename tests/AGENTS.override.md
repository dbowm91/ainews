# Testing Conventions

Contextual conventions for agents working in the `tests/` directory.

## Testing Standards

- Use `tests/factories.py` for object creation.
- Ensure `CELERY_TASK_SECRET` is set in environment for tests calling HMAC-signed tasks.
- Catch `redis.exceptions.RedisError` specifically in error-handling tests.

## Test First

Write tests before making changes to ensure the fix is verifiable. Use `tests/factories.py` for test object creation.