"""PAM MCP Server — exposes the memory vault to Claude Desktop and other MCP clients.

Run with:
    python -m pam.mcp.server

Then add to Claude Desktop's config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "pam": {
          "command": "python",
          "args": ["-m", "pam.mcp.server"],
          "cwd": "D:/LK/Projects/Portable AI memory system"
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

# ── PAM imports ──────────────────────────────────────────────────────────────
# Register adapters (side-effect import)
import pam.adapters.chatgpt  # noqa: F401
import pam.adapters.claude   # noqa: F401
import pam.adapters.copilot  # noqa: F401

from pam.config import DEFAULT_VAULT_PATH, DEFAULT_TOKEN_BUDGET
from pam.context.builder import build_context
from pam.context.privacy import PrivacyConfig
from pam.mcp.tools import ALL_TOOLS
from pam.vault.database import VaultDB
from pam.vault.models import (
    Confidence,
    ExtractionMethod,
    Memory,
    MemoryType,
    Platform,
    Provenance,
    Temporal,
)

# ── Server setup ─────────────────────────────────────────────────────────────

server = Server("pam-memory")
_db: VaultDB | None = None
_privacy: PrivacyConfig | None = None


def _get_db() -> VaultDB:
    global _db
    if _db is None:
        _db = VaultDB(DEFAULT_VAULT_PATH)
        _db.open()
    return _db


def _get_privacy() -> PrivacyConfig:
    global _privacy
    if _privacy is None:
        from pam.config import CONFIG_DIR
        _privacy = PrivacyConfig.load(CONFIG_DIR / "privacy.json")
    return _privacy


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all available PAM tools."""
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in ALL_TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    try:
        if name == "search_memory":
            result = await _handle_search_memory(arguments)
        elif name == "get_context":
            result = await _handle_get_context(arguments)
        elif name == "add_memory":
            result = await _handle_add_memory(arguments)
        elif name == "get_user_profile":
            result = await _handle_get_user_profile(arguments)
        elif name == "get_vault_stats":
            result = await _handle_get_vault_stats(arguments)
        else:
            result = f"Unknown tool: {name}"

        return [types.TextContent(type="text", text=result)]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"PAM error in {name}: {type(e).__name__}: {e}"
        )]


# ── Individual handlers ───────────────────────────────────────────────────────

async def _handle_search_memory(args: dict) -> str:
    query = args.get("query", "")
    limit = int(args.get("limit", 10))
    memory_types = args.get("memory_types", [])

    db = _get_db()

    # Try semantic search first, fall back to text
    all_memories = db.list_memories(limit=2000)

    if memory_types:
        all_memories = [m for m in all_memories if m.type.value in memory_types]

    # Filter by privacy for Claude
    privacy = _get_privacy()
    all_memories = privacy.filter_memories(all_memories, "claude")

    # Memories with embeddings → semantic search
    with_embeddings = [m for m in all_memories if m.embedding is not None]
    without_embeddings = [m for m in all_memories if m.embedding is None]

    results = []

    if with_embeddings:
        try:
            from pam.search.vector_store import search_combined
            semantic_results = search_combined(query, with_embeddings, top_k=limit)
            results = [(m, score) for m, score in semantic_results]
        except ImportError:
            pass

    # Fill remaining slots with text search
    if len(results) < limit:
        text_results = db.search_memories_text(query, limit=limit)
        seen_ids = {m.id for m, _ in results}
        for mem in text_results:
            if mem.id not in seen_ids and len(results) < limit:
                results.append((mem, 0.5))

    if not results:
        return f"No memories found matching '{query}'."

    lines = [f"## Memory search results for: '{query}'\n"]
    for mem, score in results:
        lines.append(
            f"**[{mem.type.value}]** {mem.content}\n"
            f"  *Source: {mem.provenance.platform.value} | "
            f"Confidence: {mem.confidence.score:.0%} | "
            f"Tags: {', '.join(mem.tags) if mem.tags else 'none'}*\n"
        )

    return "\n".join(lines)


