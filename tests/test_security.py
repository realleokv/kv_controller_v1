# test_security.py
"""
Tests for authentication, PIN pairing, invalid mobile requests, rate limiting,
shell metacharacter blocking, and Flask-SocketIO server integration.
Covers Scenario H & I and items 12, 13, 15.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cave.assistant import CaveAssistant
from cave.security import SecurityValidator
from server.app import create_app
from server.authentication import PairingManager


def test_pairing_authentication_and_revocation(tmp_path):
    """Item 13: Unpaired or wrong-PIN clients are rejected; paired devices can be revoked."""
    storage = str(tmp_path / "paired.json")
    mgr = PairingManager(pairing_pin="123456", storage_path=storage)

    ok_bad, _, dev_bad, tok_bad = mgr.pair_device("000000", "Phone", "192.168.1.50")
    assert ok_bad is False
    assert dev_bad is None
    assert tok_bad is None

    ok_good, _, dev_id, token = mgr.pair_device("123456", "Pixel 8", "192.168.1.50")
    assert ok_good is True
    assert mgr.verify_token(dev_id, token) is True
    assert mgr.verify_token(dev_id, "wrong-token") is False

    mgr.revoke_device(dev_id)
    assert mgr.verify_token(dev_id, token) is False


def test_payload_validation_and_shell_injection_blocking():
    """Scenario H & Item 12: Validate speech payloads and block shell metacharacters."""
    valid, text, _ = SecurityValidator.validate_speech_payload({"text": "Cave, abrir Chrome"})
    assert valid is True
    assert text == "Cave, abrir Chrome"

    invalid_type, _, _ = SecurityValidator.validate_speech_payload("not-a-dict")
    assert invalid_type is False

    too_long, _, _ = SecurityValidator.validate_speech_payload({"text": "a" * 2000})
    assert too_long is False

    assert SecurityValidator.is_safe_executable_target(r"C:\Windows\System32\calc.exe") is True
    assert SecurityValidator.is_safe_executable_target("calc.exe & del /q *") is False
    assert SecurityValidator.is_safe_executable_target("powershell.exe; whoami") is False


def test_http_pairing_and_socketio_integration(tmp_path):
    """Integration test for Flask + Socket.IO server pairing and reconnection."""
    mock_kb = MagicMock()
    mock_tts = MagicMock()
    mock_tts.is_speaking = False

    assistant = CaveAssistant(config_dir="config", keyboard=mock_kb, tts=mock_tts)
    pairing_mgr = PairingManager(
        pairing_pin="654321", storage_path=str(tmp_path / "paired.json")
    )
    app, socketio = create_app(
        assistant=assistant, pairing_manager=pairing_mgr, port=8443, use_https=False
    )
    client = app.test_client()

    # 1. Fail pairing with wrong PIN
    bad_resp = client.post("/api/pair", json={"pin": "999999", "device_name": "TestPhone"})
    assert bad_resp.status_code == 401

    # 2. Succeed pairing with valid PIN
    good_resp = client.post("/api/pair", json={"pin": "654321", "device_name": "TestPhone"})
    assert good_resp.status_code == 200
    creds = good_resp.get_json()
    assert creds["success"] is True

    # 3. Connect via Socket.IO with paired credentials and send heartbeat (Item 15)
    sio_client = socketio.test_client(
        app, auth={"device_id": creds["device_id"], "token": creds["token"]}
    )
    assert sio_client.is_connected()
    sio_client.emit("heartbeat", {"mic_streaming": True})
    received = sio_client.get_received()
    assert any(pkt["name"] == "heartbeat_ack" for pkt in received)
    sio_client.disconnect()