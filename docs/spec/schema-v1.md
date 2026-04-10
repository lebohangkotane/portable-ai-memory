# PAM Schema v1 — Portable AI Memory Interchange Format

## Overview

The PAM Schema v1 defines a universal, platform-agnostic format for representing AI conversation history and extracted memories. It enables users to export their data from one AI platform and import it into another, preserving context, preferences, and relationship history.

## Design Principles

1. **Platform-agnostic**: Works with ChatGPT, Claude, Gemini, Copilot, Grok, and any future AI platform
2. **Human-readable**: JSON format that can be inspected and edited manually
3. **Extensible**: New memory types, platforms, and metadata can be added without breaking existing data
4. **Privacy-first**: Built-in access control at the memory level
5. **Content-addressed**: SHA-256 hashing for deduplication and integrity

## Top-Level Structure

```json
{
  "schema_version": "1.0.0",
  "vault_id": "uuid",
  "owner": { "id": "uuid", "display_name": "string" },
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "memories": [...],
  "conversations": [...],
  "preferences": {...}
}
```

## Memory Object

A memory represents a single piece of extracted knowledge about the user.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Yes | Unique identifier |
| `type` | Enum | Yes | One of: fact, preference, skill, goal, relationship, instruction, context, identity, episode, reflection |
| `content` | String | Yes | The memory text |
| `content_hash` | String | Yes | `sha256:<hex>` for deduplication |
| `confidence` | Object | No | Score (0-1), decay model, last reinforced |
| `temporal` | Object | No | Created at, valid from/to, superseded by |
| `provenance` | Object | Yes | Source platform, conversation ID, extraction method |
| `access_control` | Object | No | Share/deny lists, sensitivity level |
| `tags` | Array | No | Keyword tags |
| `relations` | Array | No | Links to other memories (contradicts, supersedes, supports, related_to) |
| `embedding` | Array | No | Vector embedding for semantic search |

### Memory Types

| Type | Description | Example |
|------|-------------|---------|
| `fact` | Factual info about the user | "User is based in Johannesburg" |
| `preference` | User preferences | "Prefers concise responses" |
| `skill` | Skills and expertise | "Experienced with Python and React" |
| `goal` | Goals and projects | "Building a portable AI memory system" |
| `relationship` | People and connections | "Works with a team of 5 developers" |
| `instruction` | How the AI should behave | "Always explain code changes" |
| `context` | Background context | "Working on a deadline for Friday" |
| `identity` | Core identity info | "Software developer" |
| `episode` | Notable interactions | "Debugged a complex async issue together" |
| `reflection` | Meta-observations | "User learns best with examples" |

## Conversation Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Yes | Unique identifier |
| `source_platform` | Enum | Yes | chatgpt, claude, gemini, copilot, grok, manual, other |
| `source_id` | String | No | Original platform ID |
| `title` | String | No | Conversation title |
| `created_at` | ISO-8601 | Yes | When the conversation started |
| `updated_at` | ISO-8601 | Yes | Last message timestamp |
| `model` | String | No | AI model used (e.g., "gpt-4o", "claude-3.5-sonnet") |
| `messages` | Array | Yes | Ordered list of messages |

## Message Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Yes | Unique identifier |
| `source_id` | String | No | Original platform message ID |
| `role` | Enum | Yes | user, assistant, system, tool |
| `content` | String | Yes | Message text |
| `content_parts` | Array | No | Multimodal content (text, image, code, file) |
| `created_at` | ISO-8601 | Yes | Message timestamp |
| `metadata` | Object | No | Platform-specific metadata |

## Compatibility

PAM Schema v1 is designed to be compatible with:
- **PAM (Portable AI Memory) spec**: Can import/export PAM format
- **AMP (AI Memory Protocol)**: Message structure aligns with AMP's normalized format
- **ChatGPT exports**: Direct mapping from conversations.json
- **Claude exports**: Direct mapping from JSON export

## JSON Schema

The formal JSON Schema definition is at: `schema/portable-memory-v1.json`
