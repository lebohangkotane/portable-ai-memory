"""Memory extraction from conversations.

Extracts structured memories (facts, preferences, skills, etc.) from raw
conversation messages using heuristic rules and optional LLM-based extraction.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime

from pam.vault.models import (
    AccessControl,
    Confidence,
    Conversation,
    ExtractionMethod,
    Memory,
    MemoryType,
    Platform,
    Provenance,
    Temporal,
)


# Heuristic patterns for memory extraction
_PATTERNS: list[tuple[MemoryType, list[re.Pattern], list[str]]] = [
    # Facts about the user (from user messages)
    (
        MemoryType.FACT,
        [
            re.compile(r"\bI (?:am|'m)\b (.{5,80})", re.IGNORECASE),
            re.compile(r"\bmy name is\b (.{2,50})", re.IGNORECASE),
            re.compile(r"\bI (?:live|work|study) (?:in|at)\b (.{3,80})", re.IGNORECASE),
            re.compile(r"\bI (?:have|own|use)\b (.{5,80})", re.IGNORECASE),
        ],
        ["identity", "personal"],
    ),
    # Preferences
    (
        MemoryType.PREFERENCE,
        [
            re.compile(r"\bI (?:prefer|like|love|enjoy|want|need)\b (.{5,100})", re.IGNORECASE),
            re.compile(r"\bI (?:don't like|hate|dislike|avoid)\b (.{5,100})", re.IGNORECASE),
            re.compile(r"\bmy (?:favorite|preferred)\b (.{5,80})", re.IGNORECASE),
        ],
        ["preference"],
    ),
    # Skills
    (
        MemoryType.SKILL,
        [
            re.compile(r"\bI (?:know|use|code in|program in|work with)\b (.{3,80})", re.IGNORECASE),
            re.compile(
                r"\bI(?:'m| am) (?:familiar|experienced|proficient) (?:with|in)\b (.{3,80})",
                re.IGNORECASE,
            ),
            re.compile(r"\bI've been (?:using|working with|coding in)\b (.{3,80})", re.IGNORECASE),
        ],
        ["skill", "expertise"],
    ),
    # Goals
    (
        MemoryType.GOAL,
        [
            re.compile(
                r"\bI(?:'m| am) (?:trying to|working on|building|creating)\b (.{5,100})",
                re.IGNORECASE,
            ),
            re.compile(r"\bI want to\b (.{5,100})", re.IGNORECASE),
            re.compile(r"\bmy goal is\b (.{5,100})", re.IGNORECASE),
        ],
        ["goal", "project"],
    ),
    # Instructions (how the user wants the AI to behave)
    (
        MemoryType.INSTRUCTION,
        [
            re.compile(r"\b(?:please |always |never )(.{5,100})", re.IGNORECASE),
            re.compile(r"\bdon't (.{5,80})", re.IGNORECASE),
            re.compile(
                r"\bI (?:want you to|need you to|would like you to)\b (.{5,100})", re.IGNORECASE
            ),
        ],
        ["instruction", "behavior"],
    ),
]


def extract_memories_heuristic(
    conversation: Conversation,
    min_content_length: int = 10,
) -> list[Memory]:
    """Extract memories from a conversation using pattern matching.

    This is the fast, free, offline extraction method. It catches
    explicit statements like "I am a developer" or "I prefer Python".
    For deeper extraction, use LLM-based extraction.
    """
    memories: list[Memory] = []
    seen_hashes: set[str] = set()

    for msg in conversation.messages:
        # Only extract from user messages
        if msg.role.value != "user":
            continue

        content = msg.content
        if len(content) < min_content_length:
            continue

        for memory_type, patterns, tags in _PATTERNS:
            for pattern in patterns:
                matches = pattern.findall(content)
                for match_text in matches:
                    match_text = match_text.strip().rstrip(".,!?")
                    if len(match_text) < 5:
                        continue

                    # Build full memory content with context
                    full_content = _build_memory_content(memory_type, match_text, content)

                    mem = Memory(
                        type=memory_type,
                        content=full_content,
                        confidence=Confidence(score=0.7),  # Heuristic = lower confidence
                        temporal=Temporal(created_at=msg.created_at),
                        provenance=Provenance(
                            platform=conversation.source_platform,
                            conversation_id=conversation.id,
                            extraction_method=ExtractionMethod.HEURISTIC,
                            original_message_id=msg.id,
                        ),
                        tags=list(tags),
                    )

                    # Deduplicate by content hash
                    if mem.content_hash not in seen_hashes:
                        seen_hashes.add(mem.content_hash)
                        memories.append(mem)

    return memories


def _build_memory_content(memory_type: MemoryType, match: str, original: str) -> str:
    """Build a clean memory content string from a regex match."""
    prefix = {
        MemoryType.FACT: "User states: ",
        MemoryType.PREFERENCE: "User preference: ",
        MemoryType.SKILL: "User skill: ",
        MemoryType.GOAL: "User goal: ",
        MemoryType.INSTRUCTION: "User instruction: ",
        MemoryType.RELATIONSHIP: "User relationship: ",
        MemoryType.IDENTITY: "User identity: ",
    }
    p = prefix.get(memory_type, "")
    return f"{p}{match}"


# ── LLM-based extraction (optional, requires API key) ────────────────────────

LLM_EXTRACTION_PROMPT = """Analyze the following conversation and extract structured memories about the user.
For each memory, identify:
- type: one of [fact, preference, skill, goal, relationship, instruction, identity]
- content: the specific information (be concise but complete)
- confidence: how certain (0.0-1.0) based on how explicit the statement was
- tags: relevant keywords

Only extract information explicitly stated or strongly implied by the USER (not the assistant).
Return as JSON array.

Conversation:
{conversation_text}

Extract memories as JSON:"""


def build_llm_extraction_prompt(conversation: Conversation, max_chars: int = 8000) -> str:
    """Build a prompt for LLM-based memory extraction.

    Returns the prompt string. The caller is responsible for sending it
    to an LLM and parsing the response (to avoid hard dependency on any API).
    """
    lines = []
    for msg in conversation.messages:
        role = "User" if msg.role.value == "user" else "Assistant"
        lines.append(f"{role}: {msg.content}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[truncated]"

    return LLM_EXTRACTION_PROMPT.format(conversation_text=text)


def parse_llm_extraction_response(
    response_json: list[dict],
    conversation: Conversation,
) -> list[Memory]:
    """Parse LLM extraction response into Memory objects.

    Expects a list of dicts with: type, content, confidence, tags
    """
    memories = []
    for item in response_json:
        try:
            mem_type = MemoryType(item.get("type", "fact"))
        except ValueError:
            mem_type = MemoryType.FACT

        confidence = float(item.get("confidence", 0.8))
        tags = item.get("tags", [])
        content = item.get("content", "")

        if not content or len(content) < 5:
            continue

        memories.append(
            Memory(
                type=mem_type,
                content=content,
                confidence=Confidence(score=min(confidence, 1.0)),
                temporal=Temporal(created_at=conversation.created_at),
                provenance=Provenance(
                    platform=conversation.source_platform,
                    conversation_id=conversation.id,
                    extraction_method=ExtractionMethod.LLM,
                ),
                tags=tags,
            )
        )

    return memories


# ── LLM extraction callable ───────────────────────────────────────────────────

class LLMExtractionUnavailable(Exception):
    """Raised when LLM extraction cannot proceed (missing key or package)."""


def extract_memories_llm_sync(
    conversation: Conversation,
    api_key: str | None = None,
    model: str = "claude-haiku-4-5-20251001",
) -> list[Memory]:
    """Extract memories using Claude Haiku via the Anthropic API.

    Returns an empty list (never raises) on failure so callers can safely
    fall back to heuristic extraction.

    Requires either the ``api_key`` argument or ``ANTHROPIC_API_KEY`` env var.
    Install the package with: pip install anthropic
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        warnings.warn(
            "LLM extraction skipped: no ANTHROPIC_API_KEY found. "
            "Set the env var or use --api-key. Falling back to heuristic.",
            stacklevel=2,
        )
        return []

    try:
        import anthropic  # optional dependency
    except ImportError:
        warnings.warn(
            "LLM extraction skipped: anthropic package not installed. "
            "Run: pip install anthropic",
            stacklevel=2,
        )
        return []

    try:
        prompt = build_llm_extraction_prompt(conversation)
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Extract JSON array from response (model may wrap it in prose)
        array_match = re.search(r"\[.*\]", text, re.DOTALL)
        if not array_match:
            return []

        parsed = json.loads(array_match.group())
        if not isinstance(parsed, list):
            return []

        return parse_llm_extraction_response(parsed, conversation)

    except Exception as exc:
        warnings.warn(
            f"LLM extraction failed: {exc}. Falling back to heuristic.",
            stacklevel=2,
        )
        return []
