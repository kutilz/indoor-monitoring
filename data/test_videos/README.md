# Video Uji Coba

Folder ini menyimpan video dummy untuk pengujian sistem tanpa hardware (Mode Akuisisi).

> **Catatan:** File video tidak di-commit ke repository (tercantum di `.gitignore`).
> Unduh atau buat sendiri sesuai panduan di bawah.

## Spesifikasi Video yang Disarankan

| Parameter | Nilai |
|-----------|-------|
| Resolusi | 800x600 atau 1280x720 |
| Frame Rate | 15-30 fps |
| Format | `.mp4` (H.264) atau `.avi` |
| Durasi | 30 detik - 5 menit |
| Konten | Video ruang kelas / ruangan dengan orang berjalan |

## Cara Mendapatkan Video Uji

### Opsi 1: Rekam Sendiri
Rekam video ruang kelas dengan smartphone, pastikan:
- Sudut pandang dari atas/depan (simulasi ESP32-CAM)
- Terdapat 1-10 orang dalam frame
- Pencahayaan cukup untuk deteksi YOLOv8

### Opsi 2: Download Dataset Publik
- [MOT Challenge](https://motchallenge.net/) - dataset tracking orang
- [VIRAT Video Dataset](https://viratdata.org/) - video surveillance ruangan
- [UCF Crime Dataset](https://www.crcv.ucf.edu/research/real-world-anomaly-detection/) - indoor scenes

### Opsi 3: Buat Video Sintetis dengan OpenCV
```python
# Jalankan script ini untuk membuat video dummy sederhana
import cv2
import numpy as np

out = cv2.VideoWriter('sample_class.mp4',
                      cv2.VideoWriter_fourcc(*'mp4v'), 20, (800, 600))
for i in range(300):  # 15 detik
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    cv2.putText(frame, f'Dummy Frame {i}', (50, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 2)
    out.write(frame)
out.release()
```

## Menjalankan dengan Video Uji

```bash
cd server_ai
python main.py --mode akuisisi --source ../data/test_videos/sample_class.mp4
```
