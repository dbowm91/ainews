import logging

from flask import Response, jsonify

from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_json
from services.audit import log_admin_action

logger = logging.getLogger(__name__)


@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
@validate_csrf_json
def reload_config() -> tuple[Response, int] | Response:
    from celery_support import clear_app_cache
    from services.config_cache import get_config_cache
    from services.config_unified import reset_config, validate_config
    from services.llm import clear_provider_cache
    from tasks.edit import clear_tag_cache
    from tasks.pipeline import clear_task_fn_cache

    is_valid, errors = validate_config()
    if not is_valid:
        return jsonify({"error": "Config validation failed", "details": errors}), 400

    get_config_cache().invalidate_all()
    clear_provider_cache()
    clear_app_cache()
    reset_config()
    clear_task_fn_cache()
    clear_tag_cache()

    from celery_app import celery_app
    from config import Config
    Config.reload_beat_schedule(celery_app)

    log_admin_action(
        "config_reload",
        target_type="system",
        target_id=0,
        details={"action": "reload configuration"},
        category="config",
    )

    return jsonify({"message": "Config cache cleared"}), 200


@admin_bp.route("/api/metrics")
@require_auth
def app_metrics() -> Response:
    from services.metrics import get_metrics

    return jsonify(get_metrics().get_metrics())


@admin_bp.route("/api/metrics/prometheus")
@require_auth
def prometheus_metrics() -> Response:
    from flask import Response

    from services.metrics import get_metrics

    return Response(get_metrics().get_prometheus(), mimetype="text/plain")
