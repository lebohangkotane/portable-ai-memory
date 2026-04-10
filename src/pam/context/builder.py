"""Context builder — assembles relevant memories for injection into AI conversations.

Takes a query or conversation summary, searches the vault for relevant memories,
applies privacy filters, and formats the result within a token budget.
"""

from __future__ import annotations

from pam.vault.models import Memory, MemoryType
from pam.context.privacy import PrivacyConfig


# Rough token estimation: ~4 chars per token for English
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // CHARS_PER_TOKEN


def build_context(
    memories: list[Memory],
    privacy_config: PrivacyConfig,
    target_platform: str,
    token_budget: int = 4000,
    include_header: bool = True,
) -> str:
    """Build a formatted context string from memories.

    Args:
        memories: Relevant memories (already ranked by relevance).
        privacy_config: Privacy rules to apply.
        target_platform: Which AI platform will receive this context.
        token_budget: Maximum tokens for the output.
        include_header: Whether to add a header explaining the context.

    Returns:
        Formatted context string ready for system prompt injection.
    """
    # Apply privacy filter
    filtered = privacy_config.filter_memories(memories, target_platform)

    if not filtered:
        return ""

    parts: list[str] = []

    if include_header:
        header = (
            "[User Memory Context — from Portable AI Memory vault]\n"
            "The following is information the user has shared in previous AI conversations. "
            "Use it to personalize your responses.\n"
        )
        parts.append(header)

    # Group by type for cleaner presentation
    by_type: dict[MemoryType, list[Memory]] = {}
    for mem in filtered:
        by_type.setdefault(mem.type, []).append(mem)

    type_labels = {
        MemoryType.FACT: "Facts about the user",
        MemoryType.PREFERENCE: "User preferences",
        MemoryType.SKILL: "Skills & expertise",
        MemoryType.GOAL: "Goals & projects",
        MemoryType.INSTRUCTION: "Communication preferences",
        MemoryType.IDENTITY: "Identity",
        MemoryType.RELATIONSHIP: "Relationships",
        MemoryType.CONTEXT: "Context",
        MemoryType.EPISODE: "Notable interactions",
        MemoryType.REFLECTION: "Reflections",
    }

    budget_chars = token_budget * CHARS_PER_TOKEN
    current_chars = sum(len(p) for p in parts)

    for mem_type in [
        MemoryType.IDENTITY,
        MemoryType.FACT,
        MemoryType.SKILL,
        MemoryType.PREFERENCE,
        MemoryType.GOAL,
        MemoryType.INSTRUCTION,
        MemoryType.RELATIONSHIP,
        MemoryType.CONTEXT,
        MemoryType.EPISODE,
        MemoryType.REFLECTION,
    ]:
        mems = by_type.get(mem_type, [])
        if not mems:
            continue

        section = f"\n## {type_labels.get(mem_type, mem_type.value)}\n"
        for mem in mems:
            line = f"- {mem.content}\n"
            if current_chars + len(section) + len(line) > budget_chars:
                break
            section += line

        if current_chars + len(section) > budget_chars:
            break

        parts.append(section)
        current_chars += len(section)

    return "".join(parts)
