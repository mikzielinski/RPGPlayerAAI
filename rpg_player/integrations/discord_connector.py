"""Discord bridge used by CLI and web management panel."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from rpg_player import config


@dataclass
class DiscordState:
    enabled: bool = False
    running: bool = False
    connected: bool = False
    guild: str = ""
    text_channel: str = ""
    voice_channel: str = ""
    known_users: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_error: str = ""


class DiscordConnector:
    """Lightweight Discord integration with runtime controls."""

    def __init__(
        self,
        token: str | None = None,
        guild_id: str | None = None,
        text_channel_id: str | None = None,
        voice_channel_id: str | None = None,
        enabled: bool | None = None,
        max_messages: int = 200,
    ) -> None:
        self._token = (token if token is not None else config.DISCORD_BOT_TOKEN).strip()
        self._guild_id = (guild_id if guild_id is not None else config.DISCORD_GUILD_ID).strip()
        self._text_channel_id = (
            text_channel_id if text_channel_id is not None else config.DISCORD_TEXT_CHANNEL_ID
        ).strip()
        self._voice_channel_id = (
            voice_channel_id if voice_channel_id is not None else config.DISCORD_VOICE_CHANNEL_ID
        ).strip()
        self._enabled = config.DISCORD_ENABLED if enabled is None else bool(enabled)
        self._max_messages = max_messages

        self._state = DiscordState(enabled=bool(self._enabled))
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None
        self._text_channel = None

    @property
    def enabled(self) -> bool:
        return bool(self._enabled and self._token)

    def update_config(
        self,
        *,
        token: str | None = None,
        guild_id: str | None = None,
        text_channel_id: str | None = None,
        voice_channel_id: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Update connector config. Restart externally if already running."""
        if token is not None:
            self._token = str(token).strip()
        if guild_id is not None:
            self._guild_id = str(guild_id).strip()
        if text_channel_id is not None:
            self._text_channel_id = str(text_channel_id).strip()
        if voice_channel_id is not None:
            self._voice_channel_id = str(voice_channel_id).strip()
        if enabled is not None:
            self._enabled = bool(enabled)
        with self._lock:
            self._state.enabled = bool(self._enabled)

    def _push_message(self, author: str, text: str, channel: str = "") -> None:
        payload = {
            "time": datetime.utcnow().isoformat(),
            "author": author,
            "text": text,
            "channel": channel,
        }
        with self._lock:
            self._state.messages.append(payload)
            if len(self._state.messages) > self._max_messages:
                self._state.messages = self._state.messages[-self._max_messages :]

    def start(self) -> tuple[bool, str]:
        if not self._enabled:
            return False, "DISCORD_ENABLED=0."
        if not self._token:
            return False, "Brak DISCORD_BOT_TOKEN."
        if self._thread and self._thread.is_alive():
            return False, "Discord bot juz dziala."
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_client, daemon=True)
        self._thread.start()
        with self._lock:
            self._state.running = True
            self._state.last_error = ""
        return True, "Uruchamiam Discord bota."

    def stop(self) -> tuple[bool, str]:
        was_running = bool(self._thread and self._thread.is_alive())
        self._stop_event.set()
        if self._loop and self._client:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                fut.result(timeout=5)
            except Exception:
                pass
        with self._lock:
            self._state.running = False
            self._state.connected = False
        return (True, "Discord bot zatrzymany.") if was_running else (False, "Discord bot nie dziala.")

    def get_state_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._state.enabled,
                "running": self._state.running,
                "connected": self._state.connected,
                "guild": self._state.guild,
                "text_channel": self._state.text_channel,
                "voice_channel": self._state.voice_channel,
                "known_users": list(self._state.known_users),
                "messages": list(self._state.messages)[-60:],
                "last_error": self._state.last_error,
            }

    def get_state(self) -> dict[str, Any]:
        """Backward-compatible alias."""
        return self.get_state_snapshot()

    def _remember_user(self, user_name: str) -> None:
        cleaned = (user_name or "").strip()
        if not cleaned:
            return
        with self._lock:
            if cleaned not in self._state.known_users:
                self._state.known_users.append(cleaned)

    def update_presence(self, known_players: list[str]) -> None:
        for name in known_players:
            self._remember_user(name)

    def attach_registry(self, _registry) -> None:
        """No-op in this version; kept for compatibility."""
        return

    async def _send_text(self, text: str) -> None:
        if not self._text_channel:
            return
        await self._text_channel.send(text)

    def send_bot_message(self, text: str) -> None:
        self.relay_bot_message(text)

    def relay_bot_message(self, text: str) -> None:
        self._push_message("bot", text, "outgoing")
        if not text.strip():
            return
        if not self._loop or not self._client or not self._text_channel:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_text(text), self._loop)
        except Exception:
            pass

    def send_message(self, text: str) -> tuple[bool, str]:
        """Manual message used by web control panel."""
        text = (text or "").strip()
        if not text:
            return False, "Wiadomosc jest pusta."
        if not self._loop or not self._client or not self._text_channel:
            return False, "Discord bot nie jest polaczony z kanalem tekstowym."
        self._push_message("panel", text, "manual")
        try:
            asyncio.run_coroutine_threadsafe(self._send_text(text), self._loop)
            return True, "Wiadomosc wyslana na Discord."
        except Exception as exc:
            with self._lock:
                self._state.last_error = str(exc)
            return False, f"Blad wysylki: {exc}"

    def ask_for_introductions(self) -> tuple[bool, str]:
        intro = (
            "Czesc! Jestem RPG AI Player Bot. Napiszcie prosze: "
            "'Jestem <imie>, gram <postac>', zebym mogl mapowac gracz -> postac."
        )
        return self.send_message(intro)

    def _run_client(self) -> None:
        try:
            import discord  # optional dependency
        except Exception as exc:
            with self._lock:
                self._state.last_error = f"discord.py missing: {exc}"
                self._state.running = False
                self._state.connected = False
            return

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True
        intents.members = True

        connector = self

        class _BotClient(discord.Client):
            async def on_ready(self):
                guild = None
                if connector._guild_id:
                    try:
                        guild = self.get_guild(int(connector._guild_id))
                    except Exception:
                        guild = None
                if guild is None and self.guilds:
                    guild = self.guilds[0]
                if guild is None:
                    with connector._lock:
                        connector._state.last_error = "No guild available"
                    return

                text_channel = None
                if connector._text_channel_id:
                    try:
                        text_channel = guild.get_channel(int(connector._text_channel_id))
                    except Exception:
                        text_channel = None
                if text_channel is None:
                    text_channel = next(
                        (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
                        None,
                    )

                voice_channel = None
                if connector._voice_channel_id:
                    try:
                        voice_channel = guild.get_channel(int(connector._voice_channel_id))
                    except Exception:
                        voice_channel = None

                with connector._lock:
                    connector._state.connected = True
                    connector._state.guild = guild.name
                    connector._state.text_channel = text_channel.name if text_channel else ""
                    connector._state.voice_channel = voice_channel.name if voice_channel else ""
                    connector._state.last_error = ""
                connector._text_channel = text_channel
                connector._refresh_voice_members(voice_channel)

            async def on_message(self, message):
                if message.author.bot:
                    return
                content = (message.content or "").strip()
                if not content:
                    return
                speaker = message.author.display_name
                connector._remember_user(speaker)
                connector._push_message(
                    speaker,
                    content,
                    channel=getattr(message.channel, "name", "text"),
                )

            async def on_voice_state_update(self, member, before, after):
                if member.bot:
                    return
                voice_ch = after.channel or before.channel
                if voice_ch:
                    connector._refresh_voice_members(voice_ch)

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
            try:
                self._loop.run_until_complete(client.close())
            except Exception:
                pass
            with self._lock:
                self._state.running = False
                self._state.connected = False
            self._client = None
            self._text_channel = None
            self._loop = None

    def _refresh_voice_members(self, voice_channel) -> None:
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
