# audio_capture.py
"""Continuous local PC microphone capture with automatic reconnection."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("cave.audio_capture")

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - graceful fallback when PortAudio is absent
    sd = None


class LocalAudioCapture:
    """
    Continuously captures 16kHz 16-bit mono PCM audio from the Windows microphone
    and forwards chunks to the speech recognition engine.
    """

    SAMPLE_RATE = 16000
    BLOCK_SIZE = 2000  # 125ms blocks for low-latency wake-word detection

    def __init__(
        self,
        on_audio_chunk: Callable[[bytes], None],
        on_status_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._on_audio_chunk = on_audio_chunk
        self._on_status_change = on_status_change
        self._running = False
        self._paused_for_tts = False
        self._thread: Optional[threading.Thread] = None
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=100)

    @property
    def is_available(self) -> bool:
        return sd is not None

    def set_tts_mute(self, muted: bool) -> None:
        """Mute capture while CAVE is speaking to prevent feedback loops."""
        self._paused_for_tts = muted
        if muted:
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

    def start(self) -> bool:
        if self._running:
            return True
        if sd is None:
            logger.warning("sounddevice library not available; PC mic capture disabled.")
            if self._on_status_change:
                self._on_status_change(False)
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_worker, name="CAVE-LocalMic", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._on_status_change:
            self._on_status_change(False)

    def _audio_callback(self, indata: bytes, frames: int, time_info: object, status: object) -> None:
        if status:
            logger.debug("Audio input status: %s", status)
        if self._paused_for_tts or not self._running:
            return
        try:
            self._audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def _capture_worker(self) -> None:
        retry_delay = 2.0
        while self._running:
            try:
                with sd.RawInputStream(
                    samplerate=self.SAMPLE_RATE,
                    blocksize=self.BLOCK_SIZE,
                    dtype="int16",
                    channels=1,
                    callback=self._audio_callback,
                ):
                    logger.info("Local PC microphone stream active (16 kHz mono).")
                    if self._on_status_change:
                        self._on_status_change(True)
                    retry_delay = 2.0

                    while self._running:
                        try:
                            chunk = self._audio_queue.get(timeout=0.25)
                            if not self._paused_for_tts:
                                self._on_audio_chunk(chunk)
                        except queue.Empty:
                            continue
            except Exception as exc:
                logger.warning(
                    "Local microphone stream interrupted (%s). Retrying in %.1fs...",
                    exc,
                    retry_delay,
                )
                if self._on_status_change:
                    self._on_status_change(False)
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 15.0)