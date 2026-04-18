"""
Entry point utama — Sistem Kendali Cerdas AC & Pencahayaan Ruang Kuliah.

Penggunaan:
    # Mode Akuisisi (tanpa hardware, cocok untuk bimbingan & sidang)
    python main.py --mode akuisisi --source ../data/test_videos/sample.mp4

    # Mode Real (hardware lengkap: ESP32-CAM + Relay + Mosquitto)
    python main.py --mode real

    # Mode Real tanpa dashboard browser
    python main.py --mode real --no-dashboard
"""

import argparse
import os
import signal
import sys
import threading
import time

import cv2

import config
from stream_source import create_stream
from yolo_detector import YoloDetector
from control_logic import ControlLogic
from mock_mqtt import create_mqtt_client


# ── Argparse ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistem Kendali Cerdas AC & Pencahayaan Ruang Kuliah",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python main.py --mode akuisisi --source ../data/test_videos/kelas.mp4
  python main.py --mode real
  python main.py --mode real --no-dashboard
        """
    )
    parser.add_argument(
        "--mode",
        choices=["akuisisi", "real"],
        default=config.DEFAULT_MODE,
        help="Mode operasi sistem (default: akuisisi)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Path file video untuk mode akuisisi. "
             "Default: %(default)s dari config.py"
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Nonaktifkan dashboard web (headless mode)"
    )
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Tampilkan jendela OpenCV (berguna saat tidak ada browser)"
    )
    return parser.parse_args()


# ── FPS Counter ───────────────────────────────────────────────────────────────

class FPSCounter:
    """Hitung FPS dengan sliding window."""

    def __init__(self, window: int = 30):
        self._times = []
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


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace):
    mode = args.mode
    print(f"\n{'='*60}")
    print(f"  Sistem Kendali Cerdas AC & Pencahayaan — Mode: {mode.upper()}")
    print(f"{'='*60}\n")

    # ── Inisialisasi Komponen ─────────────────────────────────────────────────
    print("[Main] Memuat model YOLOv8...")
    detector = YoloDetector()

    print("[Main] Inisialisasi logika kendali...")
    logic = ControlLogic()

    print("[Main] Inisialisasi MQTT client...")
    mqtt_client = create_mqtt_client(mode)
    mqtt_client.connect()

    print("[Main] Membuka sumber video...")
    stream = create_stream(mode, source_path=args.source)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dashboard_thread = None
    if not args.no_dashboard:
        from dashboard.app import run_dashboard, push_frame, push_state, push_command
        dashboard_thread = threading.Thread(
            target=run_dashboard,
            kwargs={
                "host": config.DASHBOARD_HOST,
                "port": config.DASHBOARD_PORT,
            },
            daemon=True,
            name="DashboardThread"
        )
        dashboard_thread.start()
        print(f"\n[Dashboard] Buka browser di: "
              f"http://localhost:{config.DASHBOARD_PORT}\n")
    else:
        push_frame = push_state = push_command = lambda *a, **k: None

    # ── State awal dashboard ───────────────────────────────────────────────────
    if not args.no_dashboard:
        push_state({"mode": mode})

    fps_counter = FPSCounter()
    prev_state = None
    frame_count = 0

    print("[Main] Loop utama dimulai. Tekan Ctrl+C untuk berhenti.\n")

    try:
        while True:
            success, frame = stream.read()
            if not success or frame is None:
                print("[Main] Frame tidak tersedia. Menunggu...")
                time.sleep(0.5)
                continue

            frame_count += 1
            h, w = frame.shape[:2]

            # ── Deteksi YOLO ──────────────────────────────────────────────────
            detections = detector.detect(frame)

            # ── Logika Kendali ────────────────────────────────────────────────
            state = logic.process(detections, frame_width=w, frame_height=h)
            commands = logic.get_relay_commands(state, prev_state)

            # ── Kirim perintah relay (hanya yang berubah) ─────────────────────
            if commands:
                mqtt_client.publish_commands(commands)
                if not args.no_dashboard:
                    for cmd in commands:
                        push_command(cmd)

            prev_state = state

            # ── Update dashboard ──────────────────────────────────────────────
            fps = fps_counter.tick()

            state_dict = state.to_dict()
            state_dict["mode"] = mode
            state_dict["fps"]  = round(fps, 1)

            if not args.no_dashboard:
                push_state(state_dict)

                # Encode frame dengan anotasi dan kirim ke video feed
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
                annotated = detector.draw(
                    frame, detections,
                    zone_split_y=state.zone_split_y
                )
                cv2.putText(
                    annotated,
                    f"FPS: {fps:.1f} | Mode: {mode.upper()}",
                    (w - 220, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (200, 200, 200), 1
                )
                cv2.imshow("Sistem Kendali Ruang Kuliah", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[Main] Dihentikan via tombol 'q'.")
                    break

    except KeyboardInterrupt:
        print("\n[Main] Ctrl+C — Menghentikan sistem...")
    finally:
        print("[Main] Membersihkan resource...")
        stream.release()
        mqtt_client.disconnect()
        cv2.destroyAllWindows()
        print("[Main] Selesai.")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Pastikan working directory adalah server_ai/ agar import relatif berjalan
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    args = parse_args()
    run(args)
