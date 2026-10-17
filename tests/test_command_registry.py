# test_command_registry.py
"""
Tests for application alias resolution, unknown application handling,
and safe launching without arbitrary shell execution.
Covers item 5.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cave.application_manager import ApplicationManager
from cave.command_registry import CommandRegistry


def test_resolve_known_application_aliases():
    registry = CommandRegistry(config_dir="config")
    manager = ApplicationManager(registry)

    app_id, cfg, ambiguous = manager.resolve_application("meu navegador")
    assert app_id == "chrome"
    assert cfg is not None
    assert ambiguous == []

    app_id2, _, _ = manager.resolve_application("gerenciador de tarefas")
    assert app_id2 == "task_manager"


def test_unknown_application_handling():
    registry = CommandRegistry(config_dir="config")
    mock_launcher = MagicMock()
    manager = ApplicationManager(registry, process_launcher=mock_launcher)

    result = manager.launch_application("AplicativoInexistenteXYZ")
    assert result.success is False
    assert "Não encontrei" in result.message
    mock_launcher.assert_not_called()


@patch("os.path.isfile", return_value=True)
@patch.object(ApplicationManager, "is_process_running", return_value=False)
def test_safe_executable_launch_calls_popen_list(mock_running, mock_isfile):
    registry = CommandRegistry(config_dir="config")
    mock_launcher = MagicMock()
    manager = ApplicationManager(registry, process_launcher=mock_launcher)

    res = manager.launch_application("calculadora")
    assert res.success is True
    mock_launcher.assert_called_once()
    called_args = mock_launcher.call_args[0][0]
    assert isinstance(called_args, list)