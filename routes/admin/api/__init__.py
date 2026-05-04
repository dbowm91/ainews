import logging

from routes.admin import admin_api_bp as admin_api_bp
from routes.admin import require_auth as require_auth

from routes.admin.api import (
    articles as articles,
    audit as audit,
    config as config,
    health as health,
    pipeline as pipeline,
    search as search,
    sources as sources,
    webhooks as webhooks,
)

logger = logging.getLogger(__name__)