async def _handle_get_context(args: dict) -> str:
    conversation_summary = args.get("conversation_summary", "")
    token_budget = int(args.get("token_budget", DEFAULT_TOKEN_BUDGET))

    db = _get_db()
    privacy = _get_privacy()

    # Get all memories filtered by privacy
    all_memories = db.list_memories(limit=2000)
    filtered = privacy.filter_memories(all_memories, "claude")

    # If we have a summary, rank by relevance
    if conversation_summary and filtered:
        try:
            from pam.search.vector_store import search_combined
            with_embeddings = [m for m in filtered if m.embedding is not None]
            if with_embeddings:
                ranked = search_combined(conversation_summary, with_embeddings, top_k=50)
                ranked_ids = {m.id for m, _ in ranked}
                # Put ranked first, then the rest
                filtered = [m for m, _ in ranked] + [m for m in filtered if m.id not in ranked_ids]
        except ImportError:
            pass

    context = build_context(
        memories=filtered,
        privacy_config=privacy,
        target_platform="claude",
        token_budget=token_budget,
        include_header=True,
    )

    if not context:
        return "No context available yet. Import some conversations with: pam import copilot your-export.csv"

    return context


async def _handle_add_memory(args: dict) -> str:
    content = args.get("content", "").strip()
    if not content:
        return "Error: content cannot be empty."

    memory_type_str = args.get("memory_type", "fact")
    tags = args.get("tags", [])

    try:
        mem_type = MemoryType(memory_type_str)
    except ValueError:
        mem_type = MemoryType.FACT

    db = _get_db()

    mem = Memory(
        type=mem_type,
        content=content,
        confidence=Confidence(score=0.95),
        temporal=Temporal(created_at=datetime.now(UTC)),
        provenance=Provenance(
            platform=Platform.MANUAL,
            extraction_method=ExtractionMethod.MANUAL,
        ),
        tags=tags,
    )

    # Generate embedding if possible
    try:
        from pam.search.embeddings import embed_text
        mem.embedding = embed_text(content)
    except ImportError:
        pass

    db.insert_memory(mem)
    return f"Memory saved: [{mem_type.value}] {content}"


async def _handle_get_user_profile(args: dict) -> str:
    db = _get_db()
    privacy = _get_privacy()

    all_memories = db.list_memories(limit=2000)
    filtered = privacy.filter_memories(all_memories, "claude")

    # Group key identity/preference/skill memories
    identity = [m for m in filtered if m.type.value in ("identity", "fact")]
    skills = [m for m in filtered if m.type.value == "skill"]
    preferences = [m for m in filtered if m.type.value == "preference"]
    goals = [m for m in filtered if m.type.value == "goal"]
    instructions = [m for m in filtered if m.type.value == "instruction"]

    stats = db.get_stats()

    lines = ["## User Profile — from PAM vault\n"]

    if identity:
        lines.append("### Who they are")
        for m in identity[:5]:
            lines.append(f"- {m.content}")
        lines.append("")

    if skills:
        lines.append("### Skills & expertise")
        for m in skills[:8]:
            lines.append(f"- {m.content}")
        lines.append("")

    if preferences:
        lines.append("### Preferences")
        for m in preferences[:8]:
            lines.append(f"- {m.content}")
        lines.append("")

    if goals:
        lines.append("### Current goals & projects")
        for m in goals[:5]:
            lines.append(f"- {m.content}")
        lines.append("")

    if instructions:
        lines.append("### How they like to work")
        for m in instructions[:5]:
            lines.append(f"- {m.content}")
        lines.append("")

    lines.append(f"*Vault: {stats['total_memories']} memories from {stats['total_conversations']} conversations*")

    return "\n".join(lines)


async def _handle_get_vault_stats(args: dict) -> str:
    db = _get_db()
    stats = db.get_stats()

    platforms = "\n".join(
        f"  - {k}: {v} conversations"
        for k, v in stats["conversations_by_platform"].items()
    )
    types_ = "\n".join(
        f"  - {k}: {v}"
        for k, v in stats["memories_by_type"].items()
    )

    return (
        f"## PAM Vault Statistics\n\n"
        f"**Memories:** {stats['total_memories']}\n"
        f"**Conversations:** {stats['total_conversations']}\n"
        f"**Messages:** {stats['total_messages']}\n\n"
        f"**By platform:**\n{platforms}\n\n"
        f"**By memory type:**\n{types_}\n"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="pam-memory",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
