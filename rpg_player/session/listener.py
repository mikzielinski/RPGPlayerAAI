"""Continuous Whisper STT stream with silence detection and rolling buffer."""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd
import whisper

from rpg_player import config

_SAMPLE_RATE = 16000
_CHANNELS = 1
_CHUNK_FRAMES = 1024


class Listener:
    def __init__(
        self,
        char_name: str = "Bot",
        model_name: str = config.WHISPER_MODEL,
        silence_sec: float = config.SILENCE_THRESHOLD_SEC,
        max_exchanges: int = config.BUFFER_MAX_EXCHANGES,
    ):
        self._char_name = char_name
        self._silence_sec = silence_sec
        self._max_exchanges = max_exchanges
        self._model = whisper.load_model(model_name)
        self._buffer: deque[dict] = deque()
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue()
        self._running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin continuous microphone capture in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_buffer(self) -> list[dict]:
        with self._lock:
            return list(self._buffer)

    def get_buffer_text(self) -> str:
        return "\n".join(
            f"[{e['speaker']}]: {e['text']}" for e in self.get_buffer()
        )

    def add_bot_turn(self, text: str) -> None:
        """Record bot's own spoken turn into the buffer."""
        self._append_exchange(self._char_name, text)

    def listen_once(self) -> str:
        """Blocking: capture audio until silence, transcribe, return text.

        Used during onboarding (not the streaming session loop).
        """
        frames: list[np.ndarray] = []
        silent_chunks = 0
        silence_limit = int(self._silence_sec * _SAMPLE_RATE / _CHUNK_FRAMES)
        energy_threshold = 300  # RMS threshold for silence detection

        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_CHUNK_FRAMES,
        ) as stream:
            while True:
                chunk, _ = stream.read(_CHUNK_FRAMES)
                chunk_np = np.frombuffer(chunk, dtype=np.int16)
                frames.append(chunk_np)
                rms = np.sqrt(np.mean(chunk_np.astype(np.float32) ** 2))
                if rms < energy_threshold:
                    silent_chunks += 1
                    if silent_chunks >= silence_limit and len(frames) > silence_limit:
                        break
                else:
                    silent_chunks = 0

        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        result = self._model.transcribe(audio, language="pl", fp16=False)
        return result["text"].strip()

    # ------------------------------------------------------------------
    # Capture loop (session mode)
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        frames: list[np.ndarray] = []
        silent_chunks = 0
        silence_limit = int(self._silence_sec * _SAMPLE_RATE / _CHUNK_FRAMES)
        energy_threshold = 300

        def callback(indata, frame_count, time_info, status):
            self._audio_q.put(indata.copy())

        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_CHUNK_FRAMES,
            callback=callback,
        ):
            while self._running:
                try:
                    chunk = self._audio_q.get(timeout=0.1)
                except queue.Empty:
                    continue

                chunk_np = chunk.flatten()
                frames.append(chunk_np)
                rms = np.sqrt(np.mean(chunk_np.astype(np.float32) ** 2))

                if rms < energy_threshold:
                    silent_chunks += 1
                    if silent_chunks >= silence_limit and len(frames) > silence_limit * 2:
                        # Utterance complete — transcribe
                        audio = np.concatenate(frames).astype(np.float32) / 32768.0
                        try:
                            result = self._model.transcribe(
                                audio, language="pl", fp16=False
                            )
                            text = result["text"].strip()
                            if text:
                                self._append_exchange("unknown", text)
                        except Exception as e:
                            print(f"[listener] Błąd transkrypcji: {e}")
                        finally:
                            frames = []
                            silent_chunks = 0
                else:
                    silent_chunks = 0

    def _append_exchange(self, speaker: str, text: str) -> None:
        with self._lock:
            self._buffer.append({"speaker": speaker, "text": text})
            while len(self._buffer) > self._max_exchanges:
                self._buffer.popleft()
