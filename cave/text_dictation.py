# text_dictation.py
"""
Natural-language text dictation engine with spoken punctuation conversion,
Portuguese Unicode support, and safe clipboard preservation/restoration.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Dict, Optional

import pyperclip

from cave.command_registry import CommandRegistry
from cave.keyboard_controller import KeyboardController

logger = logging.getLogger("cave.text_dictation")


class TextDictationEngine:
    """
    Handles one-shot inline dictation and continuous dictation mode.
    Preserves existing Windows clipboard contents when inserting Unicode text.
    """

    def __init__(
        self,
        registry: CommandRegistry,
        keyboard: KeyboardController,
        clipboard_get: Optional[Callable[[], str]] = None,
        clipboard_set: Optional[Callable[[str], None]] = None,
        paste_delay_seconds: float = 0.06,
    ) -> None:
        self._registry = registry
        self._keyboard = keyboard
        self._clipboard_get = clipboard_get or pyperclip.paste
        self._clipboard_set = clipboard_set or pyperclip.copy
        self._paste_delay = paste_delay_seconds

    def format_spoken_text(self, raw_speech: str) -> str:
        """
        Convert spoken punctuation phrases ('vírgula', 'ponto de interrogação',
        'novo parágrafo', 'period', 'comma') into symbols and apply optional capitalization.
        """
        if not raw_speech:
            return ""

        text = raw_speech.strip()
        if self._registry.get_setting("dictation_normalize_punctuation", True):
            punct_map: Dict[str, str] = self._registry.get_punctuation_map()
            # Sort keys by length descending so "ponto de interrogação" matches before "ponto"
            sorted_phrases = sorted(punct_map.keys(), key=len, reverse=True)
            for phrase in sorted_phrases:
                replacement = punct_map[phrase]
                pattern = re.compile(
                    r"(?:^|\s+)" + re.escape(phrase) + r"(?=$|\s+|[.,!?;:])",
                    re.IGNORECASE,
                )
                text = pattern.sub(replacement, text)

        # Clean up spacing around punctuation
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        text = re.sub(r"([.,!?;:])([A-Za-zÀ-ÿ])", r"\1 \2", text)
        text = re.sub(r'"\s+', '"', text)

        if self._registry.get_setting("dictation_auto_capitalize", True) and text:
            text = text[0].upper() + text[1:]
            # Capitalize after sentence-ending punctuation
            text = re.sub(
                r"([.!?]\s+|\n+)([a-zà-ÿ])",
                lambda m: m.group(1) + m.group(2).upper(),
                text,
            )

        return text

    def insert_text(self, raw_speech: str) -> bool:
        """
        Insert formatted text into the currently focused Windows control.
        Saves the user's current clipboard, pastes the Unicode text via Ctrl+V,
        and restores the original clipboard content safely.
        Never sends Enter or submits forms automatically.
        """
        formatted = self.format_spoken_text(raw_speech)
        if not formatted:
            return False

        original_clipboard: Optional[str] = None
        clipboard_available = True

        try:
            original_clipboard = self._clipboard_get()
        except Exception as exc:
            logger.debug("Could not read prior clipboard: %s", exc)
            clipboard_available = False

        if clipboard_available:
            try:
                self._clipboard_set(formatted)
                time.sleep(0.02)
                self._keyboard.press_shortcut(["ctrl", "v"])
                time.sleep(self._paste_delay)
                return True
            except Exception as exc:
                logger.warning(
                    "Clipboard paste failed (%s); falling back to direct typing.", exc
                )
            finally:
                if original_clipboard is not None:
                    try:
                        self._clipboard_set(original_clipboard)
                    except Exception as restore_exc:
                        logger.debug(
                            "Could not restore original clipboard: %s", restore_exc
                        )

        # Fallback: direct character typing if clipboard is locked
        return self._keyboard.type_unicode_string(formatted)