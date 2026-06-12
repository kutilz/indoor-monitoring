"""
Flask dashboard — monitoring + kontrol + kalibrasi real-time.

Endpoint:
    GET  /               → Dashboard HTML
    GET  /video_feed     → MJPEG stream frame dengan anotasi YOLO
    GET  /events         → Server-Sent Events (SSE) state real-time
    GET  /api/state      → Snapshot state terkini (JSON)
    GET  /api/logs       → 50 log aksi terakhir (JSON)

    # Kalibrasi servo (continuous-rotation / jog)
    GET  /api/servo/config                     → kalibrasi tersimpan semua servo
    POST /api/servo/<id>/jog                   → jog servo (body: {dir, speed}) — heartbeat
    POST /api/servo/<id>/stop                  → hentikan satu servo segera
    POST /api/servo/stop_all                   → hentikan semua servo (emergency stop)
    POST /api/servo/<id>/click                 → test click urutan penuh
    POST /api/servo/<id>/calibrate             → simpan kalibrasi (body: {dir, speed, click_ms, return_ms, trim})

    # Kontrol manual AC
    POST /api/ac/power                         → klik tombol power AC
    POST /api/ac/temp_up                       → klik tombol naik suhu
    POST /api/ac/temp_down                     → klik tombol turun suhu

    # Kontrol manual lampu
    POST /api/lamp                             → kontrol relay (body: {state: "ON"|"OFF"})

    # Settings runtime
    GET  /api/settings                         → baca settings saat ini
    POST /api/settings                         → update & simpan settings
"""

import json
import os
import queue
import threading
import time

from flask import Flask, Response, render_template, jsonify, request

app = Flask(__name__)
app.config["SECRET_KEY"] = "classroom-ai-dashboard"

# ── Referensi ke komponen utama (diset oleh main.py) ──────────────────────────
_actuator  = None   # ActuatorClient
_logic     = None   # ControlLogic
_detector  = None   # YoloDetector
_settings_file_path = None

def set_actuator_ref(actuator):
    global _actuator
    _actuator = actuator

def set_logic_ref(logic):
    global _logic
    _logic = logic

def set_detector_ref(detector):
    global _detector
    _detector = detector

def set_settings_file(path: str):
    global _settings_file_path
    _settings_file_path = path

# ── Shared state ───────────────────────────────────────────────────────────────
_state_lock = threading.Lock()
_current_state: dict = {
    "total_persons":   0,
    "zone_front":      0,
    "zone_back":       0,
    "ac_desired":      False,
    "lamp_on":         False,
    "temp":            0.0,
    "humidity":        0.0,
    "sensor_ok":       False,
    "camera_online":   False,
    "actuator_online": False,
    "fps":             0.0,
    "frame_width":     0,
    "frame_height":    0,
    "zone_split_y":    0,
}

# Queue frame JPEG untuk /video_feed
_frame_queue: queue.Queue = queue.Queue(maxsize=2)

# Queue event SSE untuk /events
_sse_queue: queue.Queue = queue.Queue(maxsize=50)

# Log aksi (max 100 entri)
_action_log: list = []
_log_lock = threading.Lock()


# ── Public API (dipanggil oleh main.py) ────────────────────────────────────────

def push_frame(jpeg_bytes: bytes):
    """Kirim frame JPEG yang sudah dianotasi ke video feed."""
    if not _frame_queue.full():
        _frame_queue.put(jpeg_bytes)


def push_state(state: dict):
    """Update state sistem dan broadcast ke semua SSE subscriber."""
    with _state_lock:
        _current_state.update(state)
    event_data = json.dumps(state)
    if not _sse_queue.full():
        _sse_queue.put(event_data)


def push_command(entry: dict):
    """Catat satu aksi ke log dashboard."""
    with _log_lock:
        _action_log.append({
            **entry,
            "timestamp": time.strftime("%H:%M:%S")
        })
        if len(_action_log) > 100:
            _action_log.pop(0)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(data: dict = None, **kwargs) -> Response:
    payload = {"ok": True}
    if data:
        payload.update(data)
    payload.update(kwargs)
    return jsonify(payload)


def _err(msg: str, code: int = 400) -> Response:
    return jsonify({"ok": False, "error": msg}), code


def _require_actuator():
    if _actuator is None:
        return _err("Actuator client belum diinisialisasi.", 503)
    if not _actuator.online:
        return _err("Node aktuator offline.", 503)
    return None


# ── Flask Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with _state_lock:
        state = dict(_current_state)
    return render_template("index.html", state=state)


@app.route("/video_feed")
def video_feed():
    """MJPEG stream dari frame yang sudah dianotasi."""
    def generate():
        while True:
            try:
                jpeg = _frame_queue.get(timeout=2.0)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg +
                    b"\r\n"
                )
            except queue.Empty:
                continue
    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/events")
def events():
    """Server-Sent Events — update state real-time tanpa polling."""
    def generate():
        with _state_lock:
            yield f"data: {json.dumps(_current_state)}\n\n"
        while True:
            try:
                data = _sse_queue.get(timeout=15.0)
                yield f"data: {data}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify(dict(_current_state))


@app.route("/api/logs")
def api_logs():
    with _log_lock:
        return jsonify(_action_log[-50:])


# ── Kalibrasi Servo ────────────────────────────────────────────────────────────

@app.route("/api/servo/config")
def api_servo_config():
    """Ambil kalibrasi tersimpan dari node aktuator."""
    err = _require_actuator()
    if err:
        return err
    data = _actuator.get_calibration()
    return jsonify(data)


@app.route("/api/servo/<int:servo_id>/jog", methods=["POST"])
def api_servo_jog(servo_id: int):
    """Jog servo continuous-rotation (kalibrasi manual). Dipanggil sbg heartbeat."""
    if servo_id < 0 or servo_id > 2:
        return _err("servo_id harus 0-2")

    err = _require_actuator()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    direction = body.get("dir")
    speed     = body.get("speed")
    if direction is None or speed is None:
        return _err("field 'dir' dan 'speed' diperlukan")
    if str(direction).upper() not in ("CW", "CCW"):
        return _err("field 'dir' harus 'CW' atau 'CCW'")

    ok = _actuator.jog_servo(servo_id, str(direction), int(speed))
    if ok:
        return _ok(servo_id=servo_id, dir=str(direction).upper(), speed=int(speed))
    return _err("Gagal jog servo.", 502)


@app.route("/api/servo/<int:servo_id>/stop", methods=["POST"])
def api_servo_stop(servo_id: int):
    """Hentikan satu servo segera."""
    if servo_id < 0 or servo_id > 2:
        return _err("servo_id harus 0-2")

    err = _require_actuator()
    if err:
        return err

    ok = _actuator.stop_servo(servo_id)
    if ok:
        return _ok(servo_id=servo_id)
    return _err("Gagal menghentikan servo.", 502)


@app.route("/api/servo/stop_all", methods=["POST"])
def api_servo_stop_all():
    """Hentikan semua servo segera (emergency stop)."""
    err = _require_actuator()
    if err:
        return err

    ok = _actuator.stop_all_servos()
    if ok:
        return _ok()
    return _err("Gagal menghentikan semua servo.", 502)


@app.route("/api/servo/<int:servo_id>/click", methods=["POST"])
def api_servo_click(servo_id: int):
    """Jalankan urutan klik servo (untuk test kalibrasi)."""
    if servo_id < 0 or servo_id > 2:
        return _err("servo_id harus 0-2")

    err = _require_actuator()
    if err:
        return err

    servo_names = ["Power AC", "Temp Up", "Temp Down"]
    ok = _actuator.click_servo(servo_id)
    if ok:
        push_command({
            "actuator": f"Servo {servo_names[servo_id]}",
            "action":   "KLIK (test)",
            "reason":   "manual dari dashboard",
        })
        return _ok(servo_id=servo_id)
    return _err("Gagal menjalankan klik servo.", 502)


@app.route("/api/servo/<int:servo_id>/calibrate", methods=["POST"])
def api_servo_calibrate(servo_id: int):
    """Simpan nilai kalibrasi servo ke node aktuator (LittleFS)."""
    if servo_id < 0 or servo_id > 2:
        return _err("servo_id harus 0-2")

    err = _require_actuator()
    if err:
        return err

    body      = request.get_json(silent=True) or {}
    direction = body.get("dir")
    speed     = body.get("speed")
    click_ms  = body.get("click_ms")
    return_ms = body.get("return_ms")
    trim      = body.get("trim", 0)

    if direction is None or speed is None or click_ms is None or return_ms is None:
        return _err("field 'dir', 'speed', 'click_ms', 'return_ms' diperlukan")
    if str(direction).upper() not in ("CW", "CCW"):
        return _err("field 'dir' harus 'CW' atau 'CCW'")

    result = _actuator.save_calibration(
        servo_id, str(direction), int(speed),
        int(click_ms), int(return_ms), int(trim)
    )
    if result.get("ok"):
        push_command({
            "actuator": f"Servo {servo_id}",
            "action":   "Kalibrasi disimpan",
            "reason":   f"dir={result.get('click_dir')}, speed={result.get('click_speed')}, "
                        f"click_ms={result.get('click_ms')}, return_ms={result.get('return_ms')}, "
                        f"trim={result.get('trim')}",
        })
        return jsonify(result)
    return jsonify(result), 400


