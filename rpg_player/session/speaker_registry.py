"""Learns player names from self-introductions heard during the session."""
from __future__ import annotations

import re
from typing import Optional

# Matches "Jestem Marek", "Nazywam się Ania", "I'm John", "My name is Kate" etc.
_INTRO_RE = re.compile(
    r"(?:jestem|nazywam\s+si[eę]|mam\s+na\s+imi[eę]|na\s+imi[eę]\s+mam"
    r"|i(?:'m|\s+am)\s+|my\s+name\s+is\s+)"
    r"([A-ZŁŚŻŹĆŃÓĘ][A-Za-złśżźćńóęA-ZŁŚŻŹĆŃÓĘ]{1,24})",
    re.IGNORECASE,
)


class SpeakerRegistry:
    """Maps anonymous buffer labels to real player names once they self-introduce."""

    def __init__(self) -> None:
        self._names: list[str] = []   # ordered, for display
        self._log: list[dict] = []    # for session persistence

    def process(self, text: str) -> Optional[str]:
        """If text contains a name introduction return the extracted name, else None.

        The caller should use the returned name as the speaker label for that entry.
        """
        m = _INTRO_RE.search(text)
        if not m:
            return None
        name = m.group(1)
        name = name[0].upper() + name[1:]
        if name not in self._names:
            self._names.append(name)
        self._log.append({"text": text[:100], "name": name})
        return name

    @property
    def known_players(self) -> list[str]:
        return list(self._names)

    def to_dict(self) -> dict:
        return {"names": self._names, "log": self._log}

    def from_dict(self, data: dict) -> None:
        self._names = data.get("names", [])
        self._log = data.get("log", [])
