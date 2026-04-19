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
    "STARTING":    "yellow",
    "ONBOARDING":  "cyan",
    "INGESTING":   "blue",
    "LISTENING":   "green",
    "CLASSIFYING": "yellow",
    "SPEAKING":    "magenta",
    "COOLDOWN":    "red",
    "MEMORIZING":  "yellow",
    "ERROR":       "bold red",
    "STOPPED":     "dim",
}
_STATUS_ICON = {
    "STARTING":    "...",
    "ONBOARDING":  ">>",
    "INGESTING":   "**",
    "LISTENING":   "<<",
    "CLASSIFYING": "??",
    "SPEAKING":    ">>",
    "COOLDOWN":    "||",
    "MEMORIZING":  "~~",
    "ERROR":       "!!",
    "STOPPED":     "[]",
}
_DECISION_COLOR = {
    "MY_TURN":  "bold green",
    "SPEAK_UP": "bold yellow",
    "WAIT":     "dim white",
}
_MODE_LABEL = {
    "gm":     "gm — gdy zagadnięty",
    "manual": "manual — tylko [f]",
    "auto":   "auto — autonomiczny",
}


def _bar(ratio: float, width: int = 10, low: str = "green", mid: str = "yellow", high: str = "red") -> str:
    """Return a Rich markup progress bar string."""
    ratio = max(0.0, min(1.0, ratio))
    filled = round(ratio * width)
    color = high if ratio >= 0.9 else mid if ratio >= 0.6 else low
    return (
        f"[{color}]" + "█" * filled + f"[/{color}]"
        + "[dim]" + "░" * (width - filled) + "[/dim]"
    )


