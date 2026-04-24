"""Voice-driven character creation — shaped by personality and detected game universe."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from rpg_player import config
from rpg_player.tts.speaker import Speaker


class CharacterSheet(BaseModel):
    name: str
    race: str
    char_class: str
    level: int
    stats: dict[str, int]
    hp: dict[str, int]
    spells: list[str]
    inventory: list[str]
    personality: str
    backstory_short: str
    signature_phrases: list[str]
    voice_style: str


# Used when game system is already known from uploaded PDFs
_QUESTIONS_SYSTEM_KNOWN = [
    "Mam jakąś konkretną klasę lub rasę, czy mogę was zaskoczyć?",
    "Klimat sprawdzający: mroczny i brutalny, czy lekki i heroiczny?",
    "Jakieś cechy osobowości? Sarkazm? Szlachetność? Tchórzostwo?",
    "Jak ma mieć na imię moja postać, czy sam wybieram?",
]

# Used when no game files were uploaded
_QUESTIONS_SYSTEM_UNKNOWN = [
    "Jaki rodzaj gry dzisiaj gramy — fantasy, sci-fi, horror, coś innego?",
    *_QUESTIONS_SYSTEM_KNOWN,
]

_SYSTEM_PROMPT = """Jesteś asystentem tworzącym kartę postaci RPG.
Na podstawie odpowiedzi graczy oraz stylu osobowości gracza, stwórz JSON karty postaci.

{game_system_block}

Styl osobowości gracza (użyj go do kształtowania voice_style i personality postaci):
{personality_summary}

Odpowiedzi graczy na pytania dotyczące postaci:
{answers}

Schemat JSON który musisz zwrócić.
WAŻNE: użyj nazw statystyk właściwych dla systemu (np. STR/DEX/CON/INT/WIS/CHA dla D&D;
inne atrybuty dla innych systemów). Dopasuj ekwipunek, umiejętności i backstory do świata gry.
{{
  "name": "imię postaci",
  "race": "rasa lub gatunek pasujący do świata gry",
  "char_class": "klasa, kariera lub archetyp pasujący do systemu",
  "level": 1,
  "stats": {{"NazwaStatystyki": wartość, ...}},
  "hp": {{"current": 10, "max": 10}},
  "spells": [],
  "inventory": ["ekwipunek pasujący do klasy i świata gry"],
  "personality": "2-3 zdania opisujące zachowanie tej postaci",
  "backstory_short": "1-2 zdania historii pasującej do świata gry",
  "signature_phrases": ["4-6 wyrażeń charakterystycznych dla tej postaci po polsku"],
  "voice_style": "np. szorstki i konkretny / gadatliwy gawędziarz / nerwowy i niepewny"
}}

Zwróć TYLKO poprawny JSON, bez żadnego komentarza."""


def _personality_summary(personality: Optional[dict]) -> str:
    if not personality:
        return "Brak danych — graj neutralnie."
    return (
        f"Archetyp: {personality.get('table_archetype', 'nieznany')}, "
        f"humor: {personality.get('humor_level', 'umiarkowany')}, "
        f"częstotliwość mówienia: {personality.get('talk_frequency', 'umiarkowanie')}."
    )


def _game_system_block(game_type: Optional[dict]) -> str:
    if not game_type:
        return ""
    system = game_type.get("system", "").strip()
    if not system or system == "Nieznany system":
        return ""
    lines = [
        "System RPG — dostosuj postać ŚCIŚLE do tego systemu (rasa, klasa, statystyki, ekwipunek, styl mówienia):",
        f"- System: {system}",
        f"- Gatunek: {game_type.get('genre', 'fantasy')}",
        f"- Nastrój: {game_type.get('tone', 'epic')}",
        f"- Świat: {game_type.get('setting', '')}",
    ]
    kw = game_type.get("universe_keywords", [])
    if kw:
        lines.append(f"- Słowa kluczowe świata: {', '.join(kw[:10])}")
    intro = game_type.get("campaign_intro", "").strip()
    if intro:
        lines.append(f"- Intro kampanii: {intro}")
    return "\n".join(lines)


def create_character(
    tts: Speaker,
    stt,
    personality: Optional[dict] = None,
    game_type: Optional[dict] = None,
    save_path: str = config.CHARACTER_FILE,
) -> dict:
    """Run character creation conversation and save result."""
    system = (game_type or {}).get("system", "").strip()
    system_known = bool(system and system != "Nieznany system")

    if system_known:
        tts.speak(
            f"Hej! Gram z wami w {system}. "
            "Tylko kilka pytań i razem stworzymy moją postać — gotowi?"
        )
        questions = _QUESTIONS_SYSTEM_KNOWN
    else:
        tts.speak(
            "Hej wszyscy! Dołączam do waszej sesji, ale nie mam jeszcze postaci. "
            "Mogę zadać kilka krótkich pytań żeby ją stworzyć?"
        )
        questions = _QUESTIONS_SYSTEM_UNKNOWN

    answers: list[str] = []
    for question in questions:
        tts.speak(question)
        answer = stt.listen_once()
        answers.append(f"P: {question}\nO: {answer}")

    answers_text = "\n\n".join(answers)
    personality_summary = _personality_summary(personality)
    game_sys_block = _game_system_block(game_type)

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.8,
    )
    parser = JsonOutputParser(pydantic_object=CharacterSheet)
    prompt = ChatPromptTemplate.from_template(_SYSTEM_PROMPT)
    chain = prompt | llm | parser

    character: dict = chain.invoke({
        "answers": answers_text,
        "personality_summary": personality_summary,
        "game_system_block": game_sys_block,
    })

    name = character.get("name", "Postać")
    race = character.get("race", "")
    char_class = character.get("char_class", "")
    backstory = character.get("backstory_short", "")
    tts.speak(f"W porządku. Jestem {name}, {race} {char_class}. {backstory} Zaczynamy?")

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(character, f, ensure_ascii=False, indent=2)

    return character
