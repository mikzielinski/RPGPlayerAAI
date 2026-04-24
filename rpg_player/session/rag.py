"""Human-like async RAG lookup — never instant, always with Polish filler."""
from __future__ import annotations

import asyncio
import random
from typing import Optional

FILLERS_PL = [
    "Hmm, zaraz... coś mi chodzi po głowie na ten temat.",
    "Chyba było coś o tym w podręczniku, daj mi chwilę.",
    "Znam tę zasadę, tylko muszę to poukładać w głowie.",
    "Czekaj, czekaj... tak, coś pamiętam.",
    "Moment — mój {char_class} powinien to wiedzieć...",
]

TIMEOUT_PHRASES_PL = [
    "Nie jestem do końca pewien — może zapytajmy MG?",
    "Szczerze? Nie pamiętam dokładnie. DM, możesz potwierdzić?",
    "Zgłupiałem. Lepiej sprawdźcie w podręczniku niż mi wierzyć.",
]


async def human_lookup(
    query: str,
    vectorstore,
    tts,
    char_class: str,
    timeout: float = 5.0,
) -> Optional[str]:
    """RAG lookup that sounds human: speaks filler first (if TTS available), then retrieves.

    Returns concatenated page content of top matches, or None on timeout / no results.
    """
    if tts is not None:
        filler = random.choice(FILLERS_PL).replace("{char_class}", char_class)
        await tts.speak_async(filler)

    try:
        results = await asyncio.wait_for(
            vectorstore.asimilarity_search(query, k=4),
            timeout=timeout,
        )
        if results:
            return "\n\n---\n\n".join(r.page_content for r in results)
        return None
    except asyncio.TimeoutError:
        if tts is not None:
            phrase = random.choice(TIMEOUT_PHRASES_PL)
            await tts.speak_async(phrase)
        return None
