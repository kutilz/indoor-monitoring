# Skema Rangkaian

Folder ini menyimpan file skema rangkaian hardware proyek.

## File yang Diharapkan

| File | Deskripsi |
|------|-----------|
| `esp32_cam_wiring.fzz` | Skema Fritzing ESP32-CAM + Power Supply |
| `relay_module_wiring.fzz` | Skema Fritzing ESP32 + Modul Relay 4-Channel |
| `full_system.fzz` | Skema sistem lengkap |
| `esp32_cam_wiring.png` | Export PNG untuk dokumentasi |
| `relay_module_wiring.png` | Export PNG untuk dokumentasi |

## Komponen Utama

### ESP32-CAM (Node Kamera)
- **Board:** AI-Thinker ESP32-CAM
- **Kamera:** OV2640
- **Power:** 5V/2A via pin 5V & GND
- **Koneksi:** WiFi 802.11 b/g/n

### Modul Relay 4-Channel (Aktuator)
- **Tegangan Operasi:** 5V (coil)
- **Beban:** AC 220V, max 10A per channel
- **Sinyal Kontrol:** 3.3V-5V dari GPIO ESP32

### Pinout Relay ke ESP32

| Relay | GPIO ESP32 | Fungsi |
|-------|-----------|--------|
| IN1 | GPIO 12 | AC / Pendingin |
| IN2 | GPIO 13 | Lampu Zona Depan |
| IN3 | GPIO 14 | Lampu Zona Belakang |
| IN4 | GPIO 15 | (Cadangan) |
| VCC | 5V | Power relay module |
| GND | GND | Ground bersama |

> **Peringatan:** Selalu gunakan isolasi yang memadai saat bekerja dengan tegangan AC 220V.
