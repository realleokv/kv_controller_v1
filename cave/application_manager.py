# application_manager.py
"""
Safe Windows application launcher with alias resolution, multi-match ambiguity
detection, running-process verification, and strict allowlist enforcement.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from cave.command_registry import CommandRegistry
from cave.security import SecurityValidator

logger = logging.getLogger("cave.application_manager")


@dataclass
class AppLaunchResult:
    """Outcome of an application launch or lookup request."""

    success: bool
    message: str
    ambiguous_candidates: Optional[List[str]] = None
    app_id: Optional[str] = None


class ApplicationManager:
    """Manages discovery, alias matching, and safe launching of Windows applications."""

    def __init__(
        self,
        registry: CommandRegistry,
        process_launcher: Optional[Callable[[List[str]], Any]] = None,
        folder_opener: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._registry = registry
        self._process_launcher = process_launcher or self._default_process_launcher
        self._folder_opener = folder_opener or self._default_folder_opener

    @staticmethod
    def _default_process_launcher(cmd_args: List[str]) -> Any:
        # Never use shell=True
        return subprocess.Popen(
            cmd_args,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def _default_folder_opener(path_or_uri: str) -> Any:
        if hasattr(os, "startfile"):
            os.startfile(path_or_uri)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["explorer", path_or_uri], shell=False)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.strip().lower()
        nfd = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")

    def resolve_application(
        self, spoken_name: str
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], List[str]]:
        """
        Match a spoken application name against registered aliases.
        Returns (matched_app_id, app_config, ambiguous_display_names).
        """
        query = self._normalize(spoken_name)
        # Strip articles like "o", "a", "meu", "the", "my"
        for prefix in ("o ", "a ", "os ", "as ", "meu ", "minha ", "the ", "my "):
            if query.startswith(prefix):
                query = query[len(prefix) :].strip()

        if not query:
            return None, None, []

        apps = self._registry.get_applications()
        exact_matches: List[Tuple[str, Dict[str, Any]]] = []
        partial_matches: List[Tuple[str, Dict[str, Any]]] = []

        for app_id, cfg in apps.items():
            aliases = [self._normalize(a) for a in cfg.get("aliases", [])]
            display_norm = self._normalize(cfg.get("display_name", app_id))
            all_names = set(aliases + [self._normalize(app_id), display_norm])

            if query in all_names:
                exact_matches.append((app_id, cfg))
                continue

            for alias in all_names:
                if query in alias or alias in query:
                    partial_matches.append((app_id, cfg))
                    break
                if SequenceMatcher(None, query, alias).ratio() >= 0.84:
                    partial_matches.append((app_id, cfg))
                    break

        if len(exact_matches) == 1:
            return exact_matches[0][0], exact_matches[0][1], []
        if len(exact_matches) > 1:
            return (
                None,
                None,
                [m[1].get("display_name", m[0]) for m in exact_matches],
            )
        if len(partial_matches) == 1:
            return partial_matches[0][0], partial_matches[0][1], []
        if len(partial_matches) > 1:
            return (
                None,
                None,
                [m[1].get("display_name", m[0]) for m in partial_matches],
            )

        return None, None, []

    @staticmethod
    def is_process_running(process_names: List[str]) -> bool:
        if not process_names:
            return False
        lower_targets = {p.lower() for p in process_names}
        try:
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in lower_targets:
                    return True
        except Exception:
            pass
        return False

    def launch_application(self, spoken_name: str) -> AppLaunchResult:
        """Resolve and safely launch a Windows application, folder, or URI."""
        if not spoken_name or not spoken_name.strip():
            return AppLaunchResult(
                success=False,
                message="Qual aplicativo você gostaria de abrir?",
            )

        app_id, cfg, ambiguous = self.resolve_application(spoken_name)
        if ambiguous:
            names_str = ", ".join(ambiguous)
            return AppLaunchResult(
                success=False,
                message=f"Encontrei múltiplos aplicativos parecidos: {names_str}. Qual deles você deseja abrir?",
                ambiguous_candidates=ambiguous,
            )

        if not app_id or not cfg:
            return AppLaunchResult(
                success=False,
                message=f"Não encontrei o aplicativo '{spoken_name}' registrado.",
            )

        display_name = cfg.get("display_name", app_id)
        launch_type = cfg.get("launch_type", "executable")
        running_policy = self._registry.get_setting(
            "already_running_app_behavior", "focus_or_ignore"
        )

        # Check if already running
        proc_names = cfg.get("process_names", [])
        if (
            launch_type not in ("always_new", "folder", "uri")
            and running_policy == "focus_or_ignore"
            and self.is_process_running(proc_names)
        ):
            return AppLaunchResult(
                success=True,
                message=f"{display_name} já está em execução.",
                app_id=app_id,
            )

        try:
            if launch_type == "folder":
                raw_target = os.path.expandvars(cfg.get("target_path", ""))
                if not os.path.isdir(raw_target):
                    return AppLaunchResult(
                        success=False,
                        message=f"A pasta '{display_name}' não foi encontrada no caminho esperado.",
                    )
                self._folder_opener(raw_target)
                return AppLaunchResult(
                    success=True,
                    message=f"Abrindo {display_name}.",
                    app_id=app_id,
                )

            if launch_type == "uri":
                uri = cfg.get("uri", "")
                if not uri.startswith("ms-"):
                    return AppLaunchResult(
                        success=False,
                        message=f"URI de sistema inválida para {display_name}.",
                    )
                self._folder_opener(uri)
                return AppLaunchResult(
                    success=True,
                    message=f"Abrindo {display_name}.",
                    app_id=app_id,
                )

            if launch_type == "discord_updater":
                candidates = cfg.get("executable_candidates", [])
                for cand in candidates:
                    expanded = os.path.expandvars(cand)
                    parts = shlex.split(expanded, posix=False)
                    exe_path = parts[0].strip('"')
                    if os.path.isfile(exe_path) and SecurityValidator.is_safe_executable_target(exe_path):
                        self._process_launcher([exe_path] + parts[1:])
                        return AppLaunchResult(
                            success=True,
                            message=f"Abrindo {display_name}.",
                            app_id=app_id,
                        )
                return AppLaunchResult(
                    success=False,
                    message=f"{display_name} não está instalado neste computador.",
                )

            # Standard executable launch
            candidates = cfg.get("executable_candidates", [])
            for candidate in candidates:
                expanded = os.path.expandvars(candidate)
                if not SecurityValidator.is_safe_executable_target(expanded):
                    logger.error("Blocked unsafe executable path: %s", expanded)
                    continue
                if os.path.isfile(expanded):
                    self._process_launcher([expanded])
                    return AppLaunchResult(
                        success=True,
                        message=f"Abrindo {display_name}.",
                        app_id=app_id,
                    )

            return AppLaunchResult(
                success=False,
                message=f"Não encontrei o executável de {display_name} neste computador.",
                app_id=app_id,
            )

        except Exception as exc:
            logger.error("Failed to launch %s: %s", display_name, exc)
            return AppLaunchResult(
                success=False,
                message=f"Erro ao abrir {display_name}: {exc}",
                app_id=app_id,
            )