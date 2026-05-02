import time


def _retry_with_backoff(func, max_retries, base_delay=1.0, max_delay=30.0, retryable_exceptions=Exception):
    for attempt in range(max_retries):
        try:
            return func()
        except retryable_exceptions:
            if attempt == max_retries - 1:
                raise
            time.sleep(min(base_delay * 2**attempt, max_delay))
