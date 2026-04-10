# PAM — Portable AI Memory

**Own your AI relationships. Take them anywhere.**

PAM is a user-owned, encrypted vault for AI conversation history and memory. Import your conversations from ChatGPT, Claude, Gemini, and more — then carry that context to any AI platform you choose. No more starting over when you switch AI providers.

## The Problem

Every time you switch AI platforms, you lose everything:
- Months of conversation history
- Preferences the AI learned about you
- The relationship and context you built up
- Your communication style and expertise the AI understood

Each platform is a walled garden. **PAM breaks down those walls.**

## How It Works

```
ChatGPT export ──┐
Claude export  ──┼──▶ PAM Vault ──▶ Context Builder ──▶ Any AI
Gemini export  ──┘    (encrypted)    (privacy filter)
```

1. **Export** your data from any AI platform (they all offer this)
2. **Import** into your local, encrypted PAM vault
3. **Memories are extracted** automatically (facts, preferences, skills, goals)
4. **Context is injected** into whichever AI you use next (via MCP, browser extension, or API)

Your data stays on your machine. You control what each AI can see.

## Quick Start

```bash
# Install
pip install pam

# Initialize your vault
pam init

# Import ChatGPT conversations
pam import chatgpt ~/Downloads/chatgpt-export.zip

# Import Claude conversations
pam import claude ~/Downloads/claude-export.json

# See what was extracted
pam list memories

# Search your memory vault
pam search "programming languages I know"

# View stats
pam stats

# Export as portable JSON
pam export my-ai-memory.json
```

## Features

### Phase 1 (Current — MVP)
- [x] Import from ChatGPT (ZIP or JSON)
- [x] Import from Claude (JSON)
- [x] Encrypted local SQLite vault
- [x] Automatic memory extraction (heuristic)
- [x] Text and semantic search
- [x] CLI interface
- [x] Portable JSON export (universal schema v1)
- [x] Per-platform privacy controls

### Phase 2 (Planned)
- [ ] MCP server for Claude Desktop integration
- [ ] Local web UI for memory management
- [ ] LLM-based memory extraction (deeper, more accurate)
- [ ] Token budget management for context injection

### Phase 3 (Planned)
- [ ] Chrome browser extension (inject context into ChatGPT/Gemini web)
- [ ] Gemini, Copilot, Grok import adapters
- [ ] Memory deduplication and conflict resolution
- [ ] Temporal reasoning (fact validity windows)

### Phase 4 (Planned)
- [ ] Desktop app (Tauri + React)
- [ ] Memory graph visualization
- [ ] E2E encrypted cloud sync
- [ ] Formal spec publication

## Architecture

```
src/pam/
├── cli.py              # Command-line interface
├── config.py           # Global configuration
├── vault/
│   ├── database.py     # Encrypted SQLite vault
│   ├── models.py       # Pydantic models (universal schema)
│   └── encryption.py   # Key derivation and management
├── adapters/
│   ├── base.py         # Abstract adapter interface
│   ├── chatgpt.py      # ChatGPT import adapter
│   └── claude.py       # Claude import adapter
├── memory/
│   └── extractor.py    # Memory extraction (heuristic + LLM)
├── search/
│   ├── embeddings.py   # Local sentence-transformer embeddings
│   └── vector_store.py # Semantic search
├── context/
│   ├── builder.py      # Context assembly for injection
│   └── privacy.py      # Per-platform access control
└── mcp/                # MCP server (Phase 2)
```

## Universal Memory Schema

PAM uses an open, documented schema for memory interchange. See [schema/portable-memory-v1.json](schema/portable-memory-v1.json).

Key concepts:
- **Memories**: facts, preferences, skills, goals, relationships, instructions — each with confidence scores, temporal validity, and provenance tracking
- **Conversations**: normalized messages from any platform
- **Privacy controls**: per-memory and per-platform access rules

## Privacy Model

```
Default: DENY ALL — nothing shared unless explicitly allowed.

Per-platform rules:
  claude:   allow [fact, preference, skill, identity, goal]
  chatgpt:  allow [fact, preference, skill, identity, goal]
  gemini:   allow [fact, preference, skill, identity, goal]
  *:        allow [preference, skill] (public only)
```

You control exactly what each AI platform can see. Sensitive memories are never shared without explicit permission.

## Adding a New Platform Adapter

```python
from pam.adapters.base import PlatformAdapter, register_adapter
from pam.vault.models import Conversation

@register_adapter
class MyPlatformAdapter(PlatformAdapter):
    platform_name = "myplatform"
    supported_formats = [".json"]
    description = "Import from MyPlatform"

    def detect(self, path): ...
    def parse(self, path) -> Iterator[Conversation]: ...
    def get_platform_metadata(self, path) -> dict: ...
```

## Development

```bash
# Clone
git clone https://github.com/yourusername/pam.git
cd pam

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Why "PAM"?

**P**ortable **A**I **M**emory. Also, PAM is a friendly name — like a personal assistant who remembers everything about you, no matter which AI you're talking to.
