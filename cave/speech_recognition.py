# speech_recognition.py
"""
Offline streaming Speech-to-Text engine (Vosk pt-BR) processing PCM audio chunks
from either the local Windows microphone or the mobile browser WebSocket stream.
"""

from __future__ import annotations

import json
import logging
import os
from threading import Lock
from typing import Callable, Optional

logger = logging.getLogger("cave.speech_recognition")

try:
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
except Exception:  # pragma: no cover
    KaldiRecognizer = None
    Model = None


class SpeechRecognitionEngine:
    """
    Processes 16kHz 16-bit mono PCM audio streams and emits partial and final
    Brazilian Portuguese transcriptions.
    """

    SAMPLE_RATE = 16000

    def __init__(
        self,
        model_path: str = "models/vosk-model-small-pt-0.3",
        on_partial_transcript: Optional[Callable[[str, str], None]] = None,
        on_final_transcript: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._model_path = model_path
        self._on_partial = on_partial_transcript
        self._on_final = on_final_transcript
        self._model: Optional[object] = None
        self._pc_recognizer: Optional[object] = None
        self._mobile_recognizer: Optional[object] = None
        self._lock = Lock()
        self._initialized = False
        self._last_partial: str = ""

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        """Load the offline Vosk pt-BR acoustic model if present."""
        if Model is None or KaldiRecognizer is None:
            logger.warning(
                "Vosk package is not installed; server-side PCM recognition unavailable."
            )
            return False

        if not os.path.isdir(self._model_path):
            logger.warning(
                "Vosk model directory not found at '%s'. "
                "Mobile browser Web Speech API fallback remains active.",
                self._model_path,
            )
            return False

        try:
            with self._lock:
                self._model = Model(self._model_path)
                self._pc_recognizer = KaldiRecognizer(self._model, self.SAMPLE_RATE)
                self._mobile_recognizer = KaldiRecognizer(self._model, self.SAMPLE_RATE)
                self._initialized = True
            logger.info("Loaded offline Vosk pt-BR model from '%s'.", self._model_path)
            return True
        except Exception as exc:
            logger.error("Failed to initialize Vosk model: %s", exc)
            self._initialized = False
            return False

    def accept_pcm_chunk(self, pcm_bytes: bytes, source: str = "pc") -> None:
        """Feed a 16kHz 16-bit mono PCM chunk into the recognizer."""
        if not self._initialized:
            return

        with self._lock:
            recognizer = (
                self._mobile_recognizer if source == "mobile" else self._pc_recognizer
            )
            if recognizer is None:
                return

            try:
                is_final = recognizer.AcceptWaveform(pcm_bytes)
                if is_final:
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()
                    self._last_partial = ""
                    if text and self._on_final:
                        self._on_final(text, source)
                else:
                    partial_res = json.loads(recognizer.PartialResult())
                    partial_text = partial_res.get("partial", "").strip()
                    if partial_text and partial_text != self._last_partial:
                        self._last_partial = partial_text
                        if self._on_partial:
                            self._on_partial(partial_text, source)
            except Exception as exc:
                logger.error("Error processing PCM audio chunk: %s", exc)

    def reset(self) -> None:
        """Reset recognizer buffers after mode transitions."""
        with self._lock:
            self._last_partial = ""
            if self._initialized and self._model is not None:
                self._pc_recognizer = KaldiRecognizer(self._model, self.SAMPLE_RATE)
                self._mobile_recognizer = KaldiRecognizer(self._model, self.SAMPLE_RATE)