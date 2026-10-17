# assistant.py
"""
Top-level CAVE Assistant orchestrator connecting wake-word activation,
speech recognition, intent resolution, command execution, and lifecycle watchdogs.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from cave.ai_assistant import ConversationalAssistant
from cave.application_manager import ApplicationManager
from cave.audio_capture import LocalAudioCapture
from cave.command_dispatcher import CommandDispatcher, DispatchResult
from cave.command_registry import CommandRegistry
from cave.game_controller import GameController
from cave.intent_engine import IntentEngine, IntentType
from cave.keyboard_controller import KeyboardController
from cave.mouse_controller import MouseController
from cave.speech_output import SpeechOutputEngine
from cave.speech_recognition import SpeechRecognitionEngine
from cave.state_manager import AssistantMode, PipelineStage, StateManager
from cave.text_dictation import TextDictationEngine
from cave.wake_word import WakeWordDetector

logger = logging.getLogger("cave.assistant")


class CaveAssistant:
    """
    Coordinates the five core stages of CAVE:
    1. Wake-word detection ('Cave' / 'KV')
    2. Command recognition
    3. Command interpretation
    4. Command execution
    5. Execution confirmation
    """

    def __init__(
        self,
        config_dir: str = "config",
        keyboard: Optional[KeyboardController] = None,
        mouse: Optional[MouseController] = None,
        app_manager: Optional[ApplicationManager] = None,
        dictation: Optional[TextDictationEngine] = None,
        tts: Optional[SpeechOutputEngine] = None,
        on_broadcast_state: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.registry = CommandRegistry(config_dir=config_dir)
        self.state = StateManager(
            session_timeout_seconds=float(
                self.registry.get_setting("command_session_timeout_seconds", 8.0)
            ),
            duplicate_window_seconds=float(
                self.registry.get_setting("duplicate_suppression_window_seconds", 1.8)
            ),
            on_state_change=on_broadcast_state,
        )

        self.wake_detector = WakeWordDetector(
            sensitivity=float(self.registry.get_setting("wake_word_sensitivity", 0.78))
        )
        self.keyboard = keyboard or KeyboardController()
        self.mouse = mouse or MouseController()
        self.app_manager = app_manager or ApplicationManager(self.registry)
        self.dictation = dictation or TextDictationEngine(self.registry, self.keyboard)

        self.game = GameController(
            keyboard=self.keyboard,
            max_hold_seconds=float(
                self.registry.get_setting("max_key_hold_seconds", 30.0)
            ),
            short_move_seconds=float(
                self.registry.get_setting("short_move_duration_seconds", 0.6)
            ),
            on_keys_changed=self.state.set_held_keys,
        )

        self.tts = tts or SpeechOutputEngine(
            registry=self.registry,
            on_speaking_state=self._on_tts_speaking_change,
        )
        self.intent_engine = IntentEngine(self.registry)
        self.ai = ConversationalAssistant(self.registry)
        self.dispatcher = CommandDispatcher(
            registry=self.registry,
            state=self.state,
            app_manager=self.app_manager,
            dictation=self.dictation,
            keyboard=self.keyboard,
            mouse=self.mouse,
            game=self.game,
            tts=self.tts,
            ai=self.ai,
        )

        model_path = os.getenv(
            "CAVE_VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3"
        )
        self.asr = SpeechRecognitionEngine(
            model_path=model_path,
            on_partial_transcript=self._on_partial_speech,
            on_final_transcript=self._on_final_speech,
        )
        self.local_mic = LocalAudioCapture(
            on_audio_chunk=lambda chunk: self.asr.accept_pcm_chunk(chunk, source="pc"),
            on_status_change=self.state.set_pc_mic_state,
        )

        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start TTS, offline ASR, optional PC microphone, and session/heartbeat monitor."""
        if self._running:
            return
        self._running = True
        self.tts.start()
        self.asr.initialize()

        if self.registry.get_setting("enable_local_pc_microphone", True):
            self.local_mic.start()

        self._monitor_thread = threading.Thread(
            target=self._lifecycle_monitor_loop,
            name="CAVE-LifecycleMonitor",
            daemon=True,
        )
        self._monitor_thread.start()
        self.tts.speak("CAVE online.")
        logger.info("CAVE Assistant started.")

    def stop(self) -> None:
        """Gracefully stop all background workers and release any held keys."""
        self._running = False
        self.game.shutdown()
        self.local_mic.stop()
        self.tts.stop()
        self.state.return_to_standby()
        logger.info("CAVE Assistant stopped gracefully.")

    def emergency_stop(self, reason: str = "manual_trigger") -> DispatchResult:
        """Immediate emergency stop releasing all keys and resetting state."""
        logger.warning("Emergency stop triggered (%s)!", reason)
        parsed = self.intent_engine.parse("pare tudo")
        return self.dispatcher.dispatch(parsed)

    def handle_mobile_disconnect(self) -> None:
        """Release all held keys immediately when the mobile client disconnects."""
        released = self.game.release_all_keys(reason="mobile_disconnected")
        self.state.set_mobile_connection(False)
        if released:
            msg = (
                f"Celular desconectado. Teclas liberadas por segurança: "
                f"{', '.join(k.upper() for k in released)}."
            )
            self.state.record_execution("[Watchdog de Conexão]", msg, success=False)
            self.tts.speak("Conexão perdida. Todas as teclas foram liberadas.")

    def process_utterance(
        self, raw_utterance: str, source: str = "mobile", bypass_wake_word: bool = False
    ) -> Optional[DispatchResult]:
        """
        Process a complete spoken utterance through the 5-stage pipeline:
        1. Wake-word detection ('Cave' / 'KV')
        2. Command recognition & duplicate suppression
        3. Command interpretation
        4. Command execution
        5. Execution confirmation
        """
        if self.tts.is_speaking:
            logger.debug("Ignored utterance while TTS is speaking.")
            return None

        clean_utterance = (raw_utterance or "").strip()
        if not clean_utterance:
            return None

        self.state.update_speech_preview(clean_utterance)

        # Always check whether the user started the phrase with the wake word ("Cave, ...")
        ww_match = self.wake_detector.detect_and_strip(clean_utterance)
        current_mode = self.state.mode
        session_active = self.state.is_session_active() or bypass_wake_word

        if ww_match.detected:
            # Stage 1: Wake word detected
            self.state.activate_command_session()
            command_text = ww_match.remaining_command
            if not command_text:
                # User only said "Cave" / "KV" -> open session and acknowledge
                self.tts.speak("Sim?", low_level_key_event=True)
                return DispatchResult(True, "Aguardando comando...", True)
        else:
            # No wake word in this utterance
            if not session_active:
                # Reject ordinary speech in STANDBY
                logger.debug(
                    "Ignored speech in STANDBY (no wake word): %s", clean_utterance
                )
                return None
            command_text = clean_utterance

        # Stage 2: Duplicate command suppression (except continuous dictation chunks)
        norm_cmd = self.intent_engine.normalize_text(command_text)
        if current_mode != AssistantMode.DICTATION and self.state.is_duplicate_command(
            norm_cmd
        ):
            logger.info("Suppressed duplicate command: %s", command_text)
            return None

        # Refresh follow-up command session window
        self.state.refresh_session()

        # Stage 3: Command interpretation
        self.state.set_stage(PipelineStage.INTERPRETING_COMMAND)
        parsed = self.intent_engine.parse(
            utterance=command_text,
            in_dictation_mode=(self.state.mode == AssistantMode.DICTATION),
            dictation_paused=self.state.is_dictation_paused,
            in_game_mode=(self.state.mode == AssistantMode.GAME_MODE),
            awaiting_confirmation=(
                self.state.mode == AssistantMode.AWAITING_CONFIRMATION
            ),
        )

        # Stage 4 & 5: Command execution & confirmation
        return self.dispatcher.dispatch(parsed)

    def _on_partial_speech(self, partial_text: str, source: str) -> None:
        if not self.tts.is_speaking:
            self.state.update_speech_preview(partial_text)

    def _on_final_speech(self, final_text: str, source: str) -> None:
        self.process_utterance(final_text, source=source)

    def _on_tts_speaking_change(self, speaking: bool) -> None:
        self.local_mic.set_tts_mute(speaking)

    def apply_updated_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        saved = self.registry.save_settings(updates)
        self.wake_detector.sensitivity = float(
            saved.get("wake_word_sensitivity", 0.78)
        )
        self.state.update_timeouts(
            session_timeout=float(saved.get("command_session_timeout_seconds", 8.0)),
            duplicate_window=float(
                saved.get("duplicate_suppression_window_seconds", 1.8)
            ),
        )
        self.game.set_max_hold_seconds(
            float(saved.get("max_key_hold_seconds", 30.0))
        )
        return saved

    def _lifecycle_monitor_loop(self) -> None:
        while self._running:
            try:
                expired = self.state.tick()
                if expired:
                    logger.debug("Command session expired; returned to STANDBY.")

                hb_timeout = float(
                    self.registry.get_setting("heartbeat_timeout_seconds", 6.0)
                )
                if self.state.is_mobile_heartbeat_expired(hb_timeout):
                    logger.warning("Mobile client heartbeat timed out.")
                    self.handle_mobile_disconnect()
            except Exception as exc:
                logger.error("Lifecycle monitor error: %s", exc)
            time.sleep(0.5)