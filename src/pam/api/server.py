"""PAM Local HTTP API Server.

Provides a REST API on localhost:8765 for the Chrome browser extension.
The MCP server uses stdio; this server uses HTTP so browser extensions can reach it.

Run with:
    pam api
    # or directly:
    python -m pam.api.server
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from pam.api import handlers
from pam.config import DEFAULT_TOKEN_BUDGET, DEFAULT_VAULT_PATH
from pam.vault.database import VaultDB

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PAM Local API",
    description="Portable AI Memory — local REST API for browser extension integration",
    version="0.1.0",
)

# Wildcard CORS is intentional and safe: localhost:8765 is only reachable locally.
# Chrome extensions use chrome-extension://[variable-id]/ as their origin, so
# a specific origin allowlist would break every new install.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Request / Response models ─────────────────────────────────────────────────


class MemoryIn(BaseModel):
    content: str
    memory_type: str = "fact"
    tags: list[str] = []

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v.strip()


class MemoryOut(BaseModel):
    id: str
    type: str
    content: str
    confidence: float
    platform: str
    tags: list[str]
    created_at: str


class ContextResponse(BaseModel):
    context: str
    memory_count: int
    token_estimate: int


class StatsResponse(BaseModel):
    total_memories: int
    total_conversations: int
    total_messages: int
    memories_by_type: dict[str, int]
    conversations_by_platform: dict[str, int]


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_db() -> VaultDB:
    db = VaultDB(DEFAULT_VAULT_PATH)
    db.open()
    return db


def _memory_to_out(m) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        type=m.type.value,
        content=m.content,
        confidence=m.confidence.score,
        platform=m.provenance.platform.value,
        tags=m.tags,
        created_at=m.temporal.created_at.isoformat(),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    """Check if the PAM API is running."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/context", response_model=ContextResponse)
def get_context(
    summary: str = "",
    token_budget: int = DEFAULT_TOKEN_BUDGET,
):
    """Get a formatted context block about the user."""
    db = _get_db()
    try:
        text, count = handlers.get_context_string(db, summary=summary, token_budget=token_budget)
    finally:
        db.close()
    return ContextResponse(
        context=text,
        memory_count=count,
        token_estimate=len(text) // 4,
    )


@app.get("/memories", response_model=list[MemoryOut])
def list_memories(
    q: str = "",
    limit: int = 10,
    types: str = "",
):
    """Search or list memories from the vault."""
    memory_types = [t.strip() for t in types.split(",") if t.strip()] if types else []
    db = _get_db()
    try:
        mems = handlers.search_memories(db, query=q, limit=limit, memory_types=memory_types or None)
    finally:
        db.close()
    return [_memory_to_out(m) for m in mems]


@app.post("/memories", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def add_memory(body: MemoryIn):
    """Add a new memory to the vault."""
    db = _get_db()
    try:
        mem = handlers.add_memory_to_vault(
            db,
            content=body.content,
            memory_type=body.memory_type,
            tags=body.tags,
        )
    finally:
        db.close()
    return _memory_to_out(mem)


@app.get("/stats", response_model=StatsResponse)
def get_stats():
    """Get vault statistics."""
    db = _get_db()
    try:
        s = handlers.get_stats_dict(db)
    finally:
        db.close()
    return StatsResponse(
        total_memories=s["total_memories"],
        total_conversations=s["total_conversations"],
        total_messages=s.get("total_messages", 0),
        memories_by_type=s.get("memories_by_type", {}),
        conversations_by_platform=s.get("conversations_by_platform", {}),
    )


@app.get("/profile")
def get_profile():
    """Get a compact user profile summary."""
    db = _get_db()
    try:
        profile = handlers.get_compact_profile_string(db)
    finally:
        db.close()
    return {"profile": profile}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("pam.api.server:app", host="127.0.0.1", port=8765, reload=False)
