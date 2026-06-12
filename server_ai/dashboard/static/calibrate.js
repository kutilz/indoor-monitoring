/**
 * Kalibrasi Servo — logika tab "Kalibrasi Servo".
 *
 * Servo MG996R 360° (continuous rotation): TIDAK punya posisi sudut.
 * Tombol jog (CW/CCW) memutar servo SELAMA DITAHAN (heartbeat ~150ms ke
 * /api/servo/<id>/jog), dan berhenti saat dilepas (/api/servo/<id>/stop).
 * Node aktuator punya watchdog: jika heartbeat berhenti masuk (mis. koneksi
 * putus), servo otomatis berhenti sendiri.
 *
 * State kalibrasi per servo disimpan di objek `calState`:
 *   calState[id] = { dir: "CW"|"CCW", speed: 0-100, clickMs, returnMs, trim }
 *
 * Semua operasi (jog, stop, click, save) lewat proxy endpoint di Flask,
 * yang diteruskan ke node aktuator (D1 Mini / ESP32).
 */

const calState = {
  0: { dir: "CW", speed: 30, clickMs: 300, returnMs: 300, trim: 0 },
  1: { dir: "CW", speed: 30, clickMs: 300, returnMs: 300, trim: 0 },
  2: { dir: "CW", speed: 30, clickMs: 300, returnMs: 300, trim: 0 },
};

// Interval heartbeat jog yang sedang aktif, per servo (null = tidak jog)
const jogIntervals = { 0: null, 1: null, 2: null };

// ── Helpers ────────────────────────────────────────────────────────────────────
function setServoMsg(id, text, type = "ok") {
  const el = document.getElementById(`s${id}-msg`);
  if (!el) return;
  el.textContent = text;
  el.className   = `servo-msg ${type}`;
  // Fade out setelah 3 detik
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.textContent = ""; el.className = "servo-msg"; }, 3000);
}

