"""Detect and extract character data from an uploaded PDF/document.

Scans game_files/ for any file that looks like a character sheet and returns
a fully-populated character dict ready to save as character.json, or None.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from rpg_player import config

_SUPPORTED = {".pdf", ".docx"}

_DETECT_SYSTEM = """Przeanalizuj poniższy tekst i oceń czy to KARTA POSTACI RPG (character sheet).

Karta postaci typowo zawiera: imię postaci, klasę lub rolę, rasę lub gatunek,
statystyki (STR/DEX lub Siła/Zręczność lub inne atrybuty), punkty życia, ekwipunek, umiejętności.
Podręcznik zasad, przygoda, lore lub atlas NIGDY nie są kartą postaci.

Jeśli to KARTA POSTACI, zwróć JSON:
{
  "is_character_sheet": true,
  "name": "imię postaci po polsku",
  "race": "rasa lub gatunek",
  "char_class": "klasa, kariera lub archetyp",
  "level": <liczba całkowita, 1 jeśli brak>,
  "stats": {"NazwaStatystyki": <wartość_liczbowa>, ...},
  "hp": {"current": <liczba>, "max": <liczba>},
  "spells": ["lista zaklęć lub zdolności specjalnych"],
  "inventory": ["lista ekwipunku"],
  "personality": "2-3 zdania opisujące osobowość postaci po polsku",
  "backstory_short": "1-2 zdania historii postaci po polsku",
  "signature_phrases": ["wyrażenie1", "wyrażenie2", "wyrażenie3", "wyrażenie4"],
  "voice_style": "np. szorstki i konkretny / gadatliwy / ceremonijalny / ostrożny"
}

Jeśli to NIE karta postaci (podręcznik, zasady, przygoda, lore, atlas), zwróć:
{"is_character_sheet": false}

Zwróć TYLKO poprawny JSON bez komentarzy ani markdown."""


def _read_file_text(path: Path, max_chars: int = 5000) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader
            docs = PyPDFLoader(str(path)).load()
            text = "\n\n".join(d.page_content for d in docs[:3])
        elif ext == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader
            docs = Docx2txtLoader(str(path)).load()
            text = "\n\n".join(d.page_content for d in docs)
        else:
            return ""
        return text[:max_chars]
    except Exception as exc:
        print(f"[char_extract] Błąd odczytu {path.name}: {exc}")
        return ""


_DEFAULTS: dict = {
    "name": "Postać",
    "race": "Człowiek",
    "char_class": "Przygodnik",
    "level": 1,
    "stats": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
    "hp": {"current": 10, "max": 10},
    "spells": [],
    "inventory": [],
    "personality": "Zrównoważona postać gotowa na przygodę.",
    "backstory_short": "Historia do odkrycia w trakcie gry.",
    "signature_phrases": ["No to lecimy!", "Ciekawe...", "Zobaczmy co się stanie."],
    "voice_style": "neutralny",
}


def try_extract_character(
    game_files_dir: str = config.GAME_FILES_DIR,
) -> Optional[dict]:
    """Scan game files for a character sheet and extract character data.

    Returns a character dict ready to save as character.json, or None if
    no character sheet is found among the uploaded files.
    """
    game_path = Path(game_files_dir)
    if not game_path.exists():
        return None

    candidates = sorted(
        p for p in game_path.iterdir() if p.suffix.lower() in _SUPPORTED
    )
    if not candidates:
        return None

    llm = ChatOpenAI(
        model=config.CLASSIFIER_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.0,
        timeout=config.OPENAI_TIMEOUT_SEC,
    )

    for file_path in candidates:
        text = _read_file_text(file_path)
        if not text.strip():
            continue

        try:
            resp = llm.invoke([
                SystemMessage(content=_DETECT_SYSTEM),
                HumanMessage(content=f"Plik: {file_path.name}\n\n{text}"),
            ])
            raw = resp.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data: dict = json.loads(raw.strip())
        except Exception as exc:
            print(f"[char_extract] Błąd analizy {file_path.name}: {exc}")
            continue

        if data.get("is_character_sheet"):
            print(f"[char_extract] Karta postaci wykryta: {file_path.name}")
            data.pop("is_character_sheet", None)
            for key, default in _DEFAULTS.items():
                data.setdefault(key, default)
            return data

    return None
