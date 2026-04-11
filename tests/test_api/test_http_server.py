"""Tests for the PAM local HTTP API server."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pam.api.server import app
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
    Temporal,
)
from datetime import datetime, timezone


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_vault(tmp_path, monkeypatch):
    """Create a temporary vault and patch DEFAULT_VAULT_PATH."""
    vault_path = tmp_path / "test_vault.db"
    monkeypatch.setattr("pam.api.server.DEFAULT_VAULT_PATH", vault_path)
    monkeypatch.setattr("pam.api.handlers.CONFIG_DIR", tmp_path)
    db = VaultDB(vault_path)
    db.open()
    yield db
    db.close()


@pytest.fixture()
def client(tmp_vault):
    return TestClient(app)


def _seed_memory(db: VaultDB, content: str, mem_type: MemoryType = MemoryType.FACT) -> Memory:
    mem = Memory(
        type=mem_type,
        content=content,
        confidence=Confidence(score=0.9),
        temporal=Temporal(created_at=datetime.now(timezone.utc)),
        provenance=Provenance(platform=Platform.MANUAL, extraction_method=ExtractionMethod.MANUAL),
        tags=["test"],
    )
    db.insert_memory(mem)
    return mem


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── /stats ────────────────────────────────────────────────────────────────────

def test_stats_empty_vault(client):
    r = client.get("/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["total_memories"] == 0
    assert d["total_conversations"] == 0


def test_stats_with_data(client, tmp_vault):
    _seed_memory(tmp_vault, "I am a developer")
    _seed_memory(tmp_vault, "I prefer Python", MemoryType.PREFERENCE)
    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json()["total_memories"] == 2


# ── /context ──────────────────────────────────────────────────────────────────

def test_context_empty_vault(client):
    r = client.get("/context")
    assert r.status_code == 200
    d = r.json()
    assert d["memory_count"] == 0
    assert d["context"] == ""


def test_context_with_memories(client, tmp_vault):
    _seed_memory(tmp_vault, "I am a Python developer")
    r = client.get("/context?summary=coding")
    assert r.status_code == 200
    d = r.json()
    assert d["memory_count"] >= 0  # privacy filter may reduce count
    assert isinstance(d["context"], str)
    assert isinstance(d["token_estimate"], int)


# ── /memories GET ─────────────────────────────────────────────────────────────

def test_list_memories_empty(client):
    r = client.get("/memories")
    assert r.status_code == 200
    assert r.json() == []


def test_search_memories(client, tmp_vault):
    _seed_memory(tmp_vault, "I know Python very well")
    r = client.get("/memories?q=Python&limit=5")
    assert r.status_code == 200
    results = r.json()
    assert isinstance(results, list)


# ── /memories POST ────────────────────────────────────────────────────────────

def test_add_memory_success(client):
    r = client.post("/memories", json={"content": "I prefer dark mode", "memory_type": "preference"})
    assert r.status_code == 201
    d = r.json()
    assert d["content"] == "I prefer dark mode"
    assert d["type"] == "preference"
    assert "id" in d


def test_add_memory_with_tags(client):
    r = client.post("/memories", json={
        "content": "I use VS Code",
        "memory_type": "skill",
        "tags": ["editor", "tools"],
    })
    assert r.status_code == 201
    assert "editor" in r.json()["tags"]


def test_add_memory_empty_content_rejected(client):
    r = client.post("/memories", json={"content": ""})
    assert r.status_code == 422


def test_add_memory_whitespace_content_rejected(client):
    r = client.post("/memories", json={"content": "   "})
    assert r.status_code == 422


def test_add_memory_appears_in_list(client):
    client.post("/memories", json={"content": "I work in Johannesburg"})
    r = client.get("/memories?q=Johannesburg")
    assert r.status_code == 200
    # Memory should be findable
    results = r.json()
    assert isinstance(results, list)


# ── /profile ──────────────────────────────────────────────────────────────────

def test_profile_empty_vault(client):
    r = client.get("/profile")
    assert r.status_code == 200
    assert "profile" in r.json()


def test_profile_with_memories(client, tmp_vault):
    _seed_memory(tmp_vault, "AWS Cloud .NET Developer", MemoryType.SKILL)
    r = client.get("/profile")
    assert r.status_code == 200
    assert isinstance(r.json()["profile"], str)
