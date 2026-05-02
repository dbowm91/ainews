from unittest.mock import MagicMock, patch

import pytest


def _reset_singletons():
    """Reset all cached singletons to prevent cross-test contamination."""
    from extensions import reset_redis

    reset_redis()
    for module_name, attr, default in [
        ("services.config_cache", "_cache_instance", None),
        ("services.cache", "_cache_instance", None),
        ("services.metrics", "_metrics_instance", None),
        ("schemas.common", "_warned_missing_vars", None),
        ("services.config_unified", "_instance", None),
    ]:
        try:
            mod = __import__(module_name, fromlist=[""])
            if hasattr(mod, attr):
                setattr(mod, attr, default() if callable(default) else default)
        except (ImportError, AttributeError):
            pass
    try:
        from tasks.pipeline import clear_task_fn_cache

        clear_task_fn_cache()
    except (ImportError, AttributeError):
        pass
    # Clear Redis metrics keys
    try:
        from extensions import get_redis
        import redis.exceptions
        redis_client = get_redis()
        if redis_client is not None:
            keys = redis_client.keys("metrics:*")
            if keys:
                redis_client.delete(*keys)
    except (ImportError, AttributeError, redis.exceptions.RedisError):
        pass
    # Clear circuit breaker state
    try:
        from services.circuit_breaker import _breakers
        _breakers.clear()
        from extensions import get_redis
        import redis.exceptions
        redis_client = get_redis()
        if redis_client is not None:
            keys = redis_client.keys("ainews:circuit:*")
            if keys:
                redis_client.delete(*keys)
    except (ImportError, AttributeError, redis.exceptions.RedisError):
        pass


@pytest.fixture(autouse=True)
def _set_celery_task_secret(monkeypatch):
    """Set CELERY_TASK_SECRET for all tests to enable HMAC verification."""
    monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
    yield


@pytest.fixture(autouse=True)
def _reset_redis():
    """Reset the global Redis singleton and config cache between tests."""
    _reset_singletons()
    yield
    _reset_singletons()


@pytest.fixture
def mock_redis():
    """Return a plain MagicMock for tests that need full control over return values."""
    return MagicMock()


@pytest.fixture
def mock_redis_client():
    """Return a MockRedis instance for stateful Redis testing."""
    from tests.mock_redis import MockRedis
    return MockRedis()


@pytest.fixture
def mock_redis_with_eval():
    """Return a MockRedisWithEval instance for login lockout testing."""
    from tests.mock_redis import MockRedisWithEval
    return MockRedisWithEval()


@pytest.fixture
def response_cache_setup(mock_redis_client):
    """Return a ResponseCache with a MockRedis backend."""
    from services.cache import ResponseCache
    cache = ResponseCache()
    cache._redis = mock_redis_client
    return cache


@pytest.fixture(autouse=True)
def _clear_dns_cache():
    """Clear DNS cache between tests to prevent cross-test contamination."""
    try:
        from services.url import clear_dns_cache
    except ImportError:
        yield
        return
    clear_dns_cache()
    yield
    clear_dns_cache()


@pytest.fixture
def mock_celery_tasks():
    """Mock all Celery tasks to prevent actual task execution."""
    with (
        patch("tasks.select.select_article") as mock_select,
        patch("tasks.research.research_article") as mock_research,
        patch("tasks.write.write_article") as mock_write,
        patch("tasks.edit.edit_article") as mock_edit,
    ):
        yield {
            "select": mock_select,
            "research": mock_research,
            "write": mock_write,
            "edit": mock_edit,
        }


@pytest.fixture
def app(monkeypatch):
    """Create a test Flask app using create_app() with monkeypatched env vars."""
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

    from app import create_app

    app = create_app("testing")

    from celery_support import _app_cache, _app_cache_lock

    with _app_cache_lock:
        _app_cache["testing"] = app

    from extensions import limiter

    limiter.enabled = False

    with app.app_context():
        yield app

        from extensions import db

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def hashed_password():
    """Generate a hashed password for testing."""
    from werkzeug.security import generate_password_hash

    return generate_password_hash("testpass123")


@pytest.fixture
def auth_client(app, client, hashed_password):
    """Return an authenticated test client with admin session set."""
    app.config["ADMIN_PASSWORD"] = hashed_password
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


# Test data factory fixtures
@pytest.fixture
def create_source(app):
    """Factory fixture for creating test sources."""
    from tests.factories import create_source

    return create_source


@pytest.fixture
def create_article(app):
    """Factory fixture for creating test articles."""
    from tests.factories import create_article

    return create_article


@pytest.fixture
def create_tag(app):
    """Factory fixture for creating test tags."""
    from tests.factories import create_tag

    return create_tag


@pytest.fixture
def create_subscriber(app):
    """Factory fixture for creating test subscribers."""
    from tests.factories import create_subscriber

    return create_subscriber


@pytest.fixture
def seed_articles(app):
    """Factory fixture for seeding multiple test articles."""
    from tests.factories import seed_articles

    return seed_articles


@pytest.fixture
def create_pipeline_run(app):
    """Factory fixture for creating test pipeline runs."""
    from tests.factories import create_pipeline_run

    return create_pipeline_run


@pytest.fixture
def create_newsletter(app):
    """Factory fixture for creating test newsletters."""
    from tests.factories import create_newsletter

    return create_newsletter


@pytest.fixture
def setup_pipeline_mocks():
    """Shared mock setup for pipeline stage tests with automatic cleanup.

    Yields:
        Dictionary of mock objects. Patches are automatically stopped on cleanup.
    """
    from tests.helpers.pipeline_mocks import setup_pipeline_mocks as _setup

    patches, mocks = _setup()
    yield mocks
    for p in patches.values():
        p.stop()
