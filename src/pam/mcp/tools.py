"""MCP tool definitions for the PAM memory server.

Tools exposed to Claude Desktop and other MCP clients:
  - search_memory      : semantic + text search across the vault
  - get_context        : build a ready-to-use context string for a conversation
  - add_memory         : manually add a memory to the vault
  - get_user_profile   : return aggregated user preferences and identity
  - get_vault_stats    : show vault statistics
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """Structured result from a tool call."""
    content: str
    is_error: bool = False


# ── Tool schemas (passed to mcp server as tool definitions) ──────────────────

TOOL_SEARCH_MEMORY = {
    "name": "search_memory",
    "description": (
        "Search the user's personal AI memory vault for relevant information. "
        "Use this to recall facts, preferences, skills, goals, and past context "
        "about the user before responding to their message."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for (e.g. 'programming languages', 'work projects', 'preferences')"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of memories to return (default: 10)",
                "default": 10
            },
            "memory_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by type: fact, preference, skill, goal, instruction, identity, relationship, context, episode, reflection",
            },
        },
        "required": ["query"],
    },
}

TOOL_GET_CONTEXT = {
    "name": "get_context",
    "description": (
        "Get a formatted context block about the user, ready to guide your responses. "
        "Call this at the start of a conversation to personalise your assistance. "
        "Returns structured information about who the user is, what they know, and how they like to work."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "conversation_summary": {
                "type": "string",
                "description": "Brief description of what this conversation is about (used to fetch relevant memories)",
            },
            "token_budget": {
                "type": "integer",
                "description": "Maximum tokens for the context output (default: 2000)",
                "default": 2000,
            },
        },
        "required": [],
    },
}

TOOL_ADD_MEMORY = {
    "name": "add_memory",
    "description": (
        "Save a new memory about the user to their personal vault. "
        "Use this when the user shares important information about themselves, "
        "their preferences, skills, goals, or instructions for how you should behave."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The memory content to store"
            },
            "memory_type": {
                "type": "string",
                "enum": ["fact", "preference", "skill", "goal", "instruction", "identity", "relationship", "context"],
                "description": "Type of memory",
                "default": "fact",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags to categorise the memory",
            },
        },
        "required": ["content"],
    },
}

TOOL_GET_USER_PROFILE = {
    "name": "get_user_profile",
    "description": (
        "Get a summary of the user's profile — their identity, expertise, preferences, "
        "and communication style. Use this to understand who you're talking to."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

TOOL_GET_VAULT_STATS = {
    "name": "get_vault_stats",
    "description": "Get statistics about the user's memory vault — conversation count, memory count, platforms imported.",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

ALL_TOOLS = [
    TOOL_SEARCH_MEMORY,
    TOOL_GET_CONTEXT,
    TOOL_ADD_MEMORY,
    TOOL_GET_USER_PROFILE,
    TOOL_GET_VAULT_STATS,
]
