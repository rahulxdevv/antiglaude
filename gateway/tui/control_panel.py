"""Terminal User Interface (TUI) Control Panel for Antiglaude Bridge."""

import asyncio
import json
import os
import select
import subprocess
import sys
import termios
import time
import tty
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.align import Align
from rich.box import ROUNDED, SIMPLE, DOUBLE
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.style import Style
from rich.table import Table
from rich.text import Text

from gateway.auth.project_resolver import project_resolver
from gateway.auth.token_manager import token_manager
from gateway.config import DEFAULT_CONFIG
from gateway.telemetry.stats_tracker import stats_tracker

console = Console()
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"


def get_live_server_data() -> Optional[Dict[str, Any]]:
    """Query the local gateway /v1/gateway/stats endpoint."""
    url = f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}/v1/gateway/stats"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Antiglaude-TUI"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass
    return None


def get_current_claude_model() -> str:
    """Read current default model configured in ~/.claude/settings.json."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("model", "claude-sonnet-4-6")
    except Exception:
        pass
    return "claude-sonnet-4-6"


def set_current_claude_model(new_model: str) -> bool:
    """Update default model in ~/.claude/settings.json."""
    try:
        data = {}
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["model"] = new_model
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def is_daemon_running() -> bool:
    """Check if macOS LaunchAgent or server daemon is active."""
    try:
        res = subprocess.run(
            ["launchctl", "list", "com.antiglaude.bridge"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def build_tui_layout(stats: Dict[str, Any], is_server_online: bool, active_claude_model: str) -> Layout:
    """Build the Rich Layout UI tree."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="upper", size=11),
        Layout(name="models", size=9),
        Layout(name="journal", ratio=1),
        Layout(name="footer", size=3),
    )

    layout["upper"].split_row(
        Layout(name="account_card", ratio=1),
        Layout(name="quota_card", ratio=1),
    )

    # 1. Header
    header_text = Text()
    header_text.append(" ANTIGLAUDE BRIDGE ", style="bold white on #262626")
    header_text.append(" │ ", style="dim")
    if is_server_online:
        header_text.append("● ONLINE", style="bold green")
        header_text.append(f" (http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port})", style="dim green")
    else:
        header_text.append("○ OFFLINE", style="bold red")
        header_text.append(" (Press [s] to Start)", style="dim yellow")

    header_text.append(" │ ", style="dim")
    header_text.append("Default: ", style="dim")
    header_text.append(f"{active_claude_model}", style="bold cyan")
    header_text.append(" │ ", style="dim")
    header_text.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")

    layout["header"].update(Panel(Align.center(header_text), box=ROUNDED, style="dim white"))

    # 2. Account Card
    acc = stats.get("account", {})
    acc_table = Table(box=None, show_header=False, pad_edge=False)
    acc_table.add_column("Key", style="dim white", width=16)
    acc_table.add_column("Val", style="bold cyan")

    acc_table.add_row("Account:", f"[white]{acc.get('email', 'default@antigravity')}[/]")
    acc_table.add_row("Project ID:", f"[dim cyan]{acc.get('project_id', 'aicode-consumers')}[/]")
    acc_table.add_row("Tier:", f"[green]{acc.get('tier_name', 'Google AI Pro')}[/] ({acc.get('tier_id', 'g1-pro-tier')})")
    acc_table.add_row("Daemon Service:", "[green]Active (launchd)[/]" if is_daemon_running() else "[dim]Inactive[/]")
    acc_table.add_row("Uptime:", f"{stats.get('uptime_seconds', 0):,} seconds")

    layout["upper"]["account_card"].update(
        Panel(acc_table, title="[bold]Upstream Authentication[/]", box=ROUNDED, style="dim white")
    )

    # 3. Quota & Limits Card
    quota_table = Table(box=None, show_header=False, pad_edge=False)
    quota_table.add_column("Key", style="dim white", width=18)
    quota_table.add_column("Val", style="bold")

    daily_limit = stats.get("daily_limit", 1500)
    requests_today = stats.get("requests_today", 0)
    requests_remaining = stats.get("requests_remaining", daily_limit)
    pct_used = stats.get("quota_percent_used", 0.0)

    # Visual meter
    bar_width = 24
    filled = int((pct_used / 100.0) * bar_width)
    bar_color = "green" if pct_used < 60 else "yellow" if pct_used < 85 else "red"
    bar_str = f"[{bar_color}]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/] {pct_used}%"

    quota_table.add_row("Daily Request Limit:", f"[white]{daily_limit:,} reqs/day[/]")
    quota_table.add_row("Requests Today:", f"[yellow]{requests_today:,}[/] ({bar_str})")
    quota_table.add_row("Requests Remaining:", f"[bold green]{requests_remaining:,}[/]")
    quota_table.add_row("Total Lifetime Reqs:", f"[white]{stats.get('total_requests', 0):,}[/]")
    quota_table.add_row("Tokens (In / Out):", f"[dim]{stats.get('total_input_tokens', 0):,} / {stats.get('total_output_tokens', 0):,}[/]")

    layout["upper"]["quota_card"].update(
        Panel(quota_table, title="[bold]Rate Limits & Quota Meter[/]", box=ROUNDED, style="dim white")
    )

    # 4. Models Table
    models_table = Table(box=ROUNDED, expand=True)
    models_table.add_column("Model Identifier", style="bold cyan", width=28)
    models_table.add_column("Target Backend", style="white", width=28)
    models_table.add_column("Status", style="green", width=14)
    models_table.add_column("Requests", justify="right", style="yellow", width=12)
    models_table.add_column("Description", style="dim", ratio=1)

    usage = stats.get("models_usage", {})

    models_data = [
        ("claude-sonnet-4-6", "Claude 3.7 Sonnet (Thinking)", "● Active", usage.get("claude-sonnet-4-6", 0), "Primary agentic reasoning engine for Claude Code CLI"),
        ("claude-opus-4-6-thinking", "Claude 3 Opus (Extended Thinking)", "● Active", usage.get("claude-opus-4-6-thinking", 0), "Deep analytical & complex architectural problem solving"),
        ("gemini-3-flash", "Gemini 3 Flash", "● Active", usage.get("gemini-3-flash", 0), "Ultra-fast completions, syntax checks, and lightweight calls"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro", "● Active", usage.get("gemini-2.5-pro", 0), "Massive context analysis and full codebase ingestion"),
    ]

    for m_name, m_alias, m_status, m_cnt, m_desc in models_data:
        is_cur = (m_name == active_claude_model)
        m_disp = f"► {m_name}" if is_cur else f"  {m_name}"
        style = "bold white" if is_cur else None
        models_table.add_row(m_disp, m_alias, m_status, f"{m_cnt:,}", m_desc, style=style)

    layout["models"].update(
        Panel(models_table, title="[bold]Routing Matrix & Supported Models[/]", box=ROUNDED, style="dim white")
    )

    # 5. Recent Request Journal
    journal_table = Table(box=SIMPLE, expand=True)
    journal_table.add_column("Time", style="dim", width=10)
    journal_table.add_column("Client", style="dim cyan", width=14)
    journal_table.add_column("Endpoint", style="white", width=24)
    journal_table.add_column("Model", style="yellow", width=26)
    journal_table.add_column("Tokens", justify="right", style="green", width=14)
    journal_table.add_column("Latency", justify="right", style="dim white", width=12)
    journal_table.add_column("Status", justify="center", width=10)

    recent = stats.get("recent_requests", [])
    if not recent:
        journal_table.add_row("-", "-", "No recent requests logged", "-", "-", "-", "-")
    else:
        for r in list(reversed(recent))[:8]:
            status_style = "green" if r.get("status_code", 200) < 400 else "red"
            journal_table.add_row(
                r.get("time_str", "-"),
                r.get("client", "claude-code"),
                r.get("endpoint", "/v1/messages"),
                r.get("model", "-"),
                f"{r.get('total_tokens', 0):,}",
                f"{r.get('latency_ms', 0):.0f} ms",
                Text(str(r.get("status_code", 200)), style=status_style),
            )

    layout["journal"].update(
        Panel(journal_table, title="[bold]Request Journal & Latency Log[/]", box=ROUNDED, style="dim white")
    )

    # 6. Footer Controls
    footer_text = Text()
    footer_text.append(" [r] ", style="bold black on white")
    footer_text.append(" Refresh   ", style="dim white")
    footer_text.append(" [m] ", style="bold black on white")
    footer_text.append(" Switch Model   ", style="dim white")
    footer_text.append(" [c] ", style="bold black on white")
    footer_text.append(" Run Claude   ", style="dim white")
    footer_text.append(" [s] ", style="bold black on white")
    footer_text.append(" Restart Server   ", style="dim white")
    footer_text.append(" [d] ", style="bold black on white")
    footer_text.append(" Daemon Manager   ", style="dim white")
    footer_text.append(" [q] ", style="bold white on red")
    footer_text.append(" Quit", style="dim white")

    layout["footer"].update(Panel(Align.center(footer_text), box=ROUNDED, style="dim white"))

    return layout


def get_single_keypress(timeout: float = 0.5) -> Optional[str]:
    """Read a single keypress without requiring enter (macOS/Unix)."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            char = sys.stdin.read(1)
            return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None


def prompt_model_switch(console: Console) -> None:
    """Interactive modal prompt to switch active model."""
    console.clear()
    models = [
        ("1", "claude-sonnet-4-6", "Claude Sonnet 4.6 (Thinking) - Default, fast agentic reasoning"),
        ("2", "claude-opus-4-6-thinking", "Claude Opus 4.6 (Thinking) - Deep reasoning & architecture"),
        ("3", "gemini-3-flash", "Gemini 3 Flash - Ultra-fast lightweight completions"),
        ("4", "gemini-2.5-pro", "Gemini 2.5 Pro - Analytical large-context model"),
    ]

    console.print("\n[bold cyan]Select Default Model for Claude Code:[/]\n")
    for key, name, desc in models:
        console.print(f"  [bold yellow]{key}[/] -> [bold white]{name}[/]: [dim]{desc}[/]")
    console.print("\n  [bold red]0[/] -> Cancel\n")

    sys.stdout.write("Enter choice [1-4]: ")
    sys.stdout.flush()
    ch = get_single_keypress(timeout=10.0)

    mapping = {"1": "claude-sonnet-4-6", "2": "claude-opus-4-6-thinking", "3": "gemini-3-flash", "4": "gemini-2.5-pro"}
    if ch in mapping:
        selected = mapping[ch]
        set_current_claude_model(selected)
        console.print(f"\n[bold green]Switched default Claude Code model to: {selected}[/]\n")
        time.sleep(1.0)


def manage_launchagent_daemon(console: Console) -> None:
    """Install or toggle the macOS LaunchAgent daemon."""
    from gateway.daemon.macos_daemon import install_launchagent, status_launchagent, uninstall_launchagent
    console.clear()
    is_running = is_daemon_running()

    console.print("\n[bold cyan]Antiglaude Bridge - macOS LaunchAgent Daemon Manager[/]\n")
    console.print(f"Current Daemon Status: {'[bold green]Installed & Running[/]' if is_running else '[bold yellow]Not Running / Not Installed[/]'}\n")
    console.print("  [bold yellow]1[/] -> Install & Start LaunchAgent (Auto-starts on macOS boot & Antigravity launch)")
    console.print("  [bold yellow]2[/] -> Stop & Uninstall LaunchAgent")
    console.print("  [bold yellow]3[/] -> Check detailed service status")
    console.print("  [bold red]0[/] -> Back to Dashboard\n")

    sys.stdout.write("Enter choice [1-3]: ")
    sys.stdout.flush()
    ch = get_single_keypress(timeout=10.0)

    if ch == "1":
        install_launchagent()
        console.print("\n[bold green]LaunchAgent installed. Server active in background.[/]\n")
        time.sleep(1.5)
    elif ch == "2":
        uninstall_launchagent()
        console.print("\n[bold yellow]LaunchAgent stopped and uninstalled.[/]\n")
        time.sleep(1.5)
    elif ch == "3":
        status_launchagent()
        console.print("\nPress any key to return...")
        get_single_keypress(timeout=5.0)


def run_control_panel():
    """Main execution loop for TUI."""
    console.clear()

    # Pre-warm project & tier info in background
    async def _init_auth():
        try:
            token = await token_manager.get_access_token()
            await project_resolver.resolve(token)
        except Exception:
            pass

    try:
        asyncio.run(_init_auth())
    except Exception:
        pass

    with Live(console=console, screen=True, refresh_per_second=2) as live:
        while True:
            live_data = get_live_server_data()
            is_online = live_data is not None
            stats = live_data or stats_tracker.get_snapshot()
            active_model = get_current_claude_model()

            layout = build_tui_layout(stats, is_online, active_model)
            live.update(layout)

            key = get_single_keypress(timeout=1.0)
            if key == "q":
                break
            elif key == "r":
                # Manual refresh
                continue
            elif key == "m":
                live.stop()
                prompt_model_switch(console)
                live.start()
            elif key == "d":
                live.stop()
                manage_launchagent_daemon(console)
                live.start()
            elif key == "c":
                live.stop()
                console.clear()
                console.print("[bold green]Launching Claude Code...[/]")
                subprocess.run(
                    ["claude"],
                    env={
                        **os.environ,
                        "ANTHROPIC_BASE_URL": f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}",
                        "ANTHROPIC_API_KEY": "test",
                        "CLAUDE_CODE_AUTO_MODE_SERVER": "0",
                    },
                )
                console.print("\nPress any key to return to Control Panel...")
                get_single_keypress(timeout=5.0)
                live.start()
            elif key == "s":
                live.stop()
                console.clear()
                console.print("[bold yellow]Restarting/Starting Gateway Server...[/]")
                # Kill existing on port
                subprocess.run(f"lsof -ti :{DEFAULT_CONFIG.port} | xargs kill -9 2>/dev/null || true", shell=True)
                # Spawn background server
                cmd = f"{sys.executable} -m gateway.cli start --port {DEFAULT_CONFIG.port}"
                subprocess.Popen(cmd, shell=True)
                time.sleep(1.5)
                live.start()


if __name__ == "__main__":
    run_control_panel()
