# Sistem Kendali Cerdas AC & Lampu Ruang Kuliah

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-purple)
![ESP32-CAM](https://img.shields.io/badge/ESP32--CAM-AI%20Thinker-teal?logo=arduino)
![D1 Mini](https://img.shields.io/badge/D1%20Mini-ESP8266-orange?logo=arduino)
![License](https://img.shields.io/badge/License-MIT-green)

Sistem kendali otomatis AC dan lampu berbasis **computer vision (YOLOv8)** dan **IoT (ESP32)**. Kamera mendeteksi keberadaan orang, lalu:

- AC **diklik mati/hidup** otomatis via servo SG90 yang dijepit ke remote Daikin Cassette
- Lampu **dinyalakan/dimatikan** via relay
- Suhu & kelembaban ruangan dipantau via DHT22
- **Semua bisa dikalibrasi dan dikonfigurasi lewat dashboard web — tanpa edit kode**

---

## Arsitektur Sistem

```
┌──────────────────────┐  HTTP MJPEG   ┌────────────────────────────────────────────┐
│  Node 1: ESP32-CAM   │ ────────────► │  Laptop / PC (Python Server)               │
│  AI Thinker          │               │                                            │
└──────────────────────┘               │  ┌──────────┐  ┌────────────┐             │
                                       │  │ YOLOv8   │  │ControlLogic│             │
┌──────────────────────┐  HTTP REST    │  └────┬─────┘  └─────┬──────┘             │
│  Node 2: D1 Mini /   │ ◄──────────── │       └──────┬────────┘                   │
│  ESP32 (Aktuator)    │               │              │                            │
│                      │  HTTP GET     │  ┌───────────▼──────────────────────────┐ │
│  ├─ Servo 0: Power   │ ────────────► │  │ Flask Dashboard (port 5000)          │ │
│  ├─ Servo 1: Temp+   │               │  │  • Monitor: deteksi, status, log      │ │
│  ├─ Servo 2: Temp−   │               │  │  • Kalibrasi Servo: slider, test klik │ │
│  ├─ Relay: Lampu     │               │  │  • Settings: YOLO, threshold, zone    │ │
│  └─ DHT22            │               │  └──────────────────────────────────────┘ │
└──────────────────────┘               └────────────────────────────────────────────┘

Tidak ada MQTT broker — komunikasi via HTTP langsung.
```

---

## Hardware yang Dibutuhkan

| Komponen | Spesifikasi | Jumlah |
|----------|-------------|--------|
| ESP32-CAM | AI Thinker, kamera OV2640 | 1 |
| Adaptor 5V | Untuk power ESP32-CAM langsung (bukan USB programmer) | 1 |
| **Wemos D1 Mini** | ESP8266-based (cukup dari segi pin — lihat catatan di bawah) | 1 |
| **atau ESP32 Dev Board** | **Lebih disarankan** untuk stabilitas PWM servo (lihat catatan) | 1 |
| Servo SG90 | 180°, torsi 1.8 kg·cm | 3 |
| Modul Relay 1-Channel | 5V coil, beban AC 220V/10A | 1 |
| Sensor DHT22 | Suhu & kelembaban | 1 |
| Resistor 10kΩ | Pull-up untuk data DHT22 | 1 |
| Power Supply Servo | **5V/2A eksternal terpisah** untuk 3 servo | 1 |
| PC/Laptop | Untuk inferensi YOLOv8 | 1 |

### Catatan: D1 Mini vs ESP32

**D1 Mini bisa digunakan** — pin yang dibutuhkan (5 GPIO) pas dengan pin aman yang tersedia:

| Pin Board | GPIO | Fungsi |
|-----------|------|--------|
| D1 | GPIO 5 | Servo 0 — Power AC |
| D2 | GPIO 4 | Servo 1 — Temp Up |
| D5 | GPIO 14 | Servo 2 — Temp Down |
| D6 | GPIO 12 | Relay — Lampu |
| D7 | GPIO 13 | DHT22 Data |

**Tapi sangat disarankan upgrade ke ESP32** karena:
- PWM servo di ESP8266 adalah *software timer* — bisa jitter saat Wi-Fi aktif, posisi servo jadi tidak presisi
- ESP32 punya **hardware PWM (LEDC)** yang independen dari Wi-Fi, dual core
- Lebih banyak ruang jika mau tambah komponen

> **Power servo:** Jangan sambungkan servo ke pin VCC/3.3V onboard. Gunakan power supply 5V eksternal dengan GND bersama (common GND) ke board.

---

## Struktur Folder

```
indoor-monitoring/
├── edge_node/
│   ├── esp32_cam_stream/        # Firmware MJPEG HTTP Server
│   │   └── esp32_cam_stream.ino
│   └── d1mini_actuator/         # Firmware aktuator terpadu (servo + relay + DHT22)
│       └── d1mini_actuator.ino
├── server_ai/
│   ├── main.py                  # Entry point
│   ├── config.py                # Semua konfigurasi
│   ├── stream_source.py         # HTTP MJPEG stream dari ESP32-CAM
│   ├── yolo_detector.py         # YOLOv8 inference
│   ├── control_logic.py         # Logika kendali (orang → AC / lampu)
│   ├── actuator_client.py       # HTTP client ke D1 Mini REST API
│   ├── requirements.txt
│   ├── weights/                 # Simpan model .pt di sini
│   └── dashboard/               # Flask web dashboard
│       ├── app.py
│       ├── templates/index.html
│       └── static/
│           ├── script.js        # Monitor + AC/lamp controls
│           ├── calibrate.js     # Kalibrasi servo + settings
│           └── style.css
├── docs/
├── data/logs/                   # Log CSV output
├── .gitignore
└── LICENSE
```

---

## Quick Start

### 1. Setup Python

```bash
cd server_ai
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Unduh Model YOLOv8

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
move yolov8n.pt weights\    # Windows
# atau: mv yolov8n.pt weights/  (Linux/macOS)
```

### 3. Flash Firmware ESP32-CAM

1. Buka `edge_node/esp32_cam_stream/esp32_cam_stream.ino` di Arduino IDE
2. Edit `WIFI_SSID` dan `WIFI_PASSWORD`
3. Board: **AI Thinker ESP32-CAM**
4. Upload → buka Serial Monitor 115200 baud → catat IP (contoh: `192.168.1.100`)

### 4. Flash Firmware D1 Mini / ESP32

1. Buka `edge_node/d1mini_actuator/d1mini_actuator.ino` di Arduino IDE
2. Edit `WIFI_SSID` dan `WIFI_PASSWORD`
3. **Jika D1 Mini:** Board → **LOLIN(WEMOS) D1 R2 & mini**  
   **Jika ESP32:** Board → **ESP32 Dev Module**
4. Install library via Library Manager:
   - `ESP8266Servo` (D1 Mini) **atau** `ESP32Servo` (ESP32)
   - `DHTesp` by beegee-tokyo
   - `ArduinoJson` by Benoit Blanchon
   - LittleFS (sudah built-in di ESP8266/ESP32 core)
5. Upload → buka Serial Monitor 115200 → catat IP (contoh: `192.168.1.101`)
6. Test: buka `http://192.168.1.101/health` di browser → harus muncul JSON `{"status":"ok",...}`

### 5. Konfigurasi Server

Edit `server_ai/config.py`:

```python
ESP32_STREAM_URL = "http://192.168.1.100:81/stream"  # IP ESP32-CAM kamu
ACTUATOR_URL     = "http://192.168.1.101"            # IP D1 Mini kamu
```

### 6. Jalankan Server

```bash
cd server_ai
.venv\Scripts\activate
python main.py
```

Buka browser: **http://localhost:5000**

---

## Panduan Wiring D1 Mini / ESP32

```
D1 Mini / ESP32      Komponen
────────────────     ─────────────────────────────────────────
D1 (GPIO 5)    →    Servo 0 Signal (Power AC)
D2 (GPIO 4)    →    Servo 1 Signal (Temp Up)
D5 (GPIO 14)   →    Servo 2 Signal (Temp Down)
D6 (GPIO 12)   →    Relay IN (Lampu)
D7 (GPIO 13)   →    DHT22 Data

Power Supply 5V Eksternal:
  (+)   →    Servo VCC (ketiga servo)
  (-)   →    Servo GND + GND board (common ground)

DHT22:
  VCC   →    3.3V board
  DATA  →    D7 (GPIO 13)  + resistor 10kΩ ke 3.3V (pull-up)
  GND   →    GND board

Relay:
  IN    →    D6 (GPIO 12)
  VCC   →    5V board atau eksternal
  GND   →    GND board
  COM & NO   →    Sambungkan ke kabel saklar lampu (awas 220V!)
```

### Koneksi Relay ke Saklar Lampu

```
Fasa 220V → COM relay → NO relay → kabel ke beban lampu → Netral → kembali ke sumber
```

> ⚠️ **Peringatan Keselamatan:** Selalu gunakan isolasi yang memadai. Matikan MCB sebelum menyambungkan ke jaringan listrik AC 220V.

---

## Panduan Kalibrasi Servo

Servo sudah terpasang di casing 3D-printed pada remote Daikin. Default posisi servo = 90° (tengah, aman). Kalibrasi harus dilakukan sekali untuk menentukan posisi diam dan posisi klik setiap servo.

**Aturan:** Perjalanan servo (jarak antara stay dan click) **tidak boleh lebih dari 120°** — firmware dan UI akan memperingatkan jika terlewati.

### Langkah Kalibrasi via Dashboard

1. Buka **http://localhost:5000**
2. Klik tab **🎛️ Kalibrasi Servo**
3. Untuk tiap servo (Power, Temp+, Temp−):
   a. Geser **slider** → servo fisik bergerak ke sudut tersebut (klik **▶ Gerak**)
   b. Atur ke posisi di mana servo **tidak menekan tombol** → klik **📌 Set Stay**
   c. Geser slider ke posisi di mana servo **menekan tombol** (maks. 120° dari stay) → klik **🎯 Set Click**
   d. Klik **⚡ Test Klik** — servo akan bergerak: cepat 70% pertama, lambat 30% terakhir, tahan 200ms, balik ke stay
   e. Jika sudah pas, klik sekali **▶ Gerak** + **📌 Set Stay** / **🎯 Set Click** untuk pastikan disimpan
4. Klik **🔄 Refresh Kalibrasi dari Node** untuk konfirmasi nilai tersimpan di firmware

Kalibrasi disimpan ke LittleFS di D1 Mini — tidak hilang saat restart/flash ulang.

---

## Dashboard

### Tab Monitor

- **Live Feed**: Video dari ESP32-CAM dengan bounding box orang dan garis zona
- **Deteksi Orang**: Jumlah total, zona atas, zona bawah
- **AC Daikin**: Status on/off (yang diinginkan sistem), suhu & kelembaban dari DHT22, tombol manual Power/Temp+/Temp−
- **Lampu**: Status relay, tombol nyala/mati manual
- **Log Aksi**: 15 aksi terakhir dengan timestamp

### Tab Kalibrasi Servo

Panel interaktif untuk mengkalibrasi ketiga servo tanpa edit kode.

### Tab Settings

Ubah parameter sistem secara langsung (tersimpan ke `settings.json`, langsung berlaku tanpa restart):

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| YOLO Confidence | 0.5 | Threshold keyakinan deteksi orang |
| Threshold AC | 1 | Minimal orang agar AC menyala |
| Threshold Lampu | 1 | Minimal orang agar lampu menyala |
| Zone Split Ratio | 0.5 | Posisi garis zona di video (0=atas, 1=bawah) |
| Interval DHT22 | 10 | Seberapa sering baca sensor suhu (detik) |

---

## API Node Aktuator (D1 Mini / ESP32)

Bisa diakses langsung dari browser/curl untuk testing:

```bash
# Cek status node
curl http://192.168.1.101/health

# Baca sensor DHT22
curl http://192.168.1.101/sensor

# Gerakin servo (untuk kalibrasi manual)
curl -X POST "http://192.168.1.101/servo/move?id=0&angle=90"

# Klik servo (pakai kalibrasi tersimpan)
curl -X POST "http://192.168.1.101/servo/click?id=0"

# Simpan kalibrasi servo
curl -X POST "http://192.168.1.101/servo/calibrate?id=0&stay=90&click=150"

# Lihat semua kalibrasi
curl http://192.168.1.101/servo/config

# Kontrol relay lampu
curl -X POST "http://192.168.1.101/relay?state=ON"
curl -X POST "http://192.168.1.101/relay?state=OFF"
```

---

## Konfigurasi

Semua konfigurasi ada di `server_ai/config.py`. Nilai bisa di-override via environment variable:

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `ESP32_STREAM_URL` | `http://192.168.1.100:81/stream` | URL stream ESP32-CAM |
| `ACTUATOR_URL` | `http://192.168.1.101` | IP node D1 Mini |
| `ACTUATOR_TIMEOUT` | `2` | Timeout HTTP ke D1 Mini (detik) |
| `PERSON_THRESHOLD_AC` | `1` | Minimal orang untuk nyalakan AC |
| `PERSON_THRESHOLD_LAMP` | `1` | Minimal orang untuk nyalakan lampu |
| `ZONE_SPLIT_RATIO` | `0.5` | Pembagi zona frame (untuk visualisasi) |
| `YOLO_MODEL_PATH` | `weights/yolov8n.pt` | Path model YOLOv8 |
| `YOLO_CONFIDENCE` | `0.5` | Threshold confidence |
| `DASHBOARD_PORT` | `5000` | Port Flask |
| `DHT22_POLL_INTERVAL` | `10` | Interval polling sensor suhu (detik) |

---

## Library Arduino yang Dibutuhkan

Install via Arduino IDE → Library Manager:

| Library | Dibutuhkan untuk |
|---------|-----------------|
| `ESP8266Servo` (D1 Mini) **atau** `ESP32Servo` (ESP32) | Kontrol servo SG90 |
| `DHTesp` by beegee-tokyo | Sensor DHT22 |
| `ArduinoJson` by Benoit Blanchon | JSON response API |
| ESP8266/ESP32 Board Package | Semua firmware |

---

## Lisensi

MIT License — lihat file [LICENSE](LICENSE) untuk detail.