# ── Kontrol Manual AC ──────────────────────────────────────────────────────────

@app.route("/api/ac/power", methods=["POST"])
def api_ac_power():
    """Klik tombol power AC secara manual."""
    import config
    err = _require_actuator()
    if err:
        return err

    ok = _actuator.click_servo(config.SERVO_POWER)
    if ok:
        with _state_lock:
            new_state = not _current_state.get("ac_desired", False)
        push_state({"ac_desired": new_state})
        if _logic:
            _logic.force_ac_state(new_state)
        push_command({
            "actuator": "AC Power",
            "action":   "KLIK",
            "reason":   "manual dari dashboard",
        })
        return _ok(ac_desired=new_state)
    return _err("Gagal klik servo power.", 502)


@app.route("/api/ac/temp_up", methods=["POST"])
def api_ac_temp_up():
    """Klik tombol naik suhu AC."""
    import config
    err = _require_actuator()
    if err:
        return err

    ok = _actuator.click_servo(config.SERVO_TEMP_UP)
    if ok:
        push_command({"actuator": "Temp Up", "action": "KLIK", "reason": "manual"})
        return _ok()
    return _err("Gagal klik servo temp up.", 502)


@app.route("/api/ac/temp_down", methods=["POST"])
def api_ac_temp_down():
    """Klik tombol turun suhu AC."""
    import config
    err = _require_actuator()
    if err:
        return err

    ok = _actuator.click_servo(config.SERVO_TEMP_DOWN)
    if ok:
        push_command({"actuator": "Temp Down", "action": "KLIK", "reason": "manual"})
        return _ok()
    return _err("Gagal klik servo temp down.", 502)


# ── Kontrol Lampu ──────────────────────────────────────────────────────────────

@app.route("/api/lamp", methods=["POST"])
def api_lamp():
    """Kontrol relay lampu secara manual."""
    err = _require_actuator()
    if err:
        return err

    body  = request.get_json(silent=True) or {}
    state = body.get("state", "").upper()
    if state not in ("ON", "OFF"):
        return _err("field 'state' harus 'ON' atau 'OFF'")

    ok = _actuator.set_relay(state)
    if ok:
        push_state({"lamp_on": state == "ON"})
        push_command({
            "actuator": "Lampu",
            "action":   state,
            "reason":   "manual dari dashboard",
        })
        return _ok(state=state)
    return _err("Gagal mengontrol relay lampu.", 502)


# ── Settings Runtime ───────────────────────────────────────────────────────────

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """Baca settings saat ini dari file settings.json."""
    import config as cfg
    defaults = {
        "yolo_confidence":    cfg.YOLO_CONFIDENCE,
        "person_threshold_ac":   cfg.PERSON_THRESHOLD_AC,
        "person_threshold_lamp": cfg.PERSON_THRESHOLD_LAMP,
        "zone_split_ratio":   cfg.ZONE_SPLIT_RATIO,
        "dht22_poll_interval": cfg.DHT22_POLL_INTERVAL,
    }
    if _settings_file_path and os.path.exists(_settings_file_path):
        try:
            with open(_settings_file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return jsonify(defaults)


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """Simpan settings baru dan terapkan ke komponen aktif tanpa restart."""
    body = request.get_json(silent=True)
    if not body:
        return _err("Body JSON diperlukan")

    allowed = {
        "yolo_confidence", "person_threshold_ac", "person_threshold_lamp",
        "zone_split_ratio", "dht22_poll_interval"
    }
    filtered = {k: v for k, v in body.items() if k in allowed}

    if not filtered:
        return _err("Tidak ada field yang valid. Gunakan: " + ", ".join(allowed))

    # Simpan ke file
    if _settings_file_path:
        existing = {}
        if os.path.exists(_settings_file_path):
            try:
                with open(_settings_file_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.update(filtered)
        try:
            with open(_settings_file_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            return _err(f"Gagal menyimpan settings: {e}", 500)

    # Terapkan langsung ke komponen aktif (tanpa restart)
    if _detector and "yolo_confidence" in filtered:
        _detector.set_confidence(filtered["yolo_confidence"])

    if _logic:
        _logic.update_params(
            zone_split_ratio=filtered.get("zone_split_ratio"),
            threshold_ac=filtered.get("person_threshold_ac"),
            threshold_lamp=filtered.get("person_threshold_lamp"),
        )

    push_command({
        "actuator": "Settings",
        "action":   "DIPERBARUI",
        "reason":   ", ".join(f"{k}={v}" for k, v in filtered.items()),
    })

    return _ok(updated=filtered)


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_dashboard(host: str = "0.0.0.0", port: int = 5000):
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
