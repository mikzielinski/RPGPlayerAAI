"""Load character sheet from data/character.json, or return None."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rpg_player import config


def load_character(path: str = config.CHARACTER_FILE) -> Optional[dict]:
    p = Path(path)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)
