# command_dispatcher.py
"""
Dispatches parsed intents to the appropriate Windows automation controllers,
verifies execution results, and updates state and spoken feedback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from cave.ai_assistant import ConversationalAssistant
from cave.application_manager import ApplicationManager
from cave.command_registry import CommandRegistry
from cave.game_controller import GameController
from cave.intent_engine import IntentType, ParsedIntent
from cave.keyboard_controller import KeyboardController
from cave.mouse_controller import MouseController
from cave.speech_output import SpeechOutputEngine
from cave.state_manager import AssistantMode, PipelineStage, StateManager
from cave.text_dictation import TextDictationEngine

logger = logging.getLogger("cave.command_dispatcher")


@dataclass
class DispatchResult:
    """Result of executing a ParsedIntent."""

    success: bool
    message: str
    spoke_feedback: bool = False


class CommandDispatcher:
    """Routes validated intents to CAVE's specialized execution subsystems."""

    def __init__(
        self,
        registry: CommandRegistry,
        state: StateManager,
        app_manager: ApplicationManager,
        dictation: TextDictationEngine,
        keyboard: KeyboardController,
        mouse: MouseController,
        game: GameController,
        tts: SpeechOutputEngine,
        ai: Optional[ConversationalAssistant] = None,
    ) -> None:
        self._registry = registry
        self._state = state
        self._app_manager = app_manager
        self._dictation = dictation
        self._keyboard = keyboard
        self._mouse = mouse
        self._game = game
        self._tts = tts
        self._ai = ai or ConversationalAssistant(registry)

    def dispatch(self, parsed: ParsedIntent) -> DispatchResult:
        """Execute a ParsedIntent and record verified status."""
        intent = parsed.intent_type
        self._state.set_stage(PipelineStage.EXECUTING_COMMAND)

        # 1. Emergency Stop
        if intent == IntentType.EMERGENCY_STOP:
            released = self._game.disable_game_mode()
            self._state.return_to_standby()
            self._state.set_held_keys([])
            msg = (
                f"Parada de emergência executada. Teclas liberadas: {', '.join(released)}."
                if released
                else "Parada de emergência executada. Todas as teclas foram liberadas."
            )
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak("Parada de emergência. Todas as teclas foram liberadas.")
            return DispatchResult(True, msg, True)

        # 2. Confirmation Gate Handling
        if intent == IntentType.CONFIRM_ACTION:
            pending = self._state.pop_pending_confirmation()
            if pending is None:
                msg = "Não há nenhuma ação pendente de confirmação."
                self._state.record_execution(parsed.raw_text, msg, success=False)
                return DispatchResult(False, msg)
            if pending.intent_name == IntentType.CLOSE_WINDOW.value:
                combo = pending.payload.get("combo", ["alt", "f4"])
                ok = self._keyboard.press_shortcut(combo)
                msg = "Janela atual fechada." if ok else "Falha ao fechar a janela."
                self._state.record_execution(parsed.raw_text, msg, success=ok)
                self._tts.speak(msg)
                return DispatchResult(ok, msg, True)

        if intent == IntentType.CANCEL_ACTION:
            self._state.pop_pending_confirmation()
            msg = "Ação cancelada."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if parsed.requires_confirmation:
            self._state.request_confirmation(
                intent_name=intent.value,
                description=parsed.confirmation_prompt,
                payload=parsed.entities,
            )
            msg = f"{parsed.confirmation_prompt} Diga 'confirmar' ou 'cancelar'."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        # 3. Application Launching
        if intent == IntentType.LAUNCH_APP:
            app_name = parsed.entities.get("app_name", "")
            res = self._app_manager.launch_application(app_name)
            self._state.record_execution(parsed.raw_text, res.message, success=res.success)
            self._tts.speak(res.message)
            return DispatchResult(res.success, res.message, True)

        # 4. Dictation Mode Transitions & Inline Dictation
        if intent == IntentType.START_DICTATION:
            self._state.enter_dictation_mode()
            msg = "Modo ditado ativado."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent == IntentType.STOP_DICTATION:
            self._state.exit_dictation_mode()
            msg = "Modo ditado encerrado."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent == IntentType.PAUSE_DICTATION:
            self._state.set_dictation_paused(True)
            msg = "Ditado pausado."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent == IntentType.RESUME_DICTATION:
            self._state.set_dictation_paused(False)
            msg = "Ditado retomado."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent in (IntentType.DICTATE_INLINE, IntentType.DICTATION_TEXT_CHUNK):
            text_to_type = parsed.entities.get("text", "")
            ok = self._dictation.insert_text(text_to_type)
            redact = not bool(self._registry.get_setting("log_dictated_text", False))
            msg = (
                "Texto inserido com sucesso."
                if ok
                else "Não foi possível inserir o texto ditado."
            )
            self._state.record_execution(
                parsed.raw_text, msg, success=ok, redact_in_history=redact
            )
            if intent == IntentType.DICTATE_INLINE:
                self._tts.speak("Texto digitado." if ok else msg, low_level_key_event=True)
            return DispatchResult(ok, msg, False)

        # 5. Game Control Mode & Simultaneous WASD
        if intent == IntentType.ENABLE_GAME_MODE:
            self._game.enable_game_mode()
            self._state.enter_game_mode()
            msg = "Modo jogo ativado."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent == IntentType.DISABLE_GAME_MODE:
            self._game.disable_game_mode()
            self._state.exit_game_mode()
            msg = "Modo jogo desativado. Todas as teclas foram liberadas."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak("Modo jogo desativado.")
            return DispatchResult(True, msg, True)

        if intent == IntentType.GAME_HOLD_KEYS:
            if not self._game.is_enabled:
                self._game.enable_game_mode()
                self._state.enter_game_mode()
            keys = parsed.entities.get("keys", [])
            held = self._game.hold_keys(keys)
            ok = len(held) > 0
            msg = (
                f"Segurando teclas: {', '.join(k.upper() for k in held)}."
                if ok
                else "Nenhuma tecla de jogo válida reconhecida."
            )
            self._state.record_execution(parsed.raw_text, msg, success=ok)
            self._tts.speak(msg, low_level_key_event=True)
            return DispatchResult(ok, msg, False)

        if intent == IntentType.GAME_RELEASE_KEYS:
            keys = parsed.entities.get("keys", [])
            released = self._game.release_keys(keys)
            msg = f"Teclas liberadas: {', '.join(k.upper() for k in keys)}."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg, low_level_key_event=True)
            return DispatchResult(True, msg, False)

        if intent == IntentType.GAME_RELEASE_ALL:
            self._game.release_all_keys(reason="voice_command")
            msg = "Todas as teclas pressionadas foram liberadas."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        # 6. Keyboard & Shortcuts
        if intent == IntentType.PRESS_KEY:
            key = parsed.entities.get("key", "")
            ok = self._keyboard.press_key(key)
            msg = f"Tecla {key.upper()} pressionada." if ok else f"Falha ao pressionar {key}."
            self._state.record_execution(parsed.raw_text, msg, success=ok)
            self._tts.speak(msg, low_level_key_event=True)
            return DispatchResult(ok, msg, False)

        if intent in (IntentType.PRESS_SHORTCUT, IntentType.CLOSE_WINDOW):
            combo = parsed.entities.get("combo", [])
            ok = self._keyboard.press_shortcut(combo)
            combo_str = "+".join(k.upper() for k in combo)
            msg = f"Atalho {combo_str} executado." if ok else f"Falha ao executar {combo_str}."
            self._state.record_execution(parsed.raw_text, msg, success=ok)
            self._tts.speak("Comando concluído.", low_level_key_event=True)
            return DispatchResult(ok, msg, False)

        # 7. Mouse Actions
        if intent == IntentType.MOUSE_ACTION:
            action = parsed.entities.get("action")
            if action == "click":
                ok = self._mouse.click(
                    button=parsed.entities.get("button", "left"),
                    clicks=int(parsed.entities.get("clicks", 1)),
                )
            else:
                ok = self._mouse.scroll(int(parsed.entities.get("amount", -300)))
            msg = "Ação do mouse executada." if ok else "Falha na ação do mouse."
            self._state.record_execution(parsed.raw_text, msg, success=ok)
            return DispatchResult(ok, msg, False)

        # 8. Standby & System Status
        if intent == IntentType.STANDBY_SLEEP:
            self._game.release_all_keys(reason="standby")
            self._state.return_to_standby()
            msg = "Retornando ao modo de espera."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        if intent == IntentType.SYSTEM_STATUS:
            snap = self._state.get_snapshot()
            msg = f"CAVE online. Modo atual: {snap['mode']}. Teclas ativas: {len(snap['held_keys'])}."
            self._state.record_execution(parsed.raw_text, msg, success=True)
            self._tts.speak(msg)
            return DispatchResult(True, msg, True)

        # 9. Optional Conversational AI
        if intent == IntentType.AI_QUERY:
            prompt = parsed.entities.get("prompt", parsed.raw_text)
            reply = self._ai.ask(prompt)
            if parsed.entities.get("dictate_response") and reply:
                self._dictation.insert_text(reply)
            self._state.record_execution(parsed.raw_text, reply, success=True)
            self._tts.speak(reply)
            return DispatchResult(True, reply, True)

        msg = f"Comando não reconhecido: '{parsed.raw_text}'."
        self._state.record_execution(parsed.raw_text, msg, success=False)
        self._tts.speak("Não compreendi esse comando.")
        return DispatchResult(False, msg, True)