"""Structured live game-state log written as JSON Lines."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rpg_player import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    """Append-only JSONL session log with latest-state snapshot support."""

    def __init__(self, base_dir: str = config.GAME_LOGS_DIR, enabled: bool = True) -> None:
        self._enabled = enabled
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._path = self._dir / f"game_log_{ts}.jsonl"
        self._state = GameState()
        self._append(
            {
                "type": "session_start",
                "timestamp": _now_iso(),
                "state": self._state.as_dict(),
            }
        )

    @property
    def path(self) -> Path:
        return self._path

    @property
    def state(self) -> GameState:
        return self._state

    def _append(self, entry: dict[str, Any]) -> None:
        if not self._enabled:
            return
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._append(
            {
                "type": event_type,
                "timestamp": _now_iso(),
                "payload": payload,
                "state": self._state.as_dict(),
            }
        )

    def log_exchange(self, speaker: str, text: str) -> None:
        self._append(
            {
                "type": "exchange",
                "timestamp": _now_iso(),
                "speaker": speaker,
                "text": text,
                "state": self._state.as_dict(),
            }
        )

    def update_state(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        self._append(
            {
                "type": "state_update",
                "timestamp": _now_iso(),
                "state": self._state.as_dict(),
            }
        )

    def record_player_character(self, player_name: str, character_name: str) -> None:
        self._state.players[player_name] = character_name
        self._append(
            {
                "type": "player_character_map",
                "timestamp": _now_iso(),
                "player_name": player_name,
                "character_name": character_name,
                "state": self._state.as_dict(),
            }
        )

    @staticmethod
    def list_logs(base_dir: str = config.GAME_LOGS_DIR) -> list[Path]:
        p = Path(base_dir)
        if not p.exists():
            return []
        return sorted(p.glob("game_log_*.jsonl"), reverse=True)

    @staticmethod
    def tail(path: Path, limit: int = 100) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def log_state(
        self,
        event: str,
        status: str = "",
        decision: str = "",
        actor: str = "",
        detail: str = "",
        buffer: list[dict[str, Any]] | None = None,
        known_players: list[str] | None = None,
    ) -> None:
        """Convenience API used by main loop for live state snapshots."""
        payload: dict[str, Any] = {
            "event": event,
            "status": status,
            "decision": decision,
            "actor": actor,
            "detail": detail,
            "known_players": list(known_players or []),
        }
        if buffer is not None:
            payload["buffer_tail"] = list(buffer[-config.BUFFER_MAX_EXCHANGES :])
        self.log_event("state_trace", payload)
