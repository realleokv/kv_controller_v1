# authentication.py
"""
Mobile device PIN pairing, HMAC token issuance, verification, and revocation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from threading import RLock
from typing import Dict, List, Optional, Tuple


class PairingManager:
    """Manages paired mobile devices, pairing PIN verification, and revocation."""

    def __init__(
        self,
        pairing_pin: str = "482910",
        storage_path: str = "config/paired_devices.json",
    ) -> None:
        self._pin = str(pairing_pin).strip()
        self._storage_path = storage_path
        self._lock = RLock()
        self._devices: Dict[str, Dict[str, str]] = {}
        self._failed_attempts: Dict[str, Tuple[int, float]] = {}
        self._load()

    @property
    def pairing_pin(self) -> str:
        return self._pin

    def _load(self) -> None:
        if os.path.isfile(self._storage_path):
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    self._devices = json.load(f)
            except Exception:
                self._devices = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._storage_path) or ".", exist_ok=True)
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(self._devices, f, indent=2, ensure_ascii=False)

    def pair_device(
        self, submitted_pin: str, device_name: str, client_ip: str
    ) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Verify the 6-digit PIN and issue a device_id and secret token.
        Enforces brute-force lockout after 5 failed attempts from an IP.
        """
        now = time.monotonic()
        with self._lock:
            fails, last_ts = self._failed_attempts.get(client_ip, (0, 0.0))
            if fails >= 5 and (now - last_ts) < 60.0:
                return (
                    False,
                    "Muitas tentativas incorretas. Aguarde 60 segundos.",
                    None,
                    None,
                )

            if not hmac.compare_digest(str(submitted_pin).strip(), self._pin):
                self._failed_attempts[client_ip] = (fails + 1, now)
                return False, "PIN de pareamento inválido.", None, None

            self._failed_attempts.pop(client_ip, None)
            device_id = f"mob-{secrets.token_hex(4)}"
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

            self._devices[device_id] = {
                "device_id": device_id,
                "device_name": (device_name or "Smartphone")[:60],
                "client_ip": client_ip,
                "token_hash": token_hash,
                "paired_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save()
            return True, "Dispositivo pareado com sucesso.", device_id, raw_token

    def verify_token(self, device_id: Optional[str], raw_token: Optional[str]) -> bool:
        """Return True if device_id is paired and raw_token matches its SHA-256 hash."""
        if not device_id or not raw_token:
            return False
        with self._lock:
            record = self._devices.get(device_id)
            if not record:
                return False
            candidate_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            return hmac.compare_digest(candidate_hash, record.get("token_hash", ""))

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a previously paired device."""
        with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                self._save()
                return True
            return False

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._devices)
            self._devices.clear()
            self._save()
            return count

    def list_devices(self) -> List[Dict[str, str]]:
        with self._lock:
            return [
                {
                    "device_id": d["device_id"],
                    "device_name": d["device_name"],
                    "client_ip": d["client_ip"],
                    "paired_at": d["paired_at"],
                }
                for d in self._devices.values()
            ]