# test_intent_engine.py
"""
Tests for Portuguese and English text normalization and intent classification.
Covers item 4 and multi-phrasing intent resolution.
"""

from __future__ import annotations

from cave.command_registry import CommandRegistry
from cave.intent_engine import IntentEngine, IntentType


def test_portuguese_normalization():
    raw = "  Você pode ABRIR o Configurações, por favor?! "
    norm = IntentEngine.normalize_text(raw)
    assert norm == "voce pode abrir o configuracoes por favor"


def test_launch_app_variations():
    registry = CommandRegistry(config_dir="config")
    engine = IntentEngine(registry)

    phrases = [
        "abrir o Chrome",
        "iniciar Google Chrome",
        "abra meu navegador",
        "can you open Chrome for me",
        "launch my browser",
    ]
    for phrase in phrases:
        parsed = engine.parse(phrase)
        assert parsed.intent_type == IntentType.LAUNCH_APP, f"Failed on: {phrase}"
        assert parsed.entities["app_name"] != ""


def test_emergency_stop_overrides_all_modes():
    registry = CommandRegistry(config_dir="config")
    engine = IntentEngine(registry)

    parsed_dict = engine.parse("pare tudo", in_dictation_mode=True)
    parsed_game = engine.parse("stop everything", in_game_mode=True)

    assert parsed_dict.intent_type == IntentType.EMERGENCY_STOP
    assert parsed_game.intent_type == IntentType.EMERGENCY_STOP