"""Tests for the vault database."""

import tempfile
from pathlib import Path

from pam.vault.database import VaultDB
from pam.vault.models import (
    Conversation,
    Memory,
    MemoryType,
    Message,
    MessageRole,
    Platform,
    Provenance,
    ExtractionMethod,
)


def test_create_and_open_vault():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        db = VaultDB(path)
        db.open()
        assert path.exists()
        db.close()


def test_insert_and_retrieve_conversation():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            conv = Conversation(
                source_platform=Platform.CHATGPT,
                source_id="conv-123",
                title="Test Conversation",
                messages=[
                    Message(role=MessageRole.USER, content="Hello, I am a developer"),
                    Message(role=MessageRole.ASSISTANT, content="Nice to meet you!"),
                ],
            )
            db.insert_conversation(conv)

            retrieved = db.get_conversation(conv.id)
            assert retrieved is not None
            assert retrieved.title == "Test Conversation"
            assert len(retrieved.messages) == 2
            assert retrieved.messages[0].content == "Hello, I am a developer"


def test_insert_and_retrieve_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            mem = Memory(
                type=MemoryType.SKILL,
                content="User knows Python programming",
                provenance=Provenance(
                    platform=Platform.CHATGPT,
                    extraction_method=ExtractionMethod.HEURISTIC,
                ),
                tags=["python", "programming"],
            )
            db.insert_memory(mem)

            retrieved = db.get_memory(mem.id)
            assert retrieved is not None
            assert retrieved.type == MemoryType.SKILL
            assert retrieved.content == "User knows Python programming"
            assert "python" in retrieved.tags


def test_list_memories_by_type():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            for i in range(3):
                db.insert_memory(Memory(
                    type=MemoryType.SKILL,
                    content=f"Skill {i}",
                    provenance=Provenance(platform=Platform.CHATGPT),
                ))
            db.insert_memory(Memory(
                type=MemoryType.FACT,
                content="A fact",
                provenance=Provenance(platform=Platform.CHATGPT),
            ))

            skills = db.list_memories(memory_type=MemoryType.SKILL)
            assert len(skills) == 3

            facts = db.list_memories(memory_type=MemoryType.FACT)
            assert len(facts) == 1


def test_search_memories_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            db.insert_memory(Memory(
                type=MemoryType.SKILL,
                content="User knows Python and React",
                provenance=Provenance(platform=Platform.CHATGPT),
            ))
            db.insert_memory(Memory(
                type=MemoryType.PREFERENCE,
                content="User prefers dark mode",
                provenance=Provenance(platform=Platform.CLAUDE),
            ))

            results = db.search_memories_text("Python")
            assert len(results) == 1
            assert "Python" in results[0].content


def test_vault_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            db.insert_conversation(Conversation(
                source_platform=Platform.CHATGPT,
                title="Conv 1",
                messages=[Message(role=MessageRole.USER, content="Hi")],
            ))
            db.insert_memory(Memory(
                type=MemoryType.FACT,
                content="A fact",
                provenance=Provenance(platform=Platform.CHATGPT),
            ))

            s = db.get_stats()
            assert s["total_conversations"] == 1
            assert s["total_memories"] == 1
            assert s["total_messages"] == 1


def test_delete_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        with VaultDB(path) as db:
            mem = Memory(
                type=MemoryType.FACT,
                content="To be deleted",
                provenance=Provenance(platform=Platform.MANUAL),
            )
            db.insert_memory(mem)
            assert db.get_memory(mem.id) is not None

            deleted = db.delete_memory(mem.id)
            assert deleted is True
            assert db.get_memory(mem.id) is None
