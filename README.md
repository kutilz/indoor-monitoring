# Sistem Kendali Cerdas AC & Pencahayaan Ruang Kuliah

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-purple)
![ESP32](https://img.shields.io/badge/ESP32-Arduino-teal?logo=arduino)
![License](https://img.shields.io/badge/License-MIT-green)

Sistem kendali otomatis AC dan pencahayaan ruang kuliah berbasis **computer vision (YOLOv8)** dan **IoT (ESP32)**. Sistem mendeteksi keberadaan dan posisi mahasiswa di ruangan menggunakan kamera, lalu secara otomatis menyalakan/mematikan AC dan lampu sesuai zona yang terisi.

---

## Daftar Isi

- [Arsitektur Sistem](#arsitektur-sistem)
- [Hardware yang Dibutuhkan](#hardware-yang-dibutuhkan)
- [Struktur Folder](#struktur-folder)
- [Quick Start — Mode Akuisisi (Tanpa Hardware)](#quick-start--mode-akuisisi-tanpa-hardware)
- [Quick Start — Mode Real (Dengan Hardware)](#quick-start--mode-real-dengan-hardware)
- [Panduan Wiring Hardware](#panduan-wiring-hardware)
- [Konfigurasi](#konfigurasi)
- [Perintah CLI Lengkap](#perintah-cli-lengkap)

---

## Arsitektur Sistem

```
┌─────────────────────┐     HTTP MJPEG     ┌──────────────────────────────────┐
│  ESP32-CAM          │ ─────────────────► │  Python Server (PC/Laptop)       │
│  (OV2640 Camera)    │                    │                                  │
└─────────────────────┘                    │  ┌──────────────┐                │
                                           │  │ YOLOv8       │ Deteksi person │
┌─────────────────────┐                    │  └──────┬───────┘                │
│  Mosquitto MQTT     │ ◄── MQTT Publish ──│         │                        │
│  Broker             │                    │  ┌──────▼───────┐                │
└────────┬────────────┘                    │  │ Control Logic│ Zoning & Count │
         │ MQTT Subscribe                  │  └──────┬───────┘                │
         ▼                                 │         │                        │
┌─────────────────────┐                    │  ┌──────▼───────┐                │
│  ESP32 + Relay 4CH  │                    │  │ Dashboard    │ http://...5000 │
│  (GPIO 12/13/14/15) │                    │  └──────────────┘                │
│  ├─ Relay 1: AC     │                    └──────────────────────────────────┘
│  ├─ Relay 2: Lampu  │
│  └─ Relay 3: Lampu  │
└─────────────────────┘
```

---

## Hardware yang Dibutuhkan

| Komponen | Spesifikasi | Jumlah |
|----------|-------------|--------|
| ESP32-CAM | AI-Thinker, modul kamera OV2640 | 1 |
| ESP32 Dev Board | Untuk kontrol relay (bukan CAM) | 1 |
| Modul Relay 4-Channel | 5V coil, AC 220V/10A | 1 |
| Adaptor Power | 5V/2A untuk ESP32-CAM | 1 |
| PC/Laptop | CPU untuk inferensi YOLOv8 | 1 |

---

## Struktur Folder

```
indoor-monitoring/
├── .github/ISSUE_TEMPLATE/   # Template laporan bug & fitur
├── edge_node/
│   ├── esp32_cam_stream/     # Firmware MJPEG HTTP Server
│   └── esp32_relay_mqtt/     # Firmware MQTT Relay Controller
├── server_ai/
│   ├── main.py               # Entry point (--mode akuisisi/real)
│   ├── config.py             # Semua konfigurasi
│   ├── stream_source.py      # Abstraksi video (file / HTTP)
│   ├── yolo_detector.py      # YOLOv8 inference
│   ├── control_logic.py      # Logika zoning & counting
│   ├── mqtt_client.py        # Paho-MQTT (mode real)
│   ├── mock_mqtt.py          # Mock MQTT (mode akuisisi)
│   ├── requirements.txt
│   ├── weights/              # Simpan file .pt di sini (lihat panduan)
│   └── dashboard/            # Flask web dashboard
│       ├── app.py
│       ├── templates/index.html
│       └── static/
├── docs/                     # Skema & flowchart
├── data/
│   ├── test_videos/          # Video uji (tidak di-commit)
│   └── logs/                 # Log CSV output
├── .gitignore
├── LICENSE
└── CONTRIBUTING.md
```

---

## Quick Start — Mode Akuisisi (Tanpa Hardware)

> Cocok untuk **bimbingan skripsi**, **sidang**, dan **testing** tanpa perlu ESP32 atau broker MQTT.

### 1. Setup Environment Python

```bash
cd server_ai
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Unduh Model YOLOv8

```bash
# Jalankan dari dalam folder server_ai/ (virtual env aktif)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

Setelah selesai, pindahkan file `yolov8n.pt` ke folder `server_ai/weights/`:

```bash
# Windows
move yolov8n.pt weights\

# Linux / macOS
mv yolov8n.pt weights/
```

### 3. Siapkan Video Uji

Letakkan file video (`.mp4` atau `.avi`) di folder `data/test_videos/`.
Lihat `data/test_videos/README.md` untuk panduan mendapatkan video.

### 4. Jalankan Sistem

```bash
# Dari folder server_ai/
python main.py --mode akuisisi --source ../data/test_videos/sample.mp4
```

### 5. Buka Dashboard

Buka browser dan akses: **http://localhost:5000**

Dashboard menampilkan:
- Live video feed dengan bounding box deteksi orang
- Jumlah orang per zona (depan / belakang)
- Status relay AC dan lampu (ON/OFF)
- Log perintah yang dihasilkan sistem

---

## Quick Start — Mode Real (Dengan Hardware)

### 1. Upload Firmware ESP32-CAM

1. Buka `edge_node/esp32_cam_stream/esp32_cam_stream.ino` di Arduino IDE
2. Edit `WIFI_SSID` dan `WIFI_PASSWORD`
3. Pilih board: **AI Thinker ESP32-CAM**
4. Upload, lalu buka Serial Monitor @ 115200 baud
5. Catat IP address yang muncul (contoh: `192.168.1.100`)

### 2. Upload Firmware ESP32 Relay

1. Buka `edge_node/esp32_relay_mqtt/esp32_relay_mqtt.ino` di Arduino IDE
2. Edit `WIFI_SSID`, `WIFI_PASSWORD`, dan `MQTT_SERVER` (IP komputer)
3. Pilih board: **ESP32 Dev Module**
4. Upload firmware

### 3. Jalankan Mosquitto MQTT Broker

```bash
# Install Mosquitto: https://mosquitto.org/download/

# Windows (jalankan sebagai Service atau langsung)
mosquitto -v

# Linux
sudo systemctl start mosquitto
```

### 4. Konfigurasi Server

Edit `server_ai/config.py`:

```python
ESP32_STREAM_URL = "http://192.168.1.100:81/stream"  # IP ESP32-CAM kamu
MQTT_BROKER_HOST = "localhost"                         # atau IP broker
```

### 5. Jalankan Server AI

```bash
cd server_ai
.venv\Scripts\activate   # Windows
python main.py --mode real
```

### 6. Buka Dashboard

Akses: **http://localhost:5000**

---

## Panduan Wiring Hardware

### ESP32-CAM + Power Supply

```
Adaptor 5V/2A
├── (+) → ESP32-CAM pin 5V
└── (-) → ESP32-CAM pin GND
```

> **Penting:** Jangan power ESP32-CAM lewat USB programmer saat streaming, gunakan adaptor 5V/2A langsung.

### ESP32 + Modul Relay 4-Channel

```
ESP32               Modul Relay
------              -----------
GPIO 12     →       IN1  (Relay 1 - AC)
GPIO 13     →       IN2  (Relay 2 - Lampu Depan)
GPIO 14     →       IN3  (Relay 3 - Lampu Belakang)
GPIO 15     →       IN4  (Relay 4 - Cadangan)
5V          →       VCC
GND         →       GND
```

### Koneksi Beban AC (Contoh untuk Lampu)

```
Fasa AC 220V → COM relay → NO relay → Kabel ke Lampu → Netral → kembali ke sumber
```

> **Peringatan Keselamatan:** Selalu gunakan isolasi yang memadai. Jangan menyentuh terminal AC saat sistem beroperasi.

---

## Konfigurasi

Semua konfigurasi ada di `server_ai/config.py`. Nilai bisa di-override via environment variable:

| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `ESP32_STREAM_URL` | `http://192.168.1.100:81/stream` | URL MJPEG stream ESP32-CAM |
| `MQTT_BROKER_HOST` | `localhost` | IP broker Mosquitto |
| `MQTT_BROKER_PORT` | `1883` | Port MQTT |
| `PERSON_THRESHOLD_AC` | `1` | Minimal orang untuk menyalakan AC |
| `ZONE_SPLIT_RATIO` | `0.5` | Pembagi zona (0.5 = tengah frame) |
| `YOLO_MODEL_PATH` | `weights/yolov8n.pt` | Path model YOLOv8 |
| `YOLO_CONFIDENCE` | `0.5` | Threshold confidence deteksi |
| `DASHBOARD_PORT` | `5000` | Port dashboard Flask |

---

## Perintah CLI Lengkap

```bash
# Mode Akuisisi dengan video tertentu
python main.py --mode akuisisi --source ../data/test_videos/kelas.mp4

# Mode Akuisisi dengan tampilan jendela OpenCV
python main.py --mode akuisisi --source ../data/test_videos/kelas.mp4 --show-window

# Mode Real
python main.py --mode real

# Mode Real tanpa dashboard (headless)
python main.py --mode real --no-dashboard

# Mode Real dengan jendela OpenCV
python main.py --mode real --show-window

# Bantuan
python main.py --help
```

---

## Library Arduino yang Dibutuhkan

Install melalui Arduino IDE Library Manager:

| Library | Dibutuhkan untuk |
|---------|-----------------|
| `PubSubClient` by Nick O'Leary | MQTT client ESP32 Relay |
| `ArduinoJson` by Benoit Blanchon | Parse JSON payload MQTT |
| ESP32 Board Package | Semua firmware ESP32 |

---

## Lisensi

MIT License — lihat file [LICENSE](LICENSE) untuk detail.
