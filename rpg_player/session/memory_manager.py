"""Three-tier memory manager: now / context_window / context_general.

context_general is a persistent JSON file updated asynchronously via LLM
summarization whenever the rolling context_window is flushed.  This gives
the bot full long-term recall without ever losing events to buffer overflow.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from rpg_player import config

_SUMMARIZE_SYSTEM = (
    "Jesteś archiwistą sesji RPG. Twoim zadaniem jest aktualizacja pamięci ogólnej "
    "na podstawie nowych wypowiedzi. Odpowiadasz WYŁĄCZNIE poprawnym JSON — "
    "bez wyjaśnień, bez markdown, bez żadnego tekstu poza JSON."
)

_SUMMARIZE_USER = """\
Istniejąca pamięć ogólna (JSON):
{existing}

Nowe wypowiedzi do zintegrowania:
{buffer_text}

Zaktualizuj i zwróć JSON z dokładnie tymi polami:
- known_npcs: dict NPC_imię -> krótki opis/rola (zachowaj istniejące, dodaj nowe)
- known_locations: lista unikalnych lokacji (zachowaj istniejące, dodaj nowe)
- key_decisions: lista ważnych decyzji/wyborów graczy (maks. 25, zachowaj najważniejsze)
- session_notes: lista kluczowych faktów i wydarzeń fabularnych (maks. 35)
- known_players: dict imię_gracza -> klasa/rasa postaci (zachowaj istniejące)

Odpowiedz wyłącznie JSON.\
"""


class MemoryManager:
    """
    Persistent general context tier.  Thread-safe.

    The three tiers:
      now            — last_utterance (buf[-1]), passed directly to agent
      context_window — rolling Listener buffer (last N exchanges)
      context_general — this class; LLM-summarised history persisted to JSON
    """

    def __init__(self, path: str | Path | None = None):
        self._path = Path(path or config.GENERAL_CONTEXT_FILE)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()
        self._summarizing = False

    # ── Persistence ──────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "known_npcs": {},
            "known_locations": [],
            "key_decisions": [],
            "session_notes": [],
            "known_players": {},
            "last_updated": "",
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            text = json.dumps(self._data, ensure_ascii=False, indent=2)
        self._path.write_text(text, encoding="utf-8")

    # ── Public read API ──────────────────────────────────────────────

    def get_summary_text(self) -> str:
        """Compact text for inclusion in the agent system prompt."""
        with self._lock:
            d = dict(self._data)
        parts: list[str] = []
        if d.get("known_players"):
            rows = [f"  {k}: {v}" if v else f"  {k}" for k, v in d["known_players"].items()]
            parts.append("Gracze przy stole:\n" + "\n".join(rows))
        if d.get("known_npcs"):
            rows = [f"  {k}: {v}" if v else f"  {k}" for k, v in d["known_npcs"].items()]
            parts.append("Znane BN (NPC):\n" + "\n".join(rows))
        if d.get("known_locations"):
            parts.append("Odwiedzone lokacje: " + ", ".join(d["known_locations"]))
        if d.get("key_decisions"):
            rows = [f"  • {x}" for x in d["key_decisions"][-12:]]
            parts.append("Kluczowe decyzje:\n" + "\n".join(rows))
        if d.get("session_notes"):
            rows = [f"  • {x}" for x in d["session_notes"][-18:]]
            parts.append("Notatki fabularne:\n" + "\n".join(rows))
        return "\n\n".join(parts) if parts else ""

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    @property
    def is_summarizing(self) -> bool:
        return self._summarizing

    # ── Public write API ─────────────────────────────────────────────

    def replace(self, data: dict[str, Any]) -> None:
        """Full overwrite — used from web panel editor."""
        with self._lock:
            self._data = dict(data)
        self._save()

    def update_players(self, known_players: list[str]) -> None:
        """Sync SpeakerRegistry names into known_players without LLM call."""
        changed = False
        with self._lock:
            kp = self._data.setdefault("known_players", {})
            for name in known_players:
                if name not in kp:
                    kp[name] = ""
                    changed = True
        if changed:
            self._save()

    def summarize_async(self, buffer: list[dict], known_players: list[str]) -> None:
        """Fire-and-forget: summarise buffer and merge into general context.

        Safe to call every time the window is flushed; guards against
        concurrent calls via the _summarizing flag.
        """
        if self._summarizing:
            return
        t = threading.Thread(
            target=self._do_summarize,
            args=(list(buffer), list(known_players)),
            daemon=True,
        )
        t.start()

    # ── Background summarisation ─────────────────────────────────────

    def _do_summarize(self, buffer: list[dict], known_players: list[str]) -> None:
        self._summarizing = True
        try:
            buffer_text = "\n".join(f"[{e['speaker']}]: {e['text']}" for e in buffer)
            with self._lock:
                existing_json = json.dumps(self._data, ensure_ascii=False, indent=2)

            from openai import OpenAI
            client = OpenAI(
                api_key=config.OPENAI_API_KEY,
                timeout=config.OPENAI_TIMEOUT_SEC,
                max_retries=1,
            )
            resp = client.chat.completions.create(
                model=config.CLASSIFIER_MODEL,
                messages=[
                    {"role": "system", "content": _SUMMARIZE_SYSTEM},
                    {"role": "user", "content": _SUMMARIZE_USER.format(
                        existing=existing_json,
                        buffer_text=buffer_text,
                    )},
                ],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            new_data: dict[str, Any] = json.loads(raw)

            with self._lock:
                for key, cap in (("key_decisions", 25), ("session_notes", 35)):
                    old: list = self._data.get(key, [])
                    added = [x for x in new_data.get(key, []) if x not in old]
                    self._data[key] = (old + added)[-cap:]
                old_locs: list = self._data.get("known_locations", [])
                new_locs = new_data.get("known_locations", [])
                self._data["known_locations"] = list(dict.fromkeys(old_locs + new_locs))
                for key in ("known_npcs", "known_players"):
                    d = self._data.setdefault(key, {})
                    d.update(new_data.get(key, {}))
                kp_dict = self._data.setdefault("known_players", {})
                for name in known_players:
                    kp_dict.setdefault(name, "")
                self._data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            self._save()
            print(f"[memory] Pamięć ogólna zaktualizowana ({len(buffer)} wymian).")
        except Exception as exc:
            print(f"[memory] Błąd aktualizacji pamięci ogólnej: {exc}")
        finally:
            self._summarizing = False
