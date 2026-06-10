"""
Konfigurasi terpusat — Sistem Kendali AC & Lampu Ruang Kuliah.
Nilai default bisa di-override via environment variable.
Nilai runtime (dari dashboard) disimpan di settings.json dan di-merge saat startup.
"""

import os

# ── ESP32-CAM Stream ───────────────────────────────────────────────────────────
# Ganti dengan IP yang muncul di Serial Monitor ESP32-CAM saat boot pertama.
# Format: http://<IP>:81/stream  (port 81 untuk raw MJPEG stream)
ESP32_STREAM_URL = os.environ.get(
    "ESP32_STREAM_URL",
    "http://192.168.1.100:81/stream"
)

# ── Node Aktuator (D1 Mini / ESP32) ───────────────────────────────────────────
# Ganti dengan IP yang muncul di Serial Monitor node aktuator saat boot.
ACTUATOR_URL     = os.environ.get("ACTUATOR_URL", "http://192.168.1.101")
ACTUATOR_TIMEOUT = 2   # Timeout HTTP request (detik) — singkat agar tidak block loop

# ── ID Servo (sesuai firmware d1mini_actuator.ino) ────────────────────────────
SERVO_POWER    = 0   # Tombol power AC
SERVO_TEMP_UP  = 1   # Tombol naik suhu
SERVO_TEMP_DOWN = 2  # Tombol turun suhu

# ── Logika Kendali ─────────────────────────────────────────────────────────────
# Jumlah orang minimal agar AC menyala (klik tombol power)
PERSON_THRESHOLD_AC   = int(os.environ.get("PERSON_THRESHOLD_AC", 1))

# Jumlah orang minimal agar lampu menyala
PERSON_THRESHOLD_LAMP = int(os.environ.get("PERSON_THRESHOLD_LAMP", 1))

# Rasio pembagi zona depan/belakang (0.0 - 1.0)
# 0.5 = setengah frame bagian atas = depan, bawah = belakang
# (Digunakan untuk menampilkan garis zona di video, bukan untuk kontrol lampu)
ZONE_SPLIT_RATIO = float(os.environ.get("ZONE_SPLIT_RATIO", 0.5))

# ── DHT22 ──────────────────────────────────────────────────────────────────────
# Interval polling sensor suhu/kelembaban dari node aktuator (detik)
DHT22_POLL_INTERVAL = int(os.environ.get("DHT22_POLL_INTERVAL", 10))

# ── YOLOv8 ─────────────────────────────────────────────────────────────────────
YOLO_MODEL_PATH      = os.environ.get("YOLO_MODEL_PATH", "weights/yolov8n.pt")
YOLO_CONFIDENCE      = float(os.environ.get("YOLO_CONFIDENCE", 0.5))
YOLO_DEVICE          = os.environ.get("YOLO_DEVICE", "cpu")  # "cpu" | "0" (GPU)
YOLO_PERSON_CLASS_ID = 0  # Class ID 'person' di dataset COCO

# ── Dashboard Flask ─────────────────────────────────────────────────────────────
DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 5000))

# ── Settings File (runtime override dari dashboard) ───────────────────────────
# File JSON yang disimpan server saat user mengubah settings lewat UI.
# Jika file ada, nilainya dipakai menggantikan default di atas.
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "settings.json")

# ── Log ────────────────────────────────────────────────────────────────────────
LOG_DIR            = os.environ.get("LOG_DIR", "../data/logs")
LOG_COMMANDS_FILE  = "commands.csv"
