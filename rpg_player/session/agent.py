"""LangChain agent — two-layer (player + character) RPG AI agent.

Uses bind_tools + manual tool-calling loop instead of AgentExecutor so it
works with any LangChain 0.2/0.3+ version without breaking on internal moves.

Token usage is extracted from response.response_metadata and forwarded to
an optional TokenTracker so the main loop can warn the user.
"""
from __future__ import annotations

import asyncio
import random
import re
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from rpg_player import config
from rpg_player.session import rag as rag_module

_MAX_TOOL_ROUNDS = 5

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
    session_context: str = "",
    known_players: Optional[list[str]] = None,
) -> str:
    base = _SYSTEM_TEMPLATE.format(
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
    if known_players:
        base += f"\n\nGracze przy stole (znane imiona): {', '.join(known_players)}"
    if session_context:
        base += "\n\n" + session_context
    return base


def _parse_dice(notation: str) -> tuple[int, int, int]:
    notation = notation.strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", notation)
    if not match:
        raise ValueError(f"Nieprawidłowa notacja kości: {notation}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _make_tools(character: dict, vectorstore, tts):
    """Build tool callables closed over current session context."""
    char_class = character.get("char_class", "postać")

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
            mod_str = f"{modifier:+d}" if modifier else ""
            return f"[{rolls_str}]{mod_str} = {total}"
        except ValueError as e:
            return str(e)

    @tool
    def check_character_sheet(field: str) -> str:
        """Sprawdź własną kartę postaci: statystyki, ekwipunek, zaklęcia.
        Nie można sprawdzać kart innych postaci."""
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
        value = mapping.get(field.lower())
        return str(value) if value is not None else f"Nie mam takiego pola w karcie: {field}"

    @tool
    def lookup_rules(query: str) -> str:
        """Wyszukaj zasady lub informacje o świecie w załadowanych dokumentach gry.
        Używaj tylko dla konkretnych zasad, zaklęć lub lore — nie dla ogólnej wiedzy."""
        if vectorstore is None:
            return random.choice(rag_module.TIMEOUT_PHRASES_PL)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                rag_module.human_lookup(query, vectorstore, tts, char_class)
            )
        finally:
            loop.close()
        return result or random.choice(rag_module.TIMEOUT_PHRASES_PL)

    return [roll_dice, check_character_sheet, lookup_rules]


def _track_tokens(response: AIMessage, token_tracker) -> None:
    """Extract token usage from response metadata and add to tracker."""
    if token_tracker is None:
        return
    try:
        usage = (getattr(response, "response_metadata", None) or {}).get("token_usage", {})
        token_tracker.add(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )
    except Exception:
        pass


def run_agent(
    personality: dict,
    character: dict,
    vectorstore,
    tts,
    trigger_mode: str,
    buffer_text: str,
    behavior_instructions: str = "",
    session_context: str = "",
    known_players: Optional[list[str]] = None,
    token_tracker=None,
) -> str:
    """Invoke the two-layer agent and return its response text."""
    system_prompt = _build_system_prompt(
        personality, character, trigger_mode,
        session_context=session_context,
        known_players=known_players,
    )
    if behavior_instructions:
        system_prompt += "\n" + behavior_instructions

    tools = _make_tools(character, vectorstore, tts)
    tool_map = {t.name: t for t in tools}

    llm = ChatOpenAI(
        model=config.AGENT_MODEL,
        openai_api_key=config.OPENAI_API_KEY,
        temperature=0.85,
        timeout=config.OPENAI_TIMEOUT_SEC,
        max_retries=config.OPENAI_MAX_RETRIES,
    )
    llm_with_tools = llm.bind_tools(tools)

    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=buffer_text),
    ]

    for _ in range(_MAX_TOOL_ROUNDS):
        try:
            response: AIMessage = llm_with_tools.invoke(messages)
        except Exception:
            # Return a short fallback instead of hanging the whole turn.
            return "Chwileczke, chyba mam opoznienie polaczenia. Jedziemy dalej."
        messages.append(response)
        _track_tokens(response, token_tracker)

        if not getattr(response, "tool_calls", None):
            return response.content or ""

        # Execute each requested tool and feed results back
        for call in response.tool_calls:
            name = call["name"]
            args = call["args"]
            try:
                result = tool_map[name].invoke(args) if name in tool_map else f"Nieznane narzędzie: {name}"
            except Exception as exc:
                result = f"Błąd narzędzia {name}: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    # Fallback if max rounds hit
    messages.append(HumanMessage(content="Odpowiedz teraz jako postać, bez użycia narzędzi."))
    try:
        final: AIMessage = llm.invoke(messages)
    except Exception:
        return "Nie zdazylem tego dopracowac, ale jestem dalej z wami."
    _track_tokens(final, token_tracker)
    return final.content or ""
