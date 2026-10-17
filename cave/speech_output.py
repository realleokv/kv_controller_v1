# speech_output.py
"""
Thread-safe Text-to-Speech (TTS) engine supporting Brazilian Portuguese (SAPI5)
with microphone feedback-loop prevention.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from cave.command_registry import CommandRegistry

logger = logging.getLogger("cave.speech_output")

try:
    import pyttsx3
except Exception:  # pragma: no cover
    pyttsx3 = None


class SpeechOutputEngine:
    """
    Speaks concise responses in Brazilian Portuguese on a dedicated worker thread
    and engages a mute lock on the microphone during speech output + cooldown.
    """

    COOLDOWN_SECONDS = 0.40

    def __init__(
        self,
        registry: CommandRegistry,
        on_speaking_state: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._registry = registry
        self._on_speaking_state = on_speaking_state
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._is_speaking = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._tts_worker, name="CAVE-TTS", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def speak(self, text: str, low_level_key_event: bool = False) -> None:
        """Queue a phrase for spoken output if TTS is enabled and not in silent mode."""
        if not text:
            return
        if not self._registry.get_setting("tts_enabled", True):
            return
        if self._registry.get_setting("tts_silent_mode", False):
            return
        if low_level_key_event and not self._registry.get_setting(
            "verbose_key_feedback", False
        ):
            return

        self._queue.put(text)

    def _tts_worker(self) -> None:
        engine = None
        if pyttsx3 is not None:
            try:
                engine = pyttsx3.init()
                self._configure_voice(engine)
            except Exception as exc:
                logger.warning("pyttsx3 initialization failed: %s", exc)
                engine = None

        while self._running:
            try:
                phrase = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if phrase is None:
                break

            self._is_speaking = True
            if self._on_speaking_state:
                self._on_speaking_state(True)

            try:
                if engine is not None:
                    engine.setProperty(
                        "rate", int(self._registry.get_setting("tts_rate", 185))
                    )
                    engine.setProperty(
                        "volume", float(self._registry.get_setting("tts_volume", 0.9))
                    )
                    engine.say(phrase)
                    engine.runAndWait()
                else:
                    logger.info("[TTS Simulated]: %s", phrase)
            except Exception as exc:
                logger.warning("TTS playback error: %s", exc)
            finally:
                time.sleep(self.COOLDOWN_SECONDS)
                self._is_speaking = False
                if self._on_speaking_state:
                    self._on_speaking_state(False)

    def _configure_voice(self, engine: object) -> None:
        """Select a Brazilian Portuguese voice (e.g., Maria) if installed on Windows."""
        try:
            voices = engine.getProperty("voices")  # type: ignore[attr-defined]
            hint = str(self._registry.get_setting("tts_voice_hint", "maria")).lower()
            for v in voices or []:
                v_name = getattr(v, "name", "").lower()
                v_id = getattr(v, "id", "").lower()
                if hint in v_name or "portuguese" in v_name or "pt-br" in v_id or "pt_br" in v_id:
                    engine.setProperty("voice", v.id)  # type: ignore[attr-defined]
                    logger.info("Selected TTS voice: %s", v.name)
                    return
        except Exception as exc:
            logger.debug("Could not enumerate TTS voices: %s", exc)