from celery import Celery, Task
import os

# Celery CLI (`celery -A celery_app:celery_app`) requires a fully-configured
# module-level celery_app. We initialize at import time for that reason.
# Each task execution uses its own app_context() via FlaskTask.__call__,
# which is safe since Flask apps are thread-safe for read operations.

_celery = Celery("ainews")
_app_cache = {}


class FlaskTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        config_name = os.environ.get("FLASK_CONFIG", "development")
        if config_name not in _app_cache:
            from app import create_app
            _app_cache[config_name] = create_app(config_name)
        app = _app_cache[config_name]
        with app.app_context():
            return self.run(*args, **kwargs)


def _init_celery():
    from app import create_app
    app = create_app()
    _celery.config_from_object(app.config, namespace="CELERY")
    _celery.Task = FlaskTask

    import tasks.pipeline  # noqa: F401
    import tasks.crawl  # noqa: F401
    import tasks.extract  # noqa: F401
    import tasks.select  # noqa: F401
    import tasks.research  # noqa: F401
    import tasks.write  # noqa: F401
    import tasks.edit  # noqa: F401
    import tasks.retry  # noqa: F401
    import tasks.newsletter  # noqa: F401

    app.extensions["celery"] = _celery


# Initialize on import so Celery CLI (`celery -A celery_app:celery_app`) works
_init_celery()
celery_app = _celery
