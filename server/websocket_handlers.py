# websocket_handlers.py
"""
Authenticated Socket.IO real-time event handlers for mobile microphone audio streaming,
speech recognition events, heartbeats, and emergency stop controls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import current_app, request
from flask_socketio import SocketIO, disconnect, emit

from cave.security import SecurityValidator

logger = logging.getLogger("cave.server.websocket")


def register_websocket_handlers(socketio: SocketIO) -> None:
    """Register Socket.IO event handlers on the provided server instance."""

    validator = SecurityValidator()
    authenticated_sids: Dict[str, str] = {}  # sid -> device_id

    def _is_sid_authorized(sid: str) -> bool:
        if request.remote_addr in ("127.0.0.1", "::1"):
            return True
        device_id = authenticated_sids.get(sid)
        if not device_id:
            return False
        auth_mgr = current_app.config["PAIRING_MANAGER"]
        return any(d["device_id"] == device_id for d in auth_mgr.list_devices())

    @socketio.on("connect")
    def handle_connect(auth: Dict[str, Any] | None = None):
        assistant = current_app.config["ASSISTANT"]
        auth_mgr = current_app.config["PAIRING_MANAGER"]
        sid = request.sid

        if request.remote_addr in ("127.0.0.1", "::1") and not auth:
            authenticated_sids[sid] = "localhost-dashboard"
            emit("state_update", assistant.state.get_snapshot())
            return True

        auth_data = auth if isinstance(auth, dict) else {}
        device_id = auth_data.get("device_id") or request.args.get("device_id")
        token = auth_data.get("token") or request.args.get("token")

        if not auth_mgr.verify_token(device_id, token):
            logger.warning(
                "Rejected unauthenticated Socket.IO connection from %s",
                request.remote_addr,
            )
            emit("auth_error", {"message": "Dispositivo não pareado ou token inválido."})
            disconnect()
            return False

        authenticated_sids[sid] = str(device_id)
        assistant.state.set_mobile_connection(
            connected=True, device_id=str(device_id), mic_streaming=False
        )
        logger.info("Authenticated mobile client connected: %s", device_id)
        emit("state_update", assistant.state.get_snapshot())
        return True

    @socketio.on("disconnect")
    def handle_disconnect():
        sid = request.sid
        device_id = authenticated_sids.pop(sid, None)
        if device_id and device_id != "localhost-dashboard":
            assistant = current_app.config["ASSISTANT"]
            logger.info("Mobile client %s disconnected.", device_id)
            assistant.handle_mobile_disconnect()

    @socketio.on("heartbeat")
    def handle_heartbeat(payload: Any = None):
        sid = request.sid
        if not _is_sid_authorized(sid):
            emit("auth_error", {"message": "Não autorizado."})
            return
        assistant = current_app.config["ASSISTANT"]
        mic_active = (
            bool(payload.get("mic_streaming", False))
            if isinstance(payload, dict)
            else None
        )
        assistant.state.update_mobile_heartbeat(mic_streaming=mic_active)
        emit(
            "heartbeat_ack",
            {
                "server_time": assistant.state.get_snapshot()["uptime_seconds"],
                "mode": assistant.state.mode.value,
            },
        )

    @socketio.on("speech_recognized")
    def handle_speech_recognized(payload: Any):
        sid = request.sid
        if not _is_sid_authorized(sid):
            emit("auth_error", {"message": "Não autorizado."})
            return
        if not validator.check_rate_limit(sid):
            emit("error_message", {"message": "Limite de requisições excedido."})
            return

        is_valid, text, err = validator.validate_speech_payload(payload)
        if not is_valid:
            emit("error_message", {"message": err})
            return

        bypass_wake = bool(payload.get("push_to_talk", False))
        assistant = current_app.config["ASSISTANT"]
        is_final = bool(payload.get("is_final", True))

        if not is_final:
            assistant.state.update_speech_preview(text)
            return

        res = assistant.process_utterance(
            text, source="mobile", bypass_wake_word=bypass_wake
        )
        if res is not None:
            emit(
                "command_result",
                {"success": res.success, "message": res.message},
            )

    @socketio.on("audio_chunk")
    def handle_audio_chunk(raw_pcm: Any):
        sid = request.sid
        if not _is_sid_authorized(sid):
            return
        is_valid, _ = validator.validate_audio_chunk(raw_pcm)
        if not is_valid:
            return
        assistant = current_app.config["ASSISTANT"]
        assistant.state.update_mobile_heartbeat(mic_streaming=True)
        assistant.asr.accept_pcm_chunk(bytes(raw_pcm), source="mobile")

    @socketio.on("emergency_stop")
    def handle_emergency_stop(payload: Any = None):
        sid = request.sid
        if not _is_sid_authorized(sid):
            emit("auth_error", {"message": "Não autorizado."})
            return
        assistant = current_app.config["ASSISTANT"]
        res = assistant.emergency_stop(reason="mobile_emergency_button")
        emit("command_result", {"success": res.success, "message": res.message})