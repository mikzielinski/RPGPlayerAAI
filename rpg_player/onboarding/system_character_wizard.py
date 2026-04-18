"""AI character wizard with system-aware generation from rulebooks."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rpg_player import config

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
_MAX_RULEBOOK_CONTEXT_CHARS = 12000
_MAX_DOC_SNIPPET_CHARS = 2200

_SYSTEM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dnd5e": ("dungeons", "dragon", "d&d", "5e", "armor class", "ability score", "hit points"),
    "pathfinder2e": ("pathfinder", "ancestry", "feat", "class dc", "2e", "golarion"),
    "warhammer": ("warhammer", "d100", "imperium", "chaos", "sigmar", "wfrp"),
    "call_of_cthulhu": ("cthulhu", "sanity", "investigator", "lovecraft", "keeper", "coc"),
    "cyberpunk": ("cyberpunk", "edgerunner", "netrunner", "chrome", "street", "trauma team"),
    "fate": ("fate core", "aspect", "fate point", "stunt", "skill pyramid"),
}

_SYSTEM_TEMPLATES: dict[str, dict[str, Any]] = {
    "dnd5e": {
        "label": "Dungeons & Dragons 5e",
        "core_stats": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
        "mechanics_hint": "Uzyj standardowego zestawu cech D&D 5e i sensownych wartosci HP.",
    },
    "pathfinder2e": {
        "label": "Pathfinder 2e",
        "core_stats": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
        "mechanics_hint": "Uwzglednij ancestry i class feat, oraz poziom 1.",
    },
    "warhammer": {
        "label": "Warhammer Fantasy Roleplay",
        "core_stats": ["WW", "US", "K", "Odp", "Zr", "Int", "SW", "Ogd"],
        "mechanics_hint": "Uzyj stylu statystyk WFRP (d100) i kariery.",
    },
    "call_of_cthulhu": {
        "label": "Call of Cthulhu",
        "core_stats": ["STR", "CON", "POW", "DEX", "APP", "SIZ", "INT", "EDU"],
        "mechanics_hint": "Uwzglednij SAN i klimat badacza, nie bohatera akcji.",
    },
    "cyberpunk": {
        "label": "Cyberpunk",
        "core_stats": ["INT", "REF", "DEX", "TECH", "COOL", "WILL", "LUCK", "BODY", "EMP"],
        "mechanics_hint": "Podaj role i cyberware startowy pasujacy do klimatu.",
    },
    "fate": {
        "label": "Fate Core",
        "core_stats": ["Approach-Careful", "Approach-Clever", "Approach-Flashy"],
        "mechanics_hint": "Uwzglednij aspekty, stunt i stress track.",
    },
    "generic": {
        "label": "Generic RPG",
        "core_stats": ["Power", "Agility", "Mind", "Will"],
        "mechanics_hint": "Jesli brak danych systemowych, zbuduj uniwersalna karte postaci.",
    },
}


def list_supported_systems() -> list[dict[str, Any]]:
    """Return character wizard systems for web dropdown."""
    out = [{"key": "auto", "name": "Auto (wykryj z podrecznika)", "stats_preview": []}]
    for key, data in _SYSTEM_TEMPLATES.items():
        if key == "generic":
            continue
        out.append(
            {
                "key": key,
                "name": data["label"],
                "stats_preview": list(data["core_stats"])[:6],
            }
        )
    return out


def list_rulebooks(game_files_dir: str = config.GAME_FILES_DIR) -> list[dict[str, str]]:
    """Return available rulebooks for the character wizard UI."""
    root = Path(game_files_dir)
    root.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, str]] = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS:
            out.append({"name": path.name, "ext": path.suffix.lower()})
    return out


def detect_game_system(text: str, fallback: str = "generic") -> str:
    """Best-effort keyword detection of a game system."""
    lowered = (text or "").lower()
    for system, keywords in _SYSTEM_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return system
    return fallback


def _load_rulebook_context(paths: list[Path]) -> tuple[str, list[str]]:
    if not paths:
        return "", []
    try:
        from langchain_community.document_loaders import (
            Docx2txtLoader,
            PyPDFLoader,
            UnstructuredExcelLoader,
        )
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(f"Brak zaleznosci do czytania podrecznikow: {exc}") from exc

    snippets: list[str] = []
    used_files: list[str] = []
    total = 0
    for path in paths:
        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            continue
        if ext == ".pdf":
            loader = PyPDFLoader(str(path))
        elif ext == ".docx":
            loader = Docx2txtLoader(str(path))
        else:
            loader = UnstructuredExcelLoader(str(path))

        docs = loader.load()
        text_parts: list[str] = []
        chunk_len = 0
        for doc in docs:
            content = (doc.page_content or "").strip()
            if not content:
                continue
            clipped = content[:_MAX_DOC_SNIPPET_CHARS]
            text_parts.append(clipped)
            chunk_len += len(clipped)
            if chunk_len >= _MAX_DOC_SNIPPET_CHARS:
                break

        snippet = "\n".join(text_parts).strip()
        if not snippet:
            continue
        used_files.append(path.name)
        decorated = f"[RULEBOOK: {path.name}]\n{snippet}\n"
        snippets.append(decorated)
        total += len(decorated)
        if total >= _MAX_RULEBOOK_CONTEXT_CHARS:
            break

    merged = "\n".join(snippets)[:_MAX_RULEBOOK_CONTEXT_CHARS]
    return merged, used_files


def _extract_json(text: str) -> dict[str, Any]:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?", "", payload, flags=re.IGNORECASE).strip()
        payload = re.sub(r"```$", "", payload).strip()
    try:
        return json.loads(payload)
    except Exception:
        match = re.search(r"\{.*\}", payload, flags=re.DOTALL)
        if not match:
            raise ValueError("AI response does not contain valid JSON.")
        return json.loads(match.group(0))


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        split = re.split(r"[,;\n]", value)
        return [item.strip() for item in split if item.strip()]
    return []


def _to_stats(value: Any, defaults: list[str]) -> dict[str, int]:
    stats: dict[str, int] = {}
    if isinstance(value, dict):
        for key, raw in value.items():
            try:
                stats[str(key)] = int(raw)
            except Exception:
                continue
    if not stats:
        stats = {key: 10 for key in defaults}
    return stats


def _normalize_sheet(raw: dict[str, Any], system_key: str, source_rulebooks: list[str]) -> dict[str, Any]:
    template = _SYSTEM_TEMPLATES.get(system_key, _SYSTEM_TEMPLATES["generic"])
    stats_defaults = list(template["core_stats"])

    hp_raw = raw.get("hp", {})
    hp_current = 10
    hp_max = 10
    if isinstance(hp_raw, dict):
        try:
            hp_current = int(hp_raw.get("current", 10))
        except Exception:
            hp_current = 10
        try:
            hp_max = int(hp_raw.get("max", max(hp_current, 10)))
        except Exception:
            hp_max = max(hp_current, 10)

    system_raw = raw.get("system", {})
    system_name = template["label"]
    if isinstance(system_raw, dict):
        system_name = str(system_raw.get("name", system_name)).strip() or system_name

    sheet_sections = []
    if isinstance(system_raw, dict) and isinstance(system_raw.get("sheet_sections"), list):
        for section in system_raw["sheet_sections"]:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title", "")).strip() or "Sekcja"
            fields_in = section.get("fields", [])
            fields_out = []
            if isinstance(fields_in, list):
                for field in fields_in:
                    if not isinstance(field, dict):
                        continue
                    label = str(field.get("label", "")).strip()
                    if not label:
                        continue
                    fields_out.append({"label": label, "value": str(field.get("value", "")).strip()})
            if fields_out:
                sheet_sections.append({"title": title, "fields": fields_out})

    return {
        "name": str(raw.get("name", "Nowa postac")).strip() or "Nowa postac",
        "race": str(raw.get("race", "")).strip(),
        "char_class": str(raw.get("char_class", "")).strip(),
        "level": int(raw.get("level", 1) or 1),
        "stats": _to_stats(raw.get("stats"), stats_defaults),
        "hp": {"current": hp_current, "max": hp_max},
        "spells": _to_str_list(raw.get("spells")),
        "inventory": _to_str_list(raw.get("inventory")),
        "personality": str(raw.get("personality", "")).strip(),
        "backstory_short": str(raw.get("backstory_short", "")).strip(),
        "signature_phrases": _to_str_list(raw.get("signature_phrases")),
        "voice_style": str(raw.get("voice_style", "neutralny")).strip() or "neutralny",
        "system": {
            "key": system_key,
            "name": system_name,
            "source_rulebooks": source_rulebooks,
            "mechanics_hint": template["mechanics_hint"],
            "sheet_sections": sheet_sections,
        },
        "notes": _to_str_list(raw.get("notes")),
    }


def generate_character_sheet(
    *,
    concept_prompt: str,
    preferred_system: str = "auto",
    selected_rulebooks: list[Path] | None = None,
    api_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a system-aware character sheet using AI + rulebook snippets.

    Returns tuple: (character_sheet, metadata).
    """
    selected_rulebooks = selected_rulebooks or []
    rulebook_context, source_rulebooks = _load_rulebook_context(selected_rulebooks)

    detected_system = detect_game_system(
        f"{preferred_system}\n{rulebook_context}\n{' '.join(source_rulebooks)}",
        fallback="generic",
    )
    if preferred_system and preferred_system != "auto":
        detected_system = preferred_system

    template = _SYSTEM_TEMPLATES.get(detected_system, _SYSTEM_TEMPLATES["generic"])
    system_name = template["label"]

    prompt = f"""Stworz ladna i grywalna karte postaci RPG jako JSON.
Jezeli podano kontekst podrecznika, trzymaj sie tych zasad.
System docelowy: {system_name} ({detected_system}).
Wskazowka mechaniczna: {template["mechanics_hint"]}

Koncepcja od MG/gracza:
{concept_prompt or "Brak dodatkowych wskazowek - zaproponuj uniwersalna postac."}

Fragmenty podrecznika (jesli sa):
{rulebook_context or "Brak zaladowanego podrecznika."}

Wymagany format JSON:
{{
  "name": "string",
  "race": "string",
  "char_class": "string",
  "level": 1,
  "stats": {{"KEY": 10}},
  "hp": {{"current": 10, "max": 10}},
  "spells": ["..."],
  "inventory": ["..."],
  "personality": "2-3 zdania po polsku",
  "backstory_short": "1-2 zdania po polsku",
  "signature_phrases": ["4-6 krotkich kwestii po polsku"],
  "voice_style": "opis glosu",
  "system": {{
    "name": "{system_name}",
    "sheet_sections": [
      {{
        "title": "Sekcja",
        "fields": [{{"label": "Pole", "value": "Wartosc"}}]
      }}
    ]
  }},
  "notes": ["wazna notatka", "druga notatka"]
}}

Zasady:
- Zwracaj tylko czysty JSON, bez markdown.
- Karta ma byc estetyczna i gotowa do edycji w panelu WWW.
- Dane maja byc spojne z systemem i koncepcja.
"""

    resolved_api_key = (api_key or config.OPENAI_API_KEY or "").strip()
    if not resolved_api_key:
        raise ValueError("Brak OPENAI_API_KEY do generowania karty postaci.")

    try:
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(f"Brak zaleznosci langchain_openai: {exc}") from exc

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=resolved_api_key,
        temperature=0.8,
        timeout=config.AGENT_TIMEOUT_SEC,
        max_retries=config.AGENT_MAX_RETRIES,
    )
    response = llm.invoke(prompt)
    parsed = _extract_json(getattr(response, "content", str(response)))
    normalized = _normalize_sheet(parsed, detected_system, source_rulebooks)
    metadata = {
        "detected_system": detected_system,
        "system_name": system_name,
        "used_rulebooks": source_rulebooks,
        "rulebook_context_chars": len(rulebook_context),
    }
    return normalized, metadata
