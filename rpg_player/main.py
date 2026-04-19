"""Entry point — startup sequence and main session loop."""
from __future__ import annotations

import atexit
import hashlib
import json
import signal
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from pathlib import Path

from rpg_player import config
from rpg_player.behaviors import DEFAULT_CHAIN, BehaviorContext
from rpg_player.onboarding.file_ingest import ingest_game_files
from rpg_player.onboarding.personality_loader import load_personality
from rpg_player.onboarding.personality_creator import create_personality
from rpg_player.onboarding.character_loader import load_character
from rpg_player.onboarding.character_creator import create_character
from rpg_player.session.session_memory import SessionMemory
from rpg_player.session.speaker_registry import SpeakerRegistry
from rpg_player.session.token_tracker import TokenTracker
from rpg_player.session.game_log import GameLog
from rpg_player.session.memory_manager import MemoryManager
from rpg_player.session import game_detector
from rpg_player.tts.speaker import Speaker
from rpg_player.session.listener import Listener
from rpg_player.session.classifier import Classifier
from rpg_player.session import agent as agent_module
from rpg_player.integrations.discord_connector import DiscordConnector
from rpg_player.ui.dashboard import Dashboard


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BotPlayer:
    personality: dict
    character: dict
    classifier: Classifier
    token_tracker: TokenTracker = field(default_factory=TokenTracker)
    consecutive_wait: int = 0
    last_speak_up_time: float = 0.0
    cooldown_sec: float = 45.0
    _last_wait_hash: str = field(default="", compare=False, repr=False)


class InputHandler:
    """Background keyboard reader — raw single-keypress on real TTY, line-mode fallback."""

    def __init__(self) -> None:
        self._force_turn = False
        self._voice_next = False
        self._quit = False
        self._fd: int | None = None
        self._old_settings = None
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    # ── Input loop ────────────────────────────────────────────────────

    def _loop(self) -> None:
        try:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
        except Exception:
            # stdin is piped/redirected — fall back to line-buffered mode
            self._line_loop()
            return

        self._fd = fd
        self._old_settings = old
        atexit.register(self._restore)
        try:
            tty.setcbreak(fd)
            while not self._quit:
                ch = sys.stdin.read(1).lower()
                if ch == "f":
                    self._force_turn = True
                elif ch == "v":
                    self._voice_next = True
                elif ch in ("q", "\x1b"):   # q or Esc
                    self._quit = True
        except Exception:
            pass
        finally:
            self._restore()

    def _line_loop(self) -> None:
        """Fallback for non-TTY environments (piped input)."""
        while not self._quit:
            try:
                line = sys.stdin.readline().strip().lower()
            except Exception:
                break
            if line == "f":
                self._force_turn = True
            elif line == "v":
                self._voice_next = True
            elif line in ("q", "quit", "exit"):
                self._quit = True

    # ── Lifecycle ─────────────────────────────────────────────────────

    def stop(self) -> None:
        self._quit = True
        self._restore()

    def _restore(self) -> None:
        if self._old_settings is not None and self._fd is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass
            self._old_settings = None

    # ── Accessors ─────────────────────────────────────────────────────

    def consume_force(self) -> bool:
        if self._force_turn:
            self._force_turn = False
            return True
        return False

    def consume_voice_next(self) -> bool:
        if self._voice_next:
            self._voice_next = False
            return True
        return False

    @property
    def quit_requested(self) -> bool:
        return self._quit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _char_summary(character: dict) -> str:
    return (
        f"{character.get('name', 'Postac')}, "
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
        f"{personality.get('table_archetype', '-')} · "
        f"{personality.get('talk_frequency', '-')} · "
        f"humor: {personality.get('humor_level', '-')}"
    )


def _is_direct_question_to_character(buffer: list[dict], char_name: str) -> bool:
    """Heuristic: last non-bot utterance is a direct question to this character."""
    if not buffer:
        return False

    last = buffer[-1]
    speaker = str(last.get("speaker", "")).strip().lower()
    text = str(last.get("text", "")).strip().lower()
    name = char_name.lower()
    if not text or speaker == name:
        return False
    if "?" not in text:
        return False

    if name in text:
        return True

    direct_phrases = (
        "twoja kolej",
        "twoj ruch",
        "co robisz",
        "co zamierzasz",
        "co chcesz zrobic",
    )
    return any(phrase in text for phrase in direct_phrases)


