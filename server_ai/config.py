"""
Konfigurasi terpusat untuk sistem kendali AC & pencahayaan ruang kuliah.
Semua nilai default bisa di-override lewat environment variable.
"""

import os

# ── Mode ───────────────────────────────────────────────────────────────────────
# Diset oleh main.py berdasarkan argumen CLI, bukan dari env.
# Nilai valid: "akuisisi" | "real"
DEFAULT_MODE = "akuisisi"

# ── ESP32-CAM Stream (Mode Real) ───────────────────────────────────────────────
# Ganti dengan IP yang muncul di Serial Monitor ESP32-CAM saat pertama kali boot.
ESP32_STREAM_URL = os.environ.get(
    "ESP32_STREAM_URL",
    "http://192.168.1.100/stream"
)

# ── MQTT Broker (Mode Real) ────────────────────────────────────────────────────
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))
MQTT_KEEPALIVE   = 60
MQTT_CLIENT_ID   = "server_ai_controller"

# Topik MQTT
# Perintah ke relay: classroom/relay/<nomor_relay>
# Contoh payload: {"relay": 1, "state": "ON"}
MQTT_TOPIC_RELAY  = "classroom/relay"
MQTT_TOPIC_STATUS = "classroom/status"  # opsional, untuk heartbeat

# ── Logika Kendali ─────────────────────────────────────────────────────────────
# Jumlah orang minimal agar AC menyala
PERSON_THRESHOLD_AC = int(os.environ.get("PERSON_THRESHOLD_AC", 1))

# Rasio pembagi zona depan/belakang (0.0 - 1.0)
# 0.5 = setengah frame bagian atas = depan, bawah = belakang
ZONE_SPLIT_RATIO = float(os.environ.get("ZONE_SPLIT_RATIO", 0.5))

# Nomor relay untuk setiap aktuator (sesuai kabel fisik)
RELAY_AC          = 1   # GPIO 12 di ESP32
RELAY_LIGHT_FRONT = 2   # GPIO 13
RELAY_LIGHT_BACK  = 3   # GPIO 14
RELAY_SPARE       = 4   # GPIO 15 (cadangan)

# ── YOLOv8 ─────────────────────────────────────────────────────────────────────
# Path model relatif terhadap direktori server_ai/
# Unduh model dengan: python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# lalu pindahkan ke folder weights/
YOLO_MODEL_PATH  = os.environ.get("YOLO_MODEL_PATH", "weights/yolov8n.pt")
YOLO_CONFIDENCE  = float(os.environ.get("YOLO_CONFIDENCE", 0.5))
YOLO_DEVICE      = os.environ.get("YOLO_DEVICE", "cpu")  # "cpu" | "0" (GPU)

# Class ID untuk 'person' di dataset COCO (digunakan YOLOv8 default)
YOLO_PERSON_CLASS_ID = 0

# ── Dashboard Flask ─────────────────────────────────────────────────────────────
DASHBOARD_HOST    = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT    = int(os.environ.get("DASHBOARD_PORT", 5000))

# ── Log (Mode Akuisisi) ────────────────────────────────────────────────────────
LOG_DIR           = os.environ.get("LOG_DIR", "../data/logs")
LOG_COMMANDS_FILE = "commands.csv"
LOG_ENERGY_FILE   = "energy_log.csv"

# ── Mode Akuisisi - Video Sumber ───────────────────────────────────────────────
# Path default jika --source tidak diberikan di CLI
DEFAULT_TEST_VIDEO = os.environ.get(
    "DEFAULT_TEST_VIDEO",
    "../data/test_videos/sample.mp4"
)

# Jika True, video akan di-loop otomatis saat selesai (berguna untuk demo)
VIDEO_LOOP = True
