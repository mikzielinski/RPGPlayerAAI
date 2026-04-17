"""Fast LLM interrupt classifier — returns WAIT / MY_TURN / SPEAK_UP."""
from __future__ import annotations

from openai import OpenAI

from rpg_player import config

_SYSTEM_TEMPLATE = """Jesteś klasyfikatorem decydującym, czy {char_name} powinien zabrać głos przy stole RPG.

{char_name} jest graczem AI — często jedynym lub jednym z nielicznych graczy przy stole.

Opis postaci: {char_summary}

Kontekst stołu (ostatnie wypowiedzi):
{buffer_text}

Zwróć TYLKO jedno słowo — bez wyjaśnień, bez interpunkcji:
- WAIT      — nic do dodania, inni są w trakcie rozmowy lub MG jeszcze nie skończył
- MY_TURN   — {char_name} powinien teraz odpowiedzieć (patrz zasady poniżej)
- SPEAK_UP  — {char_name} ma coś wartościowego do dodania, ale nie jest bezpośrednio wezwany

Zasady MY_TURN — wystarczy JEDEN z poniższych warunków:
✓ Imię "{char_name}" padło w ostatniej wypowiedzi
✓ MG pyta o akcję w liczbie pojedynczej: "Co robisz?", "Twoja akcja", "twoja kolej", "co zamierzasz?", "co chcesz zrobić?", "twój ruch"
✓ MG pyta o akcję grupy ("Co robicie?", "Wasza kolej", "co zamierzacie?") i żaden gracz nie odpowiedział po tym pytaniu
✓ Ostatnia wypowiedź kończy się "?" po narracji lub pytaniu MG i nie ma po niej żadnej odpowiedzi gracza
✓ MG zakończył opis sceny w sposób sugerujący oczekiwanie na akcję gracza

Zasady SPEAK_UP (bądź rozważny — prawdziwy gracz nie wchodzi w słowo co 20 sekund):
✓ Postać ma konkretną umiejętność/zaklęcie/przedmiot bezpośrednio związany z sytuacją
✓ Grupa utknęła w debacie a postać ma wyraźne zdanie
✓ Postać ze względu na historię lub zdolności zauważyłaby coś czego inni nie widzą
✓ Postać naturalnie zareagowałaby emocjonalnie na to co właśnie padło

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
