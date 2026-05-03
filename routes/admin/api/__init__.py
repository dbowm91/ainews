import logging

from routes.admin import admin_api_bp as admin_api_bp
from routes.admin import require_auth as require_auth

from routes.admin.api import (
    articles,
    audit,
    config,
    health,
    pipeline,
    search,
    sources,
    webhooks,
)

logger = logging.getLogger(__name__)
