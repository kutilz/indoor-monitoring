# Sistem Kendali Cerdas AC & Lampu Ruang Kuliah

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-purple)
![ESP32-CAM](https://img.shields.io/badge/ESP32--CAM-AI%20Thinker-teal?logo=arduino)
![D1 Mini](https://img.shields.io/badge/D1%20Mini-ESP8266-orange?logo=arduino)
![License](https://img.shields.io/badge/License-MIT-green)

Sistem kendali otomatis AC dan lampu berbasis **computer vision (YOLOv8)** dan **IoT (ESP32)**. Kamera mendeteksi keberadaan orang, lalu:

- AC **diklik mati/hidup** otomatis via servo continuous-rotation MG996R yang dijepit ke remote Daikin Cassette
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
| Servo MG996R | 360° continuous rotation, torsi ~9.4 kg·cm | 3 |
| Modul Relay 1-Channel | 5V coil, beban AC 220V/10A | 1 |
| Sensor DHT22 | Suhu & kelembaban | 1 |
| Resistor 10kΩ | Pull-up untuk data DHT22 | 1 |
| Power Supply Servo | **5V/6V eksternal, min. 5A** untuk 3 servo MG996R | 1 |
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

> **Power servo:** MG996R menarik arus jauh lebih besar dari SG90 (stall current ~2.5A per servo @ 6V). Jangan sambungkan servo ke pin VCC/3.3V/5V onboard. Gunakan power supply 5V/6V eksternal **minimal 5A** dengan GND bersama (common GND) ke board.

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

Servo MG996R sudah terpasang di casing 3D-printed pada remote Daikin. Servo ini **continuous-rotation (360°)** — tidak punya posisi sudut. Sinyal PWM hanya menentukan **arah** dan **kecepatan** putar; servo berhenti saat sinyal kembali ke titik netral (~1500µs). Karena orientasi mounting tiap servo berbeda, **arah putar yang menekan tombol AC (CW atau CCW) harus dikalibrasi per servo**.

### Model Kalibrasi

| Parameter | Arti |
|-----------|------|
| **Kecepatan Jog** | Kecepatan putar saat tombol jog ditahan (0-100%) — juga dipakai sebagai kecepatan klik |
| **Arah Klik** | CW atau CCW — arah putar yang menekan tombol AC pada servo ini |
| **Durasi Klik** | Lama servo berputar ke *Arah Klik* untuk menekan tombol (ms) |
| **Durasi Kembali** | Lama servo berputar ke arah berlawanan untuk kembali ke posisi awal (ms) |
| **Trim Netral** | Koreksi titik "stop" (±100µs dari 1500µs) jika servo masih sedikit bergerak saat seharusnya diam |

### Langkah Kalibrasi via Dashboard

1. Buka **http://localhost:5000**
2. Klik tab **🎛️ Kalibrasi Servo**
3. Untuk tiap servo (Power, Temp+, Temp−):
   a. **Tahan** tombol **Putar CW** / **Putar CCW** untuk mengamati arah putar servo terhadap tombol AC — **lepas** untuk berhenti. Atur **Kecepatan Jog** agar putarannya pelan dan terkendali.
   b. Tentukan arah mana (CW/CCW) yang menekan tombol AC, lalu pilih di toggle **Arah Klik**.
   c. Atur **Durasi Klik** (cukup lama untuk menekan tombol sampai "klik") dan **Durasi Kembali** (biasanya sama dengan Durasi Klik agar servo balik ke posisi awal).
   d. Jika servo masih bergerak pelan saat seharusnya diam, geser **Trim Netral** sampai servo benar-benar berhenti.
   e. Klik **⚡ Test Klik** untuk uji coba urutan penuh (klik kalibrasi otomatis disimpan dulu sebelum test).
   f. Jika sudah pas, klik **💾 Simpan Kalibrasi**.

Kalibrasi disimpan ke LittleFS di node aktuator — tidak hilang saat restart/flash ulang.

### Safety: Watchdog Servo

Karena MG996R bertorsi besar, ada beberapa lapisan pengaman bawaan firmware:

- **Heartbeat jog**: selama tombol jog ditahan, dashboard mengirim perintah jog berulang (~150ms). Jika tidak ada perintah baru dalam **400ms** (mis. koneksi putus), servo **otomatis berhenti**.
- **Batas durasi absolut**: jog otomatis berhenti setelah **4 detik** berjalan terus-menerus, walau heartbeat masih masuk — proteksi terhadap bug frontend.
- **WiFi putus = stop instan**: jika node aktuator kehilangan koneksi WiFi, semua servo langsung dihentikan (tidak menunggu watchdog).
- **Emergency stop**: tombol **🛑 STOP SEMUA SERVO** di tab Kalibrasi menghentikan semua servo segera, dan otomatis terpanggil saat tab/halaman ditutup atau disembunyikan.

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

# Jog servo (putar selama "ditahan" — panggil berulang ~150ms sbg heartbeat)
curl -X POST "http://192.168.1.101/servo/jog?id=0&dir=CW&speed=20"

# Hentikan satu servo segera
curl -X POST "http://192.168.1.101/servo/stop?id=0"

# Hentikan SEMUA servo segera (emergency stop)
curl -X POST "http://192.168.1.101/servo/stop_all"

# Klik servo (pakai kalibrasi tersimpan: arah, kecepatan, durasi)
curl -X POST "http://192.168.1.101/servo/click?id=0"

# Simpan kalibrasi servo (dir: CW/CCW, speed: 0-100, durasi dalam ms, trim: -100..100)
curl -X POST "http://192.168.1.101/servo/calibrate?id=0&dir=CW&speed=30&click_ms=300&return_ms=300&trim=0"

# Lihat semua kalibrasi
curl http://192.168.1.101/servo/config

# Kontrol relay lampu
curl -X POST "http://192.168.1.101/relay?state=ON"
curl -X POST "http://192.168.1.101/relay?state=OFF"
```

> ⚠️ Jika `/servo/jog` dipanggil tanpa heartbeat lanjutan (mis. lewat curl sekali saja), servo akan **otomatis berhenti dalam ≤400ms** karena watchdog firmware — ini disengaja (lihat bagian Safety di Panduan Kalibrasi).

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
| `ESP8266Servo` (D1 Mini) **atau** `ESP32Servo` (ESP32) | Kontrol servo MG996R (continuous rotation) |
| `DHTesp` by beegee-tokyo | Sensor DHT22 |
| `ArduinoJson` by Benoit Blanchon | JSON response API |
| ESP8266/ESP32 Board Package | Semua firmware |

---

## Lisensi

MIT License — lihat file [LICENSE](LICENSE) untuk detail.
