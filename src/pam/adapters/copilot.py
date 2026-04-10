"""Microsoft Copilot export adapter.

Parses the CSV export from Microsoft Copilot.
Export format: account.microsoft.com/privacy/copilot → Export all activity history

The CSV contains:
  - Conversation: conversation title (groups messages)
  - Time: ISO 8601 timestamp
  - Author: "Human" (user) or "AI" (Copilot)
  - Message: message text (may contain markdown, newlines)

Note: File uses UTF-8 with BOM (utf-8-sig encoding).
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from itertools import groupby
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


def _map_role(author: str) -> MessageRole:
    """Map Copilot author field to PAM MessageRole."""
    if author.strip().lower() == "human":
        return MessageRole.USER
    return MessageRole.ASSISTANT


def _load_rows(path: Path) -> list[dict]:
    """Load all rows from the Copilot CSV export."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


@register_adapter
class CopilotAdapter(PlatformAdapter):
    """Import adapter for Microsoft Copilot activity history exports."""

    platform_name = "copilot"
    supported_formats = [".csv"]
    description = "Import conversations from Microsoft Copilot CSV export"

    def detect(self, path: Path) -> bool:
        """Detect if this is a Copilot export."""
        if path.suffix.lower() != ".csv":
            return False
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                required = {"Conversation", "Time", "Author", "Message"}
                if not required.issubset(set(headers)):
                    return False
                # Check Author values are "Human" or "AI"
                for i, row in enumerate(reader):
                    if row.get("Author") in ("Human", "AI"):
                        return True
                    if i > 10:
                        break
        except Exception:
            return False
        return False

    def parse(self, path: Path) -> Iterator[Conversation]:
        """Parse Copilot CSV export and yield normalized conversations."""
        rows = _load_rows(path)

        # Group rows by conversation title — preserving order of first appearance
        seen: dict[str, list[dict]] = {}
        for row in rows:
            title = row.get("Conversation", "Untitled").strip()
            seen.setdefault(title, []).append(row)

        for title, conv_rows in seen.items():
            # Sort messages by timestamp within each conversation
            conv_rows.sort(key=lambda r: r.get("Time", ""))

            messages = []
            for row in conv_rows:
                content = row.get("Message", "").strip()
                if not content:
                    continue
                messages.append(
                    Message(
                        role=_map_role(row.get("Author", "AI")),
                        content=content,
                        created_at=_parse_timestamp(row.get("Time")),
                    )
                )

            if not messages:
                continue

            created_at = messages[0].created_at
            updated_at = messages[-1].created_at

            yield Conversation(
                source_platform=Platform.COPILOT,
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                model="copilot",
                messages=messages,
            )

    def get_platform_metadata(self, path: Path) -> dict:
        """Extract metadata from the Copilot export."""
        rows = _load_rows(path)

        conversations = set(r.get("Conversation", "") for r in rows)
        timestamps = [
            _parse_timestamp(r.get("Time"))
            for r in rows
            if r.get("Time")
        ]

        return {
            "platform": "copilot",
            "total_conversations": len(conversations),
            "total_messages": len(rows),
            "date_range": {
                "earliest": min(timestamps).isoformat() if timestamps else None,
                "latest": max(timestamps).isoformat() if timestamps else None,
            },
        }
