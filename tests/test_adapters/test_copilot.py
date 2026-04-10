"""Tests for the Microsoft Copilot import adapter."""

import csv
import tempfile
from pathlib import Path

from pam.adapters.copilot import CopilotAdapter
from pam.vault.models import MessageRole, Platform


def _create_copilot_csv(rows: list[dict], path: Path) -> Path:
    """Helper to create a mock Copilot CSV export."""
    csv_path = path / "copilot-activity-history.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Conversation", "Time", "Author", "Message"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def _make_rows(title: str, messages: list[tuple[str, str, str]]) -> list[dict]:
    """Create mock CSV rows: (author, message, time)."""
    return [
        {"Conversation": title, "Time": time, "Author": author, "Message": msg}
        for author, msg, time in messages
    ]


def test_detect_valid_csv():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = _make_rows("Test", [
            ("Human", "Hello", "2026-01-01T10:00:00"),
            ("AI", "Hi there!", "2026-01-01T10:00:05"),
        ])
        csv_path = _create_copilot_csv(rows, Path(tmpdir))
        assert adapter.detect(csv_path) is True


def test_detect_wrong_format():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "other.json"
        path.write_text("{}")
        assert adapter.detect(path) is False


def test_detect_wrong_csv_columns():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "other.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["foo", "bar"])
            writer.writeheader()
            writer.writerow({"foo": "1", "bar": "2"})
        assert adapter.detect(csv_path) is False


def test_parse_single_conversation():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = _make_rows("AI Memory Project", [
            ("Human", "I am a developer building a memory system", "2026-01-01T10:00:00"),
            ("AI", "That sounds fascinating! Tell me more.", "2026-01-01T10:00:05"),
            ("Human", "I prefer Python for the backend", "2026-01-01T10:01:00"),
            ("AI", "Python is a great choice.", "2026-01-01T10:01:05"),
        ])
        csv_path = _create_copilot_csv(rows, Path(tmpdir))

        conversations = list(adapter.parse(csv_path))
        assert len(conversations) == 1

        conv = conversations[0]
        assert conv.title == "AI Memory Project"
        assert conv.source_platform == Platform.COPILOT
        assert len(conv.messages) == 4
        assert conv.messages[0].role == MessageRole.USER
        assert conv.messages[1].role == MessageRole.ASSISTANT
        assert conv.model == "copilot"


def test_parse_multiple_conversations():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = (
            _make_rows("Conv A", [
                ("Human", "Hello", "2026-01-01T10:00:00"),
                ("AI", "Hi!", "2026-01-01T10:00:05"),
            ])
            + _make_rows("Conv B", [
                ("Human", "Goodbye", "2026-01-02T10:00:00"),
                ("AI", "Bye!", "2026-01-02T10:00:05"),
            ])
        )
        csv_path = _create_copilot_csv(rows, Path(tmpdir))

        conversations = list(adapter.parse(csv_path))
        assert len(conversations) == 2
        titles = {c.title for c in conversations}
        assert "Conv A" in titles
        assert "Conv B" in titles


def test_messages_sorted_by_time():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Deliberately out of order
        rows = _make_rows("Test", [
            ("AI", "Second", "2026-01-01T10:00:10"),
            ("Human", "First", "2026-01-01T10:00:00"),
        ])
        csv_path = _create_copilot_csv(rows, Path(tmpdir))

        conv = list(adapter.parse(csv_path))[0]
        assert conv.messages[0].role == MessageRole.USER
        assert conv.messages[0].content == "First"


def test_get_platform_metadata():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = (
            _make_rows("Conv A", [
                ("Human", "Hi", "2026-01-01T10:00:00"),
                ("AI", "Hello", "2026-01-01T10:00:05"),
            ])
            + _make_rows("Conv B", [
                ("Human", "Bye", "2026-01-02T10:00:00"),
            ])
        )
        csv_path = _create_copilot_csv(rows, Path(tmpdir))

        meta = adapter.get_platform_metadata(csv_path)
        assert meta["platform"] == "copilot"
        assert meta["total_conversations"] == 2
        assert meta["total_messages"] == 3
        assert meta["date_range"]["earliest"] is not None
        assert meta["date_range"]["latest"] is not None


def test_skips_empty_messages():
    adapter = CopilotAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = _make_rows("Test", [
            ("Human", "Hello", "2026-01-01T10:00:00"),
            ("AI", "", "2026-01-01T10:00:05"),   # empty — should be skipped
            ("AI", "Hi there!", "2026-01-01T10:00:10"),
        ])
        csv_path = _create_copilot_csv(rows, Path(tmpdir))

        conv = list(adapter.parse(csv_path))[0]
        assert len(conv.messages) == 2
