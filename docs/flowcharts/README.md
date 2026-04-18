# Diagram Alir Sistem

Folder ini menyimpan diagram alir (flowchart) sistem.

## File yang Diharapkan

| File | Deskripsi |
|------|-----------|
| `system_overview.drawio` | Diagram arsitektur sistem keseluruhan |
| `ai_pipeline.drawio` | Alur pemrosesan AI (frame → deteksi → keputusan) |
| `control_logic.drawio` | Logika kendali zoning & threshold |
| `esp32_cam_flow.drawio` | Flowchart firmware ESP32-CAM |
| `esp32_relay_flow.drawio` | Flowchart firmware ESP32 Relay |

## Alur Sistem Utama

```
[ESP32-CAM]
    │
    │ MJPEG HTTP Stream
    ▼
[Python Server - main.py]
    │
    ├─► [stream_source.py] → Baca frame
    │
    ├─► [yolo_detector.py] → Deteksi person (YOLOv8)
    │       └── Output: list bbox + confidence
    │
    ├─► [control_logic.py] → Hitung zona
    │       ├── Zone Depan: person dengan bbox center Y < split_y
    │       ├── Zone Belakang: person dengan bbox center Y >= split_y
    │       └── Output: {ac, light_front, light_back}
    │
    ├─► [mqtt_client / mock_mqtt] → Kirim perintah relay
    │
    └─► [dashboard/app.py] → Update tampilan web real-time
```

## Tools yang Disarankan
- [draw.io](https://app.diagrams.net/) untuk membuat/mengedit diagram
- Export ke PNG/SVG untuk dokumentasi skripsi