def _resolve_decision(
    player: BotPlayer,
    buffer: list[dict],
    buffer_text: str,
    force_turn: bool,
    mode: str,
) -> tuple[str, bool]:
    """Return (decision, was_forced)."""
    if force_turn:
        player.consecutive_wait = 0
        return "MY_TURN", True

    if mode == "manual":
        return "WAIT", False

    if mode == "gm":
        char_name = player.character.get("name", "Postac")
        if _is_direct_question_to_character(buffer, char_name):
            player.consecutive_wait = 0
            return "MY_TURN", False
        return "WAIT", False

    # mode == "auto" (legacy behavior)
    decision = player.classifier.classify(buffer_text)
    if decision == "WAIT":
        player.consecutive_wait += 1
        if (
            player.consecutive_wait >= config.CONSECUTIVE_WAIT_FORCE_THRESHOLD
            and buffer_text.rstrip().endswith("?")
        ):
            player.consecutive_wait = 0
            return "MY_TURN", True
    else:
        player.consecutive_wait = 0
    return decision, False


def _ask_continue_session(session_memory: SessionMemory) -> dict | None:
    """Print a prompt and return the previous session dict or None."""
    latest = session_memory.load_latest()
    if not latest:
        return None
    char = latest.get("character", "nieznana")
    date = (latest.get("started_at") or "")[:10]
    print(f"\nZnaleziono poprzednia sesje: {char}  [{date}]")
    print("Kontynuowac poprzednia sesje? (t/n): ", end="", flush=True)
    try:
        answer = sys.stdin.readline().strip().lower()
    except Exception:
        return None
    return latest if answer in ("t", "tak", "y", "yes") else None


# ---------------------------------------------------------------------------
# Per-player turn logic
# ---------------------------------------------------------------------------

