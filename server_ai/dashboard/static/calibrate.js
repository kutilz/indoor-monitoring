/**
 * Kalibrasi Servo — logika tab "Kalibrasi Servo".
 *
 * State kalibrasi per servo disimpan di objek `calState`:
 *   calState[id] = { stay: int, click: int }
 *
 * Semua operasi (move, click, save) lewat proxy endpoint di Flask,
 * yang diteruskan ke node aktuator (D1 Mini / ESP32).
 */

const calState = { 0: { stay: 90, click: 90 }, 1: { stay: 90, click: 90 }, 2: { stay: 90, click: 90 } };

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

function updateServoUI(id) {
  const s = calState[id];
  const stayEl   = document.getElementById(`s${id}-stay-val`);
  const clickEl  = document.getElementById(`s${id}-click-val`);
  const travelEl = document.getElementById(`s${id}-travel-val`);
  if (stayEl)   stayEl.textContent   = s.stay + "°";
  if (clickEl)  clickEl.textContent  = s.click + "°";
  if (travelEl) {
    const travel = Math.abs(s.click - s.stay);
    travelEl.textContent = travel + "°";
    travelEl.style.color = travel > 110 ? "var(--red)" : "var(--orange)";
  }
}

function getSliderAngle(id) {
  const slider = document.getElementById(`s${id}-slider`);
  return slider ? parseInt(slider.value) : 90;
}

// ── Slider input live update ───────────────────────────────────────────────────
function onSliderInput(id, val) {
  const curEl = document.getElementById(`s${id}-slider-cur`);
  if (curEl) curEl.textContent = val + "°";
}

// ── Move servo ke sudut slider saat ini ───────────────────────────────────────
async function moveServo(id) {
  const angle = getSliderAngle(id);
  try {
    const r = await fetch(`/api/servo/${id}/move`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ angle })
    });
    const data = await r.json();
    if (data.ok) {
      setServoMsg(id, `Servo bergerak ke ${angle}°`);
    } else {
      setServoMsg(id, data.error || "Gagal gerak servo", "err");
    }
  } catch (e) {
    setServoMsg(id, "Koneksi error: " + e.message, "err");
  }
}

// ── Set stay angle = slider saat ini ──────────────────────────────────────────
function setStay(id) {
  const angle = getSliderAngle(id);
  calState[id].stay = angle;
  updateServoUI(id);
  setServoMsg(id, `Stay diset ke ${angle}° (belum disimpan — tekan Test Klik lalu Simpan)`);
}

// ── Set click angle = slider saat ini ────────────────────────────────────────
function setClick(id) {
  const angle  = getSliderAngle(id);
  const travel = Math.abs(angle - calState[id].stay);
  if (travel > 120) {
    setServoMsg(id, `Perjalanan ${travel}° melebihi batas 120°! Sesuaikan stay atau click.`, "err");
    return;
  }
  calState[id].click = angle;
  updateServoUI(id);
  setServoMsg(id, `Click diset ke ${angle}° (perjalanan: ${travel}°)`);
}

// ── Test klik penuh (easing) ──────────────────────────────────────────────────
async function testClick(id) {
  // Dulu kita harus simpan dulu ke node supaya node pakai nilai calState
  const saveFirst = await saveCalibration(id, false);   // silent save
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
      body:    JSON.stringify({ stay: s.stay, click: s.click })
    });
    const data = await r.json();
    if (data.ok) {
      if (showMsg) setServoMsg(id, `Kalibrasi disimpan: stay=${s.stay}°, click=${s.click}°`);
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
      calState[id].stay  = data[key].stay  ?? 90;
      calState[id].click = data[key].click ?? 90;

      // Update slider ke nilai stay (titik diam)
      const slider = document.getElementById(`s${id}-slider`);
      if (slider) {
        slider.value = calState[id].stay;
        onSliderInput(id, calState[id].stay);
      }
      updateServoUI(id);
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
