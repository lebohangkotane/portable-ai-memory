"""Local embedding generation for semantic search.

Uses sentence-transformers with a small, fast model (all-MiniLM-L6-v2, ~80MB)
that runs entirely locally — no API key, no network, no cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pam.config import DEFAULT_EMBEDDING_MODEL, EMBEDDING_DIMENSION

if TYPE_CHECKING:
    import numpy as np

# Lazy-loaded model to avoid slow import on startup
_model = None
_model_name: str | None = None


def _get_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    """Lazy-load the sentence-transformer model."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(model_name)
            _model_name = model_name
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embeddings. "
                "Install with: pip install sentence-transformers"
            )
    return _model


def embed_text(text: str, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    """Generate an embedding vector for a single text string."""
    model = _get_model(model_name)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_texts(texts: list[str], model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Generate embedding vectors for multiple texts (batched for efficiency)."""
    if not texts:
        return []
    model = _get_model(model_name)
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 50)
    return embeddings.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
