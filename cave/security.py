# security.py
"""Security validation, rate limiting, and allowlist enforcement for CAVE."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Deque, Dict, Tuple


class SecurityValidator:
    """Validates incoming WebSocket/HTTP payloads and enforces rate limits."""

    MAX_TEXT_LENGTH = 1500
    MAX_AUDIO_CHUNK_BYTES = 65536
    SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$><]")

    def __init__(
        self, max_requests_per_window: int = 40, window_seconds: float = 5.0
    ) -> None:
        self._max_requests = max_requests_per_window
        self._window_seconds = window_seconds
        self._client_timestamps: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check_rate_limit(self, client_id: str) -> bool:
        """Return True if client is within rate limits, False if throttled."""
        if not client_id:
            return False
        now = time.monotonic()
        with self._lock:
            timestamps = self._client_timestamps[client_id]
            while timestamps and (now - timestamps[0]) > self._window_seconds:
                timestamps.popleft()
            if len(timestamps) >= self._max_requests:
                return False
            timestamps.append(now)
            return True

    @classmethod
    def validate_speech_payload(cls, payload: Any) -> Tuple[bool, str, str]:
        """
        Validate incoming recognized speech JSON payload.
        Returns (is_valid, sanitized_text, error_reason).
        """
        if not isinstance(payload, dict):
            return False, "", "Payload must be a JSON object."

        raw_text = payload.get("text")
        if not isinstance(raw_text, str):
            return False, "", "Field 'text' must be a string."

        cleaned = raw_text.strip()
        if not cleaned:
            return False, "", "Empty speech text."

        if len(cleaned) > cls.MAX_TEXT_LENGTH:
            return (
                False,
                "",
                f"Speech text exceeds maximum length of {cls.MAX_TEXT_LENGTH} characters.",
            )

        # Remove null bytes or non-printable control characters except newline/tab
        sanitized = "".join(
            ch for ch in cleaned if ch in ("\n", "\t") or ord(ch) >= 32
        )
        return True, sanitized, ""

    @classmethod
    def validate_audio_chunk(cls, raw_bytes: Any) -> Tuple[bool, str]:
        """Validate binary PCM audio chunk size and type."""
        if not isinstance(raw_bytes, (bytes, bytearray)):
            return False, "Audio chunk must be binary bytes."
        if len(raw_bytes) == 0:
            return False, "Empty audio chunk."
        if len(raw_bytes) > cls.MAX_AUDIO_CHUNK_BYTES:
            return False, "Audio chunk exceeds maximum allowed byte size."
        if len(raw_bytes) % 2 != 0:
            return False, "PCM 16-bit audio chunk byte length must be even."
        return True, ""

    @classmethod
    def is_safe_executable_target(cls, target: str) -> bool:
        """Ensure an executable path does not contain command-injection chains."""
        if not target or not isinstance(target, str):
            return False
        if cls.SHELL_METACHAR_PATTERN.search(target):
            return False
        return True