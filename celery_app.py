import os

from celery import Celery, Task
from celery.signals import before_task_publish

from celery_support import _app_cache, _app_cache_lock

# Celery CLI (`celery -A celery_app:celery_app`) requires a fully-configured
# module-level celery_app. We initialize at import time for that reason.
# Each task execution uses its own app_context() via FlaskTask.__call__,
# which is safe since Flask apps are thread-safe for read operations.
from logging_config import request_id_var

_celery = Celery("ainews")


class FlaskTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        # Set request ID from Celery headers into logging context
        request_id = None
        if hasattr(self, "request") and self.request and self.request.headers:
            request_id = self.request.headers.get("X-Request-ID")
        token = None
        if request_id:
            token = request_id_var.set(request_id)

        config_name = os.environ.get("FLASK_CONFIG", "development")
        if config_name not in _app_cache:
            with _app_cache_lock:
                if config_name not in _app_cache:
                    from app import create_app

                    _app_cache[config_name] = create_app(config_name)
        app = _app_cache[config_name]
        with app.app_context():
            try:
                return self.run(*args, **kwargs)
            finally:
                from extensions import db

                db.session.remove()
                if token is not None:
                    request_id_var.reset(token)


@before_task_publish.connect
def inject_request_id(headers=None, **kwargs):
    """Inject request ID from Flask context into Celery task headers."""
    if headers is None:
        return
    # Get request ID from current logging context (set by RequestIDMiddleware)
    request_id = request_id_var.get()
    if request_id and "X-Request-ID" not in headers:
        headers["X-Request-ID"] = request_id


def _init_celery():
    from app import create_app

    app = create_app()
    _celery.config_from_object(app.config, namespace="CELERY")
    _celery.Task = FlaskTask

    import tasks.crawl  # noqa: F401
    import tasks.edit  # noqa: F401
    import tasks.extract  # noqa: F401
    import tasks.newsletter  # noqa: F401
    import tasks.pipeline  # noqa: F401
    import tasks.research  # noqa: F401
    import tasks.retry  # noqa: F401
    import tasks.select  # noqa: F401
    import tasks.write  # noqa: F401

    app.extensions["celery"] = _celery


# Initialize on import so Celery CLI (`celery -A celery_app:celery_app`) works
_init_celery()
celery_app = _celery
