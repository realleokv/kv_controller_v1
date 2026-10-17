# test_game_controller.py
"""
Tests for simultaneous WASD key holds, duplicate key-down prevention,
key release on disconnect, watchdog expiration, and emergency stop.
Covers Scenarios E, F, G and items 8, 9, 10, 11, 16.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from cave.assistant import CaveAssistant
from cave.game_controller import GameController


def test_simultaneous_wasd_holds_and_duplicate_prevention():
    """Scenario E & Item 9: Hold W and Hold D concurrently without duplicate keyDown events."""
    mock_kb = MagicMock()
    mock_kb.key_down.return_value = True
    mock_kb.key_up.return_value = True

    game = GameController(keyboard=mock_kb, max_hold_seconds=10.0)
    game.enable_game_mode()

    game.hold_keys(["w"])
    game.hold_keys(["d"])
    assert game.held_keys == ["d", "w"]
    assert mock_kb.key_down.call_count == 2

    # Holding 'w' again refreshes timer but must NOT emit a second OS key_down
    game.hold_keys(["w"])
    assert mock_kb.key_down.call_count == 2

    # Release W while D remains held
    game.release_keys(["w"])
    assert game.held_keys == ["d"]
    mock_kb.key_up.assert_called_once_with("w")

    game.shutdown()


def test_watchdog_releases_keys_on_timeout():
    """Watchdog automatically releases stuck keys when max_hold_seconds expires."""
    mock_kb = MagicMock()
    mock_kb.key_down.return_value = True
    mock_kb.key_up.return_value = True

    game = GameController(keyboard=mock_kb, max_hold_seconds=1.0)
    game.enable_game_mode()
    game._held_keys["w"] = time.monotonic() - 2.5  # Simulate expired hold

    expired = game.check_expired_holds()
    assert expired == ["w"]
    assert game.held_keys == []
    mock_kb.key_up.assert_called_once_with("w")
    game.shutdown()


def test_disconnect_and_emergency_stop_release_all_keys():
    """Scenarios F & G (Items 10 & 11): Disconnect and Emergency Stop release all held keys."""
    mock_kb = MagicMock()
    mock_kb.key_down.return_value = True
    mock_kb.key_up.return_value = True
    mock_tts = MagicMock()
    mock_tts.is_speaking = False

    assistant = CaveAssistant(
        config_dir="config",
        keyboard=mock_kb,
        tts=mock_tts,
    )

    assistant.process_utterance("Cave, ativar modo jogo")
    assistant.process_utterance("segurar W")
    assistant.process_utterance("segurar D")
    assert assistant.game.held_keys == ["d", "w"]

    # Simulate mobile disconnect (Scenario G)
    assistant.handle_mobile_disconnect()
    assert assistant.game.held_keys == []

    # Re-hold and trigger voice emergency stop (Scenario F)
    assistant.process_utterance("Cave, ativar modo jogo")
    assistant.process_utterance("segurar W e Shift")
    assert assistant.game.held_keys == ["shift", "w"]

    assistant.process_utterance("Cave, pare tudo")
    assert assistant.game.held_keys == []
    assert assistant.game.is_enabled is False
    assistant.stop()