"""Vector embedding generation for articles."""

import json
import logging

logger = logging.getLogger(__name__)

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer

    _model = None
    _model_name = "all-MiniLM-L6-v2"

    def _get_model():
        global _model
        if _model is None:
            _model = SentenceTransformer(_model_name)
        return _model

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


def generate_embedding(text: str, fallback_dim: int = 384) -> list[float] | None:
    """Generate a vector embedding for the given text.

    Args:
        text: The text to embed.
        fallback_dim: Dimension of the fallback zero vector if library unavailable.

    Returns:
        A list of floats representing the embedding, or None on failure.
    """
    if not text or not text.strip():
        return None

    if SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            model = _get_model()
            embedding = model.encode(text, show_progress_bar=False)
            return embedding.tolist()
        except Exception as e:
            logger.warning("Embedding generation failed: %s", e)
            return None
    else:
        logger.warning("sentence-transformers not available, skipping embedding")
        return None


def serialize_embedding(embedding: list[float]) -> str:
    """Serialize embedding to JSON string for database storage."""
    return json.dumps(embedding)


def deserialize_embedding(embedding_str: str) -> list[float] | None:
    """Deserialize embedding from JSON string."""
    if not embedding_str:
        return None
    try:
        return json.loads(embedding_str)
    except (json.JSONDecodeError, TypeError):
        return None
