"""Tests for the ChatGPT import adapter."""

import json
import tempfile
import zipfile
from pathlib import Path

from pam.adapters.chatgpt import ChatGPTAdapter
from pam.vault.models import MessageRole, Platform


def _create_chatgpt_export(conversations: list[dict], path: Path) -> Path:
    """Helper to create a mock ChatGPT export ZIP."""
    zip_path = path / "chatgpt_export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
    return zip_path


def _make_conversation(title: str, messages: list[tuple[str, str]]) -> dict:
    """Create a mock ChatGPT conversation with message tree structure."""
    mapping = {}
    parent_id = None

    # Root node
    root_id = "root"
    mapping[root_id] = {
        "id": root_id,
        "parent": None,
        "message": None,
    }
    parent_id = root_id

    for i, (role, content) in enumerate(messages):
        node_id = f"msg-{i}"
        mapping[node_id] = {
            "id": node_id,
            "parent": parent_id,
            "message": {
                "id": f"msg-id-{i}",
                "author": {"role": role},
                "content": {"parts": [content]},
                "create_time": 1700000000 + i * 60,
                "metadata": {"model_slug": "gpt-4o" if role == "assistant" else None},
                "weight": 1.0,
            },
        }
        parent_id = node_id

    return {
        "id": f"conv-{hash(title)}",
        "title": title,
        "create_time": 1700000000,
        "update_time": 1700000000 + len(messages) * 60,
        "mapping": mapping,
    }


def test_detect_zip():
    adapter = ChatGPTAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        zip_path = _create_chatgpt_export([_make_conversation("Test", [("user", "Hi")])], path)
        assert adapter.detect(zip_path) is True


def test_detect_json():
    adapter = ChatGPTAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "conversations.json"
        data = [_make_conversation("Test", [("user", "Hi")])]
        path.write_text(json.dumps(data))
        assert adapter.detect(path) is True


def test_detect_wrong_file():
    adapter = ChatGPTAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "random.json"
        path.write_text(json.dumps({"not": "chatgpt"}))
        assert adapter.detect(path) is False


def test_parse_conversations():
    adapter = ChatGPTAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        raw = [
            _make_conversation("Python help", [
                ("user", "I need help with Python"),
                ("assistant", "I'd be happy to help! What do you need?"),
                ("user", "I'm building a web scraper"),
                ("assistant", "Here's how you can build a web scraper..."),
            ]),
            _make_conversation("React tips", [
                ("user", "How do I use React hooks?"),
                ("assistant", "React hooks are functions that let you..."),
            ]),
        ]
        zip_path = _create_chatgpt_export(raw, path)

        conversations = list(adapter.parse(zip_path))
        assert len(conversations) == 2

        conv1 = conversations[0]
        assert conv1.title == "Python help"
        assert conv1.source_platform == Platform.CHATGPT
        assert len(conv1.messages) == 4
        assert conv1.messages[0].role == MessageRole.USER
        assert conv1.messages[1].role == MessageRole.ASSISTANT
        assert conv1.model == "gpt-4o"


def test_get_platform_metadata():
    adapter = ChatGPTAdapter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        raw = [
            _make_conversation("Conv 1", [("user", "Hi"), ("assistant", "Hello")]),
            _make_conversation("Conv 2", [("user", "Bye"), ("assistant", "Goodbye")]),
        ]
        zip_path = _create_chatgpt_export(raw, path)

        meta = adapter.get_platform_metadata(zip_path)
        assert meta["platform"] == "chatgpt"
        assert meta["total_conversations"] == 2
        assert "gpt-4o" in meta["models_used"]
