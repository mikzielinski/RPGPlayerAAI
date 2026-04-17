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

from flask import Flask, jsonify, render_template, request

from rpg_player import config
from rpg_player.session.session_memory import SessionMemory


REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
ENV_PATH = REPO_ROOT / ".env"

CHARACTER_PATH = Path(config.CHARACTER_FILE)
PERSONALITY_PATH = Path(config.PERSONALITY_FILE)
GAME_FILES_PATH = Path(config.GAME_FILES_DIR)
CHROMA_PATH = Path(config.CHROMA_DIR)
SESSIONS_PATH = Path(config.SESSIONS_DIR)

SUPPORTED_GAME_EXTENSIONS = {".pdf", ".docx", ".xlsx"}


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
        self._logs: deque[str] = deque(maxlen=800)
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
        return {"running": running, "pid": pid, "logs": list(self._logs)[-300:]}


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
    return {
        "bot": process_manager.snapshot(),
        "paths": {
            "character": str(CHARACTER_PATH),
            "personality": str(PERSONALITY_PATH),
            "game_files": str(GAME_FILES_PATH),
            "chroma": str(CHROMA_PATH),
            "sessions": str(SESSIONS_PATH),
        },
        "flags": {
            "has_character": CHARACTER_PATH.exists(),
            "has_personality": PERSONALITY_PATH.exists(),
            "has_openai_key": bool(effective_env.get("OPENAI_API_KEY", "").strip()),
            "game_files_count": len(_list_game_files()),
            "sessions_count": len(sessions),
        },
        "env": {
            "openai_api_key_masked": _mask_key(effective_env.get("OPENAI_API_KEY", "")),
            "swearing_intensity": env_file.get("SWEARING_INTENSITY", config.SWEARING_INTENSITY),
            "game_files_confirmed": env_file.get("GAME_FILES_CONFIRMED", "0"),
            "response_mode": response_mode,
            "allow_proactive_speak_up": allow_speak_up,
            "enable_additional_ai_players": additional_players_enabled,
        },
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
        swearing = payload.get("swearing_intensity")
        response_mode = payload.get("response_mode")
        allow_speak_up = payload.get("allow_proactive_speak_up")
        enable_extra_players = payload.get("enable_additional_ai_players")
        updates: dict[str, str | None] = {}

        if key is not None:
            key = str(key).strip()
            updates["OPENAI_API_KEY"] = key if key else None

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

        if allow_speak_up is not None:
            updates["ALLOW_PROACTIVE_SPEAK_UP"] = "1" if _coerce_bool(allow_speak_up) else "0"

        if enable_extra_players is not None:
            updates["ENABLE_ADDITIONAL_AI_PLAYERS"] = "1" if _coerce_bool(enable_extra_players) else "0"

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

    @app.post("/api/bot/start")
    def api_bot_start():
        ok, message = manager.start()
        return jsonify({"ok": ok, "message": message}), (200 if ok else 409)

    @app.post("/api/bot/stop")
    def api_bot_stop():
        ok, message = manager.stop()
        return jsonify({"ok": ok, "message": message}), (200 if ok else 409)

    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("RPG_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("RPG_WEB_PORT", "8080"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
