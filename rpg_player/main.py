"""Entry point — startup sequence and main session loop."""
from __future__ import annotations

import time

from rpg_player import config
from rpg_player.behaviors import DEFAULT_CHAIN, BehaviorContext
from rpg_player.onboarding.file_ingest import ingest_game_files
from rpg_player.onboarding.personality_loader import load_personality
from rpg_player.onboarding.personality_creator import create_personality
from rpg_player.onboarding.character_loader import load_character
from rpg_player.onboarding.character_creator import create_character
from rpg_player.tts.speaker import Speaker
from rpg_player.session.listener import Listener
from rpg_player.session.classifier import Classifier
from rpg_player.session import agent as agent_module
from rpg_player.ui.dashboard import Dashboard


def _char_summary(character: dict) -> str:
    return (
        f"{character.get('name', 'Postać')}, "
        f"{character.get('race', '')} {character.get('char_class', '')}, "
        f"poziom {character.get('level', 1)}. "
        f"{character.get('personality', '')}"
    )


def _char_info(character: dict) -> str:
    return (
        f"{character.get('race', '')} {character.get('char_class', '')} "
        f"Lv.{character.get('level', 1)}"
    )


def _personality_info(personality: dict) -> str:
    return (
        f"{personality.get('table_archetype', '—')} · "
        f"{personality.get('talk_frequency', '—')} · "
        f"humor: {personality.get('humor_level', '—')}"
    )


def main() -> None:
    dash = Dashboard()

    tts = Speaker()

    # 1. Ingest game files
    dash.update(status="INGESTING")
    dash.start()
    dash.log("Skanowanie plików gry...")
    vectorstore = ingest_game_files()
    if vectorstore:
        dash.log("Baza wektorowa załadowana.")
    else:
        dash.log("Brak plików gry — RAG wyłączony.")

    # 2. Load or create player personality
    dash.update(status="ONBOARDING")
    dash.log("Ładowanie osobowości gracza...")
    personality = load_personality()
    if personality is None:
        dash.log("Brak pliku osobowości — uruchamiam tworzenie...")
        listener_tmp = Listener()
        personality = create_personality(tts, listener_tmp)
        dash.log("Osobowość zapisana.")
    else:
        dash.log("Osobowość załadowana.")

    # 3. Load or create character
    dash.log("Ładowanie postaci...")
    character = load_character()
    if character is None:
        dash.log("Brak postaci — uruchamiam tworzenie...")
        listener_tmp = Listener()
        character = create_character(tts, listener_tmp, personality=personality)
        dash.log(f"Postać '{character.get('name')}' zapisana.")
    else:
        dash.log(f"Postać '{character.get('name')}' załadowana.")

    # 4. Resolve cooldown from personality
    talk_freq = personality.get("talk_frequency", "umiarkowanie")
    cooldown_sec = config.COOLDOWN_BY_FREQUENCY.get(talk_freq, config.SPEAK_UP_COOLDOWN_SEC)

    char_name = character.get("name", "Postać")
    summary = _char_summary(character)

    dash.update(
        character_name=char_name,
        character_info=_char_info(character),
        personality_info=_personality_info(personality),
        cooldown_total=cooldown_sec,
    )

    # 5. Start listener and classifier
    listener = Listener(char_name=char_name)
    classifier = Classifier(char_name=char_name, char_summary=summary)
    listener.start()

    tts.speak(f"Gotowy. Jestem {char_name}. Zaczynamy sesję.")
    dash.update(status="LISTENING")
    dash.log(f"Sesja aktywna — postać: {char_name} · cooldown: {cooldown_sec}s")

    last_speak_up_time: float = 0.0

    try:
        while True:
            time.sleep(0.5)

            now = time.time()
            cooldown_remaining = max(0.0, cooldown_sec - (now - last_speak_up_time))
            dash.update(
                cooldown_remaining=cooldown_remaining,
                buffer=listener.get_buffer(),
            )

            buffer_text = listener.get_buffer_text()
            if not buffer_text.strip():
                continue

            speak_up_blocked = cooldown_remaining > 0

            # Classify
            dash.update(status="CLASSIFYING")
            decision = classifier.classify(buffer_text)
            dash.update(last_decision=decision)

            if decision == "WAIT":
                dash.update(status="LISTENING")
                continue

            if decision == "SPEAK_UP" and speak_up_blocked:
                dash.update(status="COOLDOWN")
                continue

            # Run behavior chain
            buf = listener.get_buffer()
            last_utterance = buf[-1]["text"] if buf else ""
            ctx = BehaviorContext(
                buffer=buf,
                buffer_text=buffer_text,
                last_utterance=last_utterance,
                character=character,
                personality=personality,
                trigger_mode=decision,
            )
            behavior_instructions, triggered_names = DEFAULT_CHAIN.run(ctx)
            dash.update(behaviors_triggered=triggered_names)

            if triggered_names:
                dash.log(f"Zachowania aktywne: {', '.join(triggered_names)}")

            # Generate agent response
            dash.log(f"Agent wywoływany [{decision}]...")
            try:
                response = agent_module.run_agent(
                    personality=personality,
                    character=character,
                    vectorstore=vectorstore,
                    tts=tts,
                    trigger_mode=decision,
                    buffer_text=buffer_text,
                    behavior_instructions=behavior_instructions,
                )
            except Exception as e:
                dash.update(status="ERROR", error=str(e))
                dash.log(f"[red]Błąd agenta: {e}[/red]")
                tts.speak("Dobra, tym razem poczekam.")
                dash.update(status="LISTENING", error="")
                continue

            if response:
                dash.update(status="SPEAKING", last_response=response)
                dash.log(f"Odpowiedź: {response[:80]}{'…' if len(response) > 80 else ''}")
                tts.speak(response)
                listener.add_bot_turn(response)

                if decision == "SPEAK_UP":
                    last_speak_up_time = time.time()

            dash.update(status="LISTENING", behaviors_triggered=[])

    except KeyboardInterrupt:
        dash.log("Sesja zakończona przez użytkownika.")
        dash.update(status="STOPPED")
        time.sleep(0.5)
    finally:
        listener.stop()
        dash.stop()


if __name__ == "__main__":
    main()
