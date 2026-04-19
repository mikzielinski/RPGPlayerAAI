"""Web control panel for RPG AI Player Bot."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import datetime
import platform

from flask import Flask, jsonify, render_template, request, Response

from rpg_player import config
from rpg_player.integrations.discord_connector import DiscordConnector
from rpg_player.session.game_log import GameLog
from rpg_player.session.session_memory import SessionMemory
from rpg_player.session import secrets_manager


REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
ENV_PATH = REPO_ROOT / ".env"

CHARACTER_PATH = Path(config.CHARACTER_FILE)
PERSONALITY_PATH = Path(config.PERSONALITY_FILE)
GAME_FILES_PATH = Path(config.GAME_FILES_DIR)
CHROMA_PATH = Path(config.CHROMA_DIR)
SESSIONS_PATH = Path(config.SESSIONS_DIR)
GENERAL_CONTEXT_PATH = Path(config.GENERAL_CONTEXT_FILE)
GAME_TYPE_PATH = Path(config.GAME_TYPE_FILE)

SUPPORTED_GAME_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
SECRETS_PATH = Path(config.SECRETS_DIR)


def _env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_response_mode(value: str | None) -> str:
    if not value:
        return config.RESPONSE_MODE
    normalized = value.strip().lower()
    if normalized not in {"manual", "gm", "auto"}:
        return config.RESPONSE_MODE
    return normalized


def _load_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _save_env_values(updates: dict[str, str | None]) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue

        key, _old = line.split("=", 1)
        env_key = key.strip()
        if env_key not in remaining:
            new_lines.append(line)
            continue

        value = remaining.pop(env_key)
        if value is not None:
            new_lines.append(f"{env_key}={value}")

    for key, value in remaining.items():
        if value is not None:
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _effective_env() -> dict[str, str]:
    env = os.environ.copy()
    env_file = _load_env_file()
    # Runtime values should follow .env edits from the web panel.
    env.update(env_file)
    return env


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def _safe_read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # pragma: no cover - defensive path
        return None, str(exc)


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class BotProcessManager:
    """Keep `python -m rpg_player.main` as a controllable background process."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._logs: deque[str] = deque(maxlen=1200)
        self._reader_thread: threading.Thread | None = None

    def _append_log(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._logs.append(f"[{stamp}] {line.rstrip()}")

    def _read_proc_output(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self._append_log(line)

        return_code = proc.wait()
        self._append_log(f"Proces zakonczony z kodem: {return_code}")
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return False, "Bot juz dziala."

            env = _effective_env()
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "rpg_player.main"],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            proc = self._proc
            self._append_log("Uruchomiono proces bota.")
            self._reader_thread = threading.Thread(
                target=self._read_proc_output,
                args=(proc,),
                daemon=True,
            )
            self._reader_thread.start()
            return True, "Bot uruchomiony."

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            proc = self._proc
            if not proc or proc.poll() is not None:
                self._proc = None
                return False, "Bot nie jest uruchomiony."

            proc.terminate()

        try:
            proc.wait(timeout=10)
            self._append_log("Bot zatrzymany sygnalem terminate.")
        except subprocess.TimeoutExpired:
            proc.kill()
            self._append_log("Bot nie odpowiadal, wymuszono kill.")
        return True, "Bot zatrzymany."

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            running = bool(self._proc and self._proc.poll() is None)
            pid = self._proc.pid if running and self._proc else None
        return {"running": running, "pid": pid, "logs": list(self._logs)[-500:]}


def _list_game_files() -> list[dict[str, Any]]:
    GAME_FILES_PATH.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for path in sorted(GAME_FILES_PATH.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_GAME_EXTENSIONS:
            continue
        files.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "ext": path.suffix.lower(),
            }
        )
    return files


def _get_buffer_snapshot(game_logs: list[Path]) -> tuple[int, list]:
    """Return (current_size, buffer_entries) from the latest game log entry with buffer_tail."""
    if not game_logs:
        return 0, []
    tail = GameLog.tail(game_logs[0], limit=30)
    for entry in reversed(tail):
        bt = entry.get("payload", {}).get("buffer_tail")
        if isinstance(bt, list):
            return len(bt), bt
    return 0, []


def _discord_status() -> dict[str, Any]:
    connector = DiscordConnector(
        enabled=config.DISCORD_ENABLED,
        token=config.DISCORD_BOT_TOKEN,
        guild_id=config.DISCORD_GUILD_ID,
        text_channel_id=config.DISCORD_TEXT_CHANNEL_ID,
        voice_channel_id=config.DISCORD_VOICE_CHANNEL_ID,
    )
    return connector.get_state_snapshot()


def _system_status(process_manager: BotProcessManager) -> dict[str, Any]:
    env_file = _load_env_file()
    effective_env = _effective_env()
    sessions = SessionMemory().list_sessions()
    response_mode = _env_response_mode(env_file.get("RESPONSE_MODE"))
    allow_speak_up = _env_bool(env_file.get("ALLOW_PROACTIVE_SPEAK_UP"), config.ALLOW_PROACTIVE_SPEAK_UP)
    additional_players_enabled = _env_bool(
        env_file.get("ENABLE_ADDITIONAL_AI_PLAYERS"),
        config.ENABLE_ADDITIONAL_AI_PLAYERS,
    )
    buffer_size = int(env_file.get("BUFFER_MAX_EXCHANGES", str(config.BUFFER_MAX_EXCHANGES)))
    tts_backend = (env_file.get("TTS_BACKEND") or config.TTS_BACKEND).strip().lower()
    game_logs = GameLog.list_logs()
    latest_game_log = str(game_logs[0]) if game_logs else ""
    buffer_current, buffer_entries = _get_buffer_snapshot(game_logs)

    return {
        "bot": {**process_manager.snapshot(), "buffer": buffer_entries},
        "paths": {
            "character": str(CHARACTER_PATH),
            "personality": str(PERSONALITY_PATH),
            "game_files": str(GAME_FILES_PATH),
            "chroma": str(CHROMA_PATH),
            "sessions": str(SESSIONS_PATH),
            "game_log_latest": latest_game_log,
        },
        "flags": {
            "has_character": CHARACTER_PATH.exists(),
            "has_personality": PERSONALITY_PATH.exists(),
            "has_openai_key": bool(effective_env.get("OPENAI_API_KEY", "").strip()),
            "game_files_count": len(_list_game_files()),
            "sessions_count": len(sessions),
            "buffer_current": buffer_current,
            "has_game_type": GAME_TYPE_PATH.exists(),
            "mic_muted": Path(config.MIC_MUTE_FLAG).exists(),
        },
        "game_type": _safe_read_json(GAME_TYPE_PATH)[0] or {},
        "env": {
            "openai_api_key_masked": _mask_key(effective_env.get("OPENAI_API_KEY", "")),
            "swearing_intensity": env_file.get("SWEARING_INTENSITY", config.SWEARING_INTENSITY),
            "game_files_confirmed": env_file.get("GAME_FILES_CONFIRMED", "0"),
            "response_mode": response_mode,
            "whisper_language": env_file.get("WHISPER_LANGUAGE", config.WHISPER_LANGUAGE),
            "whisper_insecure_ssl": _env_bool(env_file.get("WHISPER_INSECURE_SSL"), config.WHISPER_INSECURE_SSL),
            "allow_proactive_speak_up": allow_speak_up,
            "enable_additional_ai_players": additional_players_enabled,
            "buffer_max_exchanges": buffer_size,
            "buffer_min_exchanges": config.BUFFER_MIN_EXCHANGES,
            "buffer_max_exchanges_limit": config.BUFFER_MAX_EXCHANGES_LIMIT,
            "tts_backend": tts_backend,
            "tts_voice": env_file.get("TTS_VOICE", config.TTS_VOICE),
            "openai_tts_model": env_file.get("OPENAI_TTS_MODEL", config.OPENAI_TTS_MODEL),
            "openai_tts_voice": env_file.get("OPENAI_TTS_VOICE", config.OPENAI_TTS_VOICE),
            "openai_tts_format": env_file.get("OPENAI_TTS_FORMAT", config.OPENAI_TTS_FORMAT),
            "buffer_flush_threshold": float(env_file.get("BUFFER_FLUSH_THRESHOLD", str(config.BUFFER_FLUSH_THRESHOLD))),
            "discord_enabled": _env_bool(env_file.get("DISCORD_ENABLED"), config.DISCORD_ENABLED),
            "discord_guild_id": env_file.get("DISCORD_GUILD_ID", config.DISCORD_GUILD_ID),
            "discord_text_channel_id": env_file.get("DISCORD_TEXT_CHANNEL_ID", config.DISCORD_TEXT_CHANNEL_ID),
            "discord_voice_channel_id": env_file.get("DISCORD_VOICE_CHANNEL_ID", config.DISCORD_VOICE_CHANNEL_ID),
            "discord_text_only": _env_bool(env_file.get("DISCORD_TEXT_ONLY"), config.DISCORD_TEXT_ONLY),
        },
        "discord": _discord_status(),
    }


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(WEB_DIR / "templates"),
        static_folder=str(WEB_DIR / "static"),
        static_url_path="/static",
    )
    manager = BotProcessManager()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        return jsonify(_system_status(manager))

    @app.get("/api/character")
    def api_get_character():
        data, error = _safe_read_json(CHARACTER_PATH)
        return jsonify({"exists": CHARACTER_PATH.exists(), "data": data, "error": error})

    @app.post("/api/character")
    def api_save_character():
        payload = request.get_json(silent=True) or {}
        data = payload.get("data")
        if not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Pole 'data' musi byc obiektem JSON."}), 400
        _safe_write_json(CHARACTER_PATH, data)
        return jsonify({"ok": True, "message": "Postac zapisana."})

    @app.get("/api/personality")
    def api_get_personality():
        data, error = _safe_read_json(PERSONALITY_PATH)
        return jsonify({"exists": PERSONALITY_PATH.exists(), "data": data, "error": error})

    @app.post("/api/personality")
    def api_save_personality():
        payload = request.get_json(silent=True) or {}
        data = payload.get("data")
        if not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Pole 'data' musi byc obiektem JSON."}), 400
        _safe_write_json(PERSONALITY_PATH, data)
        return jsonify({"ok": True, "message": "Osobowosc zapisana."})

    @app.get("/api/game-files")
    def api_game_files():
        return jsonify({"files": _list_game_files()})

    @app.post("/api/game-files/upload")
    def api_upload_game_files():
        files = request.files.getlist("files")
        if not files:
            return jsonify({"ok": False, "message": "Nie przeslano plikow."}), 400

        GAME_FILES_PATH.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        skipped: list[str] = []
        for file in files:
            filename = Path(file.filename or "").name
            if not filename:
                continue
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_GAME_EXTENSIONS:
                skipped.append(filename)
                continue
            destination = GAME_FILES_PATH / filename
            file.save(destination)
            saved.append(filename)

        if not saved and skipped:
            return jsonify({"ok": False, "message": "Brak obslugiwanych plikow.", "skipped": skipped}), 400
        _save_env_values({"GAME_FILES_CONFIRMED": "1"})
        return jsonify({"ok": True, "saved": saved, "skipped": skipped})

    @app.delete("/api/game-files/<path:filename>")
    def api_delete_game_file(filename: str):
        safe_name = Path(filename).name
        target = GAME_FILES_PATH / safe_name
        if not target.exists() or not target.is_file():
            return jsonify({"ok": False, "message": "Plik nie istnieje."}), 404
        target.unlink()
        return jsonify({"ok": True, "message": f"Usunieto {safe_name}."})

    @app.post("/api/ingest")
    def api_ingest():
        try:
            # Lazy import: lets web UI start even when LangChain stack is not installed yet.
            from rpg_player.onboarding.file_ingest import ingest_game_files

            vectorstore = ingest_game_files()
            chunks_ready = bool(vectorstore)
            return jsonify(
                {
                    "ok": True,
                    "message": "Ingest zakonczony." if chunks_ready else "Brak plikow do indeksowania.",
                }
            )
        except ModuleNotFoundError as exc:
            return jsonify({"ok": False, "message": f"Brak zaleznosci do ingest: {exc}"}), 500
        except Exception as exc:
            return jsonify({"ok": False, "message": f"Blad ingest: {exc}"}), 500

    @app.post("/api/validate")
    def api_validate_setup():
        env = _effective_env()
        completed = subprocess.run(
            [sys.executable, "scripts/validate_setup.py"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        return jsonify({"ok": completed.returncode == 0, "code": completed.returncode, "output": output})

    @app.post("/api/env")
    def api_save_env():
        payload = request.get_json(silent=True) or {}
        key = payload.get("openai_api_key")
        whisper_language = payload.get("whisper_language")
        whisper_ssl = payload.get("whisper_insecure_ssl")
        swearing = payload.get("swearing_intensity")
        response_mode = payload.get("response_mode")
        allow_speak_up = payload.get("allow_proactive_speak_up")
        enable_extra_players = payload.get("enable_additional_ai_players")
        buffer_size = payload.get("buffer_max_exchanges")
        buffer_flush_threshold = payload.get("buffer_flush_threshold")
        tts_backend = payload.get("tts_backend")
        tts_voice = payload.get("tts_voice")
        openai_tts_model = payload.get("openai_tts_model")
        openai_tts_voice = payload.get("openai_tts_voice")
        openai_tts_format = payload.get("openai_tts_format")
        discord_enabled = payload.get("discord_enabled")
        discord_token = payload.get("discord_bot_token")
        discord_guild = payload.get("discord_guild_id")
        discord_text = payload.get("discord_text_channel_id")
        discord_voice = payload.get("discord_voice_channel_id")

        updates: dict[str, str | None] = {}

        if key is not None:
            key = str(key).strip()
            updates["OPENAI_API_KEY"] = key if key else None

        if whisper_language is not None:
            lang = str(whisper_language).strip().lower()
            updates["WHISPER_LANGUAGE"] = lang if lang else "pl"

        if swearing is not None:
            swearing = str(swearing).strip().lower()
            if swearing not in {"off", "mild", "moderate", "heavy"}:
                return jsonify({"ok": False, "message": "Nieprawidlowa wartosc SWEARING_INTENSITY."}), 400
            updates["SWEARING_INTENSITY"] = swearing

        if response_mode is not None:
            response_mode = str(response_mode).strip().lower()
            if response_mode not in {"manual", "gm", "auto"}:
                return jsonify({"ok": False, "message": "Nieprawidlowa wartosc RESPONSE_MODE."}), 400
            updates["RESPONSE_MODE"] = response_mode

        if whisper_ssl is not None:
            updates["WHISPER_INSECURE_SSL"] = "1" if _coerce_bool(whisper_ssl) else "0"

        if allow_speak_up is not None:
            updates["ALLOW_PROACTIVE_SPEAK_UP"] = "1" if _coerce_bool(allow_speak_up) else "0"

        if enable_extra_players is not None:
            updates["ENABLE_ADDITIONAL_AI_PLAYERS"] = "1" if _coerce_bool(enable_extra_players) else "0"

        if buffer_size is not None:
            try:
                parsed = int(buffer_size)
            except Exception:
                return jsonify({"ok": False, "message": "BUFFER_MAX_EXCHANGES musi byc liczba."}), 400
            if parsed < config.BUFFER_MIN_EXCHANGES or parsed > config.BUFFER_MAX_EXCHANGES_LIMIT:
                return jsonify(
                    {
                        "ok": False,
                        "message": (
                            f"BUFFER_MAX_EXCHANGES musi byc w zakresie "
                            f"{config.BUFFER_MIN_EXCHANGES}-{config.BUFFER_MAX_EXCHANGES_LIMIT}."
                        ),
                    }
                ), 400
            updates["BUFFER_MAX_EXCHANGES"] = str(parsed)

        if buffer_flush_threshold is not None:
            try:
                fval = float(buffer_flush_threshold)
                if not (0.5 <= fval <= 1.0):
                    return jsonify({"ok": False, "message": "BUFFER_FLUSH_THRESHOLD musi być w zakresie 0.5–1.0."}), 400
                updates["BUFFER_FLUSH_THRESHOLD"] = str(round(fval, 2))
            except Exception:
                return jsonify({"ok": False, "message": "Nieprawidłowa wartość BUFFER_FLUSH_THRESHOLD."}), 400

        if tts_backend is not None:
            tts_backend = str(tts_backend).strip().lower()
            if tts_backend not in {"edge", "kokoro", "openai"}:
                return jsonify({"ok": False, "message": "Nieprawidlowy TTS_BACKEND."}), 400
            updates["TTS_BACKEND"] = tts_backend

        if tts_voice is not None:
            updates["TTS_VOICE"] = str(tts_voice).strip() or None

        if openai_tts_model is not None:
            updates["OPENAI_TTS_MODEL"] = str(openai_tts_model).strip() or None

        if openai_tts_voice is not None:
            updates["OPENAI_TTS_VOICE"] = str(openai_tts_voice).strip() or None

        if openai_tts_format is not None:
            fmt = str(openai_tts_format).strip().lower()
            if fmt and fmt not in config.OPENAI_TTS_ALLOWED_FORMATS:
                return jsonify({"ok": False, "message": "Nieprawidlowy OPENAI_TTS_FORMAT."}), 400
            updates["OPENAI_TTS_FORMAT"] = fmt or None

        discord_text_only = payload.get("discord_text_only")

        if discord_enabled is not None:
            updates["DISCORD_ENABLED"] = "1" if _coerce_bool(discord_enabled) else "0"

        if discord_text_only is not None:
            updates["DISCORD_TEXT_ONLY"] = "1" if _coerce_bool(discord_text_only) else "0"

        if discord_token is not None:
            token = str(discord_token).strip()
            updates["DISCORD_BOT_TOKEN"] = token if token else None

        if discord_guild is not None:
            updates["DISCORD_GUILD_ID"] = str(discord_guild).strip() or None

        if discord_text is not None:
            updates["DISCORD_TEXT_CHANNEL_ID"] = str(discord_text).strip() or None

        if discord_voice is not None:
            updates["DISCORD_VOICE_CHANNEL_ID"] = str(discord_voice).strip() or None

        if updates:
            _save_env_values(updates)
        return jsonify({"ok": True, "message": "Zmienna(e) .env zapisane."})

    @app.post("/api/reset")
    def api_reset():
        payload = request.get_json(silent=True) or {}
        target = payload.get("target")

        if target == "character":
            if CHARACTER_PATH.exists():
                CHARACTER_PATH.unlink()
            return jsonify({"ok": True, "message": "Usunieto character.json"})

        if target == "personality":
            if PERSONALITY_PATH.exists():
                PERSONALITY_PATH.unlink()
            return jsonify({"ok": True, "message": "Usunieto player_personality.json"})

        if target == "chroma":
            if CHROMA_PATH.exists():
                shutil.rmtree(CHROMA_PATH)
            CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            return jsonify({"ok": True, "message": "Wyczyszczono baze Chroma."})

        if target == "sessions":
            SESSIONS_PATH.mkdir(parents=True, exist_ok=True)
            removed = 0
            for file in SESSIONS_PATH.glob("session_*.json"):
                file.unlink()
                removed += 1
            return jsonify({"ok": True, "message": f"Usunieto sesje: {removed}"})

        return jsonify({"ok": False, "message": "Nieznany target resetu."}), 400

    @app.get("/api/sessions")
    def api_sessions():
        sessions = SessionMemory().list_sessions()
        compact = []
        for session in sessions:
            compact.append(
                {
                    "file": Path(session.get("_file", "")).name,
                    "started_at": session.get("started_at"),
                    "character": session.get("character"),
                    "known_players": session.get("known_players", []),
                    "exchanges_count": len(session.get("exchanges", [])),
                }
            )
        return jsonify({"sessions": compact})

    @app.get("/api/sessions/<path:filename>")
    def api_session_details(filename: str):
        safe_name = Path(filename).name
        target = SESSIONS_PATH / safe_name
        if not target.exists():
            return jsonify({"ok": False, "message": "Sesja nie istnieje."}), 404
        data = json.loads(target.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "session": data, "file": safe_name})

    @app.get("/api/game-log")
    def api_game_log():
        logs = GameLog.list_logs()
        latest = logs[0] if logs else None
        if not latest:
            return jsonify({"logs": [], "latest": ""})
        tail = GameLog.tail(latest, limit=config.GAME_LOG_TAIL_DEFAULT)
        return jsonify({"latest": latest.name, "logs": tail})

    @app.get("/api/discord")
    def api_discord_status():
        return jsonify(_discord_status())

    @app.post("/api/bot/start")
    def api_bot_start():
        ok, message = manager.start()
        return jsonify({"ok": ok, "message": message}), (200 if ok else 409)

    @app.post("/api/bot/stop")
    def api_bot_stop():
        ok, message = manager.stop()
        return jsonify({"ok": ok, "message": message}), (200 if ok else 409)

    @app.post("/api/bot/force")
    def api_bot_force():
        flag_path = Path(config.FORCE_TURN_FLAG)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.touch()
        return jsonify({"ok": True, "message": "Sygnał wymuszonej odpowiedzi wysłany."})

    @app.get("/api/bot/mode")
    def api_get_mode():
        muted = Path(config.MIC_MUTE_FLAG).exists()
        return jsonify({"mode": "chat" if muted else "voice", "mic_muted": muted})

    @app.post("/api/bot/mode")
    def api_set_mode():
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", "")).strip().lower()
        if mode not in {"voice", "chat"}:
            return jsonify({"ok": False, "message": "Tryb musi być 'voice' lub 'chat'."}), 400
        flag_path = Path(config.MIC_MUTE_FLAG)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "chat":
            flag_path.touch()
        else:
            flag_path.unlink(missing_ok=True)
        return jsonify({"ok": True, "mode": mode, "mic_muted": mode == "chat"})

    @app.get("/api/bot/activity")
    def api_bot_activity():
        game_logs = GameLog.list_logs()
        if not game_logs:
            return jsonify({"status": "unknown", "detail": "", "actor": "", "event": ""})
        tail = GameLog.tail(game_logs[0], limit=8)
        for entry in reversed(tail):
            p = entry.get("payload", {})
            status = p.get("status", "")
            if status and status not in ("", "unknown"):
                return jsonify({
                    "status": status,
                    "detail": p.get("detail", ""),
                    "actor": p.get("actor", ""),
                    "event": p.get("event", entry.get("type", "")),
                    "ts": entry.get("timestamp", ""),
                })
        return jsonify({"status": "unknown", "detail": "", "actor": "", "event": ""})

    @app.get("/api/memory")
    def api_get_memory():
        data, error = _safe_read_json(GENERAL_CONTEXT_PATH)
        return jsonify({"exists": GENERAL_CONTEXT_PATH.exists(), "data": data or {}, "error": error})

    @app.post("/api/memory")
    def api_save_memory():
        payload = request.get_json(silent=True) or {}
        data = payload.get("data")
        if not isinstance(data, dict):
            return jsonify({"ok": False, "message": "Pole 'data' musi być obiektem JSON."}), 400
        _safe_write_json(GENERAL_CONTEXT_PATH, data)
        return jsonify({"ok": True, "message": "Pamięć ogólna zapisana."})

    @app.post("/api/chat/message")
    def api_chat_message():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        speaker = str(payload.get("speaker", "gracz")).strip() or "gracz"
        if not text:
            return jsonify({"ok": False, "message": "Brak treści wiadomości."}), 400

        queue_path = Path(config.CHAT_QUEUE_FILE)
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        entry_q = json.dumps({"text": text, "speaker": speaker}, ensure_ascii=False)
        with open(queue_path, "a", encoding="utf-8") as fq:
            fq.write(entry_q + "\n")

        history_path = Path(config.CHAT_HISTORY_FILE)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        import datetime as _dt
        entry_h = json.dumps({
            "role": "user",
            "speaker": speaker,
            "text": text,
            "ts": _dt.datetime.utcnow().isoformat() + "Z",
        }, ensure_ascii=False)
        with open(history_path, "a", encoding="utf-8") as fh:
            fh.write(entry_h + "\n")

        flag_path = Path(config.FORCE_TURN_FLAG)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.touch()

        return jsonify({"ok": True, "message": "Wiadomość wysłana."})

    @app.get("/api/chat/history")
    def api_chat_history():
        history_path = Path(config.CHAT_HISTORY_FILE)
        user_msgs: list[dict] = []
        if history_path.exists():
            for raw in history_path.read_text(encoding="utf-8").splitlines():
                try:
                    user_msgs.append(json.loads(raw))
                except Exception:
                    pass

        game_logs = GameLog.list_logs()
        bot_msgs: list[dict] = []
        if game_logs:
            for entry in GameLog.tail(game_logs[0], limit=80):
                p = entry.get("payload", {})
                ev = p.get("event", entry.get("type", ""))
                if ev == "bot_response":
                    bot_msgs.append({
                        "role": "bot",
                        "speaker": p.get("actor", "bot"),
                        "text": p.get("detail", ""),
                        "ts": entry.get("timestamp", ""),
                    })

        combined = user_msgs + bot_msgs
        combined.sort(key=lambda x: x.get("ts", ""))
        return jsonify({"history": combined[-60:]})

    @app.delete("/api/chat/history")
    def api_clear_chat_history():
        history_path = Path(config.CHAT_HISTORY_FILE)
        if history_path.exists():
            history_path.unlink()
        return jsonify({"ok": True, "message": "Historia czatu wyczyszczona."})

    @app.get("/api/secrets")
    def api_list_secrets():
        return jsonify({"secrets": secrets_manager.list_secrets()})

    @app.post("/api/secrets")
    def api_add_secret():
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        text = str(payload.get("text", "")).strip()
        source = str(payload.get("source", "gm")).strip().lower() or "gm"
        if not text:
            return jsonify({"ok": False, "message": "Pole 'text' jest wymagane."}), 400
        entry = secrets_manager.add_text(title, text, source)
        return jsonify({"ok": True, "secret": entry})

    @app.post("/api/secrets/upload")
    def api_upload_secret():
        file = request.files.get("file")
        if not file:
            return jsonify({"ok": False, "message": "Nie przesłano pliku."}), 400
        title = request.form.get("title", "").strip()
        source = (request.form.get("source", "gm") or "gm").strip().lower()

        filename = Path(file.filename or "").name
        if not filename:
            return jsonify({"ok": False, "message": "Brak nazwy pliku."}), 400

        ext = Path(filename).suffix.lower()
        if ext not in secrets_manager.SUPPORTED_EXTS:
            return jsonify({
                "ok": False,
                "message": f"Nieobsługiwany typ pliku: {ext}. Obsługiwane: txt, pdf, png, jpg, jpeg, gif, webp",
            }), 400

        SECRETS_PATH.mkdir(parents=True, exist_ok=True)
        files_dir = SECRETS_PATH / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        dest = files_dir / filename
        file.save(dest)

        try:
            content = secrets_manager.extract_file_content(dest, config.OPENAI_API_KEY)
        except Exception as exc:
            content = f"[Błąd ekstrakcji: {exc}]"

        entry = secrets_manager.add_file(filename, content, title=title, source=source)
        return jsonify({"ok": True, "secret": entry})

    @app.delete("/api/secrets/<path:secret_id>")
    def api_delete_secret(secret_id: str):
        deleted = secrets_manager.delete(secret_id)
        if not deleted:
            return jsonify({"ok": False, "message": "Sekret nie istnieje."}), 404
        return jsonify({"ok": True, "message": "Sekret usunięty."})

    @app.post("/api/buffer/flush")
    def api_buffer_flush():
        flag_path = Path(config.BUFFER_FLUSH_FLAG)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.touch()
        return jsonify({"ok": True, "message": "Sygnał przepłukania buforu wysłany."})

    @app.get("/api/debug-dump")
    def api_debug_dump():
        env_file = _load_env_file()

        def _sanitize(d: dict) -> dict:
            out = {}
            for k, v in d.items():
                if "key" in k.lower() or "token" in k.lower() or "secret" in k.lower():
                    out[k] = "***" if v else ""
                else:
                    out[k] = v
            return out

        char_data, char_err = _safe_read_json(CHARACTER_PATH)
        pers_data, pers_err = _safe_read_json(PERSONALITY_PATH)
        mem_data, mem_err = _safe_read_json(GENERAL_CONTEXT_PATH)

        game_logs = GameLog.list_logs()
        game_log_entries: list = []
        if game_logs:
            game_log_entries = GameLog.tail(game_logs[0], limit=500)

        snap = manager.snapshot()
        buffer_current, buffer_entries = _get_buffer_snapshot(game_logs)

        # Full transcript: all bot_response + player speech from game log
        transcript = []
        for entry in game_log_entries:
            p = entry.get("payload", {})
            ev = p.get("event", entry.get("type", ""))
            if ev in ("bot_response",):
                transcript.append({
                    "t": entry.get("timestamp", ""),
                    "speaker": p.get("actor", "bot"),
                    "text": p.get("detail", ""),
                    "event": ev,
                })
            elif ev == "wait":
                bt = p.get("buffer_tail")
                if isinstance(bt, list) and bt:
                    last = bt[-1]
                    if last.get("speaker") not in (p.get("actor"), ""):
                        transcript.append({
                            "t": entry.get("timestamp", ""),
                            "speaker": last.get("speaker", "gracz"),
                            "text": last.get("text", ""),
                            "event": "player_speech",
                        })

        dump = {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "python_version": sys.version,
            "platform": platform.platform(),
            "bot_process": {
                "running": snap["running"],
                "pid": snap["pid"],
                "log_tail": snap["logs"][-200:],
            },
            "env_file": _sanitize(env_file),
            "character": {"data": char_data, "error": char_err, "exists": CHARACTER_PATH.exists()},
            "personality": {"data": pers_data, "error": pers_err, "exists": PERSONALITY_PATH.exists()},
            "context_general": {"data": mem_data, "error": mem_err, "exists": GENERAL_CONTEXT_PATH.exists()},
            "live_buffer": buffer_entries,
            "transcript": transcript,
            "game_log": {
                "file": str(game_logs[0]) if game_logs else None,
                "entries": game_log_entries,
                "total_files": len(game_logs),
            },
            "sessions": SessionMemory().list_sessions()[:10],
            "game_files": _list_game_files(),
            "config_snapshot": {
                "WHISPER_MODEL": config.WHISPER_MODEL,
                "WHISPER_ENERGY_THRESHOLD": config.WHISPER_ENERGY_THRESHOLD,
                "WHISPER_INSECURE_SSL": config.WHISPER_INSECURE_SSL,
                "SILENCE_THRESHOLD_SEC": config.SILENCE_THRESHOLD_SEC,
                "BUFFER_MAX_EXCHANGES": config.BUFFER_MAX_EXCHANGES,
                "BUFFER_FLUSH_THRESHOLD": config.BUFFER_FLUSH_THRESHOLD,
                "RESPONSE_MODE": config.RESPONSE_MODE,
                "TTS_BACKEND": config.TTS_BACKEND,
                "TTS_VOICE": config.TTS_VOICE,
                "GAME_LOG_ENABLED": config.GAME_LOG_ENABLED,
                "DISCORD_ENABLED": config.DISCORD_ENABLED,
                "AGENT_MODEL": config.AGENT_MODEL,
                "CLASSIFIER_MODEL": config.CLASSIFIER_MODEL,
            },
        }

        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        raw = json.dumps(dump, ensure_ascii=False, indent=2, default=str)
        return Response(
            raw,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="rpg_debug_{ts}.json"'},
        )

    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("RPG_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("RPG_WEB_PORT", "8080"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
