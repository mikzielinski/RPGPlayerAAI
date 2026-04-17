"""Voice-driven personality creation — all speech in Polish."""
from __future__ import annotations

import json
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from rpg_player import config
from rpg_player.tts.speaker import Speaker


class PlayerPersonality(BaseModel):
    table_archetype: str
    mistake_reaction: str
    group_relation: str
    talk_frequency: str
    humor_level: str
    extra_traits: list[str]
    forbidden_behaviors: list[str]
    language: str = "pl"


_QUESTIONS = [
    "Jaki typ gracza mam być? Na przykład: entuzjasta który ma dużo pomysłów, "
    "taktyk który mówi rzadko ale celnie, roleplayer który mocno wchodzi w postać — "
    "albo powiedz mi sam jak to widzisz.",
    "Jak często mam się odzywać? Czy mogę wchodzić w słowo, "
    "czy lepiej żebym czekał na swoją kolej?",
    "Gdy się mylę albo czegoś nie wiem — mam to przyznać wprost, "
    "spekulować głośno, żartować z siebie, czy coś innego?",
    "Jak mam się odnosić do innych graczy? Kibicować, rywalizować, "
    "mediować gdy jest kłótnia, a może coś innego?",
    "Jaki poziom humoru przy stole? Suchy, ciepły, absurdalny, "
    "a może zero żartów bo klimat jest poważny?",
    "Jest coś czego mam absolutnie nie robić przy stole? "
    "Jakieś zachowania które wam przeszkadzają?",
]

_SYSTEM_PROMPT = """Jesteś asystentem tworzącym profil osobowości gracza RPG.
Na podstawie odpowiedzi na poniższe pytania wygeneruj JSON pasujący do schematu.

Schemat JSON:
{{
  "table_archetype": "opis archetypu gracza",
  "mistake_reaction": "jak reaguje gdy się myli lub czegoś nie wie",
  "group_relation": "jak odnosi się do innych graczy",
  "talk_frequency": "często / umiarkowanie / rzadko ale trafnie",
  "humor_level": "suchy / ciepły / absurdalny / brak",
  "extra_traits": ["lista dodatkowych cech"],
  "forbidden_behaviors": ["lista zakazanych zachowań"],
  "language": "pl"
}}

Odpowiedzi graczy:
{answers}

Zwróć TYLKO poprawny JSON, bez żadnego komentarza."""


def _listen_once(stt) -> str:
    """Capture a single utterance via STT."""
    return stt.listen_once()


def create_personality(tts: Speaker, stt, save_path: str = config.PERSONALITY_FILE) -> dict:
    """Run personality onboarding conversation and save result."""

    tts.speak(
        "Hej! Zanim zaczniemy — chcę wiedzieć jak mam się przy stole zachowywać. "
        "Mogę zadać kilka pytań?"
    )

    answers: list[str] = []
    for question in _QUESTIONS:
        tts.speak(question)
        answer = _listen_once(stt)
        answers.append(f"P: {question}\nO: {answer}")

    answers_text = "\n\n".join(answers)

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.7,
    )
    parser = JsonOutputParser(pydantic_object=PlayerPersonality)
    prompt = ChatPromptTemplate.from_template(_SYSTEM_PROMPT)
    chain = prompt | llm | parser

    personality: dict = chain.invoke({"answers": answers_text})

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(personality, f, ensure_ascii=False, indent=2)

    tts.speak(
        "Dobra, rozumiem. Będę się starał grać tak jak lubicie. "
        "Zaczynamy tworzenie postaci?"
    )

    return personality
