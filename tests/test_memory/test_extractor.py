"""Tests for memory extraction."""

from pam.memory.extractor import extract_memories_heuristic
from pam.vault.models import (
    Conversation,
    Message,
    MessageRole,
    MemoryType,
    Platform,
)


def _make_conversation(messages: list[tuple[str, str]]) -> Conversation:
    return Conversation(
        source_platform=Platform.CHATGPT,
        title="Test",
        messages=[
            Message(role=MessageRole(role), content=content)
            for role, content in messages
        ],
    )


def test_extract_fact():
    conv = _make_conversation([
        ("user", "I am a software developer based in Johannesburg"),
        ("assistant", "That's great! How can I help?"),
    ])
    memories = extract_memories_heuristic(conv)
    assert len(memories) >= 1
    types = {m.type for m in memories}
    assert MemoryType.FACT in types


def test_extract_preference():
    conv = _make_conversation([
        ("user", "I prefer using Python for backend development"),
        ("assistant", "Python is a great choice!"),
    ])
    memories = extract_memories_heuristic(conv)
    assert any(m.type == MemoryType.PREFERENCE for m in memories)


def test_extract_skill():
    conv = _make_conversation([
        ("user", "I know Python, React, and Docker quite well"),
        ("assistant", "Those are excellent skills!"),
    ])
    memories = extract_memories_heuristic(conv)
    assert any(m.type == MemoryType.SKILL for m in memories)


def test_extract_goal():
    conv = _make_conversation([
        ("user", "I'm trying to build a portable AI memory system"),
        ("assistant", "That sounds like a fascinating project!"),
    ])
    memories = extract_memories_heuristic(conv)
    assert any(m.type == MemoryType.GOAL for m in memories)


def test_no_extraction_from_assistant():
    conv = _make_conversation([
        ("assistant", "I am an AI assistant and I prefer to help you"),
    ])
    memories = extract_memories_heuristic(conv)
    assert len(memories) == 0


def test_deduplication():
    conv = _make_conversation([
        ("user", "I am a developer"),
        ("user", "I am a developer"),
    ])
    memories = extract_memories_heuristic(conv)
    contents = [m.content for m in memories]
    assert len(contents) == len(set(m.content_hash for m in memories))
