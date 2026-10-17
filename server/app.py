# app.py
"""Flask and Flask-SocketIO application factory for CAVE."""

from __future__ import annotations

import os
import secrets
from typing import Tuple

from flask import Flask
from flask_socketio import SocketIO

from cave.assistant import CaveAssistant
from server.authentication import PairingManager
from server.routes import bp as routes_bp
from server.websocket_handlers import register_websocket_handlers


def create_app(
    assistant: CaveAssistant,
    pairing_manager: PairingManager | None = None,
    port: int = 8443,
    use_https: bool = True,
) -> Tuple[Flask, SocketIO]:
    """Create and configure the Flask app and Socket.IO server."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config["SECRET_KEY"] = os.getenv("CAVE_SECRET_KEY", secrets.token_hex(32))
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # 256 KB max HTTP request body
    app.config["ASSISTANT"] = assistant
    app.config["PAIRING_MANAGER"] = pairing_manager or PairingManager(
        pairing_pin=os.getenv("CAVE_PAIRING_PIN", "482910")
    )
    app.config["PORT"] = port
    app.config["USE_HTTPS"] = use_https

    socketio = SocketIO(
        app,
        async_mode="threading",
        cors_allowed_origins="*",
        max_http_buffer_size=131072,
    )

    def broadcast_state(snapshot: dict) -> None:
        try:
            socketio.emit("state_update", snapshot)
        except Exception:
            pass

    assistant.state.set_state_listener(broadcast_state)

    app.register_blueprint(routes_bp)
    register_websocket_handlers(socketio)
    return app, socketio