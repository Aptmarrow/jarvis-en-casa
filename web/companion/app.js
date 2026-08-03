/**
 * J.A.R.V.I.S. — Moto g04 Dedicated Companion App (Protocol v1)
 */

const PROTOCOL_VERSION = 1;
const SECRET_TOKEN = "jarvis_moto_g04_owner_secret_token_8765";

// DOM Elements
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const chatView = document.getElementById("chatView");
const dashView = document.getElementById("dashView");
const micBtn = document.getElementById("micBtn");
const micLabel = document.getElementById("micLabel");
const textForm = document.getElementById("textForm");
const textInput = document.getElementById("textInput");
const thinkingIndicator = document.getElementById("thinkingIndicator");

// Telemetry DOM
const valMotoBatt = document.getElementById("valMotoBatt");
const valMotoCharging = document.getElementById("valMotoCharging");

let ws = null;
let mediaRecorder = null;
let isRecording = false;
let sequenceCounter = 0;

// Switch Navigation Tabs
window.switchTab = function (tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"));
  document.querySelectorAll(".view-content").forEach((view) => view.classList.remove("active"));

  if (tabName === "chat") {
    document.querySelectorAll(".tab-btn")[0].classList.add("active");
    chatView.classList.add("active");
  } else {
    document.querySelectorAll(".tab-btn")[1].classList.add("active");
    dashView.classList.add("active");
    fetchTelemetry();
  }
};

// Connect WebSocket with Protocol v1
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host || "192.168.100.4:8765";
  const wsUrl = `${protocol}//${host}/ws?token=${SECRET_TOKEN}`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusDot.classList.remove("disconnected");
    statusText.textContent = "Moto g04 (REALTIME)";
    console.log("⚡ Protocol v1 Connected to Jarvis Server (Moto g04 Owner)");
    startBatteryTelemetry();
    startHeartbeat();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleProtoV1Message(msg);
    } catch (e) {
      console.log("Binary or raw data received:", event.data);
    }
  };

  ws.onclose = () => {
    statusDot.classList.add("disconnected");
    statusText.textContent = "Desconectado - Reintentando...";
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket Error:", err);
    ws.close();
  };
}

// Format Protocol v1 Message
function sendV1Message(msgType, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    alert("⚠️ Sin conexión con Jarvis. Reintentando...");
    return;
  }
  sequenceCounter++;
  const msg = {
    v: PROTOCOL_VERSION,
    type: msgType,
    id: `moto_${sequenceCounter}_${Date.now()}`,
    seq: sequenceCounter,
    ts: Date.now(),
    payload: payload,
  };
  ws.send(JSON.stringify(msg));
}

let thinkingTimeout = null;

// Handle Protocol v1 Server Messages
function handleProtoV1Message(msg) {
  const msgType = msg.type;
  const payload = msg.payload || {};

  if (msgType === "ai_response") {
    if (thinkingTimeout) clearTimeout(thinkingTimeout);
    if (thinkingIndicator) thinkingIndicator.style.display = "none";

    if (payload.request_text && payload.request_text.startsWith("🎙️")) {
      appendMessage("user", payload.request_text);
    }

    appendMessage("jarvis", payload.response_text || "Procesado.");

    // Play high quality Neural Audio (Tomas / Jarvis) if sent from server
    if (payload.audio_b64) {
      try {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        const audio = new Audio(payload.audio_b64);
        audio.play().catch(() => speakResponse(payload.response_text || ""));
      } catch (e) {
        speakResponse(payload.response_text || "");
      }
    } else {
      speakResponse(payload.response_text || "");
    }
  } else if (msgType === "welcome") {
    console.log("Server Welcome Payload:", payload);
  } else if (msgType === "heartbeat_ack") {
    console.debug("Heartbeat ACK received");
  }
}

