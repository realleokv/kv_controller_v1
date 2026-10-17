# intent_engine.py
"""
Modular bilingual (pt-BR and en-US) natural-language intent classification and
entity extraction engine.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from cave.command_registry import CommandRegistry


class IntentType(str, Enum):
    """Supported deterministic system intents."""

    EMERGENCY_STOP = "EMERGENCY_STOP"
    CONFIRM_ACTION = "CONFIRM_ACTION"
    CANCEL_ACTION = "CANCEL_ACTION"

    LAUNCH_APP = "LAUNCH_APP"
    CLOSE_WINDOW = "CLOSE_WINDOW"
    SWITCH_WINDOW = "SWITCH_WINDOW"

    START_DICTATION = "START_DICTATION"
    STOP_DICTATION = "STOP_DICTATION"
    PAUSE_DICTATION = "PAUSE_DICTATION"
    RESUME_DICTATION = "RESUME_DICTATION"
    DICTATE_INLINE = "DICTATE_INLINE"
    DICTATION_TEXT_CHUNK = "DICTATION_TEXT_CHUNK"

    ENABLE_GAME_MODE = "ENABLE_GAME_MODE"
    DISABLE_GAME_MODE = "DISABLE_GAME_MODE"
    GAME_HOLD_KEYS = "GAME_HOLD_KEYS"
    GAME_RELEASE_KEYS = "GAME_RELEASE_KEYS"
    GAME_RELEASE_ALL = "GAME_RELEASE_ALL"
    GAME_SHORT_MOVE = "GAME_SHORT_MOVE"

    PRESS_KEY = "PRESS_KEY"
    PRESS_SHORTCUT = "PRESS_SHORTCUT"
    MOUSE_ACTION = "MOUSE_ACTION"

    SYSTEM_STATUS = "SYSTEM_STATUS"
    STANDBY_SLEEP = "STANDBY_SLEEP"
    AI_QUERY = "AI_QUERY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ParsedIntent:
    """Structured output of the intent classification pipeline."""

    intent_type: IntentType
    raw_text: str
    normalized_text: str
    entities: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: str = ""


class IntentEngine:
    """
    Normalizes spoken Portuguese and English utterances and classifies them
    into deterministic intents with extracted arguments.
    """

    EMERGENCY_PHRASES = {
        "pare tudo",
        "parar tudo",
        "emergencia",
        "parada de emergencia",
        "stop everything",
        "emergency stop",
        "abortar tudo",
        "cancelar tudo",
    }

    CONFIRM_PHRASES = {
        "sim",
        "confirmar",
        "confirmo",
        "pode confirmar",
        "yes",
        "confirm",
        "ok confirmar",
    }

    CANCEL_PHRASES = {
        "nao",
        "cancelar",
        "cancela",
        "abortar",
        "no",
        "cancel",
    }

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    @staticmethod
    def normalize_text(text: str) -> str:
        """Lowercase, strip accents, and collapse whitespace for deterministic matching."""
        cleaned = text.strip().lower()
        nfd = unicodedata.normalize("NFD", cleaned)
        no_accents = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
        no_punct = re.sub(r"[^\w\s+]", " ", no_accents)
        return re.sub(r"\s+", " ", no_punct).strip()

    def parse(
        self,
        utterance: str,
        in_dictation_mode: bool = False,
        dictation_paused: bool = False,
        in_game_mode: bool = False,
        awaiting_confirmation: bool = False,
    ) -> ParsedIntent:
        """Classify a user utterance into a structured ParsedIntent."""
        raw = utterance.strip()
        norm = self.normalize_text(raw)

        if not norm:
            return ParsedIntent(IntentType.UNKNOWN, raw, norm)

        # 1. Emergency stop ALWAYS takes highest priority in every mode
        if norm in self.EMERGENCY_PHRASES or any(
            norm.startswith(p) for p in self.EMERGENCY_PHRASES
        ):
            return ParsedIntent(IntentType.EMERGENCY_STOP, raw, norm)

        # 2. Pending confirmation check
        if awaiting_confirmation:
            if norm in self.CONFIRM_PHRASES:
                return ParsedIntent(IntentType.CONFIRM_ACTION, raw, norm)
            if norm in self.CANCEL_PHRASES:
                return ParsedIntent(IntentType.CANCEL_ACTION, raw, norm)

        # 3. Dictation Mode handling: only exit/pause/resume are commands; everything else is text
        if in_dictation_mode:
            if norm in (
                "parar ditado",
                "sair do modo ditado",
                "desativar modo ditado",
                "encerrar ditado",
                "stop dictation",
                "exit dictation mode",
                "disable dictation mode",
            ):
                return ParsedIntent(IntentType.STOP_DICTATION, raw, norm)

            if norm in ("pausar ditado", "pause dictation"):
                return ParsedIntent(IntentType.PAUSE_DICTATION, raw, norm)

            if norm in ("retomar ditado", "continuar ditado", "resume dictation"):
                return ParsedIntent(IntentType.RESUME_DICTATION, raw, norm)

            if dictation_paused:
                return ParsedIntent(IntentType.UNKNOWN, raw, norm)

            return ParsedIntent(
                IntentType.DICTATION_TEXT_CHUNK,
                raw,
                norm,
                entities={"text": raw},
            )

        # 4. Entering / Exiting Dictation Mode
        if norm in (
            "ativar modo ditado",
            "iniciar ditado",
            "entrar no modo ditado",
            "modo ditado",
            "enable dictation mode",
            "start dictation",
            "dictation mode",
        ):
            return ParsedIntent(IntentType.START_DICTATION, raw, norm)

        # 5. Inline one-shot dictation ("digite Olá, tudo bem?", "type Hello, how are you?")
        inline_match = re.match(
            r"^(?:digite|digitar|escreva|escrever|type|write)\s+(.+)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if inline_match:
            spoken_body = inline_match.group(1).strip()
            # Ensure "write a paragraph about Python" goes to AI if it's a generation request
            norm_body = self.normalize_text(spoken_body)
            if re.match(
                r"^(?:um paragrafo sobre|uma redacao sobre|um email sobre|a paragraph about|an email about)\b",
                norm_body,
            ):
                return ParsedIntent(
                    IntentType.AI_QUERY,
                    raw,
                    norm,
                    entities={"prompt": raw, "dictate_response": True},
                )
            return ParsedIntent(
                IntentType.DICTATE_INLINE,
                raw,
                norm,
                entities={"text": spoken_body},
            )

        # 6. Game Mode activation / deactivation
        if norm in (
            "ativar modo jogo",
            "habilitar modo jogo",
            "entrar no modo jogo",
            "modo jogo",
            "enable game mode",
            "start game mode",
            "game mode",
        ):
            return ParsedIntent(IntentType.ENABLE_GAME_MODE, raw, norm)

        if norm in (
            "desativar modo jogo",
            "sair do modo jogo",
            "parar modo jogo",
            "encerrar modo jogo",
            "disable game mode",
            "exit game mode",
            "stop game mode",
        ):
            return ParsedIntent(IntentType.DISABLE_GAME_MODE, raw, norm)

        # 7. Release all keys command
        if norm in (
            "soltar todas as teclas",
            "solte todas as teclas",
            "liberar todas as teclas",
            "soltar tudo",
            "release all keys",
            "release keys",
        ):
            return ParsedIntent(IntentType.GAME_RELEASE_ALL, raw, norm)

        # 8. Hold key(s) command ("segurar W", "hold W and D", "segurar W e Shift")
        hold_match = re.match(
            r"^(?:segurar|segure|manter pressionado|hold)\s+(.+)$", norm
        )
        if hold_match:
            keys = self._extract_game_keys(hold_match.group(1))
            if keys:
                return ParsedIntent(
                    IntentType.GAME_HOLD_KEYS,
                    raw,
                    norm,
                    entities={"keys": keys},
                )

        # 9. Release specific key(s) ("soltar W", "release W")
        release_match = re.match(r"^(?:soltar|solte|liberar|release)\s+(.+)$", norm)
        if release_match:
            keys = self._extract_game_keys(release_match.group(1))
            if keys:
                return ParsedIntent(
                    IntentType.GAME_RELEASE_KEYS,
                    raw,
                    norm,
                    entities={"keys": keys},
                )

        # 10. Window management & shortcuts
        shortcuts = self._registry.get_shortcut_aliases()
        for phrase, combo in shortcuts.items():
            phrase_norm = self.normalize_text(phrase)
            if norm == phrase_norm or norm.endswith(" " + phrase_norm):
                is_close = combo == ["alt", "f4"]
                if is_close:
                    return ParsedIntent(
                        IntentType.CLOSE_WINDOW,
                        raw,
                        norm,
                        entities={"combo": combo},
                        requires_confirmation=bool(
                            self._registry.get_setting(
                                "require_confirmation_for_sensitive_actions", True
                            )
                        ),
                        confirmation_prompt="Deseja realmente fechar a janela atual?",
                    )
                return ParsedIntent(
                    IntentType.PRESS_SHORTCUT,
                    raw,
                    norm,
                    entities={"combo": combo, "label": phrase},
                )

        # 11. Momentary key press ("pressionar Enter", "press Space", "aperte F5")
        press_match = re.match(
            r"^(?:pressionar|pressione|aperte|apertar|tecla|press|hit)\s+(.+)$", norm
        )
        if press_match:
            key_target = press_match.group(1).strip()
            key_aliases = self._registry.get_key_aliases()
            resolved_key = key_aliases.get(key_target, key_target)
            if resolved_key in key_aliases.values():
                return ParsedIntent(
                    IntentType.PRESS_KEY,
                    raw,
                    norm,
                    entities={"key": resolved_key},
                )

        # Also support bare "pular" / "jump" in game mode
        if in_game_mode and norm in ("pular", "salto", "jump"):
            return ParsedIntent(
                IntentType.PRESS_KEY, raw, norm, entities={"key": "space"}
            )

        # 12. Mouse commands
        mouse_intent = self._parse_mouse_command(raw, norm)
        if mouse_intent is not None:
            return mouse_intent

        # 13. Application launching ("abrir o Chrome", "open Visual Studio Code", "launch my browser")
        app_match = re.match(
            r"^(?:voce pode\s+|poderia\s+|can you\s+|please\s+)?"
            r"(?:abrir|abra|iniciar|inicie|executar|execute|lançar|lance|open|start|launch)\s+(.+?)"
            r"(?:\s+para mim|\s+for me|\s+por favor|\s+please)?$",
            norm,
        )
        if app_match:
            app_query = app_match.group(1).strip()
            return ParsedIntent(
                IntentType.LAUNCH_APP,
                raw,
                norm,
                entities={"app_name": app_query},
            )

        # Incomplete open command ("abrir", "open")
        if norm in ("abrir", "abra", "open", "launch", "iniciar"):
            return ParsedIntent(
                IntentType.LAUNCH_APP,
                raw,
                norm,
                entities={"app_name": ""},
            )

        # 14. Standby / sleep command
        if norm in (
            "modo espera",
            "descansar",
            "dormir",
            "voltar para espera",
            "standby",
            "go to sleep",
        ):
            return ParsedIntent(IntentType.STANDBY_SLEEP, raw, norm)

        # 15. Status inquiry
        if norm in (
            "status",
            "relatorio de status",
            "status do sistema",
            "como voce esta",
            "system status",
        ):
            return ParsedIntent(IntentType.SYSTEM_STATUS, raw, norm)

        # 16. Conversational AI query if enabled or question pattern
        if self._registry.get_setting("ai_enabled", False) or norm.startswith(
            ("explique ", "o que e ", "como funciona ", "resuma ", "explain ", "what is ")
        ):
            return ParsedIntent(
                IntentType.AI_QUERY, raw, norm, entities={"prompt": raw}
            )

        return ParsedIntent(IntentType.UNKNOWN, raw, norm)

    def _extract_game_keys(self, target_phrase: str) -> List[str]:
        """Resolve spoken single keys, movement aliases, or combinations ('w e d', 'w and shift')."""
        norm_phrase = self.normalize_text(target_phrase)
        move_aliases = self._registry.get_game_movement_aliases()
        for alias, mapped_keys in move_aliases.items():
            if self.normalize_text(alias) == norm_phrase:
                return list(mapped_keys)

        key_aliases = self._registry.get_key_aliases()
        tokens = re.split(r"\s+(?:e|and|mais|\+|com|with)\s+|\s+", norm_phrase)
        resolved: List[str] = []
        for tok in tokens:
            clean = tok.strip()
            if not clean or clean in ("tecla", "teclas", "key", "keys"):
                continue
            mapped = key_aliases.get(clean, clean)
            if len(mapped) == 1 or mapped in ("shift", "space", "ctrl", "alt", "tab", "up", "down", "left", "right"):
                if mapped not in resolved:
                    resolved.append(mapped)
        return resolved

    @staticmethod
    def _parse_mouse_command(raw: str, norm: str) -> ParsedIntent | None:
        if norm in ("clique", "clicar", "clique esquerdo", "click", "left click"):
            return ParsedIntent(
                IntentType.MOUSE_ACTION,
                raw,
                norm,
                entities={"action": "click", "button": "left", "clicks": 1},
            )
        if norm in ("clique direito", "botao direito", "right click"):
            return ParsedIntent(
                IntentType.MOUSE_ACTION,
                raw,
                norm,
                entities={"action": "click", "button": "right", "clicks": 1},
            )
        if norm in ("clique duplo", "duplo clique", "double click"):
            return ParsedIntent(
                IntentType.MOUSE_ACTION,
                raw,
                norm,
                entities={"action": "click", "button": "left", "clicks": 2},
            )
        if norm in ("rolar para baixo", "scroll down", "descer pagina"):
            return ParsedIntent(
                IntentType.MOUSE_ACTION,
                raw,
                norm,
                entities={"action": "scroll", "amount": -400},
            )
        if norm in ("rolar para cima", "scroll up", "subir pagina"):
            return ParsedIntent(
                IntentType.MOUSE_ACTION,
                raw,
                norm,
                entities={"action": "scroll", "amount": 400},
            )
        return None