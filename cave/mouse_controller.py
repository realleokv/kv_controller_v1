# mouse_controller.py
"""Windows mouse movement, click, and scroll automation."""

from __future__ import annotations

import logging
from threading import RLock

logger = logging.getLogger("cave.mouse_controller")

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None


class MouseController:
    """Thread-safe mouse automation controller."""

    def __init__(self) -> None:
        self._lock = RLock()

    def move_relative(self, dx: int, dy: int, duration: float = 0.15) -> bool:
        with self._lock:
            try:
                if pyautogui is not None:
                    pyautogui.moveRel(dx, dy, duration=duration)
                    return True
            except Exception as exc:
                logger.error("Mouse move_relative failed: %s", exc)
            return False

    def click(self, button: str = "left", clicks: int = 1) -> bool:
        with self._lock:
            try:
                if pyautogui is not None:
                    pyautogui.click(button=button, clicks=clicks)
                    return True
            except Exception as exc:
                logger.error("Mouse click failed: %s", exc)
            return False

    def scroll(self, clicks: int) -> bool:
        with self._lock:
            try:
                if pyautogui is not None:
                    pyautogui.scroll(clicks)
                    return True
            except Exception as exc:
                logger.error("Mouse scroll failed: %s", exc)
            return False