"""Auto-detect RPG system, genre and tone from ingested document text."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from rpg_player import config

_DETECT_SYSTEM = (
    "Jesteś ekspertem od gier fabularnych. Przeanalizuj poniższe fragmenty dokumentów "
    "i określ typ rozgrywki. Zwróć TYLKO poprawny JSON bez komentarzy ani markdown:\n"
    "{\n"
    '  "system": "pełna nazwa systemu RPG (np. Dungeons & Dragons 5e)",\n'
    '  "genre": "gatunek: fantasy / sci-fi / horror / cyberpunk / western / modern / historical / superhero / inne",\n'
    '  "tone": "nastrój: epic / gritty / comedic / dark / cinematic / survival / pulp",\n'
    '  "setting": "krótki opis świata w 1-2 zdaniach po polsku",\n'
    '  "universe_keywords": ["lista", "słów", "kluczowych", "świata"]\n'
    "}"
)

_DETECT_USER = "Fragmenty dokumentów gry:\n\n{text}\n\n---\nOkreśl typ tej gry w formacie JSON."


def detect_and_save(doc_texts: list[str]) -> dict:
    """LLM-classify game type from raw document samples; persist and return result."""
    # Use up to 4 documents, first 1 500 chars each
    sample = "\n\n---\n\n".join(t[:1500] for t in doc_texts[:4])

    llm = ChatOpenAI(
        model=config.CLASSIFIER_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.0,
        timeout=config.OPENAI_TIMEOUT_SEC,
    )
    try:
        resp = llm.invoke([
            SystemMessage(content=_DETECT_SYSTEM),
            HumanMessage(content=_DETECT_USER.format(text=sample)),
        ])
        raw = resp.content.strip()
        # Strip markdown fences if model wraps its output
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data: dict = json.loads(raw.strip())
    except Exception as exc:
        data = {
            "system": "Nieznany system",
            "genre": "fantasy",
            "tone": "epic",
            "setting": "Świat gry nie mógł zostać określony automatycznie.",
            "universe_keywords": [],
            "error": str(exc),
        }

    data["detected_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("campaign_intro", "")
    _write(data)
    return data


def load() -> Optional[dict]:
    """Return saved game_type dict or None if detection hasn't run yet."""
    path = Path(config.GAME_TYPE_FILE)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_intro(intro_text: str) -> None:
    """Append campaign intro to existing game_type.json."""
    data = load() or {}
    data["campaign_intro"] = intro_text
    _write(data)


def build_game_context(data: dict) -> str:
    """Return formatted block for injection into agent system prompt."""
    if not data:
        return ""
    lines = [
        "=== TYP ROZGRYWKI ===",
        f"System: {data.get('system', '?')}",
        f"Gatunek: {data.get('genre', '?')}",
        f"Nastrój: {data.get('tone', '?')}",
        f"Świat: {data.get('setting', '')}",
    ]
    kw = data.get("universe_keywords", [])
    if kw:
        lines.append(f"Słowa kluczowe: {', '.join(kw)}")
    intro = data.get("campaign_intro", "").strip()
    if intro:
        lines.append(f"Intro kampanii: {intro}")
    lines.append("(koniec opisu gry)")
    return "\n".join(lines)


def _write(data: dict) -> None:
    path = Path(config.GAME_TYPE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
