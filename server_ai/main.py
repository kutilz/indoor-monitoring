"""
Entry point — Sistem Kendali Cerdas AC & Lampu Ruang Kuliah.

Penggunaan:
    python main.py [--no-dashboard] [--show-window]

Node yang dibutuhkan (gracefully handled jika offline):
    - ESP32-CAM  : MJPEG stream untuk deteksi YOLO
    - D1 Mini    : HTTP REST untuk servo AC + relay lampu + DHT22
"""

import argparse
import json
import os
import threading
import time

import cv2

import config
from stream_source import HttpStreamSource
from yolo_detector import YoloDetector
from control_logic import ControlLogic
from actuator_client import ActuatorClient


# ── Argparse ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistem Kendali Cerdas AC & Lampu Ruang Kuliah",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python main.py
  python main.py --no-dashboard
  python main.py --show-window
        """
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Nonaktifkan dashboard web (headless mode)"
    )
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Tampilkan jendela OpenCV lokal"
    )
    return parser.parse_args()


# ── Load settings.json (override config defaults) ──────────────────────────────

def load_settings() -> dict:
    """
    Baca settings.json jika ada.
    File ini dibuat oleh dashboard saat user mengubah settings via UI.
    """
    settings_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        config.SETTINGS_FILE
    )
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Settings] Gagal baca settings.json: {e}")
        return {}


def apply_settings(settings: dict, detector=None, logic=None):
    """Apply nilai dari settings dict ke komponen yang relevan."""
    if "yolo_confidence" in settings and detector:
        detector.set_confidence(settings["yolo_confidence"])
    if logic:
        logic.update_params(
            zone_split_ratio=settings.get("zone_split_ratio"),
            threshold_ac=settings.get("person_threshold_ac"),
            threshold_lamp=settings.get("person_threshold_lamp"),
        )


# ── FPS Counter ────────────────────────────────────────────────────────────────

class FPSCounter:
    def __init__(self, window: int = 30):
        self._times  = []
        self._window = window

    def tick(self) -> float:
        now = time.perf_counter()
        self._times.append(now)
        if len(self._times) > self._window:
            self._times.pop(0)
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / elapsed if elapsed > 0 else 0.0


# ── DHT22 Poll Loop ────────────────────────────────────────────────────────────

def dht_poll_loop(actuator: ActuatorClient, push_state_fn, stop_event: threading.Event):
    """
    Thread terpisah: polling sensor DHT22 dari node aktuator setiap N detik.
    Hasil dikirim ke dashboard via push_state.
    """
    interval = config.DHT22_POLL_INTERVAL
    while not stop_event.is_set():
        data = actuator.get_sensor()
        push_state_fn({
            "temp":             data.get("temp", 0.0),
            "humidity":         data.get("humidity", 0.0),
            "sensor_ok":        data.get("ok", False),
            "actuator_online":  actuator.online,
        })
        stop_event.wait(timeout=interval)


# ── Main ───────────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace):
    print(f"\n{'='*60}")
    print("  Sistem Kendali Cerdas AC & Lampu Ruang Kuliah")
    print(f"{'='*60}\n")

    # ── Load settings ─────────────────────────────────────────────────────────
    settings = load_settings()
    if settings:
        print(f"[Main] settings.json dimuat: {settings}")

    # ── Inisialisasi komponen ─────────────────────────────────────────────────
    print("[Main] Memuat model YOLOv8...")
    detector = YoloDetector()

    print("[Main] Inisialisasi logika kendali...")
    logic = ControlLogic()

    print("[Main] Inisialisasi actuator client...")
    actuator = ActuatorClient()

    # Apply settings ke detector & logic
    apply_settings(settings, detector, logic)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    push_frame   = lambda *a, **k: None
    push_state   = lambda *a, **k: None
    push_command = lambda *a, **k: None

    if not args.no_dashboard:
        from dashboard.app import (
            run_dashboard, push_frame, push_state, push_command,
            set_actuator_ref, set_logic_ref, set_detector_ref, set_settings_file
        )
        set_actuator_ref(actuator)
        set_logic_ref(logic)
        set_detector_ref(detector)
        set_settings_file(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         config.SETTINGS_FILE)
        )

        dash_thread = threading.Thread(
            target=run_dashboard,
            kwargs={"host": config.DASHBOARD_HOST, "port": config.DASHBOARD_PORT},
            daemon=True,
            name="DashboardThread"
        )
        dash_thread.start()
        print(f"\n[Dashboard] Buka browser di: http://localhost:{config.DASHBOARD_PORT}\n")

    # ── Cek konektivitas node aktuator ────────────────────────────────────────
    print("[Main] Mengecek node aktuator...")
    if actuator.is_online():
        print(f"[Main] Node aktuator online: {config.ACTUATOR_URL}")
    else:
        print(f"[Main] PERINGATAN: Node aktuator offline ({config.ACTUATOR_URL})")
        print("[Main] Kontrol servo/relay dinonaktifkan. Dashboard tetap berjalan.")

    # ── Stream video dari ESP32-CAM ───────────────────────────────────────────
    print("[Main] Membuka stream ESP32-CAM...")
    stream = HttpStreamSource()

    # ── DHT22 polling thread ──────────────────────────────────────────────────
    stop_event = threading.Event()
    dht_thread = threading.Thread(
        target=dht_poll_loop,
        args=(actuator, push_state, stop_event),
        daemon=True,
        name="DHTThread"
    )
    dht_thread.start()

    # ── State awal dashboard ──────────────────────────────────────────────────
    push_state({
        "actuator_online": actuator.online,
        "camera_online":   stream.is_connected,
        "ac_desired":      False,
        "lamp_on":         False,
        "temp":            0.0,
        "humidity":        0.0,
    })

    fps_counter = FPSCounter()
    prev_state  = None

    print("[Main] Loop utama dimulai. Tekan Ctrl+C untuk berhenti.\n")

    try:
        while True:
            success, frame = stream.read()
            camera_online  = stream.is_connected

            if not success or frame is None:
                # Kamera offline — update dashboard, skip deteksi
                push_state({"camera_online": False})
                continue

            h, w = frame.shape[:2]

            # ── Deteksi YOLO ──────────────────────────────────────────────────
            detections = detector.detect(frame)

            # ── Logika Kendali ────────────────────────────────────────────────
            state    = logic.process(detections, frame_width=w, frame_height=h)
            commands = logic.get_actuator_commands(state, prev_state)

            # ── Eksekusi perintah aktuator ────────────────────────────────────
            if actuator.online:
                for servo_id in commands["servo_clicks"]:
                    actuator.click_servo(servo_id)

                if commands["relay"] is not None:
                    actuator.set_relay(commands["relay"])

            # Log ke dashboard
            for entry in commands["log_entries"]:
                push_command(entry)

            prev_state = state

            # ── Update dashboard ──────────────────────────────────────────────
            fps       = fps_counter.tick()
            state_dict = state.to_dict()
            state_dict.update({
                "fps":             round(fps, 1),
                "camera_online":   camera_online,
                "actuator_online": actuator.online,
            })
            push_state(state_dict)

            # Frame dengan anotasi untuk video feed
            annotated = detector.draw(
                frame, detections,
                zone_split_y=state.zone_split_y
            )
            _, jpeg = cv2.imencode(
                ".jpg", annotated,
                [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            push_frame(jpeg.tobytes())

            # ── OpenCV window (opsional) ──────────────────────────────────────
            if args.show_window:
                cv2.putText(
                    annotated,
                    f"FPS: {fps:.1f} | AC: {'ON' if state.ac_desired else 'OFF'} "
                    f"| Lampu: {'ON' if state.lamp_on else 'OFF'}",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (200, 200, 200), 1
                )
                cv2.imshow("Sistem Kendali Ruang Kuliah", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        print("\n[Main] Ctrl+C — Menghentikan sistem...")
    finally:
        print("[Main] Membersihkan resource...")
        stop_event.set()
        stream.release()
        cv2.destroyAllWindows()
        print("[Main] Selesai.")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    args = parse_args()
    run(args)
