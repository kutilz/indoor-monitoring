"""
Flask web dashboard untuk monitoring real-time sistem kendali AC & Pencahayaan.
Berjalan di kedua mode (akuisisi & real) sebagai thread terpisah dari loop AI.

Endpoint:
    GET /            → Dashboard HTML
    GET /video_feed  → MJPEG stream frame yang sudah dianotasi
    GET /events      → Server-Sent Events (SSE) untuk state JSON real-time
    GET /api/state   → Snapshot state terkini (JSON)
    GET /api/logs    → 50 log perintah terakhir (JSON)
"""

import json
import queue
import threading
import time
from flask import Flask, Response, render_template, jsonify

app = Flask(__name__)
app.config["SECRET_KEY"] = "classroom-ai-dashboard"

# ── Shared state (diisi oleh loop AI di main.py) ───────────────────────────────
_state_lock = threading.Lock()
_current_state: dict = {
    "mode": "akuisisi",
    "total_persons": 0,
    "zone_front": 0,
    "zone_back": 0,
    "ac_on": False,
    "light_front_on": False,
    "light_back_on": False,
    "fps": 0.0,
    "frame_width": 0,
    "frame_height": 0,
    "zone_split_y": 0,
}

# Queue frame JPEG untuk /video_feed
_frame_queue: queue.Queue = queue.Queue(maxsize=2)

# Queue event SSE untuk /events
_sse_queue: queue.Queue = queue.Queue(maxsize=50)

# Log perintah relay (list of dict, max 100 entry)
_command_log: list = []
_log_lock = threading.Lock()


# ── Public API (dipanggil oleh main.py) ────────────────────────────────────────

def push_frame(jpeg_bytes: bytes):
    """Kirim frame JPEG yang sudah dianotasi ke video feed."""
    if not _frame_queue.full():
        _frame_queue.put(jpeg_bytes)


def push_state(state: dict):
    """Update state sistem dan kirim ke semua SSE subscriber."""
    with _state_lock:
        _current_state.update(state)
    event_data = json.dumps(state)
    if not _sse_queue.full():
        _sse_queue.put(event_data)


def push_command(command: dict):
    """Catat perintah relay ke log dashboard."""
    with _log_lock:
        _command_log.append({
            **command,
            "timestamp": time.strftime("%H:%M:%S")
        })
        if len(_command_log) > 100:
            _command_log.pop(0)


# ── Flask Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with _state_lock:
        state = dict(_current_state)
    return render_template("index.html", state=state)


@app.route("/video_feed")
def video_feed():
    """MJPEG stream dari frame yang sudah dianotasi oleh YOLO."""
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
                # Kirim frame kosong agar koneksi tidak timeout
                continue

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/events")
def events():
    """
    Server-Sent Events stream.
    Browser berlangganan ke endpoint ini untuk update real-time tanpa polling.
    """
    def generate():
        # Kirim state saat ini dulu sebagai event pertama
        with _state_lock:
            yield f"data: {json.dumps(_current_state)}\n\n"

        while True:
            try:
                data = _sse_queue.get(timeout=15.0)
                yield f"data: {data}\n\n"
            except queue.Empty:
                # Keepalive agar koneksi tidak di-drop browser/proxy
                yield ": keepalive\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/state")
def api_state():
    """Snapshot state terkini dalam format JSON."""
    with _state_lock:
        return jsonify(dict(_current_state))


@app.route("/api/logs")
def api_logs():
    """50 log perintah relay terakhir."""
    with _log_lock:
        return jsonify(_command_log[-50:])


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_dashboard(host: str = "0.0.0.0", port: int = 5000):
    """
    Jalankan Flask server. Dipanggil di thread terpisah dari main.py.
    Menggunakan Werkzeug development server (cukup untuk demo & sidang).
    """
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)  # Sembunyikan request log yang berisik

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )
