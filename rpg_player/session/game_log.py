"""Structured JSONL game log for live state and event tracking."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rpg_player import config


@dataclass
class GameState:
    scene_summary: str = ""
    active_location: str = ""
    active_npcs: list[str] = field(default_factory=list)
    quests: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    players: dict[str, str] = field(default_factory=dict)  # player_name -> character_name

    def as_dict(self) -> dict[str, Any]:
        return {
            "scene_summary": self.scene_summary,
            "active_location": self.active_location,
            "active_npcs": list(self.active_npcs),
            "quests": list(self.quests),
            "timeline": list(self.timeline),
            "players": dict(self.players),
        }


class GameLog:
    """Append-only JSONL logger for gameplay and synchronization tools."""

    def __init__(self, enabled: bool = True, logs_dir: str | None = None) -> None:
        self.enabled = bool(enabled)
        self._logs_dir = Path(logs_dir or config.GAME_LOGS_DIR)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self.state = GameState()
        self._file = self._logs_dir / f"game_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"

    @property
    def file_path(self) -> Path:
        return self._file

    def _append(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        envelope = {
            "time": datetime.utcnow().isoformat(),
            **payload,
        }
        with self._file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    def log_event(
        self,
        *,
        event: str,
        status: str = "",
        decision: str = "",
        actor: str = "",
        detail: str = "",
        buffer: list[dict[str, Any]] | None = None,
        known_players: list[str] | None = None,
    ) -> None:
        self._append(
            {
                "type": "event",
                "event": event,
                "status": status,
                "decision": decision,
                "actor": actor,
                "detail": detail,
                "buffer_tail": (buffer or [])[-10:],
                "known_players": list(known_players or []),
                "state": self.state.as_dict(),
            }
        )

    def log_exchange(self, speaker: str, text: str) -> None:
        self._append(
            {
                "type": "exchange",
                "speaker": speaker,
                "text": text,
                "state": self.state.as_dict(),
            }
        )

    def update_state(
        self,
        *,
        scene_summary: str | None = None,
        active_location: str | None = None,
        active_npcs: list[str] | None = None,
        quests: list[str] | None = None,
        timeline_append: str | None = None,
    ) -> None:
        if scene_summary is not None:
            self.state.scene_summary = scene_summary
        if active_location is not None:
            self.state.active_location = active_location
        if active_npcs is not None:
            self.state.active_npcs = list(active_npcs)
        if quests is not None:
            self.state.quests = list(quests)
        if timeline_append:
            self.state.timeline.append(timeline_append)
            if len(self.state.timeline) > 200:
                self.state.timeline = self.state.timeline[-200:]
        self._append({"type": "state_update", "state": self.state.as_dict()})

    def record_player_character(self, player_name: str, character_name: str) -> None:
        player = (player_name or "").strip()
        character = (character_name or "").strip()
        if not player or not character:
            return
        self.state.players[player] = character
        self._append(
            {
                "type": "player_map",
                "player": player,
                "character": character,
                "state": self.state.as_dict(),
            }
        )

    @staticmethod
    def list_logs(logs_dir: str | None = None) -> list[Path]:
        root = Path(logs_dir or config.GAME_LOGS_DIR)
        root.mkdir(parents=True, exist_ok=True)
        return sorted(root.glob("game_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    @staticmethod
    def tail(path: Path | str, limit: int = 80) -> list[dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-max(1, int(limit)):]:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                out.append(json.loads(stripped))
            except Exception:
                out.append({"type": "raw", "line": stripped})
        return out
