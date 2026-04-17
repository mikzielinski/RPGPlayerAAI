"""Behaviors triggered by dice roll events mentioned in the buffer."""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext

_CRIT_HIT = [
    "natural 20", "nat 20", "20 na d20", "critical hit",
    "trafienie krytyczne", "krytyczne trafienie", "krytyk", "perfekcyjny rzut",
]
_CRIT_FAIL = [
    "natural 1", "nat 1", "1 na d20", "fumble",
    "krytyczny błąd", "krytyczna porażka", "krytyczna jedynka",
]
_GOOD_ROLL = [
    "dobry rzut", "świetny rzut", "nieźle", "to dobry wynik",
    "udało się", "udało mu się", "wysoki wynik",
]


class CriticalHitBehavior(Behavior):
    """React to a critical hit with short, genuine player excitement."""

    name = "dice_crit_hit"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.last_utterance.lower()
        return any(k in text for k in _CRIT_HIT)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        humor = ctx.personality.get("humor_level", "ciepły")
        if humor == "absurdalny":
            return (
                "Właśnie padło trafienie krytyczne! Zareaguj entuzjastycznie i absurdalnie — "
                "jeden spontaniczny okrzyk jako gracz zanim odpiszesz jako postać."
            )
        return (
            "Właśnie padło trafienie krytyczne. Zareaguj krótko i spontanicznie jako gracz — "
            "jeden okrzyk lub ciepły komentarz, np. 'No tak! Tego się spodziewałem.' "
            "Potem możesz zabrać głos jako postać."
        )


class CriticalFailBehavior(Behavior):
    """React to a critical fail — sympathy or light ribbing based on humor level."""

    name = "dice_crit_fail"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.last_utterance.lower()
        return any(k in text for k in _CRIT_FAIL)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        humor = ctx.personality.get("humor_level", "ciepły")
        if humor in ("suchy", "absurdalny"):
            return (
                "Właśnie padła jedynka (krytyczna porażka). "
                "Skomentuj sucho lub absurdalnie jako gracz — jeden komentarz, potem postać."
            )
        return (
            "Właśnie padła jedynka. Zareaguj z lekką sarkazmem lub współczuciem — "
            "jedno zdanie jako gracz, np. 'Klasycznie. Właśnie tego się spodziewałem.'"
        )


class GoodRollBehavior(Behavior):
    """Acknowledge a notably good roll from another player."""

    name = "dice_good_roll"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.last_utterance.lower()
        return any(k in text for k in _GOOD_ROLL)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return (
            "Ktoś właśnie dobrze rzucił. Możesz go krótko docenić jako gracz — "
            "jedno zdanie, nie przesadzaj. Np. 'Nieźle. Zasłużone.'"
        )
