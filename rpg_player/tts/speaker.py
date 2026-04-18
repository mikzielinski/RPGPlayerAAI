"""TTS abstraction supporting Edge TTS (default) and Kokoro TTS backends.

Edge TTS prosody (rate/pitch) is adjusted automatically based on detected
emotion keywords in the spoken text.  Call next_voice() to cycle through
AVAILABLE_VOICES at runtime (bound to 'v' key in main loop).
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from rpg_player import config

# Keyword → emotion mapping for Edge TTS prosody adjustment
_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "anger": [
        "kurwa", "cholera", "do diabła", "wkurwiony", "wkurwiona",
        "wściekły", "wściekła", "nie do wiary", "przeklinam", "idiot",
    ],
    "fear": [
        "boję się", "strach", "przerażony", "przerażona",
        "zaraz zginiemy", "uciekaj", "ratunku", "ucieka",
    ],
    "joy": [
        "tak!", "niesamowite", "super", "hura", "cudownie",
        "brawo", "udało się", "wygraliśmy", "trafienie!", "świetnie",
    ],
    "sadness": [
        "niestety", "smutno", "przykro mi", "straciliśmy",
        "padł", "umarł", "szkoda", "zginął", "przegraliśmy",
    ],
}


def _detect_emotion(text: str) -> str:
    lower = text.lower()
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return emotion
    return "neutral"


class Speaker:
    def __init__(self, backend: str | None = None, voice: str | None = None):
        self._backend = (backend or config.TTS_BACKEND).strip().lower()
        available = config.AVAILABLE_VOICES or [config.TTS_VOICE]
        initial = voice or config.TTS_VOICE
        self._voice_index = available.index(initial) if initial in available else 0
        self._kokoro_pipeline = None

        if self._backend == "kokoro":
            self._init_kokoro()

    # ------------------------------------------------------------------
    # Voice management
    # ------------------------------------------------------------------

    @property
    def current_voice(self) -> str:
        available = config.AVAILABLE_VOICES or [config.TTS_VOICE]
        return available[self._voice_index % len(available)]

    @property
    def backend(self) -> str:
        return self._backend

    def set_voice(self, voice: str) -> str:
        """Set a specific voice directly and return active voice."""
        voice = (voice or "").strip()
        if not voice:
            return self.current_voice

        available = config.AVAILABLE_VOICES or [config.TTS_VOICE]
        if voice in available:
            self._voice_index = available.index(voice)
            return self.current_voice

        # For backends with open voice catalogs (e.g. edge/openai), allow direct custom id.
        if self._backend in {"edge", "openai"}:
            updated = list(available)
            updated.append(voice)
            config.AVAILABLE_VOICES = updated
            self._voice_index = len(updated) - 1
            return self.current_voice

        return self.current_voice

    def next_voice(self) -> str:
        """Cycle to the next voice in AVAILABLE_VOICES and return its name."""
        available = config.AVAILABLE_VOICES or [config.TTS_VOICE]
        self._voice_index = (self._voice_index + 1) % len(available)
        return self.current_voice

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
        elif self._backend == "openai":
            await self._speak_openai(text)
        else:
            await self._speak_edge(text)

    def set_voice_style(self, style: str) -> None:
        """Hook for NPC voice differentiation — updates internal voice hint."""
        self._voice_style_hint = style

    # ------------------------------------------------------------------
    # Edge TTS backend
    # ------------------------------------------------------------------

    async def _speak_edge(self, text: str) -> None:
        import edge_tts
        import sounddevice as sd
        import soundfile as sf

        emotion = _detect_emotion(text)
        params = config.EMOTION_VOICE_PARAMS.get(
            emotion, config.EMOTION_VOICE_PARAMS.get("neutral", {})
        )

        communicate = edge_tts.Communicate(
            text,
            self.current_voice,
            rate=params.get("rate", "+0%"),
            pitch=params.get("pitch", "+0Hz"),
        )
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
    # OpenAI TTS backend
    # ------------------------------------------------------------------

    async def _speak_openai(self, text: str) -> None:
        import sounddevice as sd
        import soundfile as sf
        from openai import OpenAI

        emotion = _detect_emotion(text)
        speed = config.OPENAI_TTS_EMOTION_SPEED.get(
            emotion, config.OPENAI_TTS_EMOTION_SPEED.get("neutral", 1.0)
        )
        client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TIMEOUT_SEC,
            max_retries=config.OPENAI_MAX_RETRIES,
        )
        audio_format = (config.OPENAI_TTS_FORMAT or "mp3").strip().lower()
        if audio_format not in config.OPENAI_TTS_ALLOWED_FORMATS:
            audio_format = "mp3"

        # audio.speech.create is sync; run in executor to keep async flow.
        loop = asyncio.get_running_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            lambda: client.audio.speech.create(
                model=config.OPENAI_TTS_MODEL,
                voice=self.current_voice or config.OPENAI_TTS_VOICE,
                input=text,
                format=audio_format,
                speed=float(speed),
            ).read(),
        )
        if not audio_bytes:
            return

        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
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
        import asyncio
        import sounddevice as sd

        loop = asyncio.get_event_loop()
        samples, sample_rate = await loop.run_in_executor(
            None,
            lambda: self._kokoro_pipeline.create(text, voice="pl_pl", speed=1.0, lang="pl"),
        )
        sd.play(samples, sample_rate)
        sd.wait()
