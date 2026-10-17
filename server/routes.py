# routes.py
"""HTTP routes for the desktop dashboard, mobile remote interface, and REST APIs."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from cave.logging_config import get_error_ring
from server.tls import get_local_lan_ip

bp = Blueprint("cave_routes", __name__)


def _is_local_dashboard_request() -> bool:
    """Dashboard management routes are restricted to localhost or paired tokens."""
    if request.remote_addr in ("127.0.0.1", "::1"):
        return True
    auth_mgr = current_app.config["PAIRING_MANAGER"]
    dev_id = request.headers.get("X-Cave-Device-Id")
    token = request.headers.get("X-Cave-Token")
    return auth_mgr.verify_token(dev_id, token)


@bp.route("/")
def dashboard_page() -> str:
    assistant = current_app.config["ASSISTANT"]
    auth_mgr = current_app.config["PAIRING_MANAGER"]
    port = current_app.config.get("PORT", 8443)
    scheme = "https" if current_app.config.get("USE_HTTPS", True) else "http"
    lan_ip = get_local_lan_ip()
    mobile_url = f"{scheme}://{lan_ip}:{port}/mobile"
    return render_template(
        "dashboard.html",
        mobile_url=mobile_url,
        pairing_pin=auth_mgr.pairing_pin,
        settings=assistant.registry.get_all_settings(),
    )


@bp.route("/mobile")
def mobile_page() -> str:
    return render_template("mobile.html")


@bp.route("/api/pair", methods=["POST"])
def api_pair_device():
    auth_mgr = current_app.config["PAIRING_MANAGER"]
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin", "")).strip()
    device_name = str(data.get("device_name", "Android Browser")).strip()
    ok, msg, device_id, token = auth_mgr.pair_device(
        pin, device_name, request.remote_addr or "unknown"
    )
    status_code = 200 if ok else 401
    return (
        jsonify(
            {
                "success": ok,
                "message": msg,
                "device_id": device_id,
                "token": token,
            }
        ),
        status_code,
    )


@bp.route("/api/status", methods=["GET"])
def api_status():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    assistant = current_app.config["ASSISTANT"]
    auth_mgr = current_app.config["PAIRING_MANAGER"]
    snapshot = assistant.state.get_snapshot()
    snapshot["recent_errors"] = get_error_ring().get_recent()
    snapshot["paired_devices"] = auth_mgr.list_devices()
    snapshot["settings"] = assistant.registry.get_all_settings()
    snapshot["applications"] = assistant.registry.get_applications()
    return jsonify(snapshot)


@bp.route("/api/settings", methods=["POST"])
def api_update_settings():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    assistant = current_app.config["ASSISTANT"]
    data = request.get_json(silent=True) or {}
    updated = assistant.apply_updated_settings(data)
    return jsonify({"success": True, "settings": updated})


@bp.route("/api/applications", methods=["POST"])
def api_register_app():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    assistant = current_app.config["ASSISTANT"]
    data = request.get_json(silent=True) or {}
    app_id = str(data.get("app_id", "")).strip()
    display_name = str(data.get("display_name", "")).strip()
    executable_path = str(data.get("executable_path", "")).strip()
    aliases = data.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.split(",") if a.strip()]

    if not app_id or not display_name or not executable_path:
        return jsonify({"success": False, "message": "Campos obrigatórios ausentes."}), 400

    assistant.registry.register_application(
        app_id=app_id,
        display_name=display_name,
        aliases=aliases,
        executable_path=executable_path,
    )
    return jsonify(
        {"success": True, "applications": assistant.registry.get_applications()}
    )


@bp.route("/api/revoke_device", methods=["POST"])
def api_revoke_device():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    auth_mgr = current_app.config["PAIRING_MANAGER"]
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", ""))
    revoked = auth_mgr.revoke_device(device_id)
    return jsonify({"success": revoked, "paired_devices": auth_mgr.list_devices()})


@bp.route("/api/emergency_stop", methods=["POST"])
def api_emergency_stop():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    assistant = current_app.config["ASSISTANT"]
    res = assistant.emergency_stop(reason="http_emergency_button")
    return jsonify({"success": res.success, "message": res.message})


@bp.route("/api/clear_history", methods=["POST"])
def api_clear_history():
    if not _is_local_dashboard_request():
        return jsonify({"error": "Unauthorized"}), 401
    assistant = current_app.config["ASSISTANT"]
    assistant.state.clear_history()
    get_error_ring().clear()
    return jsonify({"success": True})