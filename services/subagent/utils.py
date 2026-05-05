import logging
import time

from utils.text import escape_prompt_data

logger = logging.getLogger(__name__)


def _retry_with_backoff(func, max_retries, base_delay=1.0, max_delay=30.0, retryable_exceptions=Exception):
    for attempt in range(max_retries):
        try:
            return func()
        except retryable_exceptions:
            if attempt == max_retries - 1:
                raise
            time.sleep(min(base_delay * 2**attempt, max_delay))


def _is_task_revoked() -> bool:
    try:
        from celery import current_task

        if current_task and not current_task.request.called_directly:
            return current_task.request.is_effectively_revoked()
    except ImportError:
        pass
    return False


def _format_subagent_prompt(template: str, prompt_data: dict, stage: str, task_type: str) -> str | None:
    try:
        prompt_data_escaped = escape_prompt_data(prompt_data)
        return template.format(**prompt_data_escaped)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        return None
