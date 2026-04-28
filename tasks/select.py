from datetime import datetime, timezone
import hashlib
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus, truncate_for_log
from services.llm.errors import ProviderServerError
from services.task_security import verify_task

logger = get_task_logger(__name__)

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


def _assign_experiment_group(article_id: int, salt: str = "") -> str:
    """Assign experiment group using hash of article_id + salt for deterministic assignment."""
    from services.config_unified import get_config

    config = get_config()
    experiments = config.get("experiments", {})
    if not experiments.get("enabled", False):
        return "control"

    prompt_variants = experiments.get("prompt_variants", {})
    if not prompt_variants:
        return "control"

    # Use hash for deterministic assignment
    hash_input = f"{article_id}:{salt}:experiment"
    hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)

    # 70% control, 15% variant_a, 15% variant_b
    bucket = hash_val % 100
    if bucket < 70:
        return "control"
    elif bucket < 85:
        return "variant_a"
    else:
        return "variant_b"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def select_article(self, article_id: int, run_id=None):
    try:
        from schemas.tasks import SelectArticleTask
        validated = SelectArticleTask(article_id=article_id, run_id=run_id)
    except Exception as e:
        logger.warning("Invalid select_article input: %s", e)
        raise TypeError(f"Invalid select_article input: {e}") from e

    if not verify_task("select_article", (validated.article_id,), {"run_id": validated.run_id}):
        logger.error("Invalid signature for select_article task")
        raise ValueError("Invalid task signature")

    article_id = validated.article_id
    run_id = validated.run_id

    def work(article, provider, model, max_tokens):
        from extensions import db
        from models import PipelineRun
        from schemas.llm_responses import SelectionResult
        from schemas.pipeline import get_role_config
        from services.prompts import esc_xml_text, get_system_prompt
        from tasks.pipeline import _dispatch_next, _log_pipeline, _transition_article_status

        rc = get_role_config("selector")
        text_preview = (article.extracted_text or article.original_title or "")[:500]
        prompt = (
            f"<article>\n"
            f"<title>{esc_xml_text(article.original_title or '')}</title>\n"
            f"<topics>{esc_xml_text(', '.join(article.topics or []))}</topics>\n"
            f"<preview>{esc_xml_text(text_preview)}</preview>\n"
            f"</article>\n\n"
            "Should we write a condensed news article about this? "
            "Score 1-10 for newsworthiness to a tech audience. "
            "Also rate your confidence in this selection as low, medium, or high. "
            "Return JSON with selected (bool), score (1-10), reason (string), confidence (low|medium|high)."
        )

        from services.logging_utils import traced_llm_call
        from services.metrics import time_histogram

        with traced_llm_call(provider=provider.__class__.__name__, model=model, stage="select"):
            with time_histogram(
                "pipeline.stage_duration_seconds", labels={"stage": "select"}
            ):
                result = provider.chat_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=SelectionResult,
                    model=model,
                    system=get_system_prompt("selector", rc.system_prompt),
                    temperature=rc.temperature,
                    max_tokens=max_tokens,
                    stage="select",
                )

        article.selector_result = result.model_dump()

        # A/B experiment assignment (if experiments configured)
        from services.config_unified import get_config
        config = get_config()
        experiments = config.get("experiments", {})
        if experiments.get("enabled", False):
            salt = experiments.get("assignment_salt", "")
            group = _assign_experiment_group(article.id, salt)
            article.experiment_group = group
            logger.info("Assigned article %s to experiment group: %s", article.id, group)

        if result.selected and result.score >= (rc.min_score or 6):
            if result.confidence == "low":
                _transition_article_status(article, PipelineStatus.REVIEW)
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    raise
                if run_id:
                    _log_pipeline(
                        run_id,
                        "select",
                        "info",
                        "Low-confidence selected [%s/10]: %s",
                        result.score,
                        truncate_for_log(article.original_title),
                        article_id=article.id,
                    )
                _dispatch_next(
                    article_id, run_id=run_id, next_status=PipelineStatus.REVIEW
                )
            else:
                _transition_article_status(article, PipelineStatus.RESEARCHING)
                article.selected_at = datetime.now(timezone.utc).replace(tzinfo=None)
                if run_id:
                    run = db.session.get(PipelineRun, run_id)
                    if run:
                        run.articles_selected = (run.articles_selected or 0) + 1
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    raise
                if run_id:
                    _log_pipeline(
                        run_id,
                        "select",
                        "info",
                        "Selected [%s/10]: %s",
                        result.score,
                        truncate_for_log(article.original_title),
                        article_id=article.id,
                    )
                _dispatch_next(
                    article_id, run_id=run_id, next_status=PipelineStatus.RESEARCHING
                )
        else:
            _transition_article_status(article, PipelineStatus.SKIPPED)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                raise

            if run_id:
                _log_pipeline(
                    run_id,
                    "select",
                    "info",
                    "Skipped [%s/10]: %s",
                    result.score,
                    truncate_for_log(article.original_title),
                    article_id=article.id,
                )

            return {"article_id": article_id, "result": article.selector_result}

    from tasks.pipeline import run_stage
    return run_stage(
        "selector",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next=PipelineStatus.RESEARCHING,
        retry_countdown=15,
        retry_max=20,
    )