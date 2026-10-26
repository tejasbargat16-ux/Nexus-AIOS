"""
Nexus AIOS Terminal User Interface (TUI) (Phase 3).

A full-featured terminal console built with Rich.
Provides real-time daemon telemetry, interactive natural language intent execution,
tool catalog browsing, memory facts management, scheduler control, and security monitoring.
Works seamlessly across local terminals, SSH sessions, and Android Termux/proot.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any
import requests

from rich.align import Align
from rich.box import ROUNDED, SIMPLE
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()


class NexusTUI:
    """Terminal User Interface client for Nexus AIOS daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.active_tab = "intent"

    def is_daemon_online(self) -> bool:
        """Check if nexusd daemon is reachable."""
        try:
            resp = self.session.get(f"{self.base_url}/status", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        """Fetch daemon status and telemetry."""
        try:
            resp = self.session.get(f"{self.base_url}/status", timeout=3)
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

    def render_header(self, status_data: dict[str, Any]) -> Panel:
        """Render top branding and telemetry banner."""
        uptime = status_data.get("uptime_seconds", 0)
        version = status_data.get("version", "0.3.0-phase3")
        provider = status_data.get("providers", {}).get("preferred", "local")

        guard_score = status_data.get("components", {}).get("security_score", 100)
        guard_level = status_data.get("components", {}).get("security_level", "optimal")

        level_color = "green" if guard_level == "optimal" else ("yellow" if guard_level == "warning" else "red")

        header_table = Table.grid(expand=True)
        header_table.add_column(ratio=2)
        header_table.add_column(ratio=3, justify="right")

        title_text = Text()
        title_text.append("Ψ NEXUS AIOS", style="bold cyan")
        title_text.append(f" [{version}]", style="dim white")
        title_text.append(" • Autonomous Kernel Console", style="italic white")

        meta_text = Text()
        meta_text.append(f"Daemon: ", style="dim")
        meta_text.append("ONLINE", style="bold green")
        meta_text.append(f" | Uptime: {uptime}s | Router: ", style="dim")
        meta_text.append(provider.upper(), style="bold yellow")
        meta_text.append(f" | Security: ", style="dim")
        meta_text.append(f"{guard_score}% ({guard_level.upper()})", style=f"bold {level_color}")

        header_table.add_row(title_text, meta_text)
        return Panel(header_table, box=ROUNDED, style="cyan")

    def render_navigation(self) -> Panel:
        """Render hotkey navigation bar."""
        tabs = [
            ("1", "Intent Console", self.active_tab == "intent"),
            ("2", "Security Guard", self.active_tab == "guard"),
            ("3", "Scheduler", self.active_tab == "scheduler"),
            ("4", "Tools Catalog", self.active_tab == "tools"),
            ("5", "Memory Store", self.active_tab == "memory"),
            ("6", "Audit Log", self.active_tab == "audit"),
            ("q", "Quit", False),
        ]

        nav_text = Text()
        for idx, (key, label, is_active) in enumerate(tabs):
            if is_active:
                nav_text.append(f"[{key}] ", style="bold black on cyan")
                nav_text.append(f"{label} ", style="bold cyan")
            else:
                nav_text.append(f"[{key}] ", style="bold yellow")
                nav_text.append(f"{label} ", style="white")
            if idx < len(tabs) - 1:
                nav_text.append("│ ", style="dim")

        return Panel(Align.center(nav_text), box=ROUNDED, style="dim white")

    # =========================================================================
    # Views
    # =========================================================================

    def view_intent_console(self) -> None:
        """Interactive intent execution console."""
        console.print(Panel("[bold cyan]Natural Language Intent Terminal[/bold cyan]\nEnter any action or query in plain English. Nexus AIOS will plan, check permissions, and execute.\n[dim]Commands: 'clear', 'back' (to menu)[/dim]", box=ROUNDED))

        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]nexus[/bold cyan][dim]>[/dim]").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue
            if user_input.lower() in ("back", "exit", "quit", "menu"):
                break
            if user_input.lower() == "clear":
                console.clear()
                continue

            # Send intent
            with console.status("[bold green]Routing intent & planning execution...[/bold green]"):
                try:
                    resp = self.session.post(
                        f"{self.base_url}/intent",
                        json={"text": user_input, "confirmed": False},
                        timeout=30,
                    )
                    data = resp.json()
                except Exception as err:
                    console.print(f"[bold red]API Connection Failed:[/bold red] {err}")
                    continue

            # Handle confirmation required
            if data.get("status") == "confirmation_required":
                guard_info = data.get("guard", {})
                action_name = guard_info.get("action", "unknown_action")
                reason = guard_info.get("reason", "This action requires explicit confirmation.")

                console.print(
                    Panel(
                        f"[bold yellow]⚠️ Security Guard Confirmation Required[/bold yellow]\n\n"
                        f"Action: [bold white]{action_name}[/bold white]\n"
                        f"Reason: [dim]{reason}[/dim]\n"
                        f"Target: [cyan]{guard_info.get('params', {})}[/cyan]",
                        box=ROUNDED,
                        style="yellow",
                    )
                )

                confirm = Confirm.ask("Authorize execution?", default=False)
                if not confirm:
                    console.print("[dim yellow]Action aborted by user.[/dim yellow]")
                    continue

                # Resubmit with confirmation
                with console.status("[bold green]Executing authorized action...[/bold green]"):
                    try:
                        resp = self.session.post(
                            f"{self.base_url}/intent",
                            json={"text": user_input, "confirmed": True},
                            timeout=30,
                        )
                        data = resp.json()
                    except Exception as err:
                        console.print(f"[bold red]Execution error:[/bold red] {err}")
                        continue

            # Display response
            reply = data.get("reply", "No response generated.")
            provider = data.get("provider", "unknown")
            duration = data.get("duration_ms", 0)

            result_table = Table.grid(expand=True)
            result_table.add_column()
            result_table.add_row(Text(reply, style="bold white"))

            tool_result = data.get("tool_result")
            if tool_result:
                status_color = "green" if tool_result.get("status") == "ok" else "red"
                result_table.add_row(Text(""))
                result_table.add_row(Text(f"⚙️ Tool: {tool_result.get('action')}", style="bold cyan"))
                result_table.add_row(Text(f"Status: {tool_result.get('status')}", style=status_color))
                result_table.add_row(Text(f"Output: {str(tool_result.get('result'))[:500]}", style="dim"))

            console.print(
                Panel(
                    result_table,
                    title=f"[cyan]Reply ({provider} in {duration}ms)[/cyan]",
                    box=ROUNDED,
                    style="green" if data.get("status") != "error" else "red",
                )
            )

    def view_security_guard(self) -> None:
        """Security guard posture and anomaly inspection screen."""
        console.clear()
        try:
            status_resp = self.session.get(f"{self.base_url}/guard/status", timeout=5).json()
            alerts_resp = self.session.get(f"{self.base_url}/guard/alerts?limit=10", timeout=5).json()
        except Exception as err:
            console.print(f"[bold red]Failed to fetch security guard data:[/bold red] {err}")
            Prompt.ask("\nPress Enter to return...")
            return

        posture = status_resp.get("posture", status_resp)
        score = posture.get("score", 100)
        level = posture.get("level", "optimal")
        metrics = posture.get("metrics", {})
        alerts = alerts_resp.get("alerts", [])

        level_color = "green" if level == "optimal" else ("yellow" if level == "warning" else "red")

        # Telemetry panel
        res_table = Table(box=SIMPLE, expand=True)
        res_table.add_column("Metric", style="bold cyan")
        res_table.add_column("Value", style="bold white")
        res_table.add_column("Threshold / Status", style="dim")

        res_table.add_row("CPU Load", f"{metrics.get('cpu_percent', 0)}%", "Normal (<90%)")
        res_table.add_row("RAM Usage", f"{metrics.get('memory_percent', 0)}% ({metrics.get('memory_used_mb', 0)}MB / {metrics.get('memory_total_mb', 0)}MB)", "Normal (<92%)")
        res_table.add_row("Disk Usage", f"{metrics.get('disk_percent', 0)}% ({metrics.get('disk_free_gb', 0)}GB free)", "Normal (<95%)")
        res_table.add_row("Active Processes", f"{metrics.get('process_count', 0)}", "System wide")

        console.print(Panel(
            Align.center(f"[bold {level_color}]System Security Posture: {score}% ({level.upper()})[/bold {level_color}]\nProactive Tripwires Active • Audit Anomaly Engine Online"),
            box=ROUNDED,
            style=level_color,
        ))
        console.print(Panel(res_table, title="[cyan]System Health & Resource Watchdog[/cyan]", box=ROUNDED))

        # Alerts table
        alert_table = Table(box=SIMPLE, expand=True)
        alert_table.add_column("Severity", width=12)
        alert_table.add_column("Source", width=12)
        alert_table.add_column("Message", style="white")
        alert_table.add_column("Time", width=12, style="dim")

        if not alerts:
            alert_table.add_row("[green]OPTIMAL[/green]", "guard", "No active security anomalies or tripwire triggers.", "now")
        else:
            for a in alerts:
                sev = a.get("severity", "info")
                s_color = "red" if sev == "critical" else ("yellow" if sev == "warning" else "cyan")
                alert_table.add_row(
                    f"[{s_color}]{sev.upper()}[/{s_color}]",
                    a.get("source", ""),
                    a.get("message", ""),
                    time.strftime("%H:%M:%S", time.localtime(a.get("timestamp", time.time()))),
                )

        console.print(Panel(alert_table, title="[yellow]Recent Security Alerts & Tripwires[/yellow]", box=ROUNDED))

        console.print("[dim]Options: [s] Run on-demand scan | [c] Clear alerts | [Enter] Back[/dim]")
        choice = Prompt.ask("Action", default="").lower().strip()

        if choice == "s":
            with console.status("[bold green]Running comprehensive security & tripwire scan...[/bold green]"):
                try:
                    scan_res = self.session.post(f"{self.base_url}/guard/scan", timeout=10).json()
                    new_score = scan_res.get("posture", {}).get("score", 100)
                    console.print(f"[bold green]✓ Scan Complete! Posture score: {new_score}%[/bold green]")
                except Exception as err:
                    console.print(f"[bold red]Scan failed:[/bold red] {err}")
            Prompt.ask("\nPress Enter to continue...")
        elif choice == "c":
            try:
                self.session.post(f"{self.base_url}/guard/alerts/clear", timeout=5)
                console.print("[bold green]✓ Security alerts cleared.[/bold green]")
            except Exception as err:
                console.print(f"[bold red]Clear failed:[/bold red] {err}")
            Prompt.ask("\nPress Enter to continue...")

    def view_scheduler(self) -> None:
        """Scheduler control and scheduled jobs view."""
        console.clear()
        try:
            resp = self.session.get(f"{self.base_url}/scheduler/tasks", timeout=5).json()
            tasks = resp.get("tasks", [])
        except Exception as err:
            console.print(f"[bold red]Failed to fetch scheduled tasks:[/bold red] {err}")
            Prompt.ask("\nPress Enter to return...")
            return

        table = Table(box=ROUNDED, expand=True)
        table.add_column("ID", style="dim", width=16)
        table.add_column("Task Name", style="bold cyan")
        table.add_column("Action", width=10)
        table.add_column("Interval", width=10)
        table.add_column("Due In", width=10)
        table.add_column("Runs", width=6)
        table.add_column("Status", width=10)
        table.add_column("Last Result", style="dim")

        for t in tasks:
            status_style = "green" if t.get("last_status") == "ok" else ("yellow" if t.get("last_status") == "pending" else "red")
            state_marker = "🟢" if t.get("enabled") else "⚪ [dim](disabled)[/dim]"

            table.add_row(
                t.get("id"),
                f"{state_marker} {t.get('name')}",
                t.get("action_type"),
                f"{t.get('interval_seconds')}s",
                f"{t.get('due_in_seconds')}s",
                str(t.get("run_count")),
                f"[{status_style}]{t.get('last_status')}[/{status_style}]",
                str(t.get("last_result", ""))[:40],
            )

        console.print(Panel(table, title="[bold cyan]Nexus Autonomous Task Scheduler[/bold cyan]", box=ROUNDED))
        console.print("[dim]Options: [r] Trigger Task | [t] Toggle Task | [a] Add Task | [d] Delete Task | [Enter] Back[/dim]")
        choice = Prompt.ask("Action", default="").lower().strip()

        if choice == "r":
            tid = Prompt.ask("Enter Task ID to trigger now").strip()
            if tid:
                try:
                    res = self.session.post(f"{self.base_url}/scheduler/tasks/{tid}/run", timeout=10).json()
                    console.print(f"[bold green]Triggered task:[/bold green] {res.get('status')} - {res.get('result')}")
                except Exception as err:
                    console.print(f"[bold red]Trigger error:[/bold red] {err}")
                Prompt.ask("\nPress Enter to continue...")
        elif choice == "t":
            tid = Prompt.ask("Enter Task ID to toggle enabled/disabled").strip()
            if tid:
                try:
                    res = self.session.post(f"{self.base_url}/scheduler/tasks/{tid}/toggle", timeout=5).json()
                    state = "ENABLED" if res.get("task", {}).get("enabled") else "DISABLED"
                    console.print(f"[bold green]Task {tid} is now {state}[/bold green]")
                except Exception as err:
                    console.print(f"[bold red]Toggle error:[/bold red] {err}")
                Prompt.ask("\nPress Enter to continue...")
        elif choice == "a":
            name = Prompt.ask("Task Name").strip()
            action_type = Prompt.ask("Action Type", choices=["tool", "intent", "system"], default="tool")
            interval_str = Prompt.ask("Interval (seconds)", default="300")
            try:
                interval = int(interval_str)
                payload: dict[str, Any] = {}
                if action_type == "tool":
                    action = Prompt.ask("Tool name (e.g. network.check, files.list)")
                    payload = {"action": action, "params": {}}
                elif action_type == "intent":
                    text = Prompt.ask("Natural language intent string")
                    payload = {"text": text}
                elif action_type == "system":
                    payload = {"action": "guard.scan"}

                res = self.session.post(
                    f"{self.base_url}/scheduler/tasks",
                    json={"name": name, "action_type": action_type, "interval_seconds": interval, "payload": payload},
                    timeout=5,
                ).json()
                console.print(f"[bold green]✓ Created task {res.get('task', {}).get('id')}[/bold green]")
            except Exception as err:
                console.print(f"[bold red]Failed to create task:[/bold red] {err}")
            Prompt.ask("\nPress Enter to continue...")
        elif choice == "d":
            tid = Prompt.ask("Enter Task ID to delete").strip()
            if tid:
                try:
                    res = self.session.delete(f"{self.base_url}/scheduler/tasks/{tid}", timeout=5).json()
                    console.print(f"[bold green]✓ Deleted task {tid}[/bold green]")
                except Exception as err:
                    console.print(f"[bold red]Delete error:[/bold red] {err}")
                Prompt.ask("\nPress Enter to continue...")

    def view_tools_catalog(self) -> None:
        """Browse registered tools."""
        console.clear()
        try:
            resp = self.session.get(f"{self.base_url}/tools", timeout=5).json()
            tools = resp.get("tools", [])
        except Exception as err:
            console.print(f"[bold red]Failed to fetch tools:[/bold red] {err}")
            Prompt.ask("\nPress Enter to return...")
            return

        table = Table(box=ROUNDED, expand=True)
        table.add_column("Tool Action", style="bold cyan", width=22)
        table.add_column("Category", width=12, style="yellow")
        table.add_column("Description", style="white")
        table.add_column("Parameters", style="dim")

        for t in tools:
            params_str = ", ".join(t.get("parameters", {}).keys()) or "none"
            table.add_row(
                t.get("name"),
                t.get("category", "general"),
                t.get("description", ""),
                params_str,
            )

        console.print(Panel(table, title=f"[bold cyan]Registered Tools Catalog ({len(tools)} available)[/bold cyan]", box=ROUNDED))
        Prompt.ask("\nPress Enter to return...")

    def view_memory_store(self) -> None:
        """View persistent facts and preferences."""
        console.clear()
        try:
            resp = self.session.get(f"{self.base_url}/memory/facts", timeout=5).json()
            facts = resp.get("facts", [])
        except Exception as err:
            console.print(f"[bold red]Failed to fetch memory facts:[/bold red] {err}")
            Prompt.ask("\nPress Enter to return...")
            return

        table = Table(box=ROUNDED, expand=True)
        table.add_column("Key", style="bold cyan", width=26)
        table.add_column("Value", style="bold white")
        table.add_column("Category", style="yellow", width=14)
        table.add_column("Updated", style="dim", width=20)

        for f in facts:
            table.add_row(
                f.get("key"),
                str(f.get("value")),
                f.get("category", "general"),
                f.get("updated_at", ""),
            )

        console.print(Panel(table, title=f"[bold cyan]Persistent Memory Store ({len(facts)} facts)[/bold cyan]", box=ROUNDED))
        console.print("[dim]Options: [a] Add Fact | [d] Delete Fact | [s] Search | [Enter] Back[/dim]")
        choice = Prompt.ask("Action", default="").lower().strip()

        if choice == "a":
            key = Prompt.ask("Fact Key (e.g. user.name, system.model)")
            val = Prompt.ask("Fact Value")
            cat = Prompt.ask("Category", default="preference")
            try:
                self.session.post(
                    f"{self.base_url}/memory/facts",
                    json={"key": key, "value": val, "category": cat},
                    timeout=5,
                )
                console.print("[bold green]✓ Fact saved successfully.[/bold green]")
            except Exception as err:
                console.print(f"[bold red]Save failed:[/bold red] {err}")
            Prompt.ask("\nPress Enter to continue...")
        elif choice == "d":
            key = Prompt.ask("Key to delete").strip()
            if key:
                try:
                    self.session.delete(f"{self.base_url}/memory/facts/{key}", timeout=5)
                    console.print(f"[bold green]✓ Fact '{key}' deleted.[/bold green]")
                except Exception as err:
                    console.print(f"[bold red]Delete failed:[/bold red] {err}")
                Prompt.ask("\nPress Enter to continue...")
        elif choice == "s":
            q = Prompt.ask("Search query").strip()
            if q:
                try:
                    results = self.session.get(f"{self.base_url}/memory/search?q={q}", timeout=5).json()
                    console.print(f"[bold cyan]Search results for '{q}':[/bold cyan]")
                    for item in results.get("results", []):
                        console.print(f"• [bold]{item.get('key', 'history')}[/bold]: {item.get('snippet') or item.get('value')} (relevance: {item.get('relevance')})")
                except Exception as err:
                    console.print(f"[bold red]Search failed:[/bold red] {err}")
                Prompt.ask("\nPress Enter to continue...")

    def view_audit_log(self) -> None:
        """Stream recent audit log events."""
        console.clear()
        try:
            resp = self.session.get(f"{self.base_url}/audit?limit=25", timeout=5).json()
            entries = resp.get("entries", [])
        except Exception as err:
            console.print(f"[bold red]Failed to fetch audit log:[/bold red] {err}")
            Prompt.ask("\nPress Enter to return...")
            return

        table = Table(box=SIMPLE, expand=True)
        table.add_column("Time", width=10, style="dim")
        table.add_column("Event", style="bold cyan", width=22)
        table.add_column("Status", width=10)
        table.add_column("Details", style="white")

        for e in entries:
            ts = e.get("timestamp")
            time_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"
            st = e.get("status", "ok")
            s_style = "green" if st == "ok" else ("yellow" if st == "warning" else "red")
            data_str = str(e.get("data", {}))[:70]

            table.add_row(time_str, e.get("event"), f"[{s_style}]{st}[/{s_style}]", data_str)

        console.print(Panel(table, title="[bold cyan]Cryptographic Append-Only Audit Stream[/bold cyan]", box=ROUNDED))
        Prompt.ask("\nPress Enter to return...")

    def run(self) -> None:
        """Main TUI interaction loop."""
        while True:
            console.clear()
            status = self.get_status()

            if not status:
                console.print(Panel(
                    f"[bold red]⚠️ Nexus Daemon Offline[/bold red]\n"
                    f"Unable to connect to nexusd at [cyan]{self.base_url}[/cyan].\n\n"
                    f"To start the daemon, run:\n"
                    f"  [bold green]python -m nexusd.main[/bold green]\n"
                    f"or via systemd:\n"
                    f"  [bold green]sudo systemctl start nexusd[/bold green]",
                    box=ROUNDED,
                    style="red",
                ))
                choice = Prompt.ask("\n[r] Retry connection | [q] Quit", default="r").lower().strip()
                if choice == "q":
                    break
                continue

            console.print(self.render_header(status))
            console.print(self.render_navigation())

            console.print("\n[bold]Select view or operation:[/bold]")
            choice = Prompt.ask("Choose [1-6, q]", choices=["1", "2", "3", "4", "5", "6", "q"], default="1")

            if choice == "1":
                self.active_tab = "intent"
                self.view_intent_console()
            elif choice == "2":
                self.active_tab = "guard"
                self.view_security_guard()
            elif choice == "3":
                self.active_tab = "scheduler"
                self.view_scheduler()
            elif choice == "4":
                self.active_tab = "tools"
                self.view_tools_catalog()
            elif choice == "5":
                self.active_tab = "memory"
                self.view_memory_store()
            elif choice == "6":
                self.active_tab = "audit"
                self.view_audit_log()
            elif choice == "q":
                console.print("\n[dim cyan]Disconnecting from Nexus AIOS TUI. Goodbye![/dim cyan]")
                break


def main() -> None:
    """TUI CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Nexus AIOS Terminal UI (TUI)")
    parser.add_argument("--host", default=os.getenv("NEXUS_API_HOST", "127.0.0.1"), help="nexusd host")
    parser.add_argument("--port", type=int, default=int(os.getenv("NEXUS_API_PORT", "8765")), help="nexusd port")
    args = parser.parse_args()

    tui = NexusTUI(host=args.host, port=args.port)
    tui.run()


if __name__ == "__main__":
    main()
