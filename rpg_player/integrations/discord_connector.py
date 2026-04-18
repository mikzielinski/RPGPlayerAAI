"""Discord integration (MVP): text relay + voice participant awareness."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from rpg_player import config
from rpg_player.session.speaker_registry import SpeakerRegistry


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


class DiscordConnector:
    """Very lightweight Discord bridge for text + presence.

    Notes:
    - Voice capture/synthesis streaming is intentionally out-of-scope for this MVP.
    - The connector runs a background discord.py client loop when enabled.
    """

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
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None
        self._text_channel = None

    @property
    def enabled(self) -> bool:
        return bool(self._enabled and self._token)

    def _push_message(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._state.messages.append(payload)
            if len(self._state.messages) > self._max_messages:
                self._state.messages = self._state.messages[-self._max_messages :]

    def _snapshot_known_users(self) -> list[str]:
        with self._lock:
            return list(self._state.known_users)

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
        with self._lock:
            self._state.connected = False

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
            }

    def get_state_snapshot(self) -> dict[str, Any]:
        """Backward-compatible alias used by web panel."""
        return self.get_state()

    def attach_registry(self, registry: SpeakerRegistry) -> None:
        """Attach runtime speaker registry after main loop init."""
        self._registry = registry

    def relay_bot_message(self, text: str) -> None:
        """Send bot message to text channel (fire-and-forget)."""
        if not self.enabled or not self._loop or not self._client or not self._text_channel:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._text_channel.send(text), self._loop)
        except Exception:
            # Non-fatal for gameplay
            pass

    def send_bot_message(self, text: str) -> None:
        """Alias used by main loop."""
        self.relay_bot_message(text)

    def ask_for_introductions(self) -> None:
        """Ask Discord participants to map player -> character."""
        self._push_message(
            {
                "time": datetime.utcnow().isoformat(),
                "author": "system",
                "text": "Prosba o przedstawienie: imie gracza + postac.",
                "channel": "system",
            }
        )

    def update_presence(self, known_players: list[str]) -> None:
        """Keep an in-memory list of active known players from runtime registry."""
        for name in known_players:
            self._remember_known_user(name)

    def _run_client(self) -> None:
        try:
            import discord  # local import: optional dependency
        except Exception as exc:
            with self._lock:
                self._state.last_error = f"discord.py missing: {exc}"
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

                if text_channel:
                    intro = (
                        "Czesc! Jestem RPG AI Player Bot. "
                        "Przedstawcie sie prosze: imie gracza + postac "
                        "(np. 'Jestem Ania, gram Lyra')."
                    )
                    try:
                        await text_channel.send(intro)
                    except Exception:
                        pass

            async def on_message(self, message):
                if message.author.bot:
                    return
                content = (message.content or "").strip()
                if not content:
                    return
                speaker = message.author.display_name
                connector._push_message(
                    {
                        "time": datetime.utcnow().isoformat(),
                        "author": speaker,
                        "text": content,
                        "channel": getattr(message.channel, "name", ""),
                    }
                )
                if connector._registry:
                    detected = connector._registry.process(content)
                    if detected:
                        speaker = detected
                connector._remember_known_user(speaker)

            async def on_voice_state_update(self, member, before, after):
                if member.bot:
                    return
                vc = after.channel or before.channel
                if vc:
                    connector._refresh_voice_members(vc)

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
                self._state.connected = False

    def _remember_known_user(self, name: str) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        with self._lock:
            if cleaned not in self._state.known_users:
                self._state.known_users.append(cleaned)

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
