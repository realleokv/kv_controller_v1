# test_wake_word.py
"""
Tests for wake-word detection ('Cave' / 'KV'), sensitivity handling,
state transitions, and duplicate command suppression.
Covers Scenarios A, B, and items 1, 2, 3, 14, 16.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cave.assistant import CaveAssistant
from cave.state_manager import AssistantMode
from cave.wake_word import WakeWordDetector


def test_wake_word_exact_and_phonetic_variations():
    detector = WakeWordDetector(sensitivity=0.78)

    cases = [
        ("Cave, abrir o Chrome", True, "abrir o Chrome"),
        ("KV abrir calculadora", True, "abrir calculadora"),
        ("Oi Cave, ativar modo jogo", True, "ativar modo jogo"),
        ("Queive, pressione enter", True, "pressione enter"),
        ("Cá vê, digite olá mundo", True, "digite olá mundo"),
        ("K V, pare tudo", True, "pare tudo"),
    ]
    for utterance, expected_detected, expected_remainder in cases:
        res = detector.detect_and_strip(utterance)
        assert res.detected is expected_detected, f"Failed for: {utterance}"
        assert res.remaining_command == expected_remainder


def test_reject_ordinary_speech_without_wake_word(tmp_path):
    """Scenario B: Ordinary speech without the wake word must not execute commands."""
    mock_kb = MagicMock()
    mock_apps = MagicMock()
    mock_tts = MagicMock()
    mock_tts.is_speaking = False

    assistant = CaveAssistant(
        config_dir="config",
        keyboard=mock_kb,
        app_manager=mock_apps,
        tts=mock_tts,
    )

    assert assistant.state.mode == AssistantMode.STANDBY
    res = assistant.process_utterance("abrir o Chrome")
    assert res is None
    mock_apps.launch_application.assert_not_called()


def test_wake_word_and_command_in_same_utterance(tmp_path):
    """Scenario A: 'Cave, open Chrome' activates session and launches application."""
    mock_kb = MagicMock()
    mock_apps = MagicMock()
    mock_apps.launch_application.return_value = MagicMock(
        success=True, message="Abrindo Google Chrome."
    )
    mock_tts = MagicMock()
    mock_tts.is_speaking = False

    assistant = CaveAssistant(
        config_dir="config",
        keyboard=mock_kb,
        app_manager=mock_apps,
        tts=mock_tts,
    )

    res = assistant.process_utterance("Cave, abrir o Chrome")
    assert res is not None
    assert res.success is True
    mock_apps.launch_application.assert_called_once_with("o chrome")
    assert assistant.state.mode == AssistantMode.ACTIVE_SESSION


def test_duplicate_command_suppression():
    """Item 14: Overlapping microphone events must not execute the same command twice."""
    mock_kb = MagicMock()
    mock_apps = MagicMock()
    mock_apps.launch_application.return_value = MagicMock(
        success=True, message="Abrindo Calculadora."
    )
    mock_tts = MagicMock()
    mock_tts.is_speaking = False

    assistant = CaveAssistant(
        config_dir="config",
        keyboard=mock_kb,
        app_manager=mock_apps,
        tts=mock_tts,
    )

    first = assistant.process_utterance("Cave, abrir calculadora")
    second = assistant.process_utterance("Cave, abrir calculadora")

    assert first is not None
    assert second is None
    assert mock_apps.launch_application.call_count == 1