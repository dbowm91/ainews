import logging

from routes.admin import admin_bp as admin_bp, require_auth as require_auth

logger = logging.getLogger(__name__)

from routes.admin.api import (  # noqa: E402, F401
    health,
    config,
    pipeline,
    articles,
    webhooks,
    audit,
    search,
)
