import logging

from routes.admin import admin_api_bp as admin_api_bp
from routes.admin import require_auth as require_auth

logger = logging.getLogger(__name__)

from routes.admin.api import (  # noqa: F401, E402
    articles,
    audit,
    config,
    health,
    pipeline,
    search,
    sources,
    webhooks,
)
