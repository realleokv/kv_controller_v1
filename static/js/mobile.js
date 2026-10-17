// mobile.js
/**
 * CAVE (KV) Mobile Microphone & Remote Control Client
 * - Hands-free continuous microphone capture (16kHz Mono PCM stream + Web Speech API pt-BR)
 * - Screen Wake Lock API + visibility recovery
 * - Authenticated Socket.IO connection with heartbeat & bounded retry
 */
(function () {
  "use strict";

  const STORAGE_DEVICE_ID = "cave_device_id";
  const STORAGE_TOKEN = "cave_device_token";

  let socket = null;
  let audioContext = null;
  let mediaStream = null;
  let scriptProcessor = null;
  let speechRecognizer = null;
  let micStreaming = false;
  let wakeLockSentinel = null;
  let heartbeatInterval = null;
  let pttActive = false;

  const pairingModal = document.getElementById("pairingModal");
  const pairSubmitBtn = document.getElementById("pairSubmitBtn");
  const pairingError = document.getElementById("pairingError");
  const pcStatusPill = document.getElementById("pcStatusPill");
  const micStatusPill = document.getElementById("micStatusPill");
  const modeStatusPill = document.getElementById("modeStatusPill");
  const wakeStatusPill = document.getElementById("wakeStatusPill");
  const voiceOrb = document.getElementById("voiceOrb");
  const liveSpeechText = document.getElementById("liveSpeechText");
  const sessionTimerText = document.getElementById("sessionTimerText");
  const lastCommandText = document.getElementById("lastCommandText");
  const lastResultText = document.getElementById("lastResultText");
  const heldKeysContainer = document.getElementById("heldKeysContainer");
  const mobileHistoryList = document.getElementById("mobileHistoryList");
  const reconnectMicBtn = document.getElementById("reconnectMicBtn");
  const pttFallbackBtn = document.getElementById("pttFallbackBtn");
  const emergencyStopBtn = document.getElementById("emergencyStopBtn");
  const saveMobileSettingsBtn = document.getElementById("saveMobileSettingsBtn");

  function getCredentials() {
    return {
      deviceId: localStorage.getItem(STORAGE_DEVICE_ID),
      token: localStorage.getItem(STORAGE_TOKEN),
    };
  }

  function showPairingModal(reason) {
    if (reason) {
      pairingError.textContent = reason;
    }
    pairingModal.classList.remove("hidden");
  }

  async function pairWithServer() {
    pairingError.textContent = "";
    const pin = document.getElementById("pinInput").value.trim();
    const deviceName = document.getElementById("deviceNameInput").value.trim();
    try {
      const resp = await fetch("/api/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pin, device_name: deviceName }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.success) {
        pairingError.textContent = data.message || "Falha no pareamento.";
        return;
      }
      localStorage.setItem(STORAGE_DEVICE_ID, data.device_id);
      localStorage.setItem(STORAGE_TOKEN, data.token);
      pairingModal.classList.add("hidden");
      connectSocket();
      await startHandsFreeMicrophone();
    } catch (err) {
      pairingError.textContent = "Erro de conexão com o servidor PC.";
    }
  }

  function connectSocket() {
    const creds = getCredentials();
    if (!creds.deviceId || !creds.token) {
      showPairingModal();
      return;
    }

    if (socket) {
      socket.disconnect();
    }

    socket = io({
      auth: { device_id: creds.deviceId, token: creds.token },
      reconnection: true,
      reconnectionDelay: 1500,
      reconnectionDelayMax: 8000,
    });

    socket.on("connect", () => {
      pcStatusPill.textContent = "PC: Conectado";
      pcStatusPill.className = "pill online";
      startHeartbeat();
    });

    socket.on("disconnect", () => {
      pcStatusPill.textContent = "PC: Desconectado";
      pcStatusPill.className = "pill offline";
    });

    socket.on("auth_error", (data) => {
      localStorage.removeItem(STORAGE_DEVICE_ID);
      localStorage.removeItem(STORAGE_TOKEN);
      showPairingModal(data.message || "Sessão revogada. Pareie novamente.");
    });

    socket.on("state_update", (snap) => {
      renderState(snap);
    });

    socket.on("command_result", (res) => {
      lastResultText.textContent = res.message;
    });
  }

  function startHeartbeat() {
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    heartbeatInterval = setInterval(() => {
      if (socket && socket.connected) {
        socket.emit("heartbeat", { mic_streaming: micStreaming });
      }
    }, 2000);
  }

  async function requestScreenWakeLock() {
    if ("wakeLock" in navigator) {
      try {
        wakeLockSentinel = await navigator.wakeLock.request("screen");
      } catch (_) {}
    }
  }

  function downsampleTo16kHzPCM(float32Buffer, inputSampleRate) {
    const targetRate = 16000;
    if (inputSampleRate === targetRate) {
      const int16 = new Int16Array(float32Buffer.length);
      for (let i = 0; i < float32Buffer.length; i++) {
        const s = Math.max(-1, Math.min(1, float32Buffer[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      return int16.buffer;
    }
    const ratio = inputSampleRate / targetRate;
    const newLength = Math.round(float32Buffer.length / ratio);
    const result = new Int16Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accum = 0;
      let count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < float32Buffer.length; i++) {
        accum += float32Buffer[i];
        count++;
      }
      const sample = count > 0 ? accum / count : 0;
      const clamped = Math.max(-1, Math.min(1, sample));
      result[offsetResult] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result.buffer;
  }

  async function startHandsFreeMicrophone() {
    if (!window.isSecureContext) {
      micStatusPill.textContent = "Mic Bloqueado (Requer HTTPS)";
      micStatusPill.className = "pill offline";
      liveSpeechText.textContent =
        "Acesso ao microfone requer contexto seguro (HTTPS). Abra a URL https:// do CAVE.";
      return;
    }

    try {
      stopMicrophoneCapture();
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });

      const audioTracks = mediaStream.getAudioTracks();
      if (audioTracks.length > 0) {
        audioTracks[0].onended = () => {
          handleMicSuspended("Captura de áudio suspensa pelo sistema operacional.");
        };
      }

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      audioContext = new AudioCtx();
      const source = audioContext.createMediaStreamSource(mediaStream);
      scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

      scriptProcessor.onaudioprocess = (event) => {
        if (!micStreaming || !socket || !socket.connected) return;
        const inputData = event.inputBuffer.getChannelData(0);
        const pcm16Buffer = downsampleTo16kHzPCM(inputData, audioContext.sampleRate);
        socket.emit("audio_chunk", pcm16Buffer);
      };

      source.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);

      startBrowserSpeechAssist();
      await requestScreenWakeLock();

      micStreaming = true;
      micStatusPill.textContent = "Microfone: Ativo (Contínuo)";
      micStatusPill.className = "pill online";
    } catch (err) {
      handleMicSuspended("Permissão de microfone negada ou indisponível: " + err.message);
    }
  }

  function startBrowserSpeechAssist() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) return;

    try {
      speechRecognizer = new SpeechRec();
      speechRecognizer.lang = "pt-BR";
      speechRecognizer.continuous = true;
      speechRecognizer.interimResults = true;

      speechRecognizer.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript.trim();
          const isFinal = event.results[i].isFinal;
          if (transcript && socket && socket.connected) {
            socket.emit("speech_recognized", {
              text: transcript,
              is_final: isFinal,
              push_to_talk: pttActive,
            });
          }
        }
      };

      speechRecognizer.onend = () => {
        if (micStreaming && document.visibilityState === "visible") {
          setTimeout(() => {
            try {
              speechRecognizer.start();
            } catch (_) {}
          }, 300);
        }
      };

      speechRecognizer.start();
    } catch (_) {}
  }

  function stopMicrophoneCapture() {
    micStreaming = false;
    if (speechRecognizer) {
      try {
        speechRecognizer.onend = null;
        speechRecognizer.stop();
      } catch (_) {}
      speechRecognizer = null;
    }
    if (scriptProcessor) {
      try {
        scriptProcessor.disconnect();
      } catch (_) {}
      scriptProcessor = null;
    }
    if (audioContext) {
      try {
        audioContext.close();
      } catch (_) {}
      audioContext = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
  }

  function handleMicSuspended(message) {
    micStreaming = false;
    micStatusPill.textContent = "Microfone: Suspenso";
    micStatusPill.className = "pill offline";
    liveSpeechText.textContent = message;
  }

  function renderState(snap) {
    modeStatusPill.textContent = "Modo: " + snap.mode;
    voiceOrb.className = "cave-orb";

    if (snap.mode === "ACTIVE_SESSION" || snap.mode === "DICTATION") {
      voiceOrb.classList.add("listening");
      wakeStatusPill.textContent = "Sessão Ativa (" + snap.session_remaining_seconds + "s)";
      wakeStatusPill.className = "pill online";
    } else if (snap.mode === "GAME_MODE") {
      voiceOrb.classList.add("game");
      wakeStatusPill.textContent = "Modo Jogo Ativo (Comandos Diretos)";
      wakeStatusPill.className = "pill active";
    } else {
      wakeStatusPill.textContent = 'Aguardando Wake Word: "Cave" / "KV"';
      wakeStatusPill.className = "pill standby";
    }

    if (snap.current_speech) {
      liveSpeechText.textContent = '"' + snap.current_speech + '"';
    }
    if (snap.last_recognized_command) {
      lastCommandText.textContent = snap.last_recognized_command;
    }
    if (snap.last_action_result) {
      lastResultText.textContent = snap.last_action_result;
    }

    if (snap.held_keys && snap.held_keys.length > 0) {
      heldKeysContainer.innerHTML = snap.held_keys
        .map((k) => '<span class="key-badge">' + k.toUpperCase() + "</span>")
        .join("");
    } else {
      heldKeysContainer.innerHTML =
        '<span style="color: var(--text-muted); font-size: 0.85rem;">Nenhuma tecla pressionada</span>';
    }

    if (Array.isArray(snap.history)) {
      mobileHistoryList.innerHTML = snap.history
        .slice(0, 12)
        .map(
          (item) =>
            '<li class="history-item"><strong>[' +
            item.timestamp +
            "] " +
            item.command +
            "</strong><br/><span>" +
            item.result +
            "</span></li>"
        )
        .join("");
    }
  }

  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible") {
      await requestScreenWakeLock();
      if (!micStreaming && getCredentials().token) {
        await startHandsFreeMicrophone();
      }
    }
  });

  pairSubmitBtn.addEventListener("click", pairWithServer);
  reconnectMicBtn.addEventListener("click", startHandsFreeMicrophone);

  pttFallbackBtn.addEventListener("mousedown", () => {
    pttActive = true;
    pttFallbackBtn.classList.add("btn-primary");
  });
  pttFallbackBtn.addEventListener("mouseup", () => {
    setTimeout(() => {
      pttActive = false;
      pttFallbackBtn.classList.remove("btn-primary");
    }, 600);
  });

  emergencyStopBtn.addEventListener("click", () => {
    if (socket && socket.connected) {
      socket.emit("emergency_stop");
    }
  });

  saveMobileSettingsBtn.addEventListener("click", async () => {
    const creds = getCredentials();
    const sens = parseFloat(document.getElementById("sensitivityRange").value);
    const timeout = parseFloat(document.getElementById("timeoutInput").value);
    await fetch("/api/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Cave-Device-Id": creds.deviceId || "",
        "X-Cave-Token": creds.token || "",
      },
      body: JSON.stringify({
        wake_word_sensitivity: sens,
        command_session_timeout_seconds: timeout,
      }),
    });
  });

  // Initialize on page load
  const creds = getCredentials();
  if (!creds.deviceId || !creds.token) {
    showPairingModal();
  } else {
    connectSocket();
    startHandsFreeMicrophone();
  }
})();