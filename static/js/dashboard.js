// dashboard.js
/**
 * CAVE (KV) Desktop Dashboard Controller
 */
(function () {
  "use strict";

  const socket = io();

  const uptimeBadge = document.getElementById("uptimeBadge");
  const dashModePill = document.getElementById("dashModePill");
  const dashStagePill = document.getElementById("dashStagePill");
  const dashPcMicPill = document.getElementById("dashPcMicPill");
  const dashMobilePill = document.getElementById("dashMobilePill");
  const dashMobileMicPill = document.getElementById("dashMobileMicPill");
  const dashCurrentSpeech = document.getElementById("dashCurrentSpeech");
  const dashLastCommand = document.getElementById("dashLastCommand");
  const dashLastResult = document.getElementById("dashLastResult");
  const dashHeldKeys = document.getElementById("dashHeldKeys");
  const dashHistoryList = document.getElementById("dashHistoryList");
  const dashErrorsList = document.getElementById("dashErrorsList");
  const pairedDevicesList = document.getElementById("pairedDevicesList");

  function updateUI(snap) {
    uptimeBadge.textContent = "Uptime: " + snap.uptime_seconds + "s";
    dashModePill.textContent = "Modo: " + snap.mode;
    dashStagePill.textContent = "Estágio: " + snap.stage;

    dashPcMicPill.textContent = snap.pc_mic_active ? "Mic PC: Ativo" : "Mic PC: Inativo";
    dashPcMicPill.className = "pill " + (snap.pc_mic_active ? "online" : "offline");

    dashMobilePill.textContent = snap.mobile_connected
      ? "Celular: Conectado (" + (snap.mobile_device_id || "") + ")"
      : "Celular: Desconectado";
    dashMobilePill.className = "pill " + (snap.mobile_connected ? "online" : "offline");

    dashMobileMicPill.textContent = snap.mobile_mic_streaming
      ? "Stream Mobile: Ativo"
      : "Stream Mobile: Inativo";
    dashMobileMicPill.className = "pill " + (snap.mobile_mic_streaming ? "online" : "standby");

    dashCurrentSpeech.textContent = snap.current_speech || "—";
    dashLastCommand.textContent = snap.last_recognized_command || "—";
    dashLastResult.textContent = snap.last_action_result || "—";

    if (snap.held_keys && snap.held_keys.length > 0) {
      dashHeldKeys.innerHTML = snap.held_keys
        .map((k) => '<span class="key-badge">' + k.toUpperCase() + "</span>")
        .join("");
    } else {
      dashHeldKeys.textContent = "Nenhuma";
    }

    if (Array.isArray(snap.history)) {
      dashHistoryList.innerHTML = snap.history
        .map(
          (h) =>
            '<li class="history-item"><strong>[' +
            h.timestamp +
            "] (" +
            h.mode +
            ") " +
            h.command +
            "</strong><br/><span>" +
            h.result +
            "</span></li>"
        )
        .join("");
    }
  }

  async function refreshFullStatus() {
    try {
      const resp = await fetch("/api/status");
      if (!resp.ok) return;
      const data = await resp.json();
      updateUI(data);

      if (Array.isArray(data.paired_devices)) {
        pairedDevicesList.innerHTML =
          data.paired_devices.length === 0
            ? '<li class="history-item">Nenhum dispositivo pareado.</li>'
            : data.paired_devices
                .map(
                  (d) =>
                    '<li class="history-item" style="display:flex; justify-content:space-between; align-items:center;">' +
                    "<span><strong>" +
                    d.device_name +
                    "</strong> (" +
                    d.client_ip +
                    ")</span>" +
                    '<button class="btn btn-danger" style="padding:0.2rem 0.5rem; font-size:0.75rem;" data-revoke="' +
                    d.device_id +
                    '">Revogar</button></li>'
                )
                .join("");
      }

      if (Array.isArray(data.recent_errors)) {
        dashErrorsList.innerHTML =
          data.recent_errors.length === 0
            ? '<li class="history-item" style="color: var(--text-muted);">Nenhum erro registrado.</li>'
            : data.recent_errors
                .map(
                  (e) =>
                    '<li class="history-item" style="color: #f87171;">' +
                    e.message +
                    "</li>"
                )
                .join("");
      }
    } catch (_) {}
  }

  socket.on("state_update", updateUI);

  pairedDevicesList.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-revoke]");
    if (!btn) return;
    const deviceId = btn.getAttribute("data-revoke");
    await fetch("/api/revoke_device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId }),
    });
    refreshFullStatus();
  });

  document.getElementById("dashEmergencyBtn").addEventListener("click", async () => {
    await fetch("/api/emergency_stop", { method: "POST" });
  });

  document.getElementById("saveDashSettingsBtn").addEventListener("click", async () => {
    const payload = {
      wake_word_sensitivity: parseFloat(document.getElementById("cfgSensitivity").value),
      command_session_timeout_seconds: parseFloat(document.getElementById("cfgTimeout").value),
      max_key_hold_seconds: parseFloat(document.getElementById("cfgMaxHold").value),
      tts_silent_mode: document.getElementById("cfgTtsSilent").value === "true",
      ai_enabled: document.getElementById("cfgAiEnabled").value === "true",
    };
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    refreshFullStatus();
  });

  document.getElementById("registerAppBtn").addEventListener("click", async () => {
    const payload = {
      app_id: document.getElementById("newAppId").value.trim(),
      display_name: document.getElementById("newAppName").value.trim(),
      aliases: document.getElementById("newAppAliases").value.trim(),
      executable_path: document.getElementById("newAppExe").value.trim(),
    };
    const resp = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      document.getElementById("newAppId").value = "";
      document.getElementById("newAppName").value = "";
      document.getElementById("newAppAliases").value = "";
      document.getElementById("newAppExe").value = "";
      refreshFullStatus();
    }
  });

  document.getElementById("clearHistoryBtn").addEventListener("click", async () => {
    await fetch("/api/clear_history", { method: "POST" });
    refreshFullStatus();
  });

  refreshFullStatus();
  setInterval(refreshFullStatus, 4000);
})();