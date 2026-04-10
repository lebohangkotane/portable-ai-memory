"""Encrypted SQLite vault — the core storage layer for PAM.

Uses standard sqlite3 with optional sqlcipher encryption. Falls back to
unencrypted SQLite if pysqlcipher3 is not available, so the system works
out-of-the-box for development and testing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pam.vault.models import (
    Conversation,
    Memory,
    Message,
    MemoryType,
    Platform,
    Provenance,
    Confidence,
    Temporal,
    AccessControl,
    ExtractionMethod,
    Sensitivity,
    DecayModel,
)


# Try to use sqlcipher; fall back to standard sqlite3
try:
    from pysqlcipher3 import dbapi2 as sqlcipher

    HAS_SQLCIPHER = True
except ImportError:
    sqlcipher = None  # type: ignore[assignment]
    HAS_SQLCIPHER = False


SCHEMA_SQL = """
-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL,
    source_id TEXT,
    title TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    model TEXT
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    source_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Memories
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    confidence_score REAL DEFAULT 1.0,
    decay_model TEXT DEFAULT 'none',
    last_reinforced TEXT,
    created_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    superseded_by TEXT,
    platform TEXT NOT NULL,
    conversation_id TEXT,
    extraction_method TEXT DEFAULT 'manual',
    sensitivity TEXT DEFAULT 'private',
    embedding BLOB,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

