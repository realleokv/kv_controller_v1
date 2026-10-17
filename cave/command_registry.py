# command_registry.py
"""Configurable command, application, and keyboard mapping registry."""

from __future__ import annotations

import json
import os
from threading import RLock
from typing import Any, Dict, List, Optional


class CommandRegistry:
    """Loads, validates, and manages CAVE settings, apps, and command mappings."""

    def __init__(self, config_dir: str = "config") -> None:
        self._config_dir = config_dir
        self._lock = RLock()
        self.settings_path = os.path.join(config_dir, "settings.json")
        self.apps_path = os.path.join(config_dir, "applications.json")
        self.commands_path = os.path.join(config_dir, "commands.json")

        self._settings: Dict[str, Any] = {}
        self._applications: Dict[str, Dict[str, Any]] = {}
        self._commands: Dict[str, Any] = {}
        self.reload_all()

    def reload_all(self) -> None:
        """Reload all JSON configuration files safely."""
        with self._lock:
            self._settings = self._load_json(self.settings_path, default={})
            apps_data = self._load_json(self.apps_path, default={"applications": {}})
            self._applications = apps_data.get("applications", {})
            self._commands = self._load_json(self.commands_path, default={})

    @staticmethod
    def _load_json(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
        if not os.path.exists(path):
            return dict(default)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update and persist validated settings."""
        allowed_keys = {
            "wake_word_sensitivity",
            "command_session_timeout_seconds",
            "duplicate_suppression_window_seconds",
            "require_confirmation_for_sensitive_actions",
            "already_running_app_behavior",
            "max_key_hold_seconds",
            "short_move_duration_seconds",
            "heartbeat_timeout_seconds",
            "tts_enabled",
            "tts_silent_mode",
            "tts_rate",
            "tts_volume",
            "verbose_key_feedback",
            "log_dictated_text",
            "enable_local_pc_microphone",
            "enable_mobile_microphone",
            "ai_enabled",
            "ai_provider",
            "dictation_auto_capitalize",
            "dictation_normalize_punctuation",
        }
        with self._lock:
            for k, v in updates.items():
                if k in allowed_keys:
                    self._settings[k] = v
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
            return dict(self._settings)

    def register_application(
        self,
        app_id: str,
        display_name: str,
        aliases: List[str],
        executable_path: str,
        process_names: Optional[List[str]] = None,
    ) -> None:
        """Register or update a custom application in applications.json."""
        clean_id = app_id.strip().lower().replace(" ", "_")
        with self._lock:
            self._applications[clean_id] = {
                "display_name": display_name.strip(),
                "aliases": [a.strip().lower() for a in aliases if a.strip()],
                "process_names": process_names or [os.path.basename(executable_path)],
                "executable_candidates": [executable_path.strip()],
                "launch_type": "executable",
            }
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self.apps_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"applications": self._applications},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._settings.get(key, default)

    def get_all_settings(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    def get_applications(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._applications)

    def get_punctuation_map(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._commands.get("punctuation_map", {}))

    def get_key_aliases(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._commands.get("key_aliases", {}))

    def get_shortcut_aliases(self) -> Dict[str, List[str]]:
        with self._lock:
            return dict(self._commands.get("shortcut_aliases", {}))

    def get_game_movement_aliases(self) -> Dict[str, List[str]]:
        with self._lock:
            return dict(self._commands.get("game_movement_aliases", {}))