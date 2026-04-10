"""Pydantic models for the PAM universal memory schema.

These models define both the internal data structures and the interchange format (JSON export/import).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


# --- Enums ---


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    SKILL = "skill"
    GOAL = "goal"
    RELATIONSHIP = "relationship"
    INSTRUCTION = "instruction"
    CONTEXT = "context"
    IDENTITY = "identity"
    EPISODE = "episode"
    REFLECTION = "reflection"


class DecayModel(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    NONE = "none"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


class RelationType(str, Enum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    SUPPORTS = "supports"
    RELATED_TO = "related_to"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Platform(str, Enum):
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    GEMINI = "gemini"
    COPILOT = "copilot"
    GROK = "grok"
    MANUAL = "manual"
    OTHER = "other"


class ExtractionMethod(str, Enum):
    LLM = "llm"
    HEURISTIC = "heuristic"
    MANUAL = "manual"


class ContentPartType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    CODE = "code"
    FILE = "file"


# --- Sub-models ---


class Confidence(BaseModel):
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    decay_model: DecayModel = DecayModel.NONE
    last_reinforced: datetime = Field(default_factory=_now)


class Temporal(BaseModel):
    created_at: datetime = Field(default_factory=_now)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None


class Provenance(BaseModel):
    platform: Platform
    conversation_id: str | None = None
    extraction_method: ExtractionMethod = ExtractionMethod.MANUAL
    original_message_id: str | None = None


class AccessControl(BaseModel):
    share_with: list[str] = Field(default_factory=list, description="Platform names allowed")
    deny_to: list[str] = Field(default_factory=list, description="Platform names denied")
    sensitivity: Sensitivity = Sensitivity.PRIVATE


class MemoryRelation(BaseModel):
    target_id: str
    relation_type: RelationType


# --- Core models ---


class Memory(BaseModel):
    id: str = Field(default_factory=_new_id)
    type: MemoryType
    content: str
    content_hash: str = ""
    confidence: Confidence = Field(default_factory=Confidence)
    temporal: Temporal = Field(default_factory=Temporal)
    provenance: Provenance
    access_control: AccessControl = Field(default_factory=AccessControl)
    tags: list[str] = Field(default_factory=list)
    relations: list[MemoryRelation] = Field(default_factory=list)
    embedding: list[float] | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = f"sha256:{hashlib.sha256(self.content.encode()).hexdigest()}"


class ContentPart(BaseModel):
    type: ContentPartType = ContentPartType.TEXT
    data: str = ""


class Message(BaseModel):
    id: str = Field(default_factory=_new_id)
    source_id: str | None = None
    role: MessageRole
    content: str
    content_parts: list[ContentPart] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    id: str = Field(default_factory=_new_id)
    source_platform: Platform
    source_id: str | None = None
    title: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    model: str | None = None
    messages: list[Message] = Field(default_factory=list)


class UserPreferences(BaseModel):
    communication_style: str = ""
    expertise_areas: list[str] = Field(default_factory=list)
    language: str = "en"
    custom: dict[str, Any] = Field(default_factory=dict)


class Owner(BaseModel):
    id: str = Field(default_factory=_new_id)
    display_name: str = ""


# --- Top-level interchange format ---


class PortableMemoryVault(BaseModel):
    """The top-level interchange format for import/export."""

    schema_version: str = "1.0.0"
    vault_id: str = Field(default_factory=_new_id)
    owner: Owner = Field(default_factory=Owner)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    memories: list[Memory] = Field(default_factory=list)
    conversations: list[Conversation] = Field(default_factory=list)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
