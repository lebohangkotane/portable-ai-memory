"""PAM CLI — command-line interface for the Portable AI Memory system.

Usage:
    pam import chatgpt export.zip     Import conversations from ChatGPT
    pam import claude export.json     Import conversations from Claude
    pam import auto export.zip        Auto-detect platform and import
    pam search "my skills"            Search memories semantically
    pam list memories                 List all extracted memories
    pam list conversations            List imported conversations
    pam stats                         Show vault statistics
    pam export output.json            Export vault as portable JSON
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from pam import __version__
from pam.config import DEFAULT_VAULT_PATH, CONFIG_DIR
from pam.vault.database import VaultDB
from pam.vault.models import MemoryType, Platform, PortableMemoryVault
from pam.context.privacy import PrivacyConfig

# Import adapters to trigger registration
import pam.adapters.chatgpt  # noqa: F401
import pam.adapters.claude  # noqa: F401
import pam.adapters.copilot  # noqa: F401
import pam.adapters.gemini  # noqa: F401

from pam.adapters.base import get_adapter, auto_detect_adapter, list_adapters
from pam.memory.extractor import extract_memories_heuristic, extract_memories_llm_sync

console = Console()
app = typer.Typer(
    name="pam",
    help="PAM — Portable AI Memory: Own your AI conversation history.",
    no_args_is_help=True,
)


def _get_db(vault_path: Path | None = None) -> VaultDB:
    """Get a VaultDB instance."""
    path = vault_path or DEFAULT_VAULT_PATH
    db = VaultDB(path)
    db.open()
    return db


# --- Import command ---

@app.command(name="import")
def import_data(
    platform: str = typer.Argument(
        help="Platform to import from (chatgpt, claude, copilot, gemini, auto)"
    ),
    file: Path = typer.Argument(help="Path to the export file (ZIP, JSON, or CSV)"),
    extract_memories: bool = typer.Option(
        True, "--extract/--no-extract", help="Extract memories from conversations"
    ),
    use_llm: bool = typer.Option(
        False, "--llm/--no-llm",
        help="Use Claude Haiku for higher-quality memory extraction (requires ANTHROPIC_API_KEY)",
    ),
    vault_path: Optional[Path] = typer.Option(None, "--vault", help="Custom vault path"),
):
    """Import conversations from an AI platform export."""
    if not file.exists():
        console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1)

    # Get adapter
    if platform == "auto":
        adapter = auto_detect_adapter(file)
        if adapter is None:
            console.print("[red]Error: Could not detect platform from file.[/red]")
            console.print("Try specifying the platform explicitly: pam import chatgpt file.zip")
            raise typer.Exit(1)
        console.print(f"[green]Detected platform: {adapter.platform_name}[/green]")
    else:
        try:
            adapter = get_adapter(platform)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    # Validate
    issues = adapter.validate(file)
    if issues:
        for issue in issues:
            console.print(f"[yellow]Warning: {issue}[/yellow]")

    # Show metadata
    try:
        meta = adapter.get_platform_metadata(file)
        console.print(Panel(
            f"Platform: {meta.get('platform', 'unknown')}\n"
            f"Conversations: {meta.get('total_conversations', '?')}\n"
            f"Date range: {meta.get('date_range', {}).get('earliest', '?')} to "
            f"{meta.get('date_range', {}).get('latest', '?')}",
            title="Export Info",
            box=box.ROUNDED,
        ))
    except Exception as e:
        console.print(f"[yellow]Could not read metadata: {e}[/yellow]")

    # Import
    db = _get_db(vault_path)
    try:
        conv_count = 0
        mem_count = 0

        with console.status("[bold green]Importing conversations..."):
            for conversation in adapter.parse(file):
                db.insert_conversation(conversation)
                conv_count += 1

                if extract_memories:
                    if use_llm:
                        memories = extract_memories_llm_sync(conversation)
                        if not memories:
                            memories = extract_memories_heuristic(conversation)
                    else:
                        memories = extract_memories_heuristic(conversation)
                    for mem in memories:
                        db.insert_memory(mem)
                        mem_count += 1

        console.print(f"\n[bold green]Import complete![/bold green]")
        console.print(f"  Conversations imported: {conv_count}")
        if extract_memories:
            console.print(f"  Memories extracted: {mem_count}")
        console.print(f"  Vault: {db.path}")
    finally:
        db.close()


# --- Search command ---

@app.command()
def search(
    query: str = typer.Argument(help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    memory_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    vault_path: Optional[Path] = typer.Option(None, "--vault", help="Custom vault path"),
    semantic: bool = typer.Option(False, "--semantic", "-s", help="Use semantic search (requires sentence-transformers)"),
):
    """Search your memory vault."""
    db = _get_db(vault_path)
    try:
        if semantic:
            # Semantic search requires embeddings
            try:
                all_memories = db.list_memories(limit=1000)
                from pam.search.vector_store import search_combined
                results = search_combined(query, all_memories, top_k=limit)
                if not results:
                    console.print("[yellow]No matching memories found.[/yellow]")
                    return
                table = Table(title=f"Search Results: '{query}'", box=box.ROUNDED)
                table.add_column("Score", width=6)
                table.add_column("Type", width=12)
                table.add_column("Content", min_width=40)
                table.add_column("Platform", width=10)
                for mem, score in results:
                    table.add_row(
                        f"{score:.2f}",
                        mem.type.value,
                        mem.content[:100],
                        mem.provenance.platform.value,
                    )
                console.print(table)
            except ImportError:
                console.print("[yellow]sentence-transformers not installed. Using text search.[/yellow]")
                semantic = False

        if not semantic:
            # Text search
            results = db.search_memories_text(query, limit=limit)
            if not results:
                console.print("[yellow]No matching memories found.[/yellow]")
                return
            table = Table(title=f"Search Results: '{query}'", box=box.ROUNDED)
            table.add_column("Type", width=12)
            table.add_column("Content", min_width=50)
            table.add_column("Platform", width=10)
            table.add_column("Confidence", width=10)
            for mem in results:
                table.add_row(
                    mem.type.value,
                    mem.content[:100],
                    mem.provenance.platform.value,
                    f"{mem.confidence.score:.0%}",
                )
            console.print(table)
    finally:
        db.close()


# --- List command ---

list_app = typer.Typer(help="List vault contents")
app.add_typer(list_app, name="list")


@list_app.command("memories")
def list_memories(
    memory_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Filter by platform"),
    limit: int = typer.Option(50, "--limit", "-n"),
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """List extracted memories."""
    db = _get_db(vault_path)
    try:
        mt = MemoryType(memory_type) if memory_type else None
        pf = Platform(platform) if platform else None
        memories = db.list_memories(memory_type=mt, platform=pf, limit=limit)

        if not memories:
            console.print("[yellow]No memories found. Import some conversations first![/yellow]")
            return

        table = Table(title="Memories", box=box.ROUNDED)
        table.add_column("Type", width=12)
        table.add_column("Content", min_width=50)
        table.add_column("Platform", width=10)
        table.add_column("Confidence", width=10)
        table.add_column("Tags", width=20)

        for mem in memories:
            table.add_row(
                mem.type.value,
                mem.content[:80],
                mem.provenance.platform.value,
                f"{mem.confidence.score:.0%}",
                ", ".join(mem.tags[:3]),
            )
        console.print(table)
        console.print(f"\nShowing {len(memories)} memories")
    finally:
        db.close()


@list_app.command("conversations")
def list_conversations(
    platform: Optional[str] = typer.Option(None, "--platform", "-p"),
    limit: int = typer.Option(50, "--limit", "-n"),
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """List imported conversations."""
    db = _get_db(vault_path)
    try:
        pf = Platform(platform) if platform else None
        conversations = db.list_conversations(platform=pf, limit=limit)

        if not conversations:
            console.print("[yellow]No conversations found. Import some first![/yellow]")
            return

        table = Table(title="Conversations", box=box.ROUNDED)
        table.add_column("Title", min_width=40)
        table.add_column("Platform", width=10)
        table.add_column("Messages", width=9)
        table.add_column("Model", width=15)
        table.add_column("Date", width=12)

        for conv in conversations:
            table.add_row(
                conv.title[:50],
                conv.source_platform.value,
                str(len(conv.messages)),
                conv.model or "—",
                conv.created_at.strftime("%Y-%m-%d"),
            )
        console.print(table)
        console.print(f"\nShowing {len(conversations)} conversations")
    finally:
        db.close()


@list_app.command("adapters")
def list_available_adapters():
    """List available import adapters."""
    adapters = list_adapters()
    table = Table(title="Available Import Adapters", box=box.ROUNDED)
    table.add_column("Platform", width=12)
    table.add_column("Formats", width=15)
    table.add_column("Description", min_width=40)
    for name, cls in sorted(adapters.items()):
        table.add_row(
            name,
            ", ".join(cls.supported_formats),
            cls.description,
        )
    console.print(table)


# --- Stats command ---

@app.command()
def stats(
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """Show vault statistics."""
    db = _get_db(vault_path)
    try:
        s = db.get_stats()
        console.print(Panel(
            f"[bold]Total memories:[/bold] {s['total_memories']}\n"
            f"[bold]Total conversations:[/bold] {s['total_conversations']}\n"
            f"[bold]Total messages:[/bold] {s['total_messages']}\n"
            f"\n[bold]Conversations by platform:[/bold]\n"
            + "\n".join(f"  {k}: {v}" for k, v in s['conversations_by_platform'].items())
            + f"\n\n[bold]Memories by type:[/bold]\n"
            + "\n".join(f"  {k}: {v}" for k, v in s['memories_by_type'].items()),
            title="Vault Statistics",
            box=box.ROUNDED,
        ))
        console.print(f"\nVault location: {db.path}")
    finally:
        db.close()


# --- Export command ---

@app.command("export")
def export_vault(
    output: Path = typer.Argument(help="Output file path (.json)"),
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """Export the vault as a portable JSON file."""
    db = _get_db(vault_path)
    try:
        conversations = db.list_conversations(limit=10000)
        memories = db.list_memories(limit=10000)

        vault = PortableMemoryVault(
            conversations=conversations,
            memories=memories,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            vault.model_dump_json(indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]Exported to {output}[/green]")
        console.print(f"  Conversations: {len(conversations)}")
        console.print(f"  Memories: {len(memories)}")
    finally:
        db.close()


# --- Version ---

@app.command()
def version():
    """Show PAM version."""
    console.print(f"PAM — Portable AI Memory v{__version__}")


# --- Init command ---

@app.command()
def init(
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """Initialize a new PAM vault."""
    path = vault_path or DEFAULT_VAULT_PATH
    if path.exists():
        console.print(f"[yellow]Vault already exists at {path}[/yellow]")
        return

    db = VaultDB(path)
    db.open()
    db.close()

    # Create default privacy config
    privacy_path = CONFIG_DIR / "privacy.json"
    if not privacy_path.exists():
        PrivacyConfig.default().save(privacy_path)
        console.print(f"[green]Privacy config created at {privacy_path}[/green]")

    console.print(f"[green]Vault initialized at {path}[/green]")
    console.print("\nGet started:")
    console.print("  1. Export your data from ChatGPT/Claude/Gemini")
    console.print("  2. Run: pam import chatgpt your-export.zip")
    console.print("  3. Run: pam list memories")


# --- MCP command ---

@app.command()
def mcp(
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """Start the PAM MCP server for Claude Desktop integration."""
    import asyncio
    from pam.mcp.server import main as mcp_main

    console.print("[bold green]PAM MCP Server starting...[/bold green]")
    console.print("Add to Claude Desktop config:")
    console.print(f'  "pam": {{"command": "python", "args": ["-m", "pam.mcp.server"]}}')
    console.print("\n[dim]Listening on stdio...[/dim]")
    asyncio.run(mcp_main())


# --- Claude Desktop setup command ---

@app.command()
def setup_claude(
    vault_path: Optional[Path] = typer.Option(None, "--vault"),
):
    """Generate Claude Desktop config to connect PAM as an MCP server."""
    import json
    import sys

    project_dir = Path(__file__).parent.parent.parent.resolve()

    config = {
        "mcpServers": {
            "pam": {
                "command": sys.executable,
                "args": ["-m", "pam.mcp.server"],
                "cwd": str(project_dir),
            }
        }
    }

    # Common Claude Desktop config paths
    import platform
    if platform.system() == "Windows":
        config_path = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    elif platform.system() == "Darwin":
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    console.print(Panel(
        f"[bold]Claude Desktop MCP Config[/bold]\n\n"
        f"Add this to:\n[cyan]{config_path}[/cyan]\n\n"
        + json.dumps(config, indent=2),
        title="Claude Desktop Setup",
        box=box.ROUNDED,
    ))

    if typer.confirm(f"\nAuto-write to {config_path}?"):
        # Merge with existing config if it exists
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing.setdefault("mcpServers", {})
        existing["mcpServers"]["pam"] = config["mcpServers"]["pam"]

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        console.print(f"[green]Written to {config_path}[/green]")
        console.print("[yellow]Restart Claude Desktop to activate PAM.[/yellow]")
    else:
        console.print("\nCopy the config above manually.")


# --- API server command ---

@app.command()
def api(
    port: int = typer.Option(8765, "--port", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    vault_path: Optional[Path] = typer.Option(None, "--vault", help="Custom vault path"),
):
    """Start the PAM local HTTP API server (required for browser extension)."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install 'pam[full]'[/red]")
        raise typer.Exit(1)

    console.print(f"[bold green]PAM API server starting on http://{host}:{port}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    uvicorn.run("pam.api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
