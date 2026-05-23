import logging
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def generate_embedding(text: str) -> list[float]:
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    if isinstance(embedding, np.ndarray):
        return embedding.tolist()
    return embedding
