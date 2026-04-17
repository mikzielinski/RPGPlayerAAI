"""Base types for the behavior system."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BehaviorContext:
    buffer: list[dict]    # [{speaker, text}, ...]
    buffer_text: str      # full formatted string
    last_utterance: str   # text of the most recent entry
    character: dict
    personality: dict
    trigger_mode: str     # "MY_TURN" | "SPEAK_UP"


class Behavior(ABC):
    name: str = "unnamed"

    @abstractmethod
    def should_trigger(self, ctx: BehaviorContext) -> bool:
        """Return True when this behavior applies to the current moment."""
        ...

    @abstractmethod
    def get_instruction(self, ctx: BehaviorContext) -> str:
        """Return extra instruction text to inject into the agent system prompt."""
        ...
