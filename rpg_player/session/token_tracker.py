"""Track OpenAI token usage per session and warn when approaching limits."""
from __future__ import annotations

from rpg_player import config


class TokenTracker:
    def __init__(self) -> None:
        self._prompt = 0
        self._completion = 0
        self._warn_fired = False
        self._critical_fired = False

    def add(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self._prompt += prompt_tokens
        self._completion += completion_tokens

    @property
    def total(self) -> int:
        return self._prompt + self._completion

    @property
    def prompt(self) -> int:
        return self._prompt

    @property
    def completion(self) -> int:
        return self._completion

    def check_warn(self) -> str | None:
        """Return a Polish spoken warning if a threshold is newly crossed, else None."""
        if not self._critical_fired and self.total >= config.TOKEN_CRITICAL_AT:
            self._critical_fired = True
            return (
                "Hej — muszę powiedzieć, naprawdę dużo się dziś mówiło "
                "i zaczyna mi brakować miejsca w głowie. "
                "Może podsumujemy kluczowe fakty zanim zapomnę?"
            )
        if not self._warn_fired and self.total >= config.TOKEN_WARN_AT:
            self._warn_fired = True
            return (
                "Tak przy okazji — sesja jest już dość długa i zaczynam tracić wątek "
                "z początku. Dajcie mi znać jeśli coś ważnego pominę."
            )
        return None

    def summary(self) -> str:
        k = self.total / 1000
        return f"{k:.1f}k tokenów (↑{self._prompt // 1000}k / ↓{self._completion // 1000}k)"
