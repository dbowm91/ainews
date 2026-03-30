import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_redis():
    """Reset the global Redis singleton and config cache between tests."""
    from extensions import reset_redis

    reset_redis()
    try:
        from services import config_cache

        config_cache._cache_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from services import cache

        cache._cache_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from services import metrics

        metrics._metrics_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from schemas.common import _warned_missing_vars

        _warned_missing_vars.clear()
    except (ImportError, AttributeError):
        pass
    yield
    reset_redis()
    try:
        from services import config_cache

        config_cache._cache_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from services import cache

        cache._cache_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from services import metrics

        metrics._metrics_instance = None
    except (ImportError, AttributeError):
        pass
    try:
        from schemas.common import _warned_missing_vars

        _warned_missing_vars.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def _reset_factory_counter():
    """Reset factory ID counter between tests to prevent ID collisions."""
    import tests.factories as factories

    factories._counter = 0
    yield
    factories._counter = 0


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    store = {}

    def get(key):
        return store.get(key)

    def setex(key, ttl, value):
        store[key] = value

    def delete(*keys):
        for k in keys:
            store.pop(k, None)

    def keys(pattern):
        import fnmatch

        return [k for k in store if fnmatch.fnmatch(k, pattern)]

    redis.get = MagicMock(side_effect=get)
    redis.setex = MagicMock(side_effect=setex)
    redis.delete = MagicMock(side_effect=delete)
    redis.keys = MagicMock(side_effect=keys)
    return redis


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
def app():
    """Create a test Flask app with in-memory SQLite."""
    import os

    os.environ["ADMIN_PASSWORD"] = ""
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["FLASK_CONFIG"] = "testing"
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/15"

    from flask import Flask
    from config import Config

    class TestingConfig(Config):
        DEBUG = True
        TESTING = True
        SECRET_KEY = "test-secret-key"
        ADMIN_PASSWORD = ""
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False
        CELERY_BROKER_URL = "memory://"
        CELERY_RESULT_BACKEND = "cache+memory://"

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(TestingConfig)

    from extensions import db, csrf

    # Disable rate limiting in tests
    from extensions import limiter as ext_limiter

    db.init_app(app)
    csrf.init_app(app)
    ext_limiter.enabled = False

    try:
        from flask_migrate import Migrate

        Migrate(app, db)
    except ImportError:
        pass

    import models  # noqa: F401

    with app.app_context():
        db.create_all()

    from routes.public import public_bp
    from routes.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        yield app
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
