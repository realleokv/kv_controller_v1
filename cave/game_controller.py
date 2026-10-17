# game_controller.py
"""
Dedicated WASD game-control manager supporting simultaneous continuous key holds,
short-duration movements, duplicate key-down prevention, and a hardware safety watchdog.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Iterable, List, Optional, Set

from cave.keyboard_controller import KeyboardController

logger = logging.getLogger("cave.game_controller")


class GameController:
    """
    Manages simultaneous held keys for games (WASD + modifiers) with strict safety guarantees:
    - Prevents duplicate key_down calls on already-held keys.
    - Releases individual or all keys on command.
    - Runs a background watchdog that automatically releases keys exceeding max_hold_seconds.
    - Immediately releases all keys on mode exit, client disconnect, or emergency stop.
    """

    ALLOWED_GAME_KEYS: Set[str] = {
        "w",
        "a",
        "s",
        "d",
        "shift",
        "space",
        "ctrl",
        "alt",
        "e",
        "q",
        "r",
        "f",
        "c",
        "x",
        "z",
        "v",
        "tab",
        "up",
        "down",
        "left",
        "right",
        "1",
        "2",
        "3",
        "4",
    }

    def __init__(
        self,
        keyboard: KeyboardController,
        max_hold_seconds: float = 30.0,
        short_move_seconds: float = 0.6,
        on_keys_changed: Optional[Callable[[List[str]], None]] = None,
        on_watchdog_release: Optional[Callable[[List[str]], None]] = None,
    ) -> None:
        self._keyboard = keyboard
        self._max_hold_seconds = max(1.0, float(max_hold_seconds))
        self._short_move_seconds = max(0.1, float(short_move_seconds))
        self._on_keys_changed = on_keys_changed
        self._on_watchdog_release = on_watchdog_release

        self._lock = threading.RLock()
        self._enabled: bool = False
        self._held_keys: Dict[str, float] = {}  # key -> monotonic timestamp
        self._watchdog_running: bool = False
        self._watchdog_thread: Optional[threading.Thread] = None

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def held_keys(self) -> List[str]:
        with self._lock:
            return sorted(self._held_keys.keys())

    def set_max_hold_seconds(self, seconds: float) -> None:
        with self._lock:
            self._max_hold_seconds = max(1.0, float(seconds))

    def enable_game_mode(self) -> None:
        with self._lock:
            self._enabled = True
            if not self._watchdog_running:
                self._watchdog_running = True
                self._watchdog_thread = threading.Thread(
                    target=self._watchdog_loop,
                    name="CAVE-GameKeyWatchdog",
                    daemon=True,
                )
                self._watchdog_thread.start()
        logger.info("Game control mode enabled.")

    def disable_game_mode(self) -> List[str]:
        """Disable game mode and unconditionally release all held keys."""
        released = self.release_all_keys(reason="game_mode_disabled")
        with self._lock:
            self._enabled = False
        logger.info("Game control mode disabled; released keys: %s", released)
        return released

    def shutdown(self) -> None:
        """Stop the watchdog thread and release all keys during application exit."""
        self.release_all_keys(reason="shutdown")
        with self._lock:
            self._enabled = False
            self._watchdog_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)

    def hold_keys(self, keys: Iterable[str]) -> List[str]:
        """
        Hold one or more keys simultaneously (e.g., ['w'], ['w', 'd'], ['w', 'shift']).
        If a key is already held, refreshes its watchdog timer without sending a duplicate
        OS key_down event.
        """
        now = time.monotonic()
        newly_held: List[str] = []

        with self._lock:
            if not self._enabled:
                return []

            for raw_k in keys:
                k = raw_k.strip().lower()
                if k not in self.ALLOWED_GAME_KEYS:
                    logger.warning("Ignored disallowed game key hold: %s", k)
                    continue

                if k in self._held_keys:
                    # Refresh hold timestamp without sending duplicate keyDown
                    self._held_keys[k] = now
                    newly_held.append(k)
                else:
                    if self._keyboard.key_down(k):
                        self._held_keys[k] = now
                        newly_held.append(k)

            current_list = sorted(self._held_keys.keys())

        if self._on_keys_changed:
            self._on_keys_changed(current_list)
        return newly_held

    def release_keys(self, keys: Iterable[str]) -> List[str]:
        """Release specified held keys."""
        released: List[str] = []
        with self._lock:
            for raw_k in keys:
                k = raw_k.strip().lower()
                if k in self._held_keys:
                    self._keyboard.key_up(k)
                    del self._held_keys[k]
                    released.append(k)
                else:
                    # Send safety key_up even if not tracked
                    self._keyboard.key_up(k)
            current_list = sorted(self._held_keys.keys())

        if self._on_keys_changed:
            self._on_keys_changed(current_list)
        return released

    def release_all_keys(self, reason: str = "manual") -> List[str]:
        """Immediately release every currently held key."""
        released: List[str] = []
        with self._lock:
            for k in list(self._held_keys.keys()):
                try:
                    self._keyboard.key_up(k)
                except Exception as exc:
                    logger.error("Error releasing key %s: %s", k, exc)
                released.append(k)
            self._held_keys.clear()

        if released:
            logger.info("Released all held keys (%s): %s", reason, released)
        if self._on_keys_changed:
            self._on_keys_changed([])
        return sorted(released)

    def tap_game_key(self, key: str, duration: Optional[float] = None) -> bool:
        """Press and release a key momentarily (or for a short step duration)."""
        norm_key = key.strip().lower()
        if norm_key not in self.ALLOWED_GAME_KEYS:
            return False
        hold_time = duration if duration is not None else 0.05
        return self._keyboard.press_key(norm_key, duration=hold_time)

    def check_expired_holds(self) -> List[str]:
        """Inspect held keys and release any that have exceeded max_hold_seconds."""
        now = time.monotonic()
        expired: List[str] = []
        with self._lock:
            for k, started_at in list(self._held_keys.items()):
                if (now - started_at) >= self._max_hold_seconds:
                    self._keyboard.key_up(k)
                    del self._held_keys[k]
                    expired.append(k)
            current_list = sorted(self._held_keys.keys())

        if expired:
            logger.warning(
                "Watchdog released keys exceeding %.1fs hold limit: %s",
                self._max_hold_seconds,
                expired,
            )
            if self._on_keys_changed:
                self._on_keys_changed(current_list)
            if self._on_watchdog_release:
                self._on_watchdog_release(expired)
        return expired

    def _watchdog_loop(self) -> None:
        while self._watchdog_running:
            try:
                self.check_expired_holds()
            except Exception as exc:
                logger.error("Game watchdog error: %s", exc)
            time.sleep(0.2)