def _process_bot_turn(
    player: BotPlayer,
    listener: Listener,
    tts: Speaker,
    vectorstore,
    dash: Dashboard,
    registry: SpeakerRegistry,
    game_log: GameLog | None = None,
    discord_connector: DiscordConnector | None = None,
    session_context: str = "",
    general_context: str = "",
    game_context: str = "",
    force_turn: bool = False,
) -> None:
    """Classify and optionally respond for one BotPlayer. Mutates player state."""
    buf = listener.get_buffer()
    buffer_text = listener.get_buffer_text()
    if not buffer_text.strip():
        return

    char_name = player.character.get("name", "Postac")
    now = time.time()
    cooldown_remaining = max(0.0, player.cooldown_sec - (now - player.last_speak_up_time))
    speak_up_blocked = cooldown_remaining > 0

    decision, was_forced = _resolve_decision(
        player=player,
        buffer=buf,
        buffer_text=buffer_text,
        force_turn=force_turn,
        mode=config.RESPONSE_MODE,
    )
    if force_turn:
        dash.log(f"[yellow]{char_name}: wymuszona odpowiedz (klawisz f)[/yellow]")
    elif was_forced and config.RESPONSE_MODE == "auto":
        dash.log(
            f"[yellow]{char_name}: wymuszona odpowiedz po "
            f"{config.CONSECUTIVE_WAIT_FORCE_THRESHOLD} WAITs[/yellow]"
        )

    if decision == "WAIT":
        if game_log:
            buf_hash = hashlib.md5(buffer_text.encode()).hexdigest()
            if buf_hash != player._last_wait_hash:
                player._last_wait_hash = buf_hash
                game_log.log_event(
                    event="wait",
                    status="LISTENING",
                    decision=decision,
                    actor=char_name,
                    detail="Bot czeka na dalszy kontekst.",
                    buffer=buf,
                    known_players=registry.known_players,
                )
        return

    if decision == "SPEAK_UP" and not config.ALLOW_PROACTIVE_SPEAK_UP:
        dash.log(f"[dim]{char_name}: SPEAK_UP zablokowany (tryb kontrolowany)[/dim]")
        if game_log:
            game_log.log_event(
                event="blocked_speak_up",
                status="LISTENING",
                decision=decision,
                actor=char_name,
                detail="SPEAK_UP zablokowany przez ustawienia.",
                buffer=buf,
                known_players=registry.known_players,
            )
        return

    if decision == "SPEAK_UP" and speak_up_blocked:
        if game_log:
            game_log.log_event(
                event="cooldown_block",
                status="COOLDOWN",
                decision=decision,
                actor=char_name,
                detail="Cooldown blokuje SPEAK_UP.",
                buffer=buf,
                known_players=registry.known_players,
            )
        return

    # Behavior chain
    last_utterance = buf[-1]["text"] if buf else ""
    ctx = BehaviorContext(
        buffer=buf,
        buffer_text=buffer_text,
        last_utterance=last_utterance,
        character=player.character,
        personality=player.personality,
        trigger_mode=decision,
    )
    behavior_instructions, triggered_names = DEFAULT_CHAIN.run(ctx)
    if triggered_names:
        dash.log(f"{char_name} — zachowania: {', '.join(triggered_names)}")
        dash.update(behaviors_triggered=triggered_names)

    dash.update(status="CLASSIFYING", last_decision=decision)
    dash.log(f"{char_name} — agent [{decision}]...")

    try:
        response = agent_module.run_agent(
            personality=player.personality,
            character=player.character,
            vectorstore=vectorstore,
            tts=tts,
            trigger_mode=decision,
            buffer_text=buffer_text,
            last_utterance=last_utterance,
            behavior_instructions=behavior_instructions,
            session_context=session_context,
            general_context=general_context,
            game_context=game_context,
            known_players=registry.known_players,
            token_tracker=player.token_tracker,
        )
    except Exception as e:
        dash.update(status="ERROR", error=str(e))
        dash.log(f"[red]Blad agenta ({char_name}): {e}[/red]")
        if game_log:
            game_log.log_event(
                event="agent_error",
                status="ERROR",
                decision=decision,
                actor=char_name,
                detail=str(e),
                buffer=buf,
                known_players=registry.known_players,
            )
        tts.speak("Dobra, tym razem poczekam.")
        dash.update(status="LISTENING", error="")
        return

    if response:
        dash.update(status="SPEAKING", last_response=response)
        dash.log(f"{char_name}: {response[:80]}{'...' if len(response) > 80 else ''}")
        tts.speak(response)
        listener.add_bot_turn(response)
        if game_log:
            game_log.log_event(
                event="bot_response",
                status="SPEAKING",
                decision=decision,
                actor=char_name,
                detail=response,
                buffer=listener.get_buffer(),
                known_players=registry.known_players,
            )
        if discord_connector:
            discord_connector.relay_bot_message(response)

        if decision == "SPEAK_UP":
            player.last_speak_up_time = time.time()

        # Token limit warnings spoken aloud
        warn_text = player.token_tracker.check_warn()
        if warn_text:
            dash.log(f"[yellow]Token limit: {warn_text[:60]}[/yellow]")
            tts.speak(warn_text)

        dash.update(token_summary=player.token_tracker.summary())

    dash.update(status="LISTENING", behaviors_triggered=[])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # SIGTERM (web panel Stop button) → treat as Ctrl+C so finally-block saves session
    def _handle_sigterm(_sig, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Session memory check before dashboard starts (needs stdin)
    session_memory = SessionMemory()
    previous_session = _ask_continue_session(session_memory)
    session_context = ""
    known_players_prev: list[str] = []
    if previous_session:
        session_context = session_memory.build_context_block(previous_session)
        known_players_prev = previous_session.get("known_players", [])
        print(f"Kontynuuje sesje. Znani gracze: {', '.join(known_players_prev) if known_players_prev else 'brak'}")

    dash = Dashboard()
    tts = Speaker()
    game_log = GameLog(enabled=config.GAME_LOG_ENABLED)
    memory_manager = MemoryManager()
    discord_connector = DiscordConnector(enabled=config.DISCORD_ENABLED)
    input_handler = InputHandler()
    registry = SpeakerRegistry()
    if known_players_prev:
        registry.from_dict({"names": known_players_prev, "log": []})
        memory_manager.update_players(known_players_prev)
    discord_connector.attach_registry(registry)

    # 1. Ingest game files
    dash.update(status="INGESTING")
    dash.start()
    dash.log("Skanowanie plikow gry...")
    vectorstore = ingest_game_files()
    dash.log("Baza wektorowa zaladowana." if vectorstore else "Brak plikow gry — RAG wylaczony.")
    game_log.log_event(
        event="startup_ingest",
        status="INGESTING",
        detail="Ingest plikow gry zakonczony.",
        known_players=registry.known_players,
    )

    # 2. Load or create personality
    dash.update(status="ONBOARDING")
    dash.log("Ladowanie osobowosci gracza...")
    personality = load_personality()
    if personality is None:
        dash.log("Brak pliku osobowosci — uruchamiam tworzenie...")
        personality = create_personality(tts, Listener())
        dash.log("Osobowosc zapisana.")
    else:
        dash.log("Osobowosc zaladowana.")

    # 3. Load or create character
    dash.log("Ladowanie postaci...")
    character = load_character()
    if character is None:
        dash.log("Brak postaci — uruchamiam tworzenie...")
        character = create_character(tts, Listener(), personality=personality)
        dash.log(f"Postac '{character.get('name')}' zapisana.")
    else:
        dash.log(f"Postac '{character.get('name')}' zaladowana.")

    # 3b. Load game type; ask for campaign intro if not yet provided
    game_type = game_detector.load()
    if game_type:
        dash.log(
            f"Typ gry: [cyan]{game_type.get('system', '?')}[/cyan] "
            f"/ {game_type.get('genre')} / {game_type.get('tone')}"
        )
        if not game_type.get("campaign_intro") and vectorstore:
            dash.log("Pytam o intro kampanii...")
            tts.speak(
                "Zanim zaczniemy — opisz krótko kampanię. "
                "Gdzie zaczyna się akcja i o czym jest ta gra?"
            )
            _intro_listener = Listener()
            intro_text = _intro_listener.listen_once()
            if intro_text and len(intro_text.split()) >= 3:
                game_detector.save_intro(intro_text)
                game_type = game_detector.load() or game_type
                dash.log(f"[green]Intro kampanii zapisane.[/green]")
            else:
                dash.log("[dim]Intro kampanii pominięte.[/dim]")
    game_context = game_detector.build_game_context(game_type) if game_type else ""

    # 4. Primary bot player
    talk_freq = personality.get("talk_frequency", "umiarkowanie")
    cooldown_sec = config.COOLDOWN_BY_FREQUENCY.get(talk_freq, config.SPEAK_UP_COOLDOWN_SEC)
    char_name = character.get("name", "Postac")

    primary_player = BotPlayer(
        personality=personality,
        character=character,
        classifier=Classifier(char_name=char_name, char_summary=_char_summary(character)),
        token_tracker=TokenTracker(),
        cooldown_sec=cooldown_sec,
    )

    # 5. Additional players from config (guarded by explicit opt-in)
    extra_players: list[BotPlayer] = []
    if config.ENABLE_ADDITIONAL_AI_PLAYERS:
        for p_cfg in config.ADDITIONAL_PLAYERS:
            try:
                p_personality = json.loads(Path(p_cfg["personality_file"]).read_text(encoding="utf-8"))
                p_character = json.loads(Path(p_cfg["character_file"]).read_text(encoding="utf-8"))
                p_name = p_character.get("name", "Postac2")
                p_freq = p_personality.get("talk_frequency", "umiarkowanie")
                p_cooldown = config.COOLDOWN_BY_FREQUENCY.get(p_freq, config.SPEAK_UP_COOLDOWN_SEC)
                extra_players.append(BotPlayer(
                    personality=p_personality,
                    character=p_character,
                    classifier=Classifier(char_name=p_name, char_summary=_char_summary(p_character)),
                    token_tracker=TokenTracker(),
                    cooldown_sec=p_cooldown,
                ))
                dash.log(f"Dodatkowy gracz AI: {p_name}")
            except Exception as e:
                dash.log(f"[red]Blad ladowania dodatkowego gracza: {e}[/red]")
    elif config.ADDITIONAL_PLAYERS:
        dash.log("[dim]ADDITIONAL_PLAYERS skonfigurowane, ale wylaczone (ENABLE_ADDITIONAL_AI_PLAYERS=0).[/dim]")

    all_players = [primary_player] + extra_players

    dash.update(
        character_name=char_name,
        character_info=_char_info(character),
        personality_info=_personality_info(personality),
        cooldown_total=cooldown_sec,
        voice_name=tts.current_voice,
        known_players=registry.known_players,
        response_mode=config.RESPONSE_MODE,
        buffer_max_exchanges=config.BUFFER_MAX_EXCHANGES,
    )
    game_log.log_event(
        event="session_ready",
        status="LISTENING",
        actor=char_name,
        detail=(
            f"Tryb={config.RESPONSE_MODE}, buffer={config.BUFFER_MAX_EXCHANGES}, "
            f"discord={'on' if config.DISCORD_ENABLED else 'off'}"
        ),
        known_players=registry.known_players,
    )
    if config.DISCORD_ENABLED:
        discord_connector.ask_for_introductions()

    # 6. Start listener and session
    listener = Listener(char_name=char_name, registry=registry)
    listener.start()

    tts.speak(f"Gotowy. Jestem {char_name}. Zaczynamy sesje.")
    dash.update(status="LISTENING")
    dash.log(f"Sesja aktywna — {char_name} · cooldown: {cooldown_sec}s")
    dash.log(
        "[dim]Klawisze: [f] wymus odpowiedz · [v] zmien glos · [q] zakoncz | "
        f"tryb: {config.RESPONSE_MODE}[/dim]"
    )

    try:
        while True:
            if input_handler.quit_requested:
                dash.log("Konczenie sesji...")
                game_log.log_event(
                    event="shutdown_requested",
                    status="STOPPED",
                    actor=char_name,
                    detail="Zakonczenie przez uzytkownika.",
                    known_players=registry.known_players,
                )
                break

            time.sleep(0.5)

            # Buffer flush requested from web panel
            flush_flag = Path(config.BUFFER_FLUSH_FLAG)
            if flush_flag.exists():
                try:
                    flush_flag.unlink()
                except OSError:
                    pass
                listener.flush_keeping_last()
                dash.log("[yellow]Bufor przepłukany — zachowano ostatnią wypowiedź.[/yellow]")
                if game_log:
                    game_log.log_event(
                        event="buffer_flushed",
                        status="LISTENING",
                        actor=char_name,
                        detail="Bufor przepłukany z panelu webowego.",
                        known_players=registry.known_players,
                    )
                for p in all_players:
                    p._last_wait_hash = ""

            # Voice change
            if input_handler.consume_voice_next():
                new_voice = tts.next_voice()
                dash.update(voice_name=new_voice)
                dash.log(f"Glos zmieniony na: {new_voice}")

            # Dashboard state refresh
            now = time.time()
            cooldown_remaining = max(
                0.0, cooldown_sec - (now - primary_player.last_speak_up_time)
            )
            _mem = memory_manager.as_dict()
            dash.update(
                cooldown_remaining=cooldown_remaining,
                buffer=listener.get_buffer(),
                known_players=registry.known_players,
                token_summary=primary_player.token_tracker.summary(),
                memory_summarizing=memory_manager.is_summarizing,
                memory_last_updated=_mem.get("last_updated", ""),
                memory_notes_count=len(_mem.get("session_notes", [])),
            )
            if config.DISCORD_ENABLED:
                discord_connector.update_presence(registry.known_players)

            buf = listener.get_buffer()
            if not buf:
                continue

            # Auto-flush when buffer fill reaches threshold — summarise first
            max_ex = config.BUFFER_MAX_EXCHANGES
            fill = len(buf) / max_ex if max_ex else 0.0
            if fill >= config.BUFFER_FLUSH_THRESHOLD:
                memory_manager.summarize_async(list(buf), registry.known_players)
                listener.flush_keeping_last()
                pct = f"{fill:.0%}"
                dash.log(
                    f"[yellow]Auto-flush buforu ({len(buf)}/{max_ex} = {pct}) "
                    f"— kontekst zapisany do pamięci ogólnej.[/yellow]"
                )
                if game_log:
                    game_log.log_event(
                        event="buffer_auto_flushed",
                        status="LISTENING",
                        actor=char_name,
                        detail=f"Auto-flush po osiągnięciu progu {pct}.",
                        known_players=registry.known_players,
                    )
                for p in all_players:
                    p._last_wait_hash = ""
                buf = listener.get_buffer()

            # Update known players in general memory
            memory_manager.update_players(registry.known_players)
            general_context = memory_manager.get_summary_text()

            # Force key only applies to primary player
            force = input_handler.consume_force()

            for i, player in enumerate(all_players):
                _process_bot_turn(
                    player=player,
                    listener=listener,
                    tts=tts,
                    vectorstore=vectorstore,
                    dash=dash,
                    registry=registry,
                    game_log=game_log,
                    discord_connector=discord_connector,
                    session_context=session_context,
                    general_context=general_context,
                    game_context=game_context,
                    force_turn=(force and i == 0),
                )
                # Brief gap between multiple AI players speaking
                if len(all_players) > 1 and i < len(all_players) - 1:
                    time.sleep(1.0)

    except KeyboardInterrupt:
        dash.log("Sesja przerwana przez uzytkownika.")
    finally:
        input_handler.stop()
        dash.update(status="STOPPED")
        listener.stop()
        if config.DISCORD_ENABLED:
            discord_connector.stop()

        # Persist session to disk
        try:
            exchanges = [
                {"speaker": e.get("speaker", "?"), "text": e.get("text", "")}
                for e in listener.get_buffer()
            ]
            saved_path = session_memory.save(
                exchanges=exchanges,
                character=character,
                known_players=registry.known_players,
            )
            dash.log(f"Sesja zapisana: {saved_path.name}")
        except Exception as e:
            dash.log(f"[red]Blad zapisu sesji: {e}[/red]")

        time.sleep(0.5)
        dash.stop()


if __name__ == "__main__":
    main()
