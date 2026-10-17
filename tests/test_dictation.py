# test_dictation.py
"""
Tests for Dictation Mode vs Command Mode, spoken punctuation normalization,
wake-word exclusion, and clipboard preservation/restoration.
Covers Scenario D and items 6, 7, 8.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cave.command_registry import CommandRegistry
from cave.intent_engine import IntentEngine, IntentType
from cave.text_dictation import TextDictationEngine


def test_punctuation_and_portuguese_accents_formatting():
    registry = CommandRegistry(config_dir="config")
    mock_kb = MagicMock()
    dictation = TextDictationEngine(registry, mock_kb)

    raw = "olá vírgula tudo bem com você ponto de interrogação novo parágrafo este é um teste ponto final"
    formatted = dictation.format_spoken_text(raw)
    assert formatted == "Olá, tudo bem com você?\n\nEste é um teste."


def test_clipboard_restoration_after_text_insertion():
    """Item 7: Original clipboard contents must be preserved and restored after paste."""
    registry = CommandRegistry(config_dir="config")
    mock_kb = MagicMock()

    clipboard_state = {"content": "CONTEUDO_ORIGINAL_DO_USUARIO"}

    def fake_get() -> str:
        return clipboard_state["content"]

    def fake_set(val: str) -> None:
        clipboard_state["content"] = val

    dictation = TextDictationEngine(
        registry=registry,
        keyboard=mock_kb,
        clipboard_get=fake_get,
        clipboard_set=fake_set,
        paste_delay_seconds=0.0,
    )

    ok = dictation.insert_text("Bom dia a todos ponto de exclamação")
    assert ok is True
    mock_kb.press_shortcut.assert_called_once_with(["ctrl", "v"])
    # Verify original clipboard was restored
    assert clipboard_state["content"] == "CONTEUDO_ORIGINAL_DO_USUARIO"


def test_dictation_mode_vs_command_mode():
    """Item 6: Sentences in dictation mode must be typed, not interpreted as OS commands."""
    registry = CommandRegistry(config_dir="config")
    engine = IntentEngine(registry)

    # In command mode, "abrir o Chrome" is LAUNCH_APP
    cmd_parsed = engine.parse("abrir o Chrome", in_dictation_mode=False)
    assert cmd_parsed.intent_type == IntentType.LAUNCH_APP

    # In dictation mode, "abrir o Chrome" is DICTATION_TEXT_CHUNK
    dict_parsed = engine.parse("abrir o Chrome", in_dictation_mode=True)
    assert dict_parsed.intent_type == IntentType.DICTATION_TEXT_CHUNK
    assert dict_parsed.entities["text"] == "abrir o Chrome"

    # Exiting dictation mode still works via dedicated voice command
    exit_parsed = engine.parse("parar ditado", in_dictation_mode=True)
    assert exit_parsed.intent_type == IntentType.STOP_DICTATION