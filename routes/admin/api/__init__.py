import logging

from routes.admin import admin_api_bp as admin_api_bp
from routes.admin import require_auth as require_auth

from routes.admin.api import (
    alerts as alerts,
    articles as articles,
    audit as audit,
    config as config,
    health as health,
    newsletter as newsletter,
    pipeline as pipeline,
    quality as quality,
    replay as replay,
    search as search,
    source_intelligence as source_intelligence,
    sources as sources,
    theme_diagnostics as theme_diagnostics,
    topic_gap as topic_gap,
    webhooks as webhooks,
)

logger = logging.getLogger(__name__)
