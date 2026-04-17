"""Session persistence — save conversation history and reload on next run."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rpg_player import config


class SessionMemory:
    def __init__(self) -> None:
        self._dir = Path(config.SESSIONS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Query ──────────────────────────────────────────────────────────────────

    def list_sessions(self) -> list[dict]:
        """Return saved sessions as dicts, newest first."""
        out = []
        for f in sorted(self._dir.glob("session_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["_file"] = str(f)
                out.append(data)
            except Exception:
                pass
        return out

    def load_latest(self) -> Optional[dict]:
        s = self.list_sessions()
        return s[0] if s else None

    # ── Save ───────────────────────────────────────────────────────────────────

    def save(
        self,
        exchanges: list[dict],
        character: dict,
        known_players: list[str],
    ) -> Path:
        data = {
            "started_at": datetime.now().isoformat(),
            "character": character.get("name", ""),
            "exchanges": exchanges,
            "known_players": known_players,
        }
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._dir / f"session_{ts}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ── Context injection ──────────────────────────────────────────────────────

    def build_context_block(self, session: dict) -> str:
        """Format a previous session as a block injected into the agent system prompt."""
        char  = session.get("character", "nieznana")
        date  = (session.get("started_at") or "")[:10]
        players = session.get("known_players", [])
        exchanges = session.get("exchanges", [])[-config.SESSION_HISTORY_CONTEXT_EXCHANGES:]

        lines = [
            "=== POPRZEDNIA SESJA ===",
            f"Data: {date}  ·  Postać: {char}",
        ]
        if players:
            lines.append(f"Znani gracze: {', '.join(players)}")
        lines.append("Ostatnie kwestie:")
        for ex in exchanges:
            lines.append(f"  [{ex.get('speaker', '?')}]: {ex.get('text', '')}")
        lines.append("=========================")
        return "\n".join(lines)