@dataclass
class SessionState:
    status: str = "STARTING"
    character_name: str = "—"
    character_info: str = "—"
    personality_info: str = "—"
    response_mode: str = "gm"
    last_decision: str = "—"
    last_response: str = ""
    cooldown_remaining: float = 0.0
    cooldown_total: float = 45.0
    behaviors_triggered: list[str] = field(default_factory=list)
    buffer: list[dict] = field(default_factory=list)
    buffer_max_exchanges: int = 15
    error: str = ""
    token_summary: str = "0.0k tokenów"
    known_players: list[str] = field(default_factory=list)
    voice_name: str = "—"
    # three-tier memory
    memory_summarizing: bool = False
    memory_last_updated: str = ""
    memory_notes_count: int = 0


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
        self._log: deque[str] = deque(maxlen=40)
        self._lock = threading.Lock()
        self._running = False
        self._live: Optional[Live] = None
        self._console = Console()

    # ── Public API ────────────────────────────────────────────────────

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

    # ── Lifecycle ─────────────────────────────────────────────────────

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

    # ── Rendering ─────────────────────────────────────────────────────

    def _refresh_loop(self) -> None:
        while self._running:
            with self._lock:
                renderable = self._render()
            self._live.update(renderable)
            time.sleep(0.25)

    def _render(self) -> Panel:
        s = self._state

        color = _STATUS_COLOR.get(s.status, "white")
        icon  = _STATUS_ICON.get(s.status,  "o")

        # ── Buffer fill metrics ───────────────────────────────────────
        buf_len = len(s.buffer)
        buf_max = max(1, s.buffer_max_exchanges)
        buf_ratio = buf_len / buf_max
        buf_border = "red" if buf_ratio >= 0.9 else "yellow" if buf_ratio >= 0.6 else "blue"

        # ── Header ────────────────────────────────────────────────────
        status_badge = Text(f" {icon} {s.status} ", style=f"bold {color} reverse")
        if s.memory_summarizing:
            mem_badge = Text(" ~~ ZAPISUJE PAMIĘĆ ", style="bold yellow reverse")
            header = Text.assemble(
                status_badge, Text("  "), mem_badge,
                Text(f"  {s.character_name}", style="bold white"),
                Text(f"  ·  {s.character_info}", style="dim white"),
                Text(f"  ·  {s.voice_name}", style="dim cyan"),
            )
        else:
            header = Text.assemble(
                status_badge,
                Text(f"  {s.character_name}", style="bold white"),
                Text(f"  ·  {s.character_info}", style="dim white"),
                Text(f"  ·  {s.voice_name}", style="dim cyan"),
            )

        # ── Buffer / conversation panel (left) ───────────────────────
        buf_text = Text()
        if s.buffer:
            for entry in s.buffer[-16:]:
                spk = entry.get("speaker", "?")
                txt = entry.get("text", "")
                if spk == s.character_name:
                    buf_text.append(f"▶ {spk}: ", style="bold cyan")
                    buf_text.append(f"{txt}\n", style="cyan")
                else:
                    buf_text.append(f"  {spk}: ", style="dim")
                    buf_text.append(f"{txt}\n", style="white")
        else:
            buf_text = Text("(nasłuchuje...)", style="dim italic")

        buf_fill_bar = _bar(buf_ratio, width=12)
        fill_line = Text.from_markup(
            f"{buf_fill_bar} [dim]{buf_len}/{buf_max}[/dim]"
            + (f" [bold red]AUTO-FLUSH wkrótce[/bold red]" if buf_ratio >= 0.9 else "")
        )
        buf_content = RichGroup(fill_line, Text(""), buf_text)

        buffer_panel = Panel(
            buf_content,
            title=f"[bold {buf_border}]Rozmowa przy stole[/bold {buf_border}]",
            border_style=buf_border,
            box=box.ROUNDED,
        )

        # ── Stats panel (right) ───────────────────────────────────────
        stats = Table.grid(padding=(0, 1))
        stats.add_column(style="dim", min_width=14)
        stats.add_column(min_width=24)

        dec_color = _DECISION_COLOR.get(s.last_decision, "white")
        stats.add_row("Decyzja:", Text(s.last_decision, style=dec_color))

        mode_label = _MODE_LABEL.get(s.response_mode, s.response_mode)
        stats.add_row("Tryb:", Text(mode_label, style="white"))

        stats.add_row(
            "Bufor:",
            Text.from_markup(f"{_bar(buf_ratio, width=10)} [dim]{buf_len}/{buf_max}[/dim]"),
        )

        if s.cooldown_remaining > 0:
            ratio = max(0.0, (s.cooldown_total - s.cooldown_remaining) / s.cooldown_total)
            stats.add_row(
                "Cooldown:",
                Text.from_markup(f"{_bar(ratio, low='green', mid='green', high='yellow')} {s.cooldown_remaining:.0f}s"),
            )
        else:
            stats.add_row("Cooldown:", Text("gotowy", style="bold green"))

        stats.add_row("Tokeny:", Text(s.token_summary, style="dim cyan"))

        # Memory status
        if s.memory_summarizing:
            stats.add_row("Pamięć:", Text("⟳ Zapisuje...", style="bold yellow"))
        elif s.memory_last_updated:
            updated = s.memory_last_updated[-8:] if len(s.memory_last_updated) >= 8 else s.memory_last_updated
            notes_hint = f"  {s.memory_notes_count} faktów" if s.memory_notes_count else ""
            stats.add_row("Pamięć:", Text(f"OK  {updated}{notes_hint}", style="green"))
        else:
            stats.add_row("Pamięć:", Text("pusta", style="dim"))

        if s.behaviors_triggered:
            stats.add_row("Zachowania:", Text(", ".join(s.behaviors_triggered), style="yellow"))

        if s.known_players:
            stats.add_row("Gracze:", Text(", ".join(s.known_players), style="green"))

        if s.last_response:
            preview = (s.last_response[:52] + "…") if len(s.last_response) > 52 else s.last_response
            stats.add_row("Ostatnia:", Text(preview, style="cyan italic"))

        if s.error:
            stats.add_row("Błąd:", Text(s.error[:45], style="bold red"))

        stats_panel = Panel(
            stats,
            title="[bold yellow]Status sesji[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        )

        # ── Log panel (bottom) ────────────────────────────────────────
        log_text = Text()
        for entry in list(self._log)[-9:]:
            log_text.append_text(Text.from_markup(entry + "\n"))

        shortcuts = Text(
            "  [f] wymuś odpowiedź   [v] zmień głos   [q] zakończ",
            style="dim",
        )
        log_panel = Panel(
            RichGroup(log_text, shortcuts),
            title="[bold]Dziennik zdarzeń[/bold]",
            border_style="grey50",
            box=box.ROUNDED,
        )

        # ── Compose ───────────────────────────────────────────────────
        top = Columns([buffer_panel, stats_panel], expand=True)
        body = RichGroup(header, top, log_panel)

        return Panel(
            body,
            title="[bold magenta]⚔  RPG AI Player Bot[/bold magenta]",
            border_style="magenta",
            box=box.DOUBLE_EDGE,
        )