// Append Chat Message
function appendMessage(sender, text) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${sender}`;

  const senderDiv = document.createElement("div");
  senderDiv.className = "message-sender";
  senderDiv.textContent = sender === "user" ? "Rodrigo (Moto g04)" : "Jarvis";

  const bodyDiv = document.createElement("div");
  bodyDiv.innerHTML = text.replace(/\n/g, "<br>");

  msgDiv.appendChild(senderDiv);
  msgDiv.appendChild(bodyDiv);

  // Insert before thinking indicator
  if (thinkingIndicator && thinkingIndicator.parentNode === chatView) {
    chatView.insertBefore(msgDiv, thinkingIndicator);
  } else {
    chatView.appendChild(msgDiv);
  }

  chatView.scrollTop = chatView.scrollHeight;
}

// Text Form Submission
textForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = textInput.value.trim();
  if (!text) return;

  appendMessage("user", text);
  if (thinkingIndicator) thinkingIndicator.style.display = "flex";

  if (thinkingTimeout) clearTimeout(thinkingTimeout);
  thinkingTimeout = setTimeout(() => {
    if (thinkingIndicator && thinkingIndicator.style.display === "flex") {
      thinkingIndicator.style.display = "none";
      appendMessage("jarvis", "⚠️ Tiempo de espera agotado. Reintentando...");
    }
  }, 25000);

  sendV1Message("chat", { text: text });
  textInput.value = "";
  textInput.blur(); // Dismiss Android soft keyboard
});

// Mic Push-to-Talk (Opus Streaming)
micBtn.addEventListener("click", async () => {
  if (!isRecording) {
    startRecording();
  } else {
    stopRecording();
  }
});

let audioChunks = [];

async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert(
      "⚠️ Para usar el micrófono en Android Chrome sobre IP local (http://192.168.100.4:8765):\n\n" +
      "1. Abrí una pestaña en Chrome y entrá a:\n   chrome://flags/#unsafely-treat-insecure-origin-as-secure\n\n" +
      "2. Habilitá la opción (Enabled) y agregá esta dirección:\n   http://192.168.100.4:8765\n\n" +
      "3. Tocá 'Relaunch' abajo en Chrome.\n\n" +
      "¡Y listo! El micrófono quedará habilitado."
    );
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];

    // Let browser select native supported audio format
    let options = {};
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      options = { mimeType: "audio/webm;codecs=opus" };
    } else if (MediaRecorder.isTypeSupported("audio/webm")) {
      options = { mimeType: "audio/webm" };
    } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
      options = { mimeType: "audio/mp4" };
    }

    mediaRecorder = new MediaRecorder(stream, options);
    isRecording = true;
    micBtn.classList.add("recording");
    micLabel.textContent = "🔴 Grabando... Volvé a tocar para enviar";

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };

    mediaRecorder.start(100);
  } catch (err) {
    alert("⚠️ Error accediendo al micrófono del Moto g04: " + err.message);
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    isRecording = false;
    micBtn.classList.remove("recording");
    micLabel.textContent = "⚙️ Procesando audio...";

    mediaRecorder.onstop = async () => {
      micLabel.textContent = "Presioná para hablar";
      if (!audioChunks || audioChunks.length === 0) {
        alert("⚠️ No se registraron datos de audio. Por favor intentá hablar de nuevo.");
        return;
      }

      const mimeType = mediaRecorder.mimeType || "audio/webm";
      const audioBlob = new Blob(audioChunks, { type: mimeType });
      audioChunks = [];

      console.log(`🎙️ Recording finished: ${audioBlob.size} bytes (${mimeType})`);

      if (ws && ws.readyState === WebSocket.OPEN) {
        if (thinkingIndicator) thinkingIndicator.style.display = "flex";
        if (thinkingTimeout) clearTimeout(thinkingTimeout);
        thinkingTimeout = setTimeout(() => {
          if (thinkingIndicator && thinkingIndicator.style.display === "flex") {
            thinkingIndicator.style.display = "none";
            appendMessage("jarvis", "⚠️ Tiempo de espera de audio agotado.");
          }
        }, 25000);

        // Convert blob to Base64 for 100% reliable Protocol v1 JSON transmission
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Data = reader.result;
          sendV1Message("voice_audio", {
            audio_b64: base64Data,
            mime_type: mimeType
          });
        };
        reader.readAsDataURL(audioBlob);
      } else {
        alert("⚠️ Conexión WebSocket cerrada.");
      }
    };

    try {
      if (mediaRecorder.state === "recording") {
        mediaRecorder.requestData(); // Flush all pending audio frames
      }
    } catch (e) {
      console.warn("requestData error:", e);
    }

    mediaRecorder.stop();
    if (mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    }
  }
}

// HTML5 Battery API Sensor Telemetry
async function startBatteryTelemetry() {
  if ("getBattery" in navigator) {
    try {
      const battery = await navigator.getBattery();
      const sendBatteryStatus = () => {
        const battPct = Math.round(battery.level * 100);
        const charging = battery.charging;

        if (valMotoBatt) valMotoBatt.textContent = `${battPct}%`;
        if (valMotoCharging) valMotoCharging.textContent = charging ? "⚡ Cargando" : "🔋 En Batería";

        sendV1Message("device_telemetry", {
          device: "Moto g04 de Rodrigo",
          battery_level: battPct,
          charging: charging,
          network_type: "wifi",
        });
      };

      sendBatteryStatus();
      battery.addEventListener("levelchange", sendBatteryStatus);
      battery.addEventListener("chargingchange", sendBatteryStatus);
    } catch (e) {
      console.warn("Battery API unavailable:", e);
    }
  }
}

// Heartbeat Loop
function startHeartbeat() {
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendV1Message("heartbeat", {});
    }
  }, 25000);
}

// Fetch Telemetry for Dashboard View
async function fetchTelemetry() {
  try {
    const res = await fetch("/api/telemetry");
    if (res.ok) {
      const data = await res.json();
      console.log("Live Telemetry Data:", data);
    }
  } catch (e) {
    console.warn("Telemetry fetch error:", e);
  }
}

// TTS Speech Synthesis Fallback (Male voice selection)
function speakResponse(text) {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-AR";
    utterance.rate = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const maleVoice = voices.find(
      (v) =>
        v.lang.startsWith("es") &&
        (v.name.includes("Male") ||
          v.name.includes("Masculino") ||
          v.name.includes("Jorge") ||
          v.name.includes("Tomas") ||
          v.name.includes("Alvaro") ||
          v.name.includes("Pablo") ||
          v.name.includes("Carlos") ||
          v.name.includes("Diego"))
    ) || voices.find((v) => v.lang.startsWith("es"));

    if (maleVoice) utterance.voice = maleVoice;
    window.speechSynthesis.speak(utterance);
  }
}

// Connect on load
connectWebSocket();
