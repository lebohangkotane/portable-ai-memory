"""Tests for LLM-based memory extraction."""

import json
import os
import warnings
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from pam.memory.extractor import (
    build_llm_extraction_prompt,
    extract_memories_llm_sync,
    parse_llm_extraction_response,
)
from pam.vault.models import Conversation, Message, MessageRole, Platform


def _make_conversation(messages: list[tuple[str, str]] | None = None) -> Conversation:
    if messages is None:
        messages = [("user", "I am a Python developer"), ("assistant", "Great!")]
    return Conversation(
        source_platform=Platform.MANUAL,
        title="Test conversation",
        messages=[
            Message(
                role=MessageRole.USER if role == "user" else MessageRole.ASSISTANT,
                content=text,
                created_at=datetime.now(timezone.utc),
            )
            for role, text in messages
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ── extract_memories_llm_sync() ───────────────────────────────────────────────

def test_no_api_key_returns_empty_list(monkeypatch):
    """With no key, returns [] and warns — never raises."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    conv = _make_conversation()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = extract_memories_llm_sync(conv, api_key=None)
    assert result == []
    assert any("ANTHROPIC_API_KEY" in str(warning.message) for warning in w)


def test_no_anthropic_package_returns_empty_list(monkeypatch):
    """If anthropic is not installed, returns [] gracefully."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    conv = _make_conversation()
    with patch("builtins.__import__", side_effect=mock_import):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = extract_memories_llm_sync(conv, api_key=None)
    assert result == []
    assert any("anthropic" in str(warning.message).lower() for warning in w)


def test_llm_extraction_with_mock_client(monkeypatch):
    """With a mocked anthropic client, verify correct model and output parsing."""
    conv = _make_conversation()

    mock_response_text = json.dumps([
        {"type": "skill", "content": "Python developer", "confidence": 0.95, "tags": ["python"]},
    ])

    mock_content = MagicMock()
    mock_content.text = mock_response_text

    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = extract_memories_llm_sync(conv, api_key="sk-test")

    assert len(result) == 1
    assert result[0].type.value == "skill"
    assert "Python" in result[0].content
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args
    assert "claude-haiku" in call_kwargs.kwargs.get("model", call_kwargs.args[0] if call_kwargs.args else "")


def test_api_exception_returns_empty_list(monkeypatch):
    """If the API call raises, returns [] with a warning — never raises."""
    conv = _make_conversation()

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Network error")

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = extract_memories_llm_sync(conv, api_key="sk-test")

    assert result == []
    assert any("failed" in str(warning.message).lower() for warning in w)


# ── build_llm_extraction_prompt() ─────────────────────────────────────────────

def test_prompt_contains_conversation_text():
    conv = _make_conversation([("user", "I love building AI tools")])
    prompt = build_llm_extraction_prompt(conv)
    assert "I love building AI tools" in prompt
    assert "User:" in prompt


def test_prompt_truncates_long_conversations():
    long_text = "x" * 10000
    conv = _make_conversation([("user", long_text)])
    prompt = build_llm_extraction_prompt(conv, max_chars=8000)
    assert "[truncated]" in prompt
    assert len(prompt) < 10000


# ── parse_llm_extraction_response() ───────────────────────────────────────────

def test_parse_valid_response():
    conv = _make_conversation()
    items = [
        {"type": "preference", "content": "Prefers dark mode", "confidence": 0.9, "tags": ["ui"]},
        {"type": "skill", "content": "Knows Python", "confidence": 0.85, "tags": ["python"]},
    ]
    memories = parse_llm_extraction_response(items, conv)
    assert len(memories) == 2
    assert memories[0].type.value == "preference"
    assert memories[1].type.value == "skill"


def test_parse_invalid_type_defaults_to_fact():
    conv = _make_conversation()
    items = [{"type": "nonexistent_type", "content": "Some content", "confidence": 0.5, "tags": []}]
    memories = parse_llm_extraction_response(items, conv)
    assert len(memories) == 1
    assert memories[0].type.value == "fact"


def test_parse_skips_empty_content():
    conv = _make_conversation()
    items = [
        {"type": "fact", "content": "", "confidence": 0.9, "tags": []},
        {"type": "fact", "content": "   ", "confidence": 0.9, "tags": []},
        {"type": "skill", "content": "Valid content", "confidence": 0.8, "tags": []},
    ]
    memories = parse_llm_extraction_response(items, conv)
    assert len(memories) == 1


def test_parse_clamps_confidence():
    conv = _make_conversation()
    items = [{"type": "fact", "content": "Test content here", "confidence": 1.5, "tags": []}]
    memories = parse_llm_extraction_response(items, conv)
    assert len(memories) == 1
    assert memories[0].confidence.score <= 1.0
