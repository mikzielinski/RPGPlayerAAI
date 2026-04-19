"""Discord integration: text relay + full bidirectional voice (optional).

Voice mode (DISCORD_TEXT_ONLY=0):
  - Bot joins voice channel and listens via discord-ext-voice-recv + Whisper
  - Bot speaks responses via edge-tts streamed through FFmpegPCMAudio

Text-only mode (DISCORD_TEXT_ONLY=1, default):
  - Bot reads/writes text channel only, no audio I/O
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
import tempfile
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from rpg_player import config
from rpg_player.session.speaker_registry import SpeakerRegistry


# ---------------------------------------------------------------------------
# Transcription validation (mirrors listener.py — kept local to avoid circular import)
# ---------------------------------------------------------------------------

_NON_LATIN_RE = re.compile(
    r"[\u2E80-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF"
    r"\u3000-\u303F\u0600-\u06FF\u0900-\u097F"
    r"\u0E00-\u0E7F\u1100-\u11FF]"
)
_HALLUCINATION_PHRASES = re.compile(
    r"(napisy\s+wykona|subskrybuj|subscribe|przetłumaczon|tłumacz:|lektor:|"
    r"music playing|applause|inaudible|\[.*?\]|\(.*?\))",
    re.IGNORECASE,
)


def _is_valid_transcription(text: str) -> bool:
    if not text:
        return False
    if _NON_LATIN_RE.search(text):
        return False
    alpha = sum(1 for ch in text if ch.isalpha())
    if alpha / max(len(text), 1) < 0.30:
        return False
    if _HALLUCINATION_PHRASES.search(text):
        return False
    return True


# ---------------------------------------------------------------------------
# Per-user voice buffer: VAD + Whisper ASR for Discord audio packets
# ---------------------------------------------------------------------------

class _UserVoiceBuffer:
    """Buffers 20 ms PCM packets per Discord user, detects utterances, transcribes."""

    _DISCORD_SR = 48_000   # Discord: 48 kHz stereo, 20 ms/packet → 960 samples/ch
    _WHISPER_SR = 16_000

    def __init__(self, connector: "DiscordConnector", model: Any) -> None:
        self._connector = connector
        self._model = model
        self._frames: dict[int, list[np.ndarray]] = {}
        self._silent: dict[int, int] = {}
        self._lock = threading.Lock()
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="discord-asr"
        )

    def write(self, user: Any, pcm: bytes) -> None:
        if user is None or getattr(user, "bot", False) or not pcm:
            return
        uid: int = user.id
        username: str = user.display_name

        raw = np.frombuffer(pcm, dtype=np.int16)
        n = (len(raw) // 2) * 2
        if n == 0:
            return
        # Stereo interleaved → mono average
        mono = raw[:n].reshape(-1, 2).mean(axis=1).astype(np.int16)
        rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2)))

        # 960 mono samples per 20 ms packet at 48 kHz
        samples_per_pkt = self._DISCORD_SR // 50
        silence_limit = max(1, int(config.SILENCE_THRESHOLD_SEC * self._DISCORD_SR / samples_per_pkt))
        min_pkts = silence_limit * 2

        with self._lock:
            if uid not in self._frames:
                self._frames[uid] = []
                self._silent[uid] = 0

            self._frames[uid].append(mono)

            if rms < config.WHISPER_ENERGY_THRESHOLD:
                self._silent[uid] += 1
                if self._silent[uid] >= silence_limit and len(self._frames[uid]) > min_pkts:
                    frames = self._frames.pop(uid)
                    self._silent[uid] = 0
                    self._pool.submit(self._transcribe, username, frames)
            else:
                self._silent[uid] = 0

    def _transcribe(self, username: str, frames: list[np.ndarray]) -> None:
        audio_48k = np.concatenate(frames).astype(np.float32) / 32768.0
        n_out = int(len(audio_48k) * self._WHISPER_SR / self._DISCORD_SR)
        if n_out < 800:  # < 50 ms at 16 kHz — too short to be real speech
            return
        audio_16k = np.interp(
            np.linspace(0, len(audio_48k) - 1, n_out),
            np.arange(len(audio_48k)),
            audio_48k,
        )
        try:
            result = self._model.transcribe(
                audio_16k,
                language=config.WHISPER_LANGUAGE,
                fp16=False,
                initial_prompt=config.WHISPER_INITIAL_PROMPT,
            )
            text = result["text"].strip()
            if len(text.split()) < 2 or not _is_valid_transcription(text):
                return
            self._connector._push_message({
                "time": self._connector._utc_iso(),
                "author": username,
                "text": text,
                "channel": "voice",
            })
            if self._connector._registry:
                detected = self._connector._registry.process(text)
                if detected:
                    username = detected
            self._connector._remember_known_user(username)
            self._connector._queue_for_inject(username, text)
        except Exception:
            pass

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

@dataclass
class DiscordState:
    enabled: bool = False
    connected: bool = False
    guild: str = ""
    text_channel: str = ""
    voice_channel: str = ""
    known_users: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_error: str = ""


# ---------------------------------------------------------------------------
# Main connector
# ---------------------------------------------------------------------------

class DiscordConnector:
    """Discord bridge supporting text-only and full bidirectional voice modes."""

    def __init__(
        self,
        token: str | None = None,
        guild_id: str | None = None,
        text_channel_id: str | None = None,
        voice_channel_id: str | None = None,
        registry: Optional[SpeakerRegistry] = None,
        max_messages: int = 200,
        enabled: bool | None = None,
    ) -> None:
        self._token = (token if token is not None else config.DISCORD_BOT_TOKEN).strip()
        self._guild_id = (guild_id if guild_id is not None else config.DISCORD_GUILD_ID).strip()
        self._text_channel_id = (text_channel_id if text_channel_id is not None else config.DISCORD_TEXT_CHANNEL_ID).strip()
        self._voice_channel_id = (voice_channel_id if voice_channel_id is not None else config.DISCORD_VOICE_CHANNEL_ID).strip()
        self._registry = registry
        self._max_messages = max_messages
        self._enabled = config.DISCORD_ENABLED if enabled is None else bool(enabled)

        self._state = DiscordState(enabled=bool(self._enabled and self._token))
        self._lock = threading.Lock()
        self._pending: deque[dict] = deque()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None
        self._text_channel = None
        self._voice_client = None

        self._whisper_model: Any = None
        self._voice_buf: Optional[_UserVoiceBuffer] = None

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._enabled and self._token)

    @property
    def has_voice(self) -> bool:
        """True when connected to a voice channel and ready to play audio."""
        vc = self._voice_client
        return vc is not None and getattr(vc, "is_connected", lambda: False)()

    # ── Attach helpers ───────────────────────────────────────────────────────

    def attach_registry(self, registry: SpeakerRegistry) -> None:
        self._registry = registry

    def attach_whisper_model(self, model: Any) -> None:
        """Reuse the already-loaded Whisper model from main for voice RX."""
        self._whisper_model = model

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _push_message(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._state.messages.append(payload)
            if len(self._state.messages) > self._max_messages:
                self._state.messages = self._state.messages[-self._max_messages:]

    @staticmethod
    def _utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _remember_known_user(self, name: str) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        with self._lock:
            if cleaned not in self._state.known_users:
                self._state.known_users.append(cleaned)

    def _snapshot_known_users(self) -> list[str]:
        with self._lock:
            return list(self._state.known_users)

    def _refresh_voice_members(self, voice_channel: Any) -> None:
        if not voice_channel:
            return
        names = []
        try:
            for member in voice_channel.members:
                if not member.bot:
                    names.append(member.display_name)
        except Exception:
            return
        with self._lock:
            self._state.known_users = sorted(set(self._state.known_users + names))

    # ── Pending message queue ────────────────────────────────────────────────

    def _queue_for_inject(self, speaker: str, text: str) -> None:
        with self._lock:
            self._pending.append({"speaker": speaker, "text": text})

    def pop_pending_messages(self) -> list[dict]:
        with self._lock:
            msgs = list(self._pending)
            self._pending.clear()
            return msgs

    # ── Text channel messaging ───────────────────────────────────────────────

    def relay_bot_message(self, text: str) -> None:
        if not self.enabled or not self._loop or not self._client or not self._text_channel:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._text_channel.send(text), self._loop)
        except Exception:
            pass

    def send_bot_message(self, text: str) -> None:
        self.relay_bot_message(text)

    def ask_for_introductions(self) -> None:
        self._push_message({
            "time": self._utc_iso(),
            "author": "system",
            "text": "Prosba o przedstawienie: imie gracza + postac.",
            "channel": "system",
        })

    def update_presence(self, known_players: list[str]) -> None:
        for name in known_players:
            self._remember_known_user(name)

    # ── Voice channel TTS (TX) ───────────────────────────────────────────────

    def speak_in_voice_channel(self, text: str) -> None:
        """Generate TTS audio via edge-tts and play it in the Discord voice channel.

        Blocks until playback finishes, mirroring local tts.speak() behaviour.
        """
        if not self.has_voice or not self._loop:
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self._speak_voice_async(text), self._loop
            )
            fut.result(timeout=90)
        except Exception:
            pass

    async def _speak_voice_async(self, text: str) -> None:
        vc = self._voice_client
        if not vc or not vc.is_connected():
            return

        while vc.is_playing():
            await asyncio.sleep(0.1)

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice=config.TTS_VOICE)
            await communicate.save(tmp.name)

            done = asyncio.Event()

            def _after(error: Exception | None) -> None:
                done.set()

            import discord as _discord
            source = _discord.FFmpegPCMAudio(tmp.name)
            vc.play(source, after=_after)
            await done.wait()
        except Exception:
            pass
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    # ── State ────────────────────────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._state.enabled,
                "connected": self._state.connected,
                "guild": self._state.guild,
                "text_channel": self._state.text_channel,
                "voice_channel": self._state.voice_channel,
                "known_users": list(self._state.known_users),
                "messages": list(self._state.messages)[-60:],
                "last_error": self._state.last_error,
                "voice_rx": self._voice_buf is not None,
                "voice_tx": self.has_voice,
            }

    def get_state_snapshot(self) -> dict[str, Any]:
        return self.get_state()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_client, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._client:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                fut.result(timeout=5)
            except Exception:
                pass
        if self._voice_buf:
            self._voice_buf.shutdown()
        with self._lock:
            self._state.connected = False

    # ── Discord client thread ────────────────────────────────────────────────

    def _run_client(self) -> None:
        try:
            import discord
        except ImportError as exc:
            with self._lock:
                self._state.last_error = f"discord.py missing: {exc}"
            return

        # Optionally load voice receive extension
        voice_recv = None
        if not config.DISCORD_TEXT_ONLY and self._whisper_model is not None:
            try:
                from discord.ext import voice_recv as _vr
                voice_recv = _vr
            except ImportError:
                with self._lock:
                    self._state.last_error = (
                        "discord-ext-voice-recv not installed — voice RX unavailable. "
                        "Run: pip install discord-ext-voice-recv"
                    )

        connector = self
        voice_sink_obj = None

        if voice_recv and self._whisper_model:
            buf = _UserVoiceBuffer(connector, connector._whisper_model)
            connector._voice_buf = buf

            class _RPGSink(voice_recv.AudioSink):
                def wants_opus(self) -> bool:
                    return False  # request decoded PCM

                def write(self, user: Any, data: Any) -> None:
                    buf.write(user, data.pcm)

                def cleanup(self) -> None:
                    buf.shutdown()

            voice_sink_obj = _RPGSink()

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True
        intents.members = True

        class _BotClient(discord.Client):
            async def on_ready(self) -> None:
                guild = None
                if connector._guild_id:
                    guild = self.get_guild(int(connector._guild_id))
                if guild is None and self.guilds:
                    guild = self.guilds[0]
                if guild is None:
                    with connector._lock:
                        connector._state.last_error = "No guild available"
                    return

                text_channel = None
                if connector._text_channel_id:
                    text_channel = guild.get_channel(int(connector._text_channel_id))
                if text_channel is None:
                    text_channel = next(
                        (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                        None,
                    )

                voice_channel = None
                if connector._voice_channel_id:
                    voice_channel = guild.get_channel(int(connector._voice_channel_id))

                with connector._lock:
                    connector._state.connected = True
                    connector._state.guild = guild.name
                    connector._state.text_channel = text_channel.name if text_channel else ""
                    connector._state.voice_channel = voice_channel.name if voice_channel else ""
                    connector._state.last_error = ""

                connector._text_channel = text_channel
                connector._refresh_voice_members(voice_channel)

                # Join voice channel in full voice mode
                if voice_channel and not config.DISCORD_TEXT_ONLY:
                    try:
                        if voice_recv and voice_sink_obj:
                            vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                            vc.listen(voice_sink_obj)
                        else:
                            vc = await voice_channel.connect()
                        connector._voice_client = vc
                    except Exception as exc:
                        with connector._lock:
                            connector._state.last_error = f"Voice connect error: {exc}"

                if text_channel:
                    mode_hint = "tryb głosowy" if connector._voice_client else "tryb tekstowy"
                    intro = (
                        f"Czesc! Jestem RPG AI Player Bot ({mode_hint}). "
                        "Przedstawcie sie prosze: imie gracza + postac "
                        "(np. 'Jestem Ania, gram Lyra')."
                    )
                    try:
                        await text_channel.send(intro)
                    except Exception:
                        pass

            async def on_message(self, message: Any) -> None:
                if message.author.bot:
                    return
                content = (message.content or "").strip()
                if not content:
                    return
                speaker = message.author.display_name
                connector._push_message({
                    "time": connector._utc_iso(),
                    "author": speaker,
                    "text": content,
                    "channel": getattr(message.channel, "name", ""),
                })
                if connector._registry:
                    detected = connector._registry.process(content)
                    if detected:
                        speaker = detected
                connector._remember_known_user(speaker)
                connector._queue_for_inject(speaker, content)

            async def on_voice_state_update(self, member: Any, before: Any, after: Any) -> None:
                if member.bot:
                    return
                vc_ch = after.channel or before.channel
                if vc_ch:
                    connector._refresh_voice_members(vc_ch)

        client = _BotClient(intents=intents)
        self._client = client
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(client.start(self._token))
        except Exception as exc:
            with self._lock:
                self._state.last_error = str(exc)
                self._state.connected = False
        finally:
            if connector._voice_client:
                try:
                    self._loop.run_until_complete(connector._voice_client.disconnect())
                except Exception:
                    pass
            try:
                self._loop.run_until_complete(client.close())
            except Exception:
                pass
            with self._lock:
                self._state.connected = False
