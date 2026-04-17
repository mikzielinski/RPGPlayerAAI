"""Behavior for breaking silence when the DM has asked and no one answered."""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext

_DM_PROMPT_KEYWORDS = [
    "co robisz", "co robicie", "wasza kolej", "twoja kolej",
    "co zamierzasz", "co postanawiacie", "czekam na waszą decyzję",
    "co chcecie zrobić", "jaka jest wasza akcja", "co dalej",
]


class SilenceFillerBehavior(Behavior):
    """Step in when the DM asked a question and no player has responded."""

    name = "silence_filler"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        if ctx.trigger_mode != "SPEAK_UP":
            return False
        last = ctx.last_utterance.strip().lower()
        return last.endswith("?") or any(k in last for k in _DM_PROMPT_KEYWORDS)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return (
            "MG zadał pytanie i nikt nie odpowiedział — wejdź naturalnie i przerwij ciszę. "
            "Możesz zacząć od 'Dobra, to ja...' lub 'Skoro nikt...' albo po prostu zadeklaruj akcję postaci. "
            "Nie czekaj na zaproszenie."
        )