-- Memory tags
CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Memory relations
CREATE TABLE IF NOT EXISTS memory_relations (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, relation_type),
    FOREIGN KEY (source_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Access control rules
CREATE TABLE IF NOT EXISTS access_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('allow', 'deny')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_platform ON memories(platform);
CREATE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);
CREATE INDEX IF NOT EXISTS idx_access_rules_memory ON access_rules(memory_id);
"""


class VaultDB:
    """Encrypted SQLite database for the PAM vault."""

    def __init__(self, path: Path, encryption_key: str | None = None):
        self.path = path
        self.encryption_key = encryption_key
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open the database connection and initialize schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if self.encryption_key and HAS_SQLCIPHER:
            self._conn = sqlcipher.connect(str(self.path))
            self._conn.execute(f"PRAGMA key = '{self.encryption_key}'")
        else:
            self._conn = sqlite3.connect(str(self.path))

        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not open. Call open() first.")
        return self._conn

    def __enter__(self) -> VaultDB:
        self.open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # --- Conversation operations ---

    def insert_conversation(self, conv: Conversation) -> None:
        """Insert a conversation and all its messages."""
        self.conn.execute(
            """INSERT OR REPLACE INTO conversations
               (id, source_platform, source_id, title, created_at, updated_at, model)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                conv.id,
                conv.source_platform.value,
                conv.source_id,
                conv.title,
                conv.created_at.isoformat(),
                conv.updated_at.isoformat(),
                conv.model,
            ),
        )
        for i, msg in enumerate(conv.messages):
            self.conn.execute(
                """INSERT OR REPLACE INTO messages
                   (id, conversation_id, source_id, role, content, created_at, sort_order, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg.id,
                    conv.id,
                    msg.source_id,
                    msg.role.value,
                    msg.content,
                    msg.created_at.isoformat(),
                    i,
                    json.dumps(msg.metadata),
                ),
            )
        self.conn.commit()

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Retrieve a conversation by ID."""
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_conversation(row)

    def list_conversations(
        self, platform: Platform | None = None, limit: int = 100, offset: int = 0
    ) -> list[Conversation]:
        """List conversations, optionally filtered by platform."""
        if platform:
            rows = self.conn.execute(
                "SELECT * FROM conversations WHERE source_platform = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (platform.value, limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_conversation(r) for r in rows]

    def _row_to_conversation(self, row: tuple) -> Conversation:
        conv_id = row[0]
        messages_rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sort_order",
            (conv_id,),
        ).fetchall()
        messages = [
            Message(
                id=m[0],
                source_id=m[2],
                role=m[3],
                content=m[4],
                created_at=datetime.fromisoformat(m[5]),
                metadata=json.loads(m[7]) if m[7] else {},
            )
            for m in messages_rows
        ]
        return Conversation(
            id=row[0],
            source_platform=Platform(row[1]),
            source_id=row[2],
            title=row[3] or "",
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            model=row[6],
            messages=messages,
        )

    # --- Memory operations ---

    def insert_memory(self, mem: Memory) -> None:
        """Insert a memory record."""
        embedding_blob = None
        if mem.embedding:
            import struct
            embedding_blob = struct.pack(f"{len(mem.embedding)}f", *mem.embedding)

        self.conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, type, content, content_hash, confidence_score, decay_model,
                last_reinforced, created_at, valid_from, valid_to, superseded_by,
                platform, conversation_id, extraction_method, sensitivity, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mem.id,
                mem.type.value,
                mem.content,
                mem.content_hash,
                mem.confidence.score,
                mem.confidence.decay_model.value,
                mem.confidence.last_reinforced.isoformat(),
                mem.temporal.created_at.isoformat(),
                mem.temporal.valid_from.isoformat() if mem.temporal.valid_from else None,
                mem.temporal.valid_to.isoformat() if mem.temporal.valid_to else None,
                mem.temporal.superseded_by,
                mem.provenance.platform.value,
                mem.provenance.conversation_id,
                mem.provenance.extraction_method.value,
                mem.access_control.sensitivity.value,
                embedding_blob,
            ),
        )
        # Tags
        for tag in mem.tags:
            self.conn.execute(
                "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (mem.id, tag),
            )
        # Relations
        for rel in mem.relations:
            self.conn.execute(
                "INSERT OR IGNORE INTO memory_relations (source_id, target_id, relation_type) VALUES (?, ?, ?)",
                (mem.id, rel.target_id, rel.relation_type.value),
            )
        # Access rules
        for platform_name in mem.access_control.share_with:
            self.conn.execute(
                "INSERT INTO access_rules (memory_id, platform, action, created_at) VALUES (?, ?, 'allow', ?)",
                (mem.id, platform_name, datetime.now(UTC).isoformat()),
            )
        for platform_name in mem.access_control.deny_to:
            self.conn.execute(
                "INSERT INTO access_rules (memory_id, platform, action, created_at) VALUES (?, ?, 'deny', ?)",
                (mem.id, platform_name, datetime.now(UTC).isoformat()),
            )
        self.conn.commit()

    def get_memory(self, memory_id: str) -> Memory | None:
        """Retrieve a memory by ID."""
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_memory(row)

    def list_memories(
        self,
        memory_type: MemoryType | None = None,
        platform: Platform | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories with optional filters."""
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []

        if memory_type:
            query += " AND type = ?"
            params.append(memory_type.value)
        if platform:
            query += " AND platform = ?"
            params.append(platform.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        memories = [self._row_to_memory(r) for r in rows]

        if tags:
            memories = [
                m for m in memories if any(t in m.tags for t in tags)
            ]

        return memories

    def search_memories_text(self, query: str, limit: int = 20) -> list[Memory]:
        """Simple text search on memory content."""
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        cursor = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def _row_to_memory(self, row: tuple) -> Memory:
        memory_id = row[0]
        tags_rows = self.conn.execute(
            "SELECT tag FROM memory_tags WHERE memory_id = ?", (memory_id,)
        ).fetchall()
        tags = [t[0] for t in tags_rows]

        relations_rows = self.conn.execute(
            "SELECT target_id, relation_type FROM memory_relations WHERE source_id = ?",
            (memory_id,),
        ).fetchall()

        embedding = None
        if row[15]:
            import struct
            n_floats = len(row[15]) // 4
            embedding = list(struct.unpack(f"{n_floats}f", row[15]))

        return Memory(
            id=row[0],
            type=MemoryType(row[1]),
            content=row[2],
            content_hash=row[3],
            confidence=Confidence(
                score=row[4],
                decay_model=DecayModel(row[5]),
                last_reinforced=datetime.fromisoformat(row[6]) if row[6] else datetime.now(UTC),
            ),
            temporal=Temporal(
                created_at=datetime.fromisoformat(row[7]),
                valid_from=datetime.fromisoformat(row[8]) if row[8] else None,
                valid_to=datetime.fromisoformat(row[9]) if row[9] else None,
                superseded_by=row[10],
            ),
            provenance=Provenance(
                platform=Platform(row[11]),
                conversation_id=row[12],
                extraction_method=ExtractionMethod(row[13]) if row[13] else ExtractionMethod.MANUAL,
            ),
            access_control=AccessControl(
                sensitivity=Sensitivity(row[14]) if row[14] else Sensitivity.PRIVATE,
            ),
            tags=tags,
            relations=[
                {"target_id": r[0], "relation_type": r[1]} for r in relations_rows
            ],
            embedding=embedding,
        )

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        """Get vault statistics."""
        mem_count = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conv_count = self.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        msg_count = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        platforms = self.conn.execute(
            "SELECT source_platform, COUNT(*) FROM conversations GROUP BY source_platform"
        ).fetchall()

        types = self.conn.execute(
            "SELECT type, COUNT(*) FROM memories GROUP BY type"
        ).fetchall()

        return {
            "total_memories": mem_count,
            "total_conversations": conv_count,
            "total_messages": msg_count,
            "conversations_by_platform": {p[0]: p[1] for p in platforms},
            "memories_by_type": {t[0]: t[1] for t in types},
        }
