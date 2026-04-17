"""Behavior that shapes how the bot handles rules uncertainty before RAG lookups."""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext

_RULE_KEYWORDS = [
    "zasad", "mechani", "jak działa", "czy mogę", "modyfikator",
    "premia", "kara", "zaklęcie", "zdolność", "umiejętność", "test",
    "trudność", "dc", "saving throw", "rzut obronny", "check",
]


class RulesUncertaintyBehavior(Behavior):
    """Before checking rules, have the character express doubt in-voice first."""

    name = "rules_uncertainty"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.buffer_text.lower()
        return any(k in text for k in _RULE_KEYWORDS)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        reaction = ctx.personality.get("mistake_reaction", "przyznam otwarcie")
        return (
            f"Rozmowa dotyczy zasad lub mechanik. Twój styl wobec niepewności: {reaction}. "
            "Zanim użyjesz narzędzia lookup_rules — powiedz jako postać że coś próbujesz sobie przypomnieć. "
            "Nigdy nie udawaj że jesteś pewien zasad których nie znasz. "
            "Dopuszczalne zwroty: 'Chyba tak to działa, ale sprawdźmy', 'Nie jestem pewien — DM?', "
            "'Pamiętam że coś o tym było w podręczniku...'."
        )
