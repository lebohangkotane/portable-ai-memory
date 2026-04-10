"""ChatGPT export adapter.

Parses the conversations.json file from ChatGPT's data export ZIP.
Export format: Settings → Data Controls → Export Data → ZIP delivered via email.

The ZIP contains:
  - conversations.json: Array of conversation objects
  - Each conversation has: title, create_time, update_time, mapping (tree of messages)
  - Messages are in a tree structure (mapping), not a flat list
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pam.adapters.base import PlatformAdapter, register_adapter
from pam.vault.models import (
    Conversation,
    Message,
    MessageRole,
    Platform,
)


def _unix_to_datetime(ts: float | None) -> datetime:
    """Convert Unix timestamp to datetime, with fallback."""
    if ts is None or ts == 0:
        return datetime.now(tz=timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _extract_role(message: dict) -> MessageRole:
    """Map ChatGPT role to PAM MessageRole."""
    role = message.get("author", {}).get("role", "user")
    mapping = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
        "tool": MessageRole.TOOL,
    }
    return mapping.get(role, MessageRole.USER)


def _extract_content(message: dict) -> str:
    """Extract text content from a ChatGPT message node."""
    content = message.get("content", {})
    parts = content.get("parts", [])
    text_parts = []
    for part in parts:
        if isinstance(part, str):
            text_parts.append(part)
        elif isinstance(part, dict):
            # Could be an image, code, or other structured content
            if "text" in part:
                text_parts.append(part["text"])
    return "\n".join(text_parts)


def _get_model(message: dict) -> str | None:
    """Extract model slug from a ChatGPT message."""
    metadata = message.get("metadata", {})
    return metadata.get("model_slug")


def _flatten_message_tree(mapping: dict[str, Any]) -> list[dict]:
    """Flatten ChatGPT's tree-structured messages into a chronological list.

    ChatGPT stores messages as a tree (mapping) where each node has a parent.
    We traverse the tree to get messages in order.
    """
    if not mapping:
        return []

    # Find root node (no parent or parent not in mapping)
    nodes = {}
    children: dict[str, list[str]] = {}
    for node_id, node in mapping.items():
        nodes[node_id] = node
        parent_id = node.get("parent")
        if parent_id:
            children.setdefault(parent_id, []).append(node_id)

    # Find root(s)
    roots = [
        nid for nid, node in nodes.items()
        if node.get("parent") is None or node.get("parent") not in nodes
    ]

    # DFS to flatten — follow the tree in order
    result = []

    def walk(node_id: str) -> None:
        node = nodes.get(node_id)
        if not node:
            return
        msg = node.get("message")
        if msg and msg.get("content", {}).get("parts"):
            content = _extract_content(msg)
            if content.strip():
                result.append(msg)
        for child_id in children.get(node_id, []):
            walk(child_id)

    for root_id in roots:
        walk(root_id)

    return result


@register_adapter
class ChatGPTAdapter(PlatformAdapter):
    """Import adapter for ChatGPT data exports."""

    platform_name = "chatgpt"
    supported_formats = [".zip", ".json"]
    description = "Import conversations from ChatGPT data export (ZIP or conversations.json)"

    def detect(self, path: Path) -> bool:
        """Detect if this is a ChatGPT export."""
        if path.suffix == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    return "conversations.json" in zf.namelist()
            except zipfile.BadZipFile:
                return False
        elif path.suffix == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # ChatGPT exports are an array of objects with "mapping" keys
                if isinstance(data, list) and len(data) > 0:
                    return "mapping" in data[0]
            except (json.JSONDecodeError, KeyError, IndexError):
                return False
        return False

    def parse(self, path: Path) -> Iterator[Conversation]:
        """Parse ChatGPT export and yield normalized conversations."""
        raw_conversations = self._load_conversations(path)

        for raw_conv in raw_conversations:
            conv_id = raw_conv.get("id", raw_conv.get("conversation_id", ""))
            title = raw_conv.get("title", "Untitled")
            created = _unix_to_datetime(raw_conv.get("create_time"))
            updated = _unix_to_datetime(raw_conv.get("update_time"))

            # Flatten the message tree
            mapping = raw_conv.get("mapping", {})
            flat_messages = _flatten_message_tree(mapping)

            if not flat_messages:
                continue

            # Detect model from first assistant message
            model = None
            messages = []
            for i, msg in enumerate(flat_messages):
                role = _extract_role(msg)
                content = _extract_content(msg)
                msg_time = _unix_to_datetime(msg.get("create_time"))

                if role == MessageRole.ASSISTANT and model is None:
                    model = _get_model(msg)

                messages.append(
                    Message(
                        source_id=msg.get("id"),
                        role=role,
                        content=content,
                        created_at=msg_time,
                        metadata={
                            "original_model": _get_model(msg),
                            "weight": msg.get("weight", 1.0),
                        },
                    )
                )

            yield Conversation(
                source_platform=Platform.CHATGPT,
                source_id=conv_id,
                title=title,
                created_at=created,
                updated_at=updated,
                model=model,
                messages=messages,
            )

    def get_platform_metadata(self, path: Path) -> dict:
        """Extract metadata from the ChatGPT export."""
        raw = self._load_conversations(path)
        timestamps = []
        models_seen = set()

        for conv in raw:
            ct = conv.get("create_time")
            if ct:
                timestamps.append(ct)
            mapping = conv.get("mapping", {})
            for node in mapping.values():
                msg = node.get("message")
                if msg is None:
                    continue
                model = (msg.get("metadata") or {}).get("model_slug")
                if model:
                    models_seen.add(model)

        return {
            "platform": "chatgpt",
            "total_conversations": len(raw),
            "date_range": {
                "earliest": _unix_to_datetime(min(timestamps)).isoformat() if timestamps else None,
                "latest": _unix_to_datetime(max(timestamps)).isoformat() if timestamps else None,
            },
            "models_used": sorted(models_seen),
        }

    def _load_conversations(self, path: Path) -> list[dict]:
        """Load conversations.json from either a ZIP or direct JSON file."""
        if path.suffix == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                with zf.open("conversations.json") as f:
                    return json.loads(f.read().decode("utf-8"))
        else:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
