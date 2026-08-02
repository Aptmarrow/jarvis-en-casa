"""CLI Transport for Jarvis — interactive REPL with Rich."""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jarvis.core.types import Event, EventType, ToolRequest

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI
    from jarvis.runtime.scheduler import Scheduler

logger = logging.getLogger(__name__)

# ─── Command aliases ──────────────────────────────────────────────────────────

ALIASES: dict[str, str] = {
    "lt": "list-tools",
    "perms": "permissions",
    "r": "restart",
    "q": "exit",
}

COMMANDS = [
    "status",
    "list-tools",
    "call",
    "state",
    "permissions",
    "events",
    "schedule",
    "restart",
    "reload",
    "help",
    "exit",
    "quit",
]


class JarvisCLI:
    """Interactive REPL for Jarvis — the primary dev/debug interface."""

    def __init__(self) -> None:
        self.console = Console()
        self.api: JarvisAPI | None = None
        self.scheduler: Scheduler | None = None
        self.orchestrator: Any = None
        self.recent_events: list[Event] = []
        self._start_time = datetime.now()
        self._repl_task: asyncio.Task | None = None

    async def start(
        self,
        api: JarvisAPI,
        scheduler: Scheduler | None = None,
        orchestrator: Any = None,
    ) -> None:
        """Start the CLI transport."""
        self.api = api
        self.scheduler = scheduler
        self.orchestrator = orchestrator
        self._start_time = datetime.now()

        # Subscribe to all events for the `events` command and permission handling
        await self.api.subscribe("*", self._collect_event)
        await self.api.subscribe(
            EventType.PERMISSION_REQUEST, self._handle_permission_request
        )

        self._setup_autocomplete()

        self.console.print(
            Panel(
                "[cyan bold]J.A.R.V.I.S.[/cyan bold] CLI v0.1.0\n"
                "Type [cyan]help[/cyan] for commands.",
                border_style="cyan",
                expand=False,
            )
        )

        loop = asyncio.get_running_loop()
        self._repl_task = loop.create_task(self._repl_loop())

    def _setup_autocomplete(self) -> None:
        """Set up readline tab-completion for commands and tool names."""
        try:
            import readline

            tool_names = [t.name for t in (self.api.list_tools() if self.api else [])]
            all_completions = COMMANDS + list(ALIASES.keys()) + tool_names

            def completer(text: str, state: int) -> str | None:
                line = readline.get_line_buffer().lstrip()
                if line.startswith("call "):
                    options = [t for t in tool_names if t.startswith(text)]
                else:
                    options = [c for c in all_completions if c.startswith(text)]
                return options[state] if state < len(options) else None

            readline.set_completer(completer)
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass

    # ─── Event handlers ────────────────────────────────────────────────────

    _pending_permission: Event | None = None

    async def _collect_event(self, event: Event) -> None:
        """Buffer recent events for the `events` command."""
        self.recent_events.append(event)
        if len(self.recent_events) > 200:
            self.recent_events = self.recent_events[-100:]

    async def _handle_permission_request(self, event: Event) -> None:
        """Display a permission confirmation prompt."""
        self._pending_permission = event
        tool_name = event.data.get("tool_name", "unknown")
        perms = event.data.get("permissions", [])
        self.console.print()
        self.console.print(
            Panel(
                f"[yellow]Tool:[/yellow]        {tool_name}\n"
                f"[yellow]Permissions:[/yellow] {', '.join(perms)}\n\n"
                "Allow? [bold][y/N][/bold]",
                title="⚠️  Permission Required",
                border_style="yellow",
                expand=False,
            )
        )

    # ─── REPL Loop ─────────────────────────────────────────────────────────

    async def _repl_loop(self) -> None:
        """Main read-eval-print loop."""
        loop = asyncio.get_running_loop()

        while True:
            try:
                line = await loop.run_in_executor(
                    None, input, "\033[36mjarvis> \033[0m"
                )
                line = line.strip()

                # Handle pending permission response
                if self._pending_permission is not None:
                    granted = line.lower() in ("y", "yes")
                    await self.api.publish(
                        Event(
                            type=EventType.PERMISSION_RESPONSE,
                            data={"granted": granted},
                            source="cli",
                        )
                    )
                    self._pending_permission = None
                    status = "[green]Granted[/green]" if granted else "[red]Denied[/red]"
                    self.console.print(f"  → {status}")
                    continue

                if not line:
                    continue

                # Parse command
                try:
                    parts = shlex.split(line)
                except ValueError as e:
                    self.console.print(f"[red]Parse error:[/red] {e}")
                    continue

                cmd = ALIASES.get(parts[0], parts[0])

                if cmd in ("exit", "quit"):
                    self.console.print("[cyan]Shutting down J.A.R.V.I.S...[/cyan]")
                    import os
                    os._exit(0)

                if cmd in ("restart", "reload"):
                    self.console.print("[cyan bold]⚡ Restarting J.A.R.V.I.S. process 100%...[/cyan bold]")
                    import os
                    import sys
                    os.execv(sys.executable, [sys.executable, "-m", "jarvis"])

                # Dispatch to handler
                handler = getattr(self, f"_cmd_{cmd.replace('-', '_')}", None)
                if handler:
                    try:
                        await handler(parts[1:])
                    except Exception as e:
                        self.console.print(
                            Panel(
                                f"[red]{e}[/red]",
                                title="Error",
                                border_style="red",
                                expand=False,
                            )
                        )
                elif self.orchestrator:
                    response = await self.orchestrator.process_user_request(line)
                    self.console.print(
                        Panel(
                            f"[magenta]{response}[/magenta]",
                            title="🤖 Jarvis",
                            border_style="magenta",
                            expand=False,
                        )
                    )
                else:
                    self.console.print(
                        "[magenta]AI Orchestrator not active. Use [bold]help[/bold] to see commands.[/magenta]"
                    )

            except EOFError:
                self.console.print("\n[cyan]Goodbye.[/cyan]")
                break
            except KeyboardInterrupt:
                self.console.print()
                continue

    # ─── Command handlers ──────────────────────────────────────────────────

    async def _cmd_help(self, args: list[str]) -> None:
        """Show available commands."""
        table = Table(title="Available Commands", border_style="cyan")
        table.add_column("Command", style="cyan bold")
        table.add_column("Alias", style="dim")
        table.add_column("Description")

        cmds = [
            ("status", "", "System status overview"),
            ("list-tools", "lt", "List all registered tools"),
            ("call <tool> [--key val]", "", "Execute a tool"),
            ("state", "", "Show global system state"),
            ("permissions", "perms", "Show permission configuration"),
            ("events [N]", "", "Show last N events (default 20)"),
            ("schedule", "", "Show scheduled tasks"),
            ("help", "", "This help message"),
            ("exit", "q", "Exit the CLI"),
        ]
        for name, alias, desc in cmds:
            table.add_row(name, alias, desc)

        self.console.print(table)

    async def _cmd_status(self, args: list[str]) -> None:
        """Show system status."""
        assert self.api is not None

        uptime = datetime.now() - self._start_time
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hours}h {mins}m {secs}s"

        tools = self.api.list_tools()
        plugins = self.api.plugin_registry.list_plugins()
        sched_tasks = self.scheduler.list_tasks() if self.scheduler else []
        active_tasks = sum(1 for t in sched_tasks if t.enabled)

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="cyan", justify="right")
        grid.add_column(style="white")

        grid.add_row("Version:", "0.1.0")
        grid.add_row("Uptime:", uptime_str)
        grid.add_row("Plugins:", str(len(plugins)))
        grid.add_row("Tools:", str(len(tools)))
        grid.add_row(
            "Scheduler:",
            f"[green]Running[/green] ({active_tasks} active)"
            if self.scheduler
            else "[red]Stopped[/red]",
        )
        grid.add_row("Events:", str(len(self.recent_events)))

        self.console.print(
            Panel(grid, title="⚡ System Status", border_style="cyan", expand=False)
        )

    async def _cmd_list_tools(self, args: list[str]) -> None:
        """List all registered tools."""
        assert self.api is not None

        tools = self.api.list_tools()
        if not tools:
            self.console.print("[yellow]No tools registered.[/yellow]")
            return

        table = Table(title="Registered Tools", border_style="cyan")
        table.add_column("Tool", style="cyan")
        table.add_column("Description")
        table.add_column("Plugin", style="magenta")
        table.add_column("Permissions")

        for t in sorted(tools, key=lambda x: x.name):
            perms = (
                ", ".join(f"[yellow]{p}[/yellow]" for p in t.permissions)
                if t.permissions
                else "[dim]none[/dim]"
            )
            table.add_row(t.name, t.description, t.plugin_name, perms)

        self.console.print(table)

    async def _cmd_call(self, args: list[str]) -> None:
        """Execute a tool: call <tool_name> [--key value ...]"""
        assert self.api is not None

        if not args:
            self.console.print("[red]Usage:[/red] call <tool_name> [--key value ...]")
            return

        tool_name = args[0]
        kwargs: dict[str, Any] = {}

        # Parse --key value pairs
        i = 1
        while i < len(args):
            if args[i].startswith("--") and i + 1 < len(args):
                key = args[i][2:]
                val = args[i + 1]
                # Try to parse as int/float/bool
                try:
                    kwargs[key] = int(val)
                except ValueError:
                    try:
                        kwargs[key] = float(val)
                    except ValueError:
                        if val.lower() in ("true", "false"):
                            kwargs[key] = val.lower() == "true"
                        else:
                            kwargs[key] = val
                i += 2
            else:
                i += 1

        start = time.perf_counter()
        result = await self.api.call_tool(tool_name, kwargs, source="cli")
        elapsed = (time.perf_counter() - start) * 1000

        if result.success:
            self.console.print(
                Panel(
                    f"[green]✓[/green] {result.data}",
                    title=f"{tool_name} ({elapsed:.1f}ms)",
                    border_style="green",
                    expand=False,
                )
            )
        else:
            self.console.print(
                Panel(
                    f"[red]✗[/red] {result.error}",
                    title=f"{tool_name} ({elapsed:.1f}ms)",
                    border_style="red",
                    expand=False,
                )
            )

    async def _cmd_state(self, args: list[str]) -> None:
        """Show global system state."""
        assert self.api is not None

        state_dict = await self.api.snapshot_state()

        table = Table(title="System State", border_style="cyan")
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        table.add_column("Type", style="dim")

        for k, v in sorted(state_dict.items()):
            if isinstance(v, bool):
                val_str = f"[green]{v}[/green]" if v else f"[red]{v}[/red]"
            else:
                val_str = str(v)
            table.add_row(k, val_str, type(v).__name__)

        self.console.print(table)

    async def _cmd_permissions(self, args: list[str]) -> None:
        """Show permission configuration."""
        assert self.api is not None

        perms = self.api.get_permissions_config()

        table = Table(title="Permission Configuration", border_style="cyan")
        table.add_column("Permission", style="cyan")
        table.add_column("Level")

        level_colors = {
            "auto": "green",
            "confirm": "yellow",
            "confirm_always": "red",
            "deny": "dark_red",
        }

        for p, level in sorted(perms.items()):
            color = level_colors.get(level, "white")
            table.add_row(p, f"[{color}]{level}[/{color}]")

        self.console.print(table)

    async def _cmd_events(self, args: list[str]) -> None:
        """Show recent events."""
        count = int(args[0]) if args else 20

        table = Table(title=f"Recent Events (last {count})", border_style="cyan")
        table.add_column("Time", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Source", style="magenta")
        table.add_column("Data")

        for e in self.recent_events[-count:]:
            ts = e.timestamp.strftime("%H:%M:%S.%f")[:-3]
            data_str = str(e.data)
            if len(data_str) > 60:
                data_str = data_str[:57] + "..."
            table.add_row(ts, str(e.type), e.source, data_str)

        self.console.print(table)

    async def _cmd_schedule(self, args: list[str]) -> None:
        """Show scheduled tasks."""
        if not self.scheduler:
            self.console.print("[yellow]Scheduler not running.[/yellow]")
            return

        tasks = self.scheduler.list_tasks()

        table = Table(title="Scheduled Tasks", border_style="cyan")
        table.add_column("Name", style="cyan")
        table.add_column("Cron", style="yellow")
        table.add_column("Tool", style="magenta")
        table.add_column("Enabled")
        table.add_column("Last Run")
        table.add_column("Next Run")

        for t in tasks:
            enabled = "[green]Yes[/green]" if t.enabled else "[red]No[/red]"
            last = (
                t.last_run.strftime("%H:%M:%S") if t.last_run else "[dim]Never[/dim]"
            )
            nxt = (
                t.next_run.strftime("%H:%M:%S") if t.next_run else "[dim]—[/dim]"
            )
            table.add_row(t.name, t.cron, t.tool_name, enabled, last, nxt)

        self.console.print(table)
