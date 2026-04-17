"""Voice-driven character creation — shaped by personality, all speech in Polish."""
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


_QUESTIONS = [
    "Jaki rodzaj gry dzisiaj gramy — fantasy, sci-fi, horror, coś innego?",
    "Mam jakąś konkretną klasę lub rasę, czy mogę was zaskoczyć?",
    "Klimat sprawdzający: mroczny i brutalny, czy lekki i heroiczny?",
    "Jakieś cechy osobowości? Sarkazm? Szlachetność? Tchórzostwo?",
    "Jak ma mieć na imię moja postać, czy sam wybieram?",
]

_SYSTEM_PROMPT = """Jesteś asystentem tworzącym kartę postaci RPG.
Na podstawie odpowiedzi graczy oraz stylu osobowości gracza, stwórz JSON karty postaci.

Styl osobowości gracza (użyj go do kształtowania voice_style i personality postaci):
{personality_summary}

Odpowiedzi graczy na pytania dotyczące postaci:
{answers}

Schemat JSON który musisz zwrócić:
{{
  "name": "imię postaci",
  "race": "rasa",
  "char_class": "klasa",
  "level": 1,
  "stats": {{"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}},
  "hp": {{"current": 10, "max": 10}},
  "spells": [],
  "inventory": ["podstawowy ekwipunek pasujący do klasy"],
  "personality": "2-3 zdania opisujące zachowanie tej postaci",
  "backstory_short": "1-2 zdania historii",
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


def create_character(
    tts: Speaker,
    stt,
    personality: Optional[dict] = None,
    save_path: str = config.CHARACTER_FILE,
) -> dict:
    """Run character creation conversation and save result."""

    tts.speak(
        "Hej wszyscy! Dołączam do waszej sesji, ale nie mam jeszcze postaci. "
        "Mogę zadać kilka krótkich pytań żeby ją stworzyć?"
    )

    answers: list[str] = []
    for question in _QUESTIONS:
        tts.speak(question)
        answer = stt.listen_once()
        answers.append(f"P: {question}\nO: {answer}")

    answers_text = "\n\n".join(answers)
    personality_summary = _personality_summary(personality)

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.8,
    )
    parser = JsonOutputParser(pydantic_object=CharacterSheet)
    prompt = ChatPromptTemplate.from_template(_SYSTEM_PROMPT)
    chain = prompt | llm | parser

    character: dict = chain.invoke(
        {"answers": answers_text, "personality_summary": personality_summary}
    )

    # Speak intro in character voice
    name = character.get("name", "Postać")
    race = character.get("race", "")
    char_class = character.get("char_class", "")
    backstory = character.get("backstory_short", "")
    intro = f"W porządku. Jestem {name}, {race} {char_class}. {backstory} Zaczynamy?"
    tts.speak(intro)

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(character, f, ensure_ascii=False, indent=2)

    return character
