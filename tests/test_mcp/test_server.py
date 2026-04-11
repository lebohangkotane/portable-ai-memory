"""Tests for the PAM MCP server tool handlers."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from pam.vault.database import VaultDB
from pam.vault.models import (
    Confidence,
    Conversation,
    ExtractionMethod,
    Memory,
    MemoryType,
    Message,
    MessageRole,
    Platform,
    Provenance,
)
from pam.context.privacy import PrivacyConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_memory(content: str, mem_type: MemoryType = MemoryType.FACT) -> Memory:
    return Memory(
        type=mem_type,
        content=content,
        confidence=Confidence(score=0.9),
        provenance=Provenance(
            platform=Platform.COPILOT,
            extraction_method=ExtractionMethod.HEURISTIC,
        ),
    )


def _seed_vault(db: VaultDB) -> None:
    """Seed test vault with sample data."""
    db.insert_memory(_make_memory("User is a software developer", MemoryType.IDENTITY))
    db.insert_memory(_make_memory("User knows Python, React, and C#", MemoryType.SKILL))
    db.insert_memory(_make_memory("User prefers concise responses", MemoryType.PREFERENCE))
    db.insert_memory(_make_memory("User is building a portable AI memory system", MemoryType.GOAL))
    db.insert_memory(_make_memory("User is based in South Africa", MemoryType.FACT))

    db.insert_conversation(Conversation(
        source_platform=Platform.COPILOT,
        title="Python help",
        messages=[
            Message(role=MessageRole.USER, content="How do I use async in Python?"),
            Message(role=MessageRole.ASSISTANT, content="Here's how async works..."),
        ],
    ))


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_memory_text_fallback(tmp_path):
    """search_memory falls back to text search when no embeddings exist."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()
    _seed_vault(db)

    # Patch the global _db
    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_search_memory
        result = await _handle_search_memory({"query": "Python", "limit": 5})
        assert "Python" in result
        assert "skill" in result.lower() or "memory" in result.lower()
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_search_memory_no_results(tmp_path):
    """search_memory returns a friendly message when nothing is found."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_search_memory
        result = await _handle_search_memory({"query": "quantum physics", "limit": 5})
        assert "No memories found" in result
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_add_memory(tmp_path):
    """add_memory saves a memory and confirms it."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_add_memory
        result = await _handle_add_memory({
            "content": "User enjoys working with Docker",
            "memory_type": "preference",
            "tags": ["docker", "devops"],
        })
        assert "Memory saved" in result
        assert "preference" in result

        # Verify it's in the vault
        memories = db.list_memories(memory_type=MemoryType.PREFERENCE)
        assert any("Docker" in m.content for m in memories)
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_add_memory_empty_content(tmp_path):
    """add_memory rejects empty content."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_add_memory
        result = await _handle_add_memory({"content": ""})
        assert "Error" in result
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_get_user_profile(tmp_path):
    """get_user_profile returns structured user info."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()
    _seed_vault(db)

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_get_user_profile
        result = await _handle_get_user_profile({})
        assert "User Profile" in result
        assert "developer" in result.lower() or "skill" in result.lower()
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_get_vault_stats(tmp_path):
    """get_vault_stats returns accurate counts."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()
    _seed_vault(db)

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_get_vault_stats
        result = await _handle_get_vault_stats({})
        assert "Vault Statistics" in result
        assert "5" in result  # 5 memories seeded
        assert "1" in result  # 1 conversation seeded
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_get_context_empty_vault(tmp_path):
    """get_context handles empty vault gracefully."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_get_context
        result = await _handle_get_context({})
        assert "No context available" in result or "pam import" in result
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()


@pytest.mark.asyncio
async def test_get_context_with_memories(tmp_path):
    """get_context returns formatted context when memories exist."""
    db = VaultDB(tmp_path / "vault.db")
    db.open()
    _seed_vault(db)

    import pam.mcp.server as srv
    original_db = srv._db
    srv._db = db
    srv._privacy = PrivacyConfig.default()

    try:
        from pam.mcp.server import _handle_get_context
        result = await _handle_get_context({"token_budget": 2000})
        assert "Memory Context" in result or "##" in result
    finally:
        srv._db = original_db
        srv._privacy = None
        db.close()
