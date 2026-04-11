"""Tests for the Google Gemini import adapter."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pam.adapters.gemini import GeminiAdapter
from pam.vault.models import MessageRole, Platform


def _write_gemini_json(conversations: list[dict], path: Path) -> Path:
    """Write a mock Gemini JSON export file."""
    out = path / "gemini-export.json"
    out.write_text(json.dumps(conversations), encoding="utf-8")
    return out


def _make_conv(title: str, turns: list[tuple[str, str]], create_time: str = "2024-03-01T10:00:00Z") -> dict:
    """Build a well-formed Gemini conversation dict."""
    return {
        "title": title,
        "create_time": create_time,
        "update_time": create_time,
        "conversation": [
            {"role": role, "parts": [{"text": text}]}
            for role, text in turns
        ],
    }


# ── detect() ─────────────────────────────────────────────────────────────────

def test_detect_valid_json():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_conv("Test", [("user", "Hello"), ("model", "Hi")])
        path = _write_gemini_json([conv], Path(tmpdir))
        assert adapter.detect(path) is True


def test_detect_wrong_extension():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "export.csv"
        p.write_text("not json")
        assert adapter.detect(p) is False


def test_detect_wrong_json_structure():
    """A Claude-style JSON (not a list) should not be detected."""
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "claude.json"
        p.write_text(json.dumps({"chat_messages": []}))
        assert adapter.detect(p) is False


def test_detect_missing_conversation_key():
    """JSON array without 'conversation' key should not be detected."""
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "other.json"
        p.write_text(json.dumps([{"title": "test", "messages": []}]))
        assert adapter.detect(p) is False


# ── parse() ──────────────────────────────────────────────────────────────────

def test_parse_single_conversation():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_conv("My chat", [("user", "Hello world"), ("model", "Hi there")])
        path = _write_gemini_json([conv], Path(tmpdir))
        convs = list(adapter.parse(path))
        assert len(convs) == 1
        assert convs[0].title == "My chat"
        assert convs[0].source_platform == Platform.GEMINI
        assert convs[0].model == "gemini"
        assert len(convs[0].messages) == 2


def test_parse_multiple_conversations():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        data = [
            _make_conv("Chat 1", [("user", "Question 1"), ("model", "Answer 1")]),
            _make_conv("Chat 2", [("user", "Question 2"), ("model", "Answer 2")]),
        ]
        path = _write_gemini_json(data, Path(tmpdir))
        convs = list(adapter.parse(path))
        assert len(convs) == 2
        assert {c.title for c in convs} == {"Chat 1", "Chat 2"}


def test_role_mapping():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_conv("Roles", [("user", "Hello"), ("model", "Hi")])
        path = _write_gemini_json([conv], Path(tmpdir))
        convs = list(adapter.parse(path))
        msgs = convs[0].messages
        assert msgs[0].role == MessageRole.USER
        assert msgs[1].role == MessageRole.ASSISTANT


def test_multi_part_text_joined():
    """A turn with multiple parts should have their text joined."""
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = {
            "title": "Multi-part",
            "create_time": "2024-03-01T10:00:00Z",
            "update_time": "2024-03-01T10:00:00Z",
            "conversation": [
                {"role": "user", "parts": [{"text": "Part one"}, {"text": "Part two"}]},
            ],
        }
        path = _write_gemini_json([conv], Path(tmpdir))
        convs = list(adapter.parse(path))
        assert "Part one" in convs[0].messages[0].content
        assert "Part two" in convs[0].messages[0].content


def test_skips_empty_turns():
    """Turns with no text content should be skipped."""
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = {
            "title": "Sparse",
            "create_time": "2024-03-01T10:00:00Z",
            "update_time": "2024-03-01T10:00:00Z",
            "conversation": [
                {"role": "user", "parts": [{"text": ""}]},
                {"role": "model", "parts": [{"text": "Valid response"}]},
            ],
        }
        path = _write_gemini_json([conv], Path(tmpdir))
        convs = list(adapter.parse(path))
        assert len(convs) == 1
        assert len(convs[0].messages) == 1
        assert convs[0].messages[0].role == MessageRole.ASSISTANT


def test_timestamps_parsed():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_conv("TS test", [("user", "hi")], create_time="2024-06-15T08:30:00Z")
        path = _write_gemini_json([conv], Path(tmpdir))
        convs = list(adapter.parse(path))
        dt = convs[0].created_at
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15


def test_skips_conversation_with_no_messages():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        data = [
            {"title": "Empty", "create_time": "2024-01-01T00:00:00Z", "update_time": "2024-01-01T00:00:00Z", "conversation": []},
            _make_conv("Valid", [("user", "Hello")]),
        ]
        path = _write_gemini_json(data, Path(tmpdir))
        convs = list(adapter.parse(path))
        assert len(convs) == 1
        assert convs[0].title == "Valid"


# ── get_platform_metadata() ───────────────────────────────────────────────────

def test_get_platform_metadata():
    adapter = GeminiAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        data = [
            _make_conv("C1", [("user", "a"), ("model", "b")], create_time="2024-01-01T00:00:00Z"),
            _make_conv("C2", [("user", "c")], create_time="2024-06-01T00:00:00Z"),
        ]
        path = _write_gemini_json(data, Path(tmpdir))
        meta = adapter.get_platform_metadata(path)
        assert meta["platform"] == "gemini"
        assert meta["total_conversations"] == 2
        assert meta["total_messages"] == 3
        assert meta["date_range"]["earliest"] is not None
        assert meta["date_range"]["latest"] is not None
