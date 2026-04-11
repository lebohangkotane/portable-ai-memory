"""Google Gemini export adapter.

Parses the JSON export from Google Takeout for Gemini conversations.
Export path: takeout.google.com → Select "Gemini Apps Activity" → Download

The JSON file is a top-level array where each element is a conversation:
  {
    "title": "conversation title",
    "create_time": "2024-01-15T10:30:00.000000Z",
    "update_time": "2024-01-15T11:00:00.000000Z",
    "conversation": [
      {"role": "user",  "parts": [{"text": "message text"}]},
      {"role": "model", "parts": [{"text": "response text"}]}
    ]
  }
"""

from __future__ import annotations

import json
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


def _parse_iso(ts: str | None) -> datetime:
    """Parse ISO 8601 timestamp with fallback to now."""
    if not ts:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(tz=timezone.utc)


def _map_role(role: str) -> MessageRole:
    """Map Gemini role field to PAM MessageRole."""
    if role.strip().lower() == "model":
        return MessageRole.ASSISTANT
    return MessageRole.USER


def _parts_to_text(parts: list[dict]) -> str:
    """Join text from all parts of a Gemini turn."""
    return "\n".join(p.get("text", "") for p in parts if p.get("text", "").strip()).strip()


def _load_export(path: Path) -> list[dict]:
    """Load and parse the Gemini JSON export file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    return data


@register_adapter
class GeminiAdapter(PlatformAdapter):
    """Import adapter for Google Gemini conversation exports (Google Takeout)."""

    platform_name = "gemini"
    supported_formats = [".json"]
    description = "Import conversations from Google Gemini (Google Takeout JSON export)"

    def detect(self, path: Path) -> bool:
        """Detect if this is a Gemini Takeout export."""
        if path.suffix.lower() != ".json":
            return False
        try:
            data = _load_export(path)
            if not data:
                return False
            first = data[0]
            # Gemini exports have both "conversation" and "create_time" at the top level
            if "conversation" not in first or "create_time" not in first:
                return False
            # Spot-check that conversation turns have "role" and "parts"
            turns = first.get("conversation", [])
            if turns and isinstance(turns[0], dict):
                return "role" in turns[0] and "parts" in turns[0]
            return True
        except Exception:
            return False

    def parse(self, path: Path) -> Iterator[Conversation]:
        """Parse Gemini JSON export and yield normalized conversations."""
        data = _load_export(path)

        for item in data:
            turns = item.get("conversation", [])
            if not turns:
                continue

            messages = []
            for turn in turns:
                parts = turn.get("parts", [])
                content = _parts_to_text(parts)
                if not content:
                    continue
                messages.append(
                    Message(
                        role=_map_role(turn.get("role", "user")),
                        content=content,
                        created_at=_parse_iso(item.get("create_time")),
                    )
                )

            if not messages:
                continue

            created_at = _parse_iso(item.get("create_time"))
            updated_at = _parse_iso(item.get("update_time"))
            title = item.get("title", "Untitled").strip() or "Untitled"

            yield Conversation(
                source_platform=Platform.GEMINI,
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                model="gemini",
                messages=messages,
            )

    def get_platform_metadata(self, path: Path) -> dict:
        """Extract metadata from the Gemini export."""
        data = _load_export(path)

        total_messages = sum(len(item.get("conversation", [])) for item in data)
        timestamps = [
            _parse_iso(item.get("create_time"))
            for item in data
            if item.get("create_time")
        ]

        return {
            "platform": "gemini",
            "total_conversations": len(data),
            "total_messages": total_messages,
            "date_range": {
                "earliest": min(timestamps).isoformat() if timestamps else None,
                "latest": max(timestamps).isoformat() if timestamps else None,
            },
        }
