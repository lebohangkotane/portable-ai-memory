"""Vector search for semantic memory retrieval.

Uses in-memory cosine similarity search over stored embeddings.
For the MVP, this avoids the sqlite-vec dependency while still providing
fast semantic search. Can be upgraded to sqlite-vec for larger vaults.
"""

from __future__ import annotations

import struct
from typing import Any

from pam.vault.models import Memory
from pam.search.embeddings import cosine_similarity, embed_text


def search_memories_semantic(
    query: str,
    memories: list[Memory],
    top_k: int = 10,
    min_score: float = 0.3,
) -> list[tuple[Memory, float]]:
    """Search memories by semantic similarity to a query.

    Args:
        query: The search query text.
        memories: List of memories with embeddings.
        top_k: Maximum number of results to return.
        min_score: Minimum cosine similarity threshold.

    Returns:
        List of (memory, score) tuples, sorted by descending score.
    """
    query_embedding = embed_text(query)

    scored: list[tuple[Memory, float]] = []
    for mem in memories:
        if mem.embedding is None:
            continue
        score = cosine_similarity(query_embedding, mem.embedding)
        if score >= min_score:
            scored.append((mem, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def search_combined(
    query: str,
    memories: list[Memory],
    top_k: int = 10,
    semantic_weight: float = 0.7,
    text_weight: float = 0.3,
) -> list[tuple[Memory, float]]:
    """Combined semantic + text search with weighted scoring.

    Blends cosine similarity with simple keyword matching for
    more robust results.
    """
    query_lower = query.lower()
    query_terms = set(query_lower.split())
    query_embedding = embed_text(query)

    scored: list[tuple[Memory, float]] = []
    for mem in memories:
        # Semantic score
        semantic_score = 0.0
        if mem.embedding is not None:
            semantic_score = cosine_similarity(query_embedding, mem.embedding)

        # Text match score
        content_lower = mem.content.lower()
        matching_terms = sum(1 for t in query_terms if t in content_lower)
        text_score = matching_terms / max(len(query_terms), 1)

        # Combined score
        combined = (semantic_weight * semantic_score) + (text_weight * text_score)

        if combined > 0.2:
            scored.append((mem, combined))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
