"""Entry point — startup sequence and main session loop."""
from __future__ import annotations

import time

from rpg_player import config
from rpg_player.onboarding.file_ingest import ingest_game_files
from rpg_player.onboarding.personality_loader import load_personality
from rpg_player.onboarding.personality_creator import create_personality
from rpg_player.onboarding.character_loader import load_character
from rpg_player.onboarding.character_creator import create_character
from rpg_player.tts.speaker import Speaker
from rpg_player.session.listener import Listener
from rpg_player.session.classifier import Classifier
from rpg_player.session import agent as agent_module


def _char_summary(character: dict) -> str:
    return (
        f"{character.get('name', 'Postać')}, "
        f"{character.get('race', '')} {character.get('char_class', '')}, "
        f"poziom {character.get('level', 1)}. "
        f"{character.get('personality', '')}"
    )


def main() -> None:
    tts = Speaker()

    # 1. Ingest game files (skip silently if none present)
    vectorstore = ingest_game_files()

    # 2. Load or create player personality
    personality = load_personality()
    if personality is None:
        listener_tmp = Listener()
        personality = create_personality(tts, listener_tmp)

    # 3. Load or create character (personality shapes the conversation tone)
    character = load_character()
    if character is None:
        listener_tmp = Listener()
        character = create_character(tts, listener_tmp, personality=personality)

    # 4. Resolve effective cooldown from personality
    talk_freq = personality.get("talk_frequency", "umiarkowanie")
    cooldown_sec = config.COOLDOWN_BY_FREQUENCY.get(talk_freq, config.SPEAK_UP_COOLDOWN_SEC)

    char_name = character.get("name", "Postać")
    summary = _char_summary(character)

    # 5. Start listener and classifier
    listener = Listener(char_name=char_name)
    classifier = Classifier(char_name=char_name, char_summary=summary)
    listener.start()

    tts.speak(f"Gotowy. Jestem {char_name}. Zaczynamy sesję.")

    last_speak_up_time: float = 0.0
    session_active = True

    print(f"[main] Sesja aktywna. Postać: {char_name}. Cooldown SPEAK_UP: {cooldown_sec}s")

    try:
        while session_active:
            time.sleep(0.5)  # polling interval

            buffer_text = listener.get_buffer_text()
            if not buffer_text.strip():
                continue

            now = time.time()
            speak_up_blocked = (now - last_speak_up_time) < cooldown_sec

            # Always check MY_TURN; only check SPEAK_UP if cooldown elapsed
            decision = classifier.classify(buffer_text)

            if decision == "WAIT":
                continue

            if decision == "SPEAK_UP" and speak_up_blocked:
                continue

            # Generate response
            trigger_mode = decision  # "MY_TURN" or "SPEAK_UP"
            try:
                response = agent_module.run_agent(
                    personality=personality,
                    character=character,
                    vectorstore=vectorstore,
                    tts=tts,
                    trigger_mode=trigger_mode,
                    buffer_text=buffer_text,
                )
            except Exception as e:
                print(f"[main] Błąd agenta: {e}")
                tts.speak("Dobra, tym razem poczekam.")
                continue

            if response:
                tts.speak(response)
                listener.add_bot_turn(response)

                if decision == "SPEAK_UP":
                    last_speak_up_time = time.time()

    except KeyboardInterrupt:
        print("\n[main] Sesja zakończona.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
