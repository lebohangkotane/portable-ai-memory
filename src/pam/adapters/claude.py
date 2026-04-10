"""Claude export adapter.

Parses the JSON export from Claude (Anthropic).
Export format: Settings → Privacy → Export Data → JSON delivered via email link.

Claude exports contain an array of conversation objects, each with:
  - uuid, name, created_at, updated_at
  - chat_messages: flat array of messages with sender ("human" or "assistant")
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from pam.adapters.base import PlatformAdapter, register_adapter
from pam.vault.models import (
    Conversation,
    Message,
    MessageRole,
    Platform,
)


def _parse_timestamp(ts: str | None) -> datetime:
    """Parse ISO timestamp with fallback."""
    if not ts:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=timezone.utc)


def _map_role(sender: str) -> MessageRole:
    """Map Claude sender to PAM MessageRole."""
    mapping = {
        "human": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
    }
    return mapping.get(sender, MessageRole.USER)


@register_adapter
class ClaudeAdapter(PlatformAdapter):
    """Import adapter for Claude (Anthropic) data exports."""

    platform_name = "claude"
    supported_formats = [".json", ".zip"]
    description = "Import conversations from Claude data export (JSON)"

    def detect(self, path: Path) -> bool:
        """Detect if this is a Claude export."""
        try:
            data = self._load_data(path)
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                return "chat_messages" in first or (
                    "uuid" in first and "name" in first
                )
            if isinstance(data, dict):
                # Some Claude exports wrap in a top-level object
                return "conversations" in data or "chat_messages" in data
        except Exception:
            return False
        return False

    def parse(self, path: Path) -> Iterator[Conversation]:
        """Parse Claude export and yield normalized conversations."""
        data = self._load_data(path)

        conversations = data if isinstance(data, list) else data.get("conversations", [data])

        for raw_conv in conversations:
            conv_id = raw_conv.get("uuid", raw_conv.get("id", ""))
            title = raw_conv.get("name", raw_conv.get("title", "Untitled"))
            created = _parse_timestamp(raw_conv.get("created_at"))
            updated = _parse_timestamp(raw_conv.get("updated_at"))

            raw_messages = raw_conv.get("chat_messages", [])
            if not raw_messages:
                continue

            messages = []
            for msg in raw_messages:
                sender = msg.get("sender", "human")
                text = msg.get("text", "")

                # Some exports use content array instead of text
                if not text and "content" in msg:
                    content_items = msg["content"]
                    if isinstance(content_items, list):
                        text = "\n".join(
                            item.get("text", str(item))
                            for item in content_items
                            if isinstance(item, dict)
                        )
                    elif isinstance(content_items, str):
                        text = content_items

                if not text.strip():
                    continue

                messages.append(
                    Message(
                        source_id=msg.get("uuid", msg.get("id")),
                        role=_map_role(sender),
                        content=text,
                        created_at=_parse_timestamp(msg.get("created_at")),
                        metadata={
                            "sender": sender,
                        },
                    )
                )

            if messages:
                yield Conversation(
                    source_platform=Platform.CLAUDE,
                    source_id=conv_id,
                    title=title,
                    created_at=created,
                    updated_at=updated,
                    messages=messages,
                )

    def get_platform_metadata(self, path: Path) -> dict:
        """Extract metadata from the Claude export."""
        data = self._load_data(path)
        conversations = data if isinstance(data, list) else data.get("conversations", [data])

        timestamps = []
        for conv in conversations:
            ts = conv.get("created_at")
            if ts:
                timestamps.append(_parse_timestamp(ts))

        return {
            "platform": "claude",
            "total_conversations": len(conversations),
            "date_range": {
                "earliest": min(timestamps).isoformat() if timestamps else None,
                "latest": max(timestamps).isoformat() if timestamps else None,
            },
        }

    def _load_data(self, path: Path) -> list | dict:
        """Load JSON data from file or ZIP."""
        if path.suffix == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                # Look for JSON files in the ZIP
                json_files = [n for n in zf.namelist() if n.endswith(".json")]
                if not json_files:
                    raise ValueError("No JSON files found in ZIP")
                with zf.open(json_files[0]) as f:
                    return json.loads(f.read().decode("utf-8"))
        else:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
