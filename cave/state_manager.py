# state_manager.py
"""Thread-safe state machine managing CAVE modes, sessions, and command history."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Callable, Deque, Dict, List, Optional


class AssistantMode(str, Enum):
    """Primary operational modes of CAVE."""

    STANDBY = "STANDBY"
    ACTIVE_SESSION = "ACTIVE_SESSION"
    DICTATION = "DICTATION"
    GAME_MODE = "GAME_MODE"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    STOPPED = "STOPPED"


class PipelineStage(str, Enum):
    """Fine-grained execution stages for UI feedback."""

    IDLE = "IDLE"
    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    RECOGNIZING_SPEECH = "RECOGNIZING_SPEECH"
    INTERPRETING_COMMAND = "INTERPRETING_COMMAND"
    EXECUTING_COMMAND = "EXECUTING_COMMAND"
    EXECUTION_CONFIRMED = "EXECUTION_CONFIRMED"
    ERROR = "ERROR"


@dataclass
class PendingConfirmation:
    """Represents a sensitive command waiting for user confirmation."""

    intent_name: str
    description: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.monotonic)
    timeout_seconds: float = 15.0

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) >= self.timeout_seconds


class StateManager:
    """Thread-safe central state store for CAVE."""

    def __init__(
        self,
        session_timeout_seconds: float = 8.0,
        duplicate_window_seconds: float = 1.8,
        on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self._lock = RLock()
        self._start_time = time.monotonic()
        self._mode: AssistantMode = AssistantMode.STANDBY
        self._stage: PipelineStage = PipelineStage.IDLE
        self._session_timeout = float(session_timeout_seconds)
        self._session_expires_at: float = 0.0
        self._duplicate_window = float(duplicate_window_seconds)

        self._last_command_norm: str = ""
        self._last_command_ts: float = 0.0

        self._pc_mic_active: bool = False
        self._mobile_connected: bool = False
        self._mobile_mic_streaming: bool = False
        self._mobile_device_id: Optional[str] = None
        self._last_mobile_heartbeat: float = 0.0

        self._current_speech: str = ""
        self._last_recognized_command: str = ""
        self._last_action_result: str = "CAVE inicializado e em espera."
        self._last_action_success: bool = True
        self._dictation_paused: bool = False
        self._held_keys: List[str] = []
        self._pending_confirmation: Optional[PendingConfirmation] = None

        self._history: Deque[Dict[str, Any]] = deque(maxlen=100)
        self._on_state_change = on_state_change

    def set_state_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._on_state_change = callback

    def _notify(self) -> None:
        callback = self._on_state_change
        if callback is not None:
            snapshot = self.get_snapshot()
            try:
                callback(snapshot)
            except Exception:
                pass

    @property
    def mode(self) -> AssistantMode:
        with self._lock:
            self._check_expirations_locked()
            return self._mode

    @property
    def stage(self) -> PipelineStage:
        with self._lock:
            return self._stage

    def set_stage(self, stage: PipelineStage) -> None:
        with self._lock:
            self._stage = stage
        self._notify()

    def activate_command_session(self) -> None:
        """Transition from STANDBY into an active command session window."""
        with self._lock:
            if self._mode == AssistantMode.STANDBY:
                self._mode = AssistantMode.ACTIVE_SESSION
            self._session_expires_at = time.monotonic() + self._session_timeout
            self._stage = PipelineStage.WAKE_WORD_DETECTED
        self._notify()

    def refresh_session(self) -> None:
        """Extend the active command session follow-up window."""
        with self._lock:
            if self._mode == AssistantMode.ACTIVE_SESSION:
                self._session_expires_at = time.monotonic() + self._session_timeout
        self._notify()

    def is_session_active(self) -> bool:
        """Return True if CAVE is in an active session, dictation mode, or game mode."""
        with self._lock:
            self._check_expirations_locked()
            return self._mode in (
                AssistantMode.ACTIVE_SESSION,
                AssistantMode.DICTATION,
                AssistantMode.GAME_MODE,
                AssistantMode.AWAITING_CONFIRMATION,
            )

    def _check_expirations_locked(self) -> None:
        now = time.monotonic()
        if (
            self._mode == AssistantMode.ACTIVE_SESSION
            and self._session_expires_at > 0
            and now >= self._session_expires_at
        ):
            self._mode = AssistantMode.STANDBY
            self._stage = PipelineStage.IDLE
            self._session_expires_at = 0.0

        if (
            self._mode == AssistantMode.AWAITING_CONFIRMATION
            and self._pending_confirmation is not None
            and self._pending_confirmation.is_expired()
        ):
            self._pending_confirmation = None
            self._mode = AssistantMode.STANDBY
            self._stage = PipelineStage.IDLE

    def tick(self) -> bool:
        """Periodic check to expire timed-out command sessions. Returns True if expired."""
        with self._lock:
            prev_mode = self._mode
            self._check_expirations_locked()
            changed = prev_mode != self._mode
        if changed:
            self._notify()
        return changed

    def enter_dictation_mode(self) -> None:
        with self._lock:
            self._mode = AssistantMode.DICTATION
            self._dictation_paused = False
            self._stage = PipelineStage.EXECUTION_CONFIRMED
        self._notify()

    def set_dictation_paused(self, paused: bool) -> None:
        with self._lock:
            self._dictation_paused = paused
        self._notify()

    @property
    def is_dictation_paused(self) -> bool:
        with self._lock:
            return self._dictation_paused

    def exit_dictation_mode(self) -> None:
        with self._lock:
            self._mode = AssistantMode.STANDBY
            self._dictation_paused = False
            self._stage = PipelineStage.IDLE
            self._session_expires_at = 0.0
        self._notify()

    def enter_game_mode(self) -> None:
        with self._lock:
            self._mode = AssistantMode.GAME_MODE
            self._stage = PipelineStage.EXECUTION_CONFIRMED
        self._notify()

    def exit_game_mode(self) -> None:
        with self._lock:
            self._mode = AssistantMode.STANDBY
            self._stage = PipelineStage.IDLE
            self._held_keys = []
            self._session_expires_at = 0.0
        self._notify()

    def request_confirmation(
        self, intent_name: str, description: str, payload: Dict[str, Any]
    ) -> None:
        with self._lock:
            self._pending_confirmation = PendingConfirmation(
                intent_name=intent_name,
                description=description,
                payload=payload,
            )
            self._mode = AssistantMode.AWAITING_CONFIRMATION
            self._stage = PipelineStage.INTERPRETING_COMMAND
        self._notify()

    def pop_pending_confirmation(self) -> Optional[PendingConfirmation]:
        with self._lock:
            self._check_expirations_locked()
            pending = self._pending_confirmation
            self._pending_confirmation = None
            if self._mode == AssistantMode.AWAITING_CONFIRMATION:
                self._mode = AssistantMode.STANDBY
            return pending

    def return_to_standby(self) -> None:
        with self._lock:
            self._mode = AssistantMode.STANDBY
            self._stage = PipelineStage.IDLE
            self._session_expires_at = 0.0
            self._pending_confirmation = None
            self._dictation_paused = False
        self._notify()

    def is_duplicate_command(self, normalized_command: str) -> bool:
        """Check and update duplicate suppression window to avoid double execution."""
        clean = normalized_command.strip().lower()
        if not clean:
            return False
        now = time.monotonic()
        with self._lock:
            if (
                clean == self._last_command_norm
                and (now - self._last_command_ts) < self._duplicate_window
            ):
                return True
            self._last_command_norm = clean
            self._last_command_ts = now
            return False

    def update_speech_preview(self, text: str) -> None:
        with self._lock:
            self._current_speech = text
        self._notify()

    def record_execution(
        self,
        command_text: str,
        result_message: str,
        success: bool = True,
        redact_in_history: bool = False,
    ) -> None:
        with self._lock:
            display_cmd = "[Texto ditado oculto]" if redact_in_history else command_text
            self._last_recognized_command = display_cmd
            self._last_action_result = result_message
            self._last_action_success = success
            self._stage = (
                PipelineStage.EXECUTION_CONFIRMED if success else PipelineStage.ERROR
            )
            self._history.appendleft(
                {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "command": display_cmd,
                    "result": result_message,
                    "success": success,
                    "mode": self._mode.value,
                }
            )
        self._notify()

    def set_held_keys(self, keys: List[str]) -> None:
        with self._lock:
            self._held_keys = sorted(list(keys))
        self._notify()

    def set_pc_mic_state(self, active: bool) -> None:
        with self._lock:
            self._pc_mic_active = active
        self._notify()

    def set_mobile_connection(
        self,
        connected: bool,
        device_id: Optional[str] = None,
        mic_streaming: bool = False,
    ) -> None:
        with self._lock:
            self._mobile_connected = connected
            self._mobile_device_id = device_id if connected else None
            self._mobile_mic_streaming = mic_streaming if connected else False
            if connected:
                self._last_mobile_heartbeat = time.monotonic()
        self._notify()

    def update_mobile_heartbeat(self, mic_streaming: Optional[bool] = None) -> None:
        with self._lock:
            self._last_mobile_heartbeat = time.monotonic()
            self._mobile_connected = True
            if mic_streaming is not None:
                self._mobile_mic_streaming = mic_streaming

    def is_mobile_heartbeat_expired(self, timeout_seconds: float) -> bool:
        with self._lock:
            if not self._mobile_connected:
                return False
            return (time.monotonic() - self._last_mobile_heartbeat) > timeout_seconds

    def update_timeouts(
        self, session_timeout: float, duplicate_window: float
    ) -> None:
        with self._lock:
            self._session_timeout = max(2.0, float(session_timeout))
            self._duplicate_window = max(0.3, float(duplicate_window))

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
        self._notify()

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._check_expirations_locked()
            uptime_sec = int(time.monotonic() - self._start_time)
            remaining_session = max(
                0.0,
                round(self._session_expires_at - time.monotonic(), 1)
                if self._mode == AssistantMode.ACTIVE_SESSION
                else 0.0,
            )
            return {
                "mode": self._mode.value,
                "stage": self._stage.value,
                "session_remaining_seconds": remaining_session,
                "dictation_paused": self._dictation_paused,
                "pc_mic_active": self._pc_mic_active,
                "mobile_connected": self._mobile_connected,
                "mobile_mic_streaming": self._mobile_mic_streaming,
                "mobile_device_id": self._mobile_device_id,
                "current_speech": self._current_speech,
                "last_recognized_command": self._last_recognized_command,
                "last_action_result": self._last_action_result,
                "last_action_success": self._last_action_success,
                "held_keys": list(self._held_keys),
                "awaiting_confirmation": (
                    self._pending_confirmation.description
                    if self._pending_confirmation
                    else None
                ),
                "uptime_seconds": uptime_sec,
                "history": list(self._history)[:25],
            }