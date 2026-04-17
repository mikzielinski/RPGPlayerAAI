"""Fast LLM interrupt classifier — returns WAIT / MY_TURN / SPEAK_UP."""
from __future__ import annotations

from openai import OpenAI

from rpg_player import config

_SYSTEM_TEMPLATE = """Jesteś klasyfikatorem decydującym, czy {char_name} powinien zabrać głos przy stole RPG.

Opis postaci: {char_summary}

Kontekst stołu (ostatnie wypowiedzi):
{buffer_text}

Zwróć TYLKO jedno słowo — bez wyjaśnień, bez interpunkcji:
- WAIT      — nic istotnego do dodania, inni są w trakcie rozmowy
- MY_TURN   — MG lub gracz zwrócił się bezpośrednio do {char_name} z imienia, lub zapytał o jego akcję
- SPEAK_UP  — {char_name} ma coś naprawdę wartościowego lub zgodnego z postacią do powiedzenia TERAZ

Zasady SPEAK_UP (bądź konserwatywny — prawdziwy gracz nie wchodzi w słowo co 20 sekund):
- Postać ma konkretną umiejętność, zaklęcie lub przedmiot bezpośrednio powiązany z tym co omawiają
- Grupa utknęła w debacie a postać ma wyraźną opinię zgodną z postacią
- Historia postaci sprawia że zauważyła coś czego inni nie wspomnieli
- Minęło ponad 30 sekund ciszy po pytaniu MG bez odpowiedzi gracza
- Postać naturalnie zareagowałaby emocjonalnie na to co właśnie padło

Gdy nie jesteś pewien, zwróć WAIT."""


class Classifier:
    def __init__(self, char_name: str, char_summary: str):
        self._char_name = char_name
        self._char_summary = char_summary
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)

    def classify(self, buffer_text: str) -> str:
        """Return 'WAIT', 'MY_TURN', or 'SPEAK_UP'."""
        if not buffer_text.strip():
            return "WAIT"

        system_prompt = _SYSTEM_TEMPLATE.format(
            char_name=self._char_name,
            char_summary=self._char_summary,
            buffer_text=buffer_text,
        )

        response = self._client.chat.completions.create(
            model=config.CLASSIFIER_MODEL,
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=5,
            temperature=0,
        )

        decision = response.choices[0].message.content.strip().upper()
        if decision not in ("WAIT", "MY_TURN", "SPEAK_UP"):
            return "WAIT"
        return decision
