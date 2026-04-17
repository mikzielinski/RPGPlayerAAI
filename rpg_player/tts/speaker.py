"""TTS abstraction supporting Edge TTS (default) and Kokoro TTS backends."""
from __future__ import annotations

import asyncio
import io
import random
import tempfile
from pathlib import Path
from typing import Optional

from rpg_player import config


class Speaker:
    def __init__(self, backend: str | None = None, voice: str | None = None):
        self._backend = backend or config.TTS_BACKEND
        self._voice = voice or config.TTS_VOICE
        self._kokoro_pipeline = None

        if self._backend == "kokoro":
            self._init_kokoro()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Blocking TTS playback."""
        asyncio.run(self.speak_async(text))

    async def speak_async(self, text: str) -> None:
        """Non-blocking TTS playback (awaitable)."""
        if self._backend == "kokoro":
            await self._speak_kokoro(text)
        else:
            await self._speak_edge(text)

    def set_voice_style(self, style: str) -> None:
        """Hook for future NPC voice differentiation — updates internal voice hint."""
        self._voice_style_hint = style

    # ------------------------------------------------------------------
    # Edge TTS backend
    # ------------------------------------------------------------------

    async def _speak_edge(self, text: str) -> None:
        import edge_tts
        import sounddevice as sd
        import soundfile as sf

        communicate = edge_tts.Communicate(text, self._voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        if not audio_bytes:
            return

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            data, samplerate = sf.read(tmp_path, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Kokoro TTS backend
    # ------------------------------------------------------------------

    def _init_kokoro(self) -> None:
        try:
            from kokoro_onnx import Kokoro
            model_path = Path("data/kokoro-v0_19.onnx")
            voices_path = Path("data/voices.json")
            if not model_path.exists():
                raise FileNotFoundError(
                    "Kokoro model not found at data/kokoro-v0_19.onnx. "
                    "Download it manually or switch TTS_BACKEND to 'edge'."
                )
            self._kokoro_pipeline = Kokoro(str(model_path), str(voices_path))
        except ImportError:
            raise ImportError(
                "kokoro-onnx is not installed. Run: pip install kokoro-onnx"
            )

    async def _speak_kokoro(self, text: str) -> None:
        import sounddevice as sd
        import numpy as np

        loop = asyncio.get_event_loop()
        samples, sample_rate = await loop.run_in_executor(
            None,
            lambda: self._kokoro_pipeline.create(text, voice="pl_pl", speed=1.0, lang="pl"),
        )
        sd.play(samples, sample_rate)
        sd.wait()
