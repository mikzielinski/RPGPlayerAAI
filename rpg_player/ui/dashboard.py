"""Rich terminal dashboard — live session status display."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rich import box
from rich.columns import Columns
from rich.console import Console, Group as RichGroup
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_STATUS_COLOR = {
    "STARTING": "yellow",
    "ONBOARDING": "cyan",
    "INGESTING": "blue",
    "LISTENING": "green",
    "CLASSIFYING": "yellow",
    "SPEAKING": "magenta",
    "COOLDOWN": "red",
    "ERROR": "bold red",
    "STOPPED": "dim",
}
_STATUS_ICON = {
    "STARTING": "⏳",
    "ONBOARDING": "💬",
    "INGESTING": "📚",
    "LISTENING": "🎤",
    "CLASSIFYING": "🤔",
    "SPEAKING": "🔊",
    "COOLDOWN": "⏱",
    "ERROR": "✖",
    "STOPPED": "■",
}
_DECISION_COLOR = {
    "MY_TURN": "bold green",
    "SPEAK_UP": "bold yellow",
    "WAIT": "dim white",
}


@dataclass
class SessionState:
    status: str = "STARTING"
    character_name: str = "—"
    character_info: str = "—"
    personality_info: str = "—"
    last_decision: str = "—"
    last_response: str = ""
    cooldown_remaining: float = 0.0
    cooldown_total: float = 45.0
    behaviors_triggered: list[str] = field(default_factory=list)
    buffer: list[dict] = field(default_factory=list)
    error: str = ""


class Dashboard:
    """Thread-safe Rich live dashboard.

    Usage:
        dash = Dashboard()
        dash.start()
        dash.update(status="LISTENING", character_name="Aldric")
        dash.log("Session started")
        dash.stop()
    """

    def __init__(self) -> None:
        self._state = SessionState()
        self._log: deque[str] = deque(maxlen=30)
        self._lock = threading.Lock()
        self._running = False
        self._live: Optional[Live] = None
        self._console = Console()

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(self, **kwargs) -> None:
        """Update one or more state fields. Thread-safe."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)

    def log(self, message: str) -> None:
        """Append a timestamped entry to the event log."""
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._log.append(f"[dim]{ts}[/dim]  {message}")

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=4,
            screen=False,
            transient=False,
        )
        self._live.__enter__()
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._live:
            self._live.__exit__(None, None, None)

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _refresh_loop(self) -> None:
        while self._running:
            with self._lock:
                renderable = self._render()
            self._live.update(renderable)
            time.sleep(0.25)

    def _render(self) -> Panel:
        s = self._state

        color = _STATUS_COLOR.get(s.status, "white")
        icon = _STATUS_ICON.get(s.status, "●")

        # ── Header ─────────────────────────────────────────────────────────────
        status_badge = Text(f" {icon} {s.status} ", style=f"bold {color} reverse")
        header = Text.assemble(
            status_badge,
            Text(f"  {s.character_name}", style="bold white"),
            Text(f"  ·  {s.character_info}", style="dim white"),
        )

        # ── Buffer panel (left) ────────────────────────────────────────────────
        buf_text = Text()
        if s.buffer:
            for entry in s.buffer[-14:]:
                spk = entry.get("speaker", "?")
                txt = entry.get("text", "")
                if spk == s.character_name:
                    buf_text.append(f"▶ {spk}: ", style="bold cyan")
                    buf_text.append(f"{txt}\n", style="cyan")
                else:
                    buf_text.append(f"  {spk}: ", style="dim")
                    buf_text.append(f"{txt}\n", style="white")
        else:
            buf_text = Text("(nasłuchuję...)", style="dim italic")

        buffer_panel = Panel(
            buf_text,
            title="[bold blue]⚔  Rozmowa przy stole[/bold blue]",
            border_style="blue",
            box=box.ROUNDED,
        )

        # ── Stats panel (right) ────────────────────────────────────────────────
        stats = Table.grid(padding=(0, 1))
        stats.add_column(style="dim", min_width=16)
        stats.add_column(min_width=22)

        dec_color = _DECISION_COLOR.get(s.last_decision, "white")
        stats.add_row("Decyzja:", Text(s.last_decision, style=dec_color))
        stats.add_row("Styl gracza:", Text(s.personality_info, style="white"))

        if s.cooldown_remaining > 0:
            ratio = max(0.0, (s.cooldown_total - s.cooldown_remaining) / s.cooldown_total)
            filled = int(ratio * 10)
            bar = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (10 - filled) + "[/dim]"
            stats.add_row("Cooldown:", Text.from_markup(f"{bar} {s.cooldown_remaining:.0f}s"))
        else:
            stats.add_row("Cooldown:", Text("✓ gotowy", style="bold green"))

        if s.behaviors_triggered:
            joined = ", ".join(s.behaviors_triggered)
            stats.add_row("Zachowania:", Text(joined, style="yellow"))
        else:
            stats.add_row("Zachowania:", Text("brak", style="dim"))

        if s.last_response:
            preview = (s.last_response[:55] + "…") if len(s.last_response) > 55 else s.last_response
            stats.add_row("Ostatnia:", Text(preview, style="cyan italic"))

        if s.error:
            stats.add_row("Błąd:", Text(s.error[:45], style="bold red"))

        stats_panel = Panel(
            stats,
            title="[bold yellow]📊  Status sesji[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        )

        # ── Log panel (bottom) ─────────────────────────────────────────────────
        log_text = Text()
        for entry in list(self._log)[-8:]:
            log_text.append_text(Text.from_markup(entry + "\n"))
        log_panel = Panel(
            log_text,
            title="[bold]📋  Dziennik zdarzeń[/bold]",
            border_style="grey50",
            box=box.ROUNDED,
        )

        # ── Compose ────────────────────────────────────────────────────────────
        top = Columns([buffer_panel, stats_panel], expand=True)
        body = RichGroup(header, top, log_panel)

        return Panel(
            body,
            title="[bold magenta]⚔  RPG AI Player Bot[/bold magenta]",
            border_style="magenta",
            box=box.DOUBLE_EDGE,
        )
