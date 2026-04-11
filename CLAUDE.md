# PAM — Portable AI Memory

User-owned, encrypted vault for AI conversation history. Lets users migrate context between AI platforms (ChatGPT, Claude, Copilot, Gemini) without losing accumulated knowledge.

## Stack
- Python 3.14, SQLite (WAL mode), Pydantic v2, Typer+Rich CLI
- `mcp` 1.27 for Claude Desktop integration
- sentence-transformers (all-MiniLM-L6-v2) for semantic search
- Apache 2.0, local-first, privacy-first (DENY ALL default)

## Structure
```
src/pam/
  vault/        — SQLite DB (database.py) + Pydantic models (models.py)
  adapters/     — Platform importers: chatgpt.py, claude.py, copilot.py
  memory/       — Heuristic extractor (extractor.py)
  search/       — Embeddings (embeddings.py) + vector store (vector_store.py)
  context/      — Privacy filter (privacy.py) + context builder (builder.py)
  mcp/          — MCP server (server.py) + tool schemas (tools.py)
  cli.py        — Typer CLI entry point
  config.py     — Paths and defaults
```

## Phases
- **Phase 1** (done): Vault + adapters (ChatGPT, Claude, Copilot) + CLI + tests
- **Phase 2** (done): MCP server — 5 tools live in Claude Desktop
- **Phase 3** (next): Browser extension + Gemini adapter + LLM-powered extraction
- **Phase 4** (future): Tauri desktop app, React UI, cloud sync, open spec RFC

## Key facts
- Vault at `%APPDATA%\pam\vault.db` (Windows)
- Real data: 407 Copilot convos, 8,622 messages, 737 memories imported and working
- MCP config at `%APPDATA%\Claude\claude_desktop_config.json`
- Python at `C:\Python314\python.exe`
- GitHub: `lebohangkotane/portable-ai-memory`
- `gh` CLI at `C:\Program Files\GitHub CLI\gh.exe`
- Tests: `pytest` — 40 tests passing across all modules

## Conventions
- Use `datetime.now(UTC)` not `datetime.utcnow()` (deprecated in 3.14)
- Feature branches → PR → merge, never commit directly to master
- Windows terminal is CP1252 — avoid non-ASCII chars in CLI output
- `NotificationOptions()` not `None` for mcp 1.27 `get_capabilities()`
