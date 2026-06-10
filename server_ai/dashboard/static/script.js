/**
 * Monitor tab — SSE state updates, AC/lamp controls, log rendering.
 */

// ── Element refs ──────────────────────────────────────────────────────────────
const fpsLabel       = document.getElementById("fps-label");
const pillCamera     = document.getElementById("pill-camera");
const pillActuator   = document.getElementById("pill-actuator");

const totalEl        = document.getElementById("total-persons");
const frontEl        = document.getElementById("zone-front");
const backEl         = document.getElementById("zone-back");

const acStateEl      = document.getElementById("ac-state");
const roomTempEl     = document.getElementById("room-temp");
const roomHumEl      = document.getElementById("room-humidity");
const sensorOfflineMsg = document.getElementById("sensor-offline-msg");

const lampDot        = document.getElementById("lamp-dot");
const lampStateEl    = document.getElementById("lamp-state");

const logBody        = document.getElementById("log-body");
const logCount       = document.getElementById("log-count");

const videoFeed      = document.getElementById("video-feed");
const videoOverlay   = document.getElementById("video-overlay");

const thrAcDisplay   = document.getElementById("threshold-ac-display");
const thrLampDisplay = document.getElementById("threshold-lamp-display");

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("tab-btn--active"));
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("tab-content--active"));
    btn.classList.add("tab-btn--active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("tab-content--active");

    // Load kalibrasi saat tab kalibrasi dibuka
    if (btn.dataset.tab === "calibrate") loadCalibration();
    if (btn.dataset.tab === "settings")  loadSettings();
  });
});

// ── SSE ───────────────────────────────────────────────────────────────────────
function connectSSE() {
  const evtSource = new EventSource("/events");
  evtSource.onmessage = (e) => {
    try { applyState(JSON.parse(e.data)); }
    catch (err) { console.warn("SSE parse error:", err); }
  };
  evtSource.onerror = () => {
    console.warn("SSE disconnected. Retrying in 3s...");
    evtSource.close();
    setTimeout(connectSSE, 3000);
  };
}

// ── Apply state ───────────────────────────────────────────────────────────────
function applyState(state) {
  // FPS
  if (state.fps !== undefined) {
    fpsLabel.textContent = state.fps.toFixed(1) + " FPS";
  }

  // Online pills
  if (state.camera_online !== undefined)   setPill(pillCamera,   state.camera_online);
  if (state.actuator_online !== undefined) setPill(pillActuator, state.actuator_online);

  // Detection counts
  setCount(totalEl, state.total_persons);
  setCount(frontEl, state.zone_front);
  setCount(backEl,  state.zone_back);

  // AC
  if (state.ac_desired !== undefined) setACState(state.ac_desired);

  // Sensor
  if (state.temp !== undefined && state.humidity !== undefined) {
    const ok = state.sensor_ok !== false;
    if (ok && state.temp > 0) {
      roomTempEl.textContent = state.temp.toFixed(1);
      roomHumEl.textContent  = state.humidity.toFixed(1);
      sensorOfflineMsg.style.display = "none";
    } else if (!ok) {
      roomTempEl.textContent = "--";
      roomHumEl.textContent  = "--";
      sensorOfflineMsg.style.display = "block";
    }
  }

  // Lamp
  if (state.lamp_on !== undefined) setLampState(state.lamp_on);
}

function setPill(el, online) {
  el.className = "pill " + (online ? "pill--online" : "pill--offline");
}

function setCount(el, value) {
  if (!el || value === undefined) return;
  const num = parseInt(value) || 0;
  if (el.textContent !== String(num)) {
    el.textContent = num;
    el.classList.add("pulse");
    setTimeout(() => el.classList.remove("pulse"), 300);
  }
}

function setACState(on) {
  acStateEl.textContent = on ? "ON" : "OFF";
  acStateEl.className   = "ac-state-value" + (on ? " on" : "");
}

function setLampState(on) {
  lampStateEl.textContent = on ? "ON" : "OFF";
  lampStateEl.className   = "lamp-state" + (on ? " on" : "");
  lampDot.className       = "lamp-dot" + (on ? " on" : "");
}

// ── Log ───────────────────────────────────────────────────────────────────────
async function refreshLog() {
  try {
    const logs = await (await fetch("/api/logs")).json();
    renderLog(logs);
  } catch (_) {}
}

function renderLog(logs) {
  if (!logs || logs.length === 0) {
    logBody.innerHTML = '<tr><td colspan="4" class="log-empty">Belum ada aksi.</td></tr>';
    logCount.textContent = "(0)";
    return;
  }
  logCount.textContent = `(${logs.length})`;
  const recent = [...logs].reverse().slice(0, 15);
  logBody.innerHTML = recent.map(e => {
    const isOn = e.action === "ON" || e.action === "KLIK" || e.action === "KLIK (test)";
    return `<tr>
      <td>${e.timestamp || "-"}</td>
      <td>${e.actuator || "-"}</td>
      <td class="${isOn ? "log-on-text" : "log-off-text"}">${e.action || "-"}</td>
      <td style="color:var(--text-muted)">${e.reason || "-"}</td>
    </tr>`;
  }).join("");
}

// ── Video feed ────────────────────────────────────────────────────────────────
videoFeed.addEventListener("load",  () => { videoOverlay.style.display = "none"; });
videoFeed.addEventListener("error", () => { videoOverlay.style.display = "flex"; });

// ── AC Buttons ────────────────────────────────────────────────────────────────
async function postApi(url, body = null) {
  const opts = { method: "POST" };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body    = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  return r.json();
}

document.getElementById("btn-ac-power").addEventListener("click", async () => {
  const r = await postApi("/api/ac/power");
  if (r.ok) setACState(r.ac_desired);
  else alert("Gagal klik power AC: " + (r.error || ""));
});

document.getElementById("btn-temp-up").addEventListener("click", async () => {
  const r = await postApi("/api/ac/temp_up");
  if (!r.ok) alert("Gagal klik Temp+: " + (r.error || ""));
});

document.getElementById("btn-temp-down").addEventListener("click", async () => {
  const r = await postApi("/api/ac/temp_down");
  if (!r.ok) alert("Gagal klik Temp−: " + (r.error || ""));
});

// ── Lamp Buttons ──────────────────────────────────────────────────────────────
document.getElementById("btn-lamp-on").addEventListener("click", async () => {
  const r = await postApi("/api/lamp", { state: "ON" });
  if (r.ok) setLampState(true);
  else alert("Gagal nyalakan lampu: " + (r.error || ""));
});

document.getElementById("btn-lamp-off").addEventListener("click", async () => {
  const r = await postApi("/api/lamp", { state: "OFF" });
  if (r.ok) setLampState(false);
  else alert("Gagal matikan lampu: " + (r.error || ""));
});

// ── Settings (load thresholds untuk tampilan) ─────────────────────────────────
async function loadSettingsForDisplay() {
  try {
    const s = await (await fetch("/api/settings")).json();
    if (thrAcDisplay && s.person_threshold_ac !== undefined)
      thrAcDisplay.textContent = s.person_threshold_ac;
    if (thrLampDisplay && s.person_threshold_lamp !== undefined)
      thrLampDisplay.textContent = s.person_threshold_lamp;
  } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
connectSSE();
setInterval(refreshLog, 2000);
refreshLog();
loadSettingsForDisplay();
