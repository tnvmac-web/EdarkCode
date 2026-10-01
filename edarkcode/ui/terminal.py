"""Terminal rendering: turns StreamEvents into rich, live output."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text

from ..core.types import StreamEvent

PHASE_STYLE = {
    "research": ("magenta", "recalling context"),
    "planning": ("cyan", "planning"),
    "executing": ("green", "executing"),
    "reflecting": ("yellow", "reflecting"),
}


class TerminalRenderer:
    """Renders agent events to the terminal with a live status line."""

    def __init__(self, console: Console | None = None, show_tool_output: bool = True) -> None:
        self.console = console or Console()
        self.show_tool_output = show_tool_output
        self._spinner_text = "working"
        self._live: Live | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._live = Live(
            Spinner("dots", text=Text(" starting", style="dim")),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _set_status(self, text: str) -> None:
        self._spinner_text = text
        if self._live is not None:
            self._live.update(Spinner("dots", text=Text(f" {text}", style="dim")))

    # -- event handling ----------------------------------------------------
    def render(self, event: StreamEvent) -> None:
        handler = {
            "phase": self._phase,
            "plan": self._plan,
            "iteration": self._iteration,
            "message": self._message,
            "tool_call": self._tool_call,
            "tool_result": self._tool_result,
            "error": self._error,
            "complete": self._complete,
        }.get(event.type)
        if handler:
            handler(event.data)

    def _phase(self, data: dict[str, Any]) -> None:
        phase = data.get("phase", "")
        color, label = PHASE_STYLE.get(phase, ("blue", phase))
        self._set_status(label)
        self.console.print(f"[{color}]◆[/{color}] [bold {color}]{label}[/bold {color}]")

    def _plan(self, data: dict[str, Any]) -> None:
        steps = data.get("steps") or []
        if not steps:
            return
        body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        self.console.print(Panel(body, title="plan", border_style="cyan", padding=(0, 1)))

    def _iteration(self, data: dict[str, Any]) -> None:
        self._set_status(f"iteration {data.get('iteration')}/{data.get('max')}")

    def _message(self, data: dict[str, Any]) -> None:
        content = (data.get("content") or "").strip()
        if not content:
            return
        if self._live is not None:
            self._live.stop()
        if data.get("final"):
            self.console.print(Panel(Markdown(content), title="[bold green]result[/bold green]", border_style="green"))
        else:
            self.console.print(Markdown(content))
        if self._live is not None:
            self._live.start()

    def _tool_call(self, data: dict[str, Any]) -> None:
        name = data.get("name", "?")
        args = data.get("arguments") or {}
        preview = ", ".join(f"{k}={_short(v)}" for k, v in list(args.items())[:3])
        self.console.print(f"  [bold yellow]→[/bold yellow] [yellow]{name}[/yellow][dim]({preview})[/dim]")
        self._set_status(f"running {name}")

    def _tool_result(self, data: dict[str, Any]) -> None:
        status = data.get("status")
        name = data.get("name", "?")
        ms = data.get("duration_ms")
        if status == "success":
            self.console.print(f"  [green]✓[/green] [dim]{name} ({ms} ms)[/dim]")
        else:
            err = (data.get("error") or "failed").splitlines()[0]
            self.console.print(f"  [red]✗[/red] [red]{name}[/red] [dim]{err}[/dim]")
        if self.show_tool_output:
            output = (data.get("output") or "").strip()
            if output:
                snippet = "\n".join(output.splitlines()[:15])
                self.console.print(Panel(snippet, border_style="dim", padding=(0, 1), title="[dim]output[/dim]"))

    def _error(self, data: dict[str, Any]) -> None:
        panel = Panel(str(data.get("message", "error")), title="[bold red]error[/bold red]", border_style="red")
        self.console.print(panel)

    def _complete(self, data: dict[str, Any]) -> None:
        self._set_status("done")
        self.console.print(
            f"[dim]iterations={data.get('iterations')} "
            f"tool_calls={data.get('tool_calls')} "
            f"tokens={data.get('prompt_tokens')}+{data.get('completion_tokens')}[/dim]"
        )


def _short(value: Any, limit: int = 40) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_syntax(code: str, language: str = "python") -> Syntax:
    return Syntax(code, language, theme="monokai", line_numbers=False)
