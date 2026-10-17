# main.py
"""
Main entrypoint for CAVE (KV) — Personal AI Desktop Assistant.
Handles environment loading, logging setup, TLS certificate creation,
graceful shutdown signals, and starting the server and assistant engine.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from dotenv import load_dotenv

from cave.assistant import CaveAssistant
from cave.logging_config import setup_logging
from server.app import create_app
from server.authentication import PairingManager
from server.tls import ensure_local_tls_cert, get_local_lan_ip


def main() -> None:
    load_dotenv()
    setup_logging()
    logger = logging.getLogger("cave.main")

    host = os.getenv("CAVE_HOST", "0.0.0.0")
    port = int(os.getenv("CAVE_PORT", "8443"))
    use_https = os.getenv("CAVE_USE_HTTPS", "true").lower() in ("1", "true", "yes")
    pairing_pin = os.getenv("CAVE_PAIRING_PIN", "482910")

    assistant = CaveAssistant(config_dir="config")
    pairing_manager = PairingManager(pairing_pin=pairing_pin)
    app, socketio = create_app(
        assistant=assistant,
        pairing_manager=pairing_manager,
        port=port,
        use_https=use_https,
    )

    def _graceful_shutdown(signum: int, frame: object) -> None:
        logger.info("Received shutdown signal (%s). Releasing keys and stopping CAVE...", signum)
        assistant.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    assistant.start()

    lan_ip = get_local_lan_ip()
    scheme = "https" if use_https else "http"
    print("\n" + "=" * 68)
    print("  CAVE (KV) — PERSONAL AI DESKTOP ASSISTANT ONLINE")
    print("=" * 68)
    print(f"  Desktop Dashboard : {scheme}://127.0.0.1:{port}/")
    print(f"  Mobile Remote URL : {scheme}://{lan_ip}:{port}/mobile")
    print(f"  Mobile Pairing PIN: {pairing_pin}")
    print("=" * 68 + "\n")

    try:
        if use_https:
            cert_path, key_path = ensure_local_tls_cert()
            socketio.run(
                app,
                host=host,
                port=port,
                ssl_context=(cert_path, key_path),
                allow_unsafe_werkzeug=True,
            )
        else:
            socketio
            
        if use_https:
            cert_path, key_path = ensure_local_tls_cert()
            socketio.run(
                app,
                host=host,
                port=port,
                ssl_context=(cert_path, key_path),
                allow_unsafe_werkzeug=True,
            )
        else:
            socketio.run(
                app,
                host=host,
                port=port,
                allow_unsafe_werkzeug=True,
            )
    finally:
        assistant.stop()


if __name__ == "__main__":
    main()