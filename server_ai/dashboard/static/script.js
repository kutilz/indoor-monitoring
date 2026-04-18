/**
 * Dashboard client-side logic.
 * Berlangganan ke SSE /events untuk menerima state update real-time,
 * lalu memperbarui semua elemen UI.
 */

// ── Element references ────────────────────────────────────────────────────────
const modeBadge      = document.getElementById("mode-badge");
const fpsLabel       = document.getElementById("fps-label");
const totalEl        = document.getElementById("total-persons");
const frontEl        = document.getElementById("zone-front");
const backEl         = document.getElementById("zone-back");
const logBody        = document.getElementById("log-body");
const logCount       = document.getElementById("log-count");

const relayAcItem    = document.getElementById("relay-ac");
const relayFrontItem = document.getElementById("relay-light-front");
const relayBackItem  = document.getElementById("relay-light-back");

const relayAcState   = document.getElementById("relay-ac-state");
const relayFrontState= document.getElementById("relay-front-state");
const relayBackState = document.getElementById("relay-back-state");

const relayAcDot     = document.getElementById("relay-ac-dot");
const relayFrontDot  = document.getElementById("relay-front-dot");
const relayBackDot   = document.getElementById("relay-back-dot");

const videoFeed      = document.getElementById("video-feed");
const videoOverlay   = document.getElementById("video-overlay");

// ── State ─────────────────────────────────────────────────────────────────────
let lastState = {};
let commandLogs = [];

// ── SSE Connection ────────────────────────────────────────────────────────────
function connectSSE() {
  const evtSource = new EventSource("/events");

  evtSource.onmessage = (e) => {
    try {
      const state = JSON.parse(e.data);
      applyState(state);
    } catch (err) {
      console.warn("SSE parse error:", err);
    }
  };

  evtSource.onerror = () => {
    console.warn("SSE disconnected. Retrying in 3s...");
    evtSource.close();
    setTimeout(connectSSE, 3000);
  };
}

// ── Apply state to UI ─────────────────────────────────────────────────────────
function applyState(state) {
  lastState = state;

  // Mode badge
  if (state.mode) {
    const isReal = state.mode === "real";
    modeBadge.textContent = state.mode.toUpperCase();
    modeBadge.className = "badge " + (isReal ? "badge--real" : "badge--akuisisi");
  }

  // FPS
  if (state.fps !== undefined) {
    fpsLabel.textContent = state.fps.toFixed(1) + " FPS";
  }

  // Person counts (animate number change)
  setCount(totalEl, state.total_persons);
  setCount(frontEl, state.zone_front);
  setCount(backEl,  state.zone_back);

  // Relay states
  setRelay(relayAcItem,    relayAcState,    relayAcDot,    state.ac_on);
  setRelay(relayFrontItem, relayFrontState, relayFrontDot, state.light_front_on);
  setRelay(relayBackItem,  relayBackState,  relayBackDot,  state.light_back_on);
}

function setCount(el, value) {
  if (el && value !== undefined) {
    const num = parseInt(value) || 0;
    if (el.textContent !== String(num)) {
      el.textContent = num;
      el.classList.add("pulse");
      setTimeout(() => el.classList.remove("pulse"), 300);
    }
  }
}

function setRelay(item, stateEl, dot, isOn) {
  if (!item) return;
  if (isOn) {
    item.classList.add("relay-item--on");
    stateEl.textContent = "ON";
    stateEl.className = "relay-state relay-on";
    dot.className = "relay-indicator relay-indicator--on";
  } else {
    item.classList.remove("relay-item--on");
    stateEl.textContent = "OFF";
    stateEl.className = "relay-state relay-off";
    dot.className = "relay-indicator relay-indicator--off";
  }
}

// ── Fetch & render command log ─────────────────────────────────────────────────
async function refreshLog() {
  try {
    const res  = await fetch("/api/logs");
    const logs = await res.json();
    commandLogs = logs;
    renderLog(logs);
  } catch (_) {}
}

function renderLog(logs) {
  if (!logs || logs.length === 0) {
    logBody.innerHTML = '<tr><td colspan="3" class="log-empty">Belum ada perintah.</td></tr>';
    logCount.textContent = "(0)";
    return;
  }

  logCount.textContent = `(${logs.length})`;

  // Tampilkan 10 terbaru, terbaru di atas
  const recent = [...logs].reverse().slice(0, 10);
  logBody.innerHTML = recent.map(cmd => {
    const isOn = cmd.state === "ON";
    return `<tr>
      <td>${cmd.timestamp || "-"}</td>
      <td>${cmd.name || `Relay ${cmd.relay}`}</td>
      <td class="${isOn ? "log-on" : "log-off"}">${cmd.state}</td>
    </tr>`;
  }).join("");
}

// ── Video feed status ─────────────────────────────────────────────────────────
videoFeed.addEventListener("load", () => {
  videoOverlay.style.display = "none";
});

videoFeed.addEventListener("error", () => {
  videoOverlay.style.display = "flex";
});

// ── Init ──────────────────────────────────────────────────────────────────────
connectSSE();
setInterval(refreshLog, 2000);  // Refresh log setiap 2 detik
refreshLog();                   // Langsung fetch saat halaman dibuka
