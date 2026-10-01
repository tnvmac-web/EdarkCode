"""edarkcode CLI."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .core.config import Settings
from .core.factory import build_agent
from .ui.terminal import TerminalRenderer

app = typer.Typer(
    name="edarkcode",
    help="edarkcode — autonomous coding agent.",
    no_args_is_help=True,
    add_completion=False,
)
config_app = typer.Typer(help="Manage configuration.", no_args_is_help=True)
memory_app = typer.Typer(help="Inspect memory and lessons.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(memory_app, name="memory")

console = Console()


def _force_utf8_output() -> None:
    """Windows consoles default to a legacy code page (cp1252/cp437), which cannot
    encode the symbols rich prints. Reconfigure the streams to UTF-8 so the CLI
    never dies with a UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def _load_settings(workspace: str | None, model: str | None, provider: str | None) -> Settings:
    settings = Settings.load()
    if workspace:
        settings.workspace = Path(workspace).resolve()
    if model:
        settings.llm.model = model
    if provider:
        settings.llm.provider = provider
    return settings


def _terminal_approver(renderer: TerminalRenderer):
    async def approver(name: str, args: dict) -> bool:
        preview = json.dumps(args, indent=2)[:800]
        console.print(f"\n[bold yellow]Approve tool call[/bold yellow] [yellow]{name}[/yellow]?")
        console.print(f"[dim]{preview}[/dim]")
        try:
            answer = await asyncio.to_thread(input, "  [y/N/a=allow all] ")
        except (EOFError, KeyboardInterrupt):
            return False
        answer = answer.strip().lower()
        if answer == "a":
            renderer.console.print("[dim]Auto-approving remaining tools for this run.[/dim]")
            return True
        return answer in ("y", "yes")

    return approver


async def _run_goal(settings: Settings, goal: str, yes: bool, show_output: bool) -> int:
    renderer = TerminalRenderer(console=console, show_tool_output=show_output)
    approver = None if yes else _terminal_approver(renderer)
    agent = build_agent(settings, approver=approver)

    renderer.start()
    exit_code = 0
    try:
        async for event in agent.run(goal):
            renderer.render(event)
            if event.type == "error":
                exit_code = 1
    except KeyboardInterrupt:
        renderer.stop()
        console.print("\n[red]Interrupted.[/red]")
        return 130
    finally:
        renderer.stop()
        await agent.llm.aclose()
    return exit_code


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"edarkcode {__version__}")


@app.command()
def run(
    goal: str = typer.Argument(..., help="What the agent should accomplish."),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace root (default: cwd)."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the model."),
    provider: str | None = typer.Option(None, "--provider", "-p", help="Override the provider."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve all tool calls."),
    show_output: bool = typer.Option(True, "--show-output/--no-show-output", help="Print tool output."),
) -> None:
    """Run the agent on a single goal."""
    settings = _load_settings(workspace, model, provider)
    code = asyncio.run(_run_goal(settings, goal, yes, show_output))
    raise typer.Exit(code)


@app.command()
def chat(
    workspace: str | None = typer.Option(None, "--workspace", "-w"),
    model: str | None = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve all tool calls."),
) -> None:
    """Interactive session: type goals, get results, repeat."""
    settings = _load_settings(workspace, model, None)
    console.print(f"[bold]edarkcode[/bold] {__version__} — workspace [cyan]{settings.workspace}[/cyan]")
    console.print("[dim]Type a goal, or 'exit' to quit.[/dim]\n")
    while True:
        try:
            goal = input("edarkcode> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if goal.lower() in ("exit", "quit", ":q"):
            break
        if not goal:
            continue
        asyncio.run(_run_goal(settings, goal, yes, True))
        console.print()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Start the web API (HTTP + WebSocket)."""
    import uvicorn

    from .web.app import create_app

    settings = _load_settings(workspace, None, None)
    application = create_app(settings)
    console.print(f"[bold]edarkcode web[/bold] on http://{host}:{port}")
    uvicorn.run(application, host=host, port=port, log_level="info")


@config_app.command("show")
def config_show() -> None:
    """Show the effective configuration."""
    settings = Settings.load()
    data = settings.model_dump(mode="json")
    if data.get("llm", {}).get("api_key"):
        data["llm"]["api_key"] = "***set***"
    console.print_json(json.dumps(data, default=str))


@config_app.command("init")
def config_init() -> None:
    """Write a default config file."""
    path = Settings().save()
    console.print(f"Wrote {path}")


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a config value, e.g. `edarkcode config set llm.model gpt-4o`."""
    settings = Settings.load()
    parts = key.split(".")
    obj = settings
    for part in parts[:-1]:
        obj = getattr(obj, part)
    if not hasattr(obj, parts[-1]):
        console.print(f"[red]Unknown key: {key}[/red]")
        raise typer.Exit(1)
    current = getattr(obj, parts[-1])
    if isinstance(current, bool):
        value = value.lower() in ("1", "true", "yes", "on")
    elif isinstance(current, int):
        value = int(value)
    elif isinstance(current, float):
        value = float(value)
    setattr(obj, parts[-1], value)
    path = settings.save()
    console.print(f"Set {key} = {value} in {path}")


@memory_app.command("list")
def memory_list(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """List recent memory entries."""
    from .memory.store import MemoryStore

    settings = Settings.load()
    store = MemoryStore(settings.memory.path, max_entries=settings.memory.max_entries)
    entries = store.entries()[-limit:]
    if not entries:
        console.print("[dim]No memories yet.[/dim]")
        return
    for e in entries:
        console.print(f"[dim]{e.text[:160]}[/dim]")


@memory_app.command("lessons")
def memory_lessons() -> None:
    """List learned lessons."""
    from .memory.store import LessonStore

    settings = Settings.load()
    store = LessonStore(settings.self_improvement.path, max_entries=settings.self_improvement.max_lessons)
    entries = store.lessons()
    if not entries:
        console.print("[dim]No lessons learned yet.[/dim]")
        return
    for e in entries:
        tags = f" [dim]({', '.join(e.tags)})[/dim]" if e.tags else ""
        console.print(f"• {e.text}{tags}")


@app.command()
def doctor() -> None:
    """Check that the environment is ready."""
    settings = Settings.load()
    ok = True
    console.print(f"Python: {sys.version.split()[0]}")
    console.print(f"Workspace: {settings.workspace}")
    console.print(f"Provider: {settings.llm.provider}  Model: {settings.llm.model}")
    if settings.llm.api_key:
        console.print("[green]✓[/green] API key configured")
    else:
        console.print("[red]✗[/red] No API key — set EDARKCODE_LLM__API_KEY")
        ok = False
    try:
        import httpx  # noqa: F401
        import rich  # noqa: F401

        console.print("[green]✓[/green] Core dependencies importable")
    except ImportError as e:
        console.print(f"[red]✗[/red] Missing dependency: {e}")
        ok = False
    raise typer.Exit(0 if ok else 1)


def main() -> None:
    _force_utf8_output()
    app()


if __name__ == "__main__":
    _force_utf8_output()
    main()
