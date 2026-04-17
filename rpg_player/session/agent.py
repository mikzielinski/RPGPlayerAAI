"""LangChain agent — two-layer (player + character) RPG AI agent."""
from __future__ import annotations

import asyncio
import random
import re
from typing import Optional

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from rpg_player import config
from rpg_player.session import rag as rag_module

_SYSTEM_TEMPLATE = """=== WARSTWA GRACZA ===
Jesteś graczem przy stole RPG. Twój styl bycia przy stole:
- Archetyp: {table_archetype}
- Jak często mówisz: {talk_frequency}
- Gdy się mylisz: {mistake_reaction}
- Wobec innych graczy: {group_relation}
- Poziom humoru: {humor_level}
- Nigdy nie rób: {forbidden_behaviors}

Mów po polsku. Zawsze. Zarówno jako gracz jak i jako postać.
Reaguj naturalnie na sytuacje przy stole — na rzuty kośćmi, zwroty fabularne, decyzje grupy.
Odpowiedzi krótkie (1–3 zdania) chyba że sytuacja wymaga więcej.

=== WARSTWA POSTACI ===
Jesteś {char_name}, {char_race} {char_class}.
Osobowość: {char_personality}
Skrót historii: {backstory_short}
Styl mówienia: {voice_style}
Charakterystyczne zwroty (używaj naturalnie, nie w każdej turze): {signature_phrases}

Wiesz TYLKO to co zostało powiedziane głośno przy tym stole.
Nie znasz planów MG ani sekretów innych postaci.
Gdy nie jesteś pewien zasad lub wiedzy o świecie — powiedz to w postaci zanim cokolwiek sprawdzisz.
Nigdy nie wychodź z postaci. Nigdy nie mów "jako AI...".

Tryb wyzwolenia: {trigger_mode}
- MY_TURN: odpowiedz bezpośrednio, zostałeś wywołany
- SPEAK_UP: wejdź naturalnie — zacznij od "Czekaj—", "Właściwie...", "Hej, a co jeśli..." albo wskocz w połowie myśli"""


def _build_system_prompt(
    personality: dict,
    character: dict,
    trigger_mode: str,
) -> str:
    return _SYSTEM_TEMPLATE.format(
        table_archetype=personality.get("table_archetype", "neutralny"),
        talk_frequency=personality.get("talk_frequency", "umiarkowanie"),
        mistake_reaction=personality.get("mistake_reaction", "przyznam otwarcie"),
        group_relation=personality.get("group_relation", "współpracuję"),
        humor_level=personality.get("humor_level", "ciepły"),
        forbidden_behaviors=", ".join(personality.get("forbidden_behaviors", [])),
        char_name=character.get("name", "Postać"),
        char_race=character.get("race", ""),
        char_class=character.get("char_class", ""),
        char_personality=character.get("personality", ""),
        backstory_short=character.get("backstory_short", ""),
        voice_style=character.get("voice_style", "neutralny"),
        signature_phrases=", ".join(character.get("signature_phrases", [])),
        trigger_mode=trigger_mode,
    )


def _parse_dice(notation: str) -> tuple[int, int, int]:
    """Parse NdM+K notation into (num, sides, modifier)."""
    notation = notation.strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", notation)
    if not match:
        raise ValueError(f"Nieprawidłowa notacja kości: {notation}")
    num = int(match.group(1))
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)
    return num, sides, modifier


def build_agent(
    personality: dict,
    character: dict,
    vectorstore,
    tts,
    trigger_mode: str,
) -> AgentExecutor:
    """Construct and return an AgentExecutor for the current turn."""

    char_class = character.get("char_class", "postać")
    char_name = character.get("name", "Postać")

    # ----- Tool definitions (closures capture char/vectorstore context) -----

    @tool
    def roll_dice(notation: str) -> str:
        """Rzuć kośćmi używając notacji RPG (np. '2d6+3', '1d20').
        Zwraca wynik tak jak postać by go opisała."""
        import random as _r

        try:
            num, sides, modifier = _parse_dice(notation)
            rolls = [_r.randint(1, sides) for _ in range(num)]
            total = sum(rolls) + modifier
            rolls_str = "+".join(str(r) for r in rolls)
            mod_str = f"{modifier:+d}" if modifier != 0 else ""
            return f"[{rolls_str}]{mod_str} = {total}"
        except ValueError as e:
            return str(e)

    @tool
    def check_character_sheet(field: str) -> str:
        """Sprawdź własną kartę postaci: statystyki, ekwipunek, zaklęcia.
        Nie można sprawdzać kart innych postaci."""
        field_lower = field.lower()
        mapping = {
            "stats": character.get("stats", {}),
            "statystyki": character.get("stats", {}),
            "hp": character.get("hp", {}),
            "zdrowie": character.get("hp", {}),
            "spells": character.get("spells", []),
            "zaklęcia": character.get("spells", []),
            "inventory": character.get("inventory", []),
            "ekwipunek": character.get("inventory", []),
            "name": character.get("name", ""),
            "imię": character.get("name", ""),
            "class": character.get("char_class", ""),
            "klasa": character.get("char_class", ""),
            "race": character.get("race", ""),
            "rasa": character.get("race", ""),
            "level": character.get("level", 1),
            "poziom": character.get("level", 1),
        }
        value = mapping.get(field_lower)
        if value is None:
            return f"Nie mam takiego pola w karcie: {field}"
        return str(value)

    @tool
    def lookup_rules(query: str) -> str:
        """Wyszukaj zasady lub informacje o świecie w załadowanych dokumentach gry.
        Używaj tylko dla konkretnych zasad, zaklęć lub informacji o świecie — nie dla ogólnej wiedzy."""
        if vectorstore is None:
            phrase = random.choice(rag_module.TIMEOUT_PHRASES_PL)
            return phrase

        # Run async RAG lookup in sync context
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                rag_module.human_lookup(query, vectorstore, tts, char_class)
            )
        finally:
            loop.close()

        return result or random.choice(rag_module.TIMEOUT_PHRASES_PL)

    # ----- Build agent -----

    system_prompt = _build_system_prompt(personality, character, trigger_mode)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.85,
    )

    tools = [roll_dice, check_character_sheet, lookup_rules]
    agent = create_openai_tools_agent(llm, tools, prompt)

    return AgentExecutor(agent=agent, tools=tools, verbose=False)


def run_agent(
    personality: dict,
    character: dict,
    vectorstore,
    tts,
    trigger_mode: str,
    buffer_text: str,
) -> str:
    """Build agent for this turn, invoke with buffer context, return response text."""
    executor = build_agent(personality, character, vectorstore, tts, trigger_mode)
    result = executor.invoke({
        "input": buffer_text,
        "chat_history": [],
    })
    return result.get("output", "")
