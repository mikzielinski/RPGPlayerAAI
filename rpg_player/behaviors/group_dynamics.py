"""Behavior for contributing to group debates and planning discussions."""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext

_DEBATE_KEYWORDS = [
    "co robimy", "jaki plan", "jak to zrobimy", "proponuję", "może powinniśmy",
    "a co jeśli", "co myślisz", "wasza opinia", "co robimy dalej",
    "zagłosujmy", "decydujemy", "co zamierzacie", "jaka decyzja",
    "plan na", "taktyka", "strategia",
]


class GroupDebateBehavior(Behavior):
    """Offer one concise player-layer opinion when the group is planning or stuck."""

    name = "group_debate"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.buffer_text[-600:].lower()
        return any(k in text for k in _DEBATE_KEYWORDS)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        archetype = ctx.personality.get("table_archetype", "neutralny")
        relation = ctx.personality.get("group_relation", "współpracuję")
        return (
            f"Grupa dyskutuje lub planuje. Twój archetyp gracza: {archetype}, "
            f"stosunek do grupy: {relation}. "
            "Wnieś JEDNĄ konkretną opinię jako gracz (nie jako postać), potem ustąp miejsca. "
            "Użyj zwrotów jak: 'Wydaje mi się że...', 'A co jeśli...', 'Nie wiem, ryzykujemy?'. "
            "Nie dominuj dyskusji — jeden pomysł, potem słuchaj."
        )
