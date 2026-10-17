# keyboard_controller.py
"""
Low-level Windows keyboard controller using Win32 SendInput hardware scan codes
for game compatibility and PyAutoGUI for desktop shortcuts.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from threading import RLock
from typing import Dict, List, Optional

logger = logging.getLogger("cave.keyboard_controller")

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.01
except Exception:  # pragma: no cover
    pyautogui = None


# Win32 Hardware Scan Codes (Set 1) for reliable DirectInput/Game compatibility
WIN32_SCANCODES: Dict[str, int] = {
    "esc": 0x01,
    "1": 0x02,
    "2": 0x03,
    "3": 0x04,
    "4": 0x05,
    "5": 0x06,
    "6": 0x07,
    "7": 0x08,
    "8": 0x09,
    "9": 0x0A,
    "0": 0x0B,
    "backspace": 0x0E,
    "tab": 0x0F,
    "q": 0x10,
    "w": 0x11,
    "e": 0x12,
    "r": 0x13,
    "t": 0x14,
    "y": 0x15,
    "u": 0x16,
    "i": 0x17,
    "o": 0x18,
    "p": 0x19,
    "enter": 0x1C,
    "ctrl": 0x1D,
    "a": 0x1E,
    "s": 0x1F,
    "d": 0x20,
    "f": 0x21,
    "g": 0x22,
    "h": 0x23,
    "j": 0x24,
    "k": 0x25,
    "l": 0x26,
    "shift": 0x2A,
    "z": 0x2C,
    "x": 0x2D,
    "c": 0x2E,
    "v": 0x2F,
    "b": 0x30,
    "n": 0x31,
    "m": 0x32,
    "alt": 0x38,
    "space": 0x39,
    "f1": 0x3B,
    "f2": 0x3C,
    "f3": 0x3D,
    "f4": 0x3E,
    "f5": 0x3F,
    "f6": 0x40,
    "f7": 0x41,
    "f8": 0x42,
    "f9": 0x43,
    "f10": 0x44,
    "f11": 0x57,
    "f12": 0x58,
    "home": 0x47,
    "up": 0x48,
    "pageup": 0x49,
    "left": 0x4B,
    "right": 0x4D,
    "end": 0x4F,
    "down": 0x50,
    "pagedown": 0x51,
    "delete": 0x53,
}

EXTENDED_KEYS = {"up", "down", "left", "right", "home", "end", "pageup", "pagedown", "delete"}


# Win32 SendInput C structures for Windows
if sys.platform == "win32":
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KeyBdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_short),
            ("wParamH", ctypes.c_ushort),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class Input_I(ctypes.Union):
        _fields_ = [
            ("ki", KeyBdInput),
            ("mi", MouseInput),
            ("hi", HardwareInput),
        ]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]


class KeyboardController:
    """Thread-safe Windows keyboard automation controller."""

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def __init__(self, use_win32_scancodes: bool = True) -> None:
        self._lock = RLock()
        self._use_scancodes = use_win32_scancodes and (sys.platform == "win32")

    def _send_win32_scancode(self, key: str, key_up: bool = False) -> bool:
        scancode = WIN32_SCANCODES.get(key.lower())
        if scancode is None or sys.platform != "win32":
            return False
        flags = self.KEYEVENTF_SCANCODE
        if key.lower() in EXTENDED_KEYS:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= self.KEYEVENTF_KEYUP

        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scancode, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        return True

    def key_down(self, key: str) -> bool:
        """Press and hold a key down without releasing it."""
        norm_key = key.strip().lower()
        with self._lock:
            try:
                if self._use_scancodes and self._send_win32_scancode(norm_key, key_up=False):
                    return True
                if pyautogui is not None:
                    pyautogui.keyDown(norm_key)
                    return True
            except Exception as exc:
                logger.error("Failed key_down(%s): %s", norm_key, exc)
            return False

    def key_up(self, key: str) -> bool:
        """Release a held key."""
        norm_key = key.strip().lower()
        with self._lock:
            try:
                if self._use_scancodes and self._send_win32_scancode(norm_key, key_up=True):
                    return True
                if pyautogui is not None:
                    pyautogui.keyUp(norm_key)
                    return True
            except Exception as exc:
                logger.error("Failed key_up(%s): %s", norm_key, exc)
            return False

    def press_key(self, key: str, duration: float = 0.04) -> bool:
        """Perform a momentary key press and release."""
        norm_key = key.strip().lower()
        with self._lock:
            if not self.key_down(norm_key):
                return False
            time.sleep(max(0.01, duration))
            return self.key_up(norm_key)

    def press_shortcut(self, keys: List[str]) -> bool:
        """Execute a key combination such as ['ctrl', 'c'] or ['alt', 'tab']."""
        if not keys:
            return False
        norm_keys = [k.strip().lower() for k in keys if k.strip()]
        with self._lock:
            try:
                if pyautogui is not None:
                    pyautogui.hotkey(*norm_keys, interval=0.02)
                    return True
                # Fallback via sequential key_down / reverse key_up
                for k in norm_keys:
                    self.key_down(k)
                time.sleep(0.03)
                for k in reversed(norm_keys):
                    self.key_up(k)
                return True
            except Exception as exc:
                logger.error("Failed press_shortcut(%s): %s", norm_keys, exc)
                for k in reversed(norm_keys):
                    self.key_up(k)
                return False

    def type_unicode_string(self, text: str) -> bool:
        """Fallback character-by-character typing if clipboard paste is unavailable."""
        with self._lock:
            try:
                if pyautogui is not None:
                    pyautogui.write(text, interval=0.01)
                    return True
            except Exception as exc:
                logger.error("Failed type_unicode_string: %s", exc)
            return False