function setEmergencyMsg(text, type = "ok") {
  const el = document.getElementById("emergency-msg");
  if (!el) return;
  el.textContent = text;
  el.className   = `servo-msg ${type}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.textContent = ""; el.className = "servo-msg"; }, 3000);
}

// ── Jog (tahan untuk putar, lepas untuk berhenti) ──────────────────────────────

async function sendJog(id, dir, speed) {
  try {
    await fetch(`/api/servo/${id}/jog`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ dir, speed })
    });
  } catch (e) {
    // Koneksi gagal — hentikan heartbeat lokal. Node akan auto-stop via watchdog.
    if (jogIntervals[id]) {
      clearInterval(jogIntervals[id]);
      jogIntervals[id] = null;
    }
    setServoMsg(id, "Koneksi terputus — servo berhenti otomatis (watchdog)", "err");
  }
}

async function sendStop(id) {
  try {
    await fetch(`/api/servo/${id}/stop`, { method: "POST" });
  } catch (_) {
    // Tidak masalah — node akan auto-stop via watchdog jika koneksi putus.
  }
}

function startJog(id, dir) {
  if (jogIntervals[id]) return; // sudah jog, jangan dobel
  const speed = calState[id].speed;
  sendJog(id, dir, speed);
  jogIntervals[id] = setInterval(() => sendJog(id, dir, speed), 150);
}

function stopJog(id) {
  if (jogIntervals[id]) {
    clearInterval(jogIntervals[id]);
    jogIntervals[id] = null;
  }
  sendStop(id);
}

function setupJogButtons() {
  document.querySelectorAll(".jog-btn").forEach(btn => {
    const id  = parseInt(btn.dataset.servo, 10);
    const dir = btn.dataset.dir;

    const start = (e) => { e.preventDefault(); startJog(id, dir); };
    const stop  = (e) => { e.preventDefault(); stopJog(id); };

    btn.addEventListener("pointerdown",  start);
    btn.addEventListener("pointerup",    stop);
    btn.addEventListener("pointerleave", stop);
    btn.addEventListener("pointercancel", stop);
  });
}
setupJogButtons();

// ── Emergency stop ─────────────────────────────────────────────────────────────

async function stopAllServos() {
  // Hentikan semua heartbeat lokal segera
  for (const id of Object.keys(jogIntervals)) {
    if (jogIntervals[id]) {
      clearInterval(jogIntervals[id]);
      jogIntervals[id] = null;
    }
  }
  try {
    const r = await fetch("/api/servo/stop_all", { method: "POST", keepalive: true });
    const data = await r.json();
    if (data.ok) {
      setEmergencyMsg("Semua servo dihentikan.");
    } else {
      setEmergencyMsg(data.error || "Gagal menghentikan servo", "err");
    }
  } catch (e) {
    setEmergencyMsg("Koneksi error: " + e.message, "err");
  }
}

// Bersihkan: hentikan heartbeat + kirim stop saat pindah tab / tutup halaman,
// agar servo tidak terus berputar jika tombol jog kebetulan masih "ditekan"
// secara logis (mis. event pointerup tidak sempat terkirim).
function cleanupOnExit() {
  for (const id of Object.keys(jogIntervals)) {
    if (jogIntervals[id]) {
      clearInterval(jogIntervals[id]);
      jogIntervals[id] = null;
      fetch(`/api/servo/${id}/stop`, { method: "POST", keepalive: true }).catch(() => {});
    }
  }
}

window.addEventListener("beforeunload", cleanupOnExit);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") cleanupOnExit();
});

// ── Input handlers ────────────────────────────────────────────────────────────

function onSpeedInput(id, val) {
  calState[id].speed = parseInt(val, 10);
  const el = document.getElementById(`s${id}-speed-val`);
  if (el) el.textContent = val + "%";
}

function onDurationInput(id, field, val) {
  calState[id][field] = parseInt(val, 10);
  const suffix = field === "clickMs" ? "click-ms" : "return-ms";
  const el = document.getElementById(`s${id}-${suffix}-val`);
  if (el) el.textContent = val + "ms";
}

function onTrimInput(id, val) {
  const v = parseInt(val, 10);
  calState[id].trim = v;
  const el = document.getElementById(`s${id}-trim-val`);
  if (el) el.textContent = (v > 0 ? "+" : "") + v + "us";
}

function setClickDir(id, dir) {
  calState[id].dir = dir;
  updateDirToggleUI(id);
}

function updateDirToggleUI(id) {
  const cwBtn  = document.getElementById(`s${id}-dir-cw`);
  const ccwBtn = document.getElementById(`s${id}-dir-ccw`);
  if (cwBtn)  cwBtn.classList.toggle("dir-toggle--active",  calState[id].dir === "CW");
  if (ccwBtn) ccwBtn.classList.toggle("dir-toggle--active", calState[id].dir === "CCW");
}

// ── Test klik (jog ke arah klik, lalu jog balik) ───────────────────────────────
async function testClick(id) {
  // Simpan dulu ke node supaya node pakai nilai calState saat ini
  const saveFirst = await saveCalibration(id, false);
  if (!saveFirst) {
    setServoMsg(id, "Gagal simpan kalibrasi ke node sebelum test klik", "err");
    return;
  }

  setServoMsg(id, "Menjalankan klik...");
  try {
    const r = await fetch(`/api/servo/${id}/click`, { method: "POST" });
    const data = await r.json();
    if (data.ok) {
      setServoMsg(id, `Klik berhasil (servo ${id})`);
    } else {
      setServoMsg(id, data.error || "Klik gagal", "err");
    }
  } catch (e) {
    setServoMsg(id, "Koneksi error: " + e.message, "err");
  }
}

// ── Simpan kalibrasi ke node (LittleFS) ───────────────────────────────────────
async function saveCalibration(id, showMsg = true) {
  const s = calState[id];
  try {
    const r = await fetch(`/api/servo/${id}/calibrate`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        dir:       s.dir,
        speed:     s.speed,
        click_ms:  s.clickMs,
        return_ms: s.returnMs,
        trim:      s.trim,
      })
    });
    const data = await r.json();
    if (data.ok) {
      if (showMsg) {
        setServoMsg(id, `Kalibrasi disimpan: ${s.dir}, speed=${s.speed}%, ` +
                        `klik=${s.clickMs}ms, kembali=${s.returnMs}ms, trim=${s.trim}us`);
      }
      return true;
    } else {
      if (showMsg) setServoMsg(id, data.error || "Gagal simpan", "err");
      return false;
    }
  } catch (e) {
    if (showMsg) setServoMsg(id, "Koneksi error: " + e.message, "err");
    return false;
  }
}

// ── Load kalibrasi dari node ──────────────────────────────────────────────────
async function loadCalibration() {
  const warnEl = document.getElementById("calib-actuator-warn");
  try {
    const r    = await fetch("/api/servo/config");
    const data = await r.json();

    if (data.error) {
      if (warnEl) warnEl.style.display = "block";
      return;
    }
    if (warnEl) warnEl.style.display = "none";

    for (let id = 0; id < 3; id++) {
      const key = `servo${id}`;
      if (!data[key]) continue;
      const cfg = data[key];

      calState[id].dir      = cfg.click_dir   ?? "CW";
      calState[id].speed    = cfg.click_speed ?? 30;
      calState[id].clickMs  = cfg.click_ms    ?? 300;
      calState[id].returnMs = cfg.return_ms   ?? 300;
      calState[id].trim     = cfg.trim        ?? 0;

      const speedSlider = document.getElementById(`s${id}-speed-slider`);
      if (speedSlider) {
        speedSlider.value = calState[id].speed;
        onSpeedInput(id, calState[id].speed);
      }

      const clickSlider = document.getElementById(`s${id}-click-ms-slider`);
      if (clickSlider) {
        clickSlider.value = calState[id].clickMs;
        onDurationInput(id, "clickMs", calState[id].clickMs);
      }

      const returnSlider = document.getElementById(`s${id}-return-ms-slider`);
      if (returnSlider) {
        returnSlider.value = calState[id].returnMs;
        onDurationInput(id, "returnMs", calState[id].returnMs);
      }

      const trimSlider = document.getElementById(`s${id}-trim-slider`);
      if (trimSlider) {
        trimSlider.value = calState[id].trim;
        onTrimInput(id, calState[id].trim);
      }

      updateDirToggleUI(id);
    }
  } catch (_) {
    if (warnEl) warnEl.style.display = "block";
  }
}

// ── Settings tab ──────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const s = await (await fetch("/api/settings")).json();

    const fields = {
      "s-yolo-conf":   { key: "yolo_confidence",    valId: "s-yolo-conf-val",   fmt: v => parseFloat(v).toFixed(2) },
      "s-thr-ac":      { key: "person_threshold_ac",  valId: null },
      "s-thr-lamp":    { key: "person_threshold_lamp", valId: null },
      "s-zone-split":  { key: "zone_split_ratio",    valId: "s-zone-split-val",  fmt: v => parseFloat(v).toFixed(2) },
      "s-dht-interval":{ key: "dht22_poll_interval", valId: null },
    };

    for (const [elemId, cfg] of Object.entries(fields)) {
      const el  = document.getElementById(elemId);
      const val = s[cfg.key];
      if (!el || val === undefined) continue;
      el.value = val;
      if (cfg.valId) {
        const valEl = document.getElementById(cfg.valId);
        if (valEl) valEl.textContent = cfg.fmt ? cfg.fmt(val) : val;
      }
    }
  } catch (_) {}
}

async function saveSettings() {
  const msgEl = document.getElementById("settings-msg");
  const fields = {
    "s-yolo-conf":   "yolo_confidence",
    "s-thr-ac":      "person_threshold_ac",
    "s-thr-lamp":    "person_threshold_lamp",
    "s-zone-split":  "zone_split_ratio",
    "s-dht-interval":"dht22_poll_interval",
  };

  const body = {};
  for (const [elemId, key] of Object.entries(fields)) {
    const el = document.getElementById(elemId);
    if (el) body[key] = parseFloat(el.value);
  }

  try {
    const r    = await fetch("/api/settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body)
    });
    const data = await r.json();
    if (data.ok) {
      msgEl.textContent = "Settings berhasil disimpan dan diterapkan.";
      msgEl.className   = "settings-msg ok";
    } else {
      msgEl.textContent = "Gagal: " + (data.error || "Unknown error");
      msgEl.className   = "settings-msg err";
    }
  } catch (e) {
    msgEl.textContent = "Koneksi error: " + e.message;
    msgEl.className   = "settings-msg err";
  }

  clearTimeout(msgEl._t);
  msgEl._t = setTimeout(() => { msgEl.textContent = ""; msgEl.className = "settings-msg"; }, 4000);

  // Update display thresholds di monitor tab
  if (typeof loadSettingsForDisplay === "function") loadSettingsForDisplay();
}
