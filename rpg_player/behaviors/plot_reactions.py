"""Behaviors triggered by story-level events: plot twists and emotional scenes."""
from __future__ import annotations

from rpg_player.behaviors.base import Behavior, BehaviorContext

_TWIST_KEYWORDS = [
    "nie spodziewałem", "to był zdrajca", "okazuje się", "w rzeczywistości",
    "plot twist", "zdrada", "ukryta tożsamość", "naprawdę był", "to był on",
    "tak naprawdę", "zdradzili nas", "szokujące", "nie do wiary",
    "zdrajca", "zdemaskował", "ujawnił się",
]
_EMOTIONAL_KEYWORDS = [
    "umiera", "śmierć postaci", "pożegnanie", "ofiara", "ostatnie słowa",
    "płacze", "zginął", "zginęła", "zginęli", "poświęcił", "poświęciła",
    "ostatni oddech", "kona", "odchodzi",
]


class PlotTwistBehavior(Behavior):
    """React naturally as a player to a sudden story revelation."""

    name = "plot_twist"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        text = ctx.last_utterance.lower()
        return any(k in text for k in _TWIST_KEYWORDS)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return (
            "Właśnie nastąpił zwrot fabularny lub zaskakujące odkrycie. "
            "Zareaguj naturalnie jako gracz — zdziwienie, podekscytowanie, niedowierzanie. "
            "Jedno lub dwa zdania, np. 'Czekaj — to znaczy że...?' lub 'Nie spodziewałem się tego.'"
        )


class EmotionalSceneBehavior(Behavior):
    """Stay quiet or react with restraint during emotionally heavy scenes."""

    name = "emotional_scene"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        humor = ctx.personality.get("humor_level", "ciepły")
        if humor == "absurdalny":
            return False
        text = ctx.last_utterance.lower()
        return any(k in text for k in _EMOTIONAL_KEYWORDS)

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return (
            "Trwa emocjonalna lub dramatyczna scena. NIE żartuj. "
            "Cisza jest równie ważną odpowiedzią. Jeśli reagujesz, rób to krótko i z szacunkiem — "
            "jeden krótki komentarz jako gracz albo milczenie jako postać."
        )
