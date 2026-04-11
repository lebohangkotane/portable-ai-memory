"""Shared business logic for PAM API handlers.

Pure functions that operate on VaultDB + PrivacyConfig with no
FastAPI or MCP dependencies. Used by both the HTTP server and MCP server.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pam.config import CONFIG_DIR, DEFAULT_TOKEN_BUDGET
from pam.context.builder import build_context
from pam.context.privacy import PrivacyConfig
from pam.vault.database import VaultDB
from pam.vault.models import (
    Confidence,
    ExtractionMethod,
    Memory,
    MemoryType,
    Platform,
    Provenance,
    Temporal,
)


def _get_privacy(privacy: PrivacyConfig | None = None) -> PrivacyConfig:
    if privacy is not None:
        return privacy
    return PrivacyConfig.load(CONFIG_DIR / "privacy.json")


def search_memories(
    db: VaultDB,
    query: str,
    limit: int = 10,
    memory_types: list[str] | None = None,
    privacy: PrivacyConfig | None = None,
) -> list[Memory]:
    """Search memories with privacy filtering and optional semantic search."""
    priv = _get_privacy(privacy)
    all_memories = db.list_memories(limit=2000)

    if memory_types:
        all_memories = [m for m in all_memories if m.type.value in memory_types]

    all_memories = priv.filter_memories(all_memories, "claude")

    with_embeddings = [m for m in all_memories if m.embedding is not None]
    without_embeddings = [m for m in all_memories if m.embedding is None]

    results: list[Memory] = []

    if with_embeddings:
        try:
            from pam.search.vector_store import search_combined
            scored = search_combined(query, with_embeddings, top_k=limit)
            results = [m for m, _ in scored]
        except ImportError:
            pass

    # Fill remaining slots with text search
    if len(results) < limit:
        remaining = limit - len(results)
        result_ids = {m.id for m in results}
        text_hits = db.search_memories_text(query, limit=remaining * 2)
        for m in text_hits:
            if m.id not in result_ids and len(results) < limit:
                if m.id in {x.id for x in all_memories}:
                    results.append(m)

    # If still empty, return top memories
    if not results:
        results = all_memories[:limit]

    return results[:limit]


def get_context_string(
    db: VaultDB,
    summary: str = "",
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    privacy: PrivacyConfig | None = None,
) -> tuple[str, int]:
    """Build a formatted context string. Returns (text, memory_count)."""
    priv = _get_privacy(privacy)
    all_memories = db.list_memories(limit=2000)
    filtered = priv.filter_memories(all_memories, "claude")

    if not filtered:
        return "", 0

    # Rank by recency and confidence
    filtered.sort(key=lambda m: (m.confidence.score, m.temporal.created_at), reverse=True)

    context = build_context(filtered, priv, "claude", token_budget=token_budget)
    return context, len(filtered)


def add_memory_to_vault(
    db: VaultDB,
    content: str,
    memory_type: str = "fact",
    tags: list[str] | None = None,
) -> Memory:
    """Add a manually created memory to the vault."""
    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        mem_type = MemoryType.FACT

    mem = Memory(
        type=mem_type,
        content=content,
        confidence=Confidence(score=0.9),
        temporal=Temporal(created_at=datetime.now(UTC)),
        provenance=Provenance(
            platform=Platform.MANUAL,
            extraction_method=ExtractionMethod.MANUAL,
        ),
        tags=tags or [],
    )
    db.insert_memory(mem)
    return mem


def get_stats_dict(db: VaultDB) -> dict[str, Any]:
    """Return vault statistics as a plain dict."""
    return db.get_stats()


def get_compact_profile_string(
    db: VaultDB,
    privacy: PrivacyConfig | None = None,
) -> str:
    """Return a short (2-3 sentence) profile summary."""
    priv = _get_privacy(privacy)
    all_memories = priv.filter_memories(db.list_memories(limit=500), "claude")
    stats = db.get_stats()

    skills = [m.content[:80] for m in all_memories if m.type.value == "skill"][:3]
    goals = [m.content[:80] for m in all_memories if m.type.value == "goal"][:2]
    prefs = [m.content[:80] for m in all_memories if m.type.value == "preference"][:2]

    parts = []
    if skills:
        parts.append("Skills: " + "; ".join(skills))
    if goals:
        parts.append("Goals: " + "; ".join(goals))
    if prefs:
        parts.append("Prefers: " + "; ".join(prefs))

    summary = ". ".join(parts)
    summary += f". (Vault: {stats['total_memories']} memories, {stats['total_conversations']} conversations)"
    return summary
