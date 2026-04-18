# Panduan Kontribusi

Terima kasih telah tertarik untuk berkontribusi pada proyek ini!

## Cara Berkontribusi

### Melaporkan Bug
1. Pastikan bug belum dilaporkan di [Issues](../../issues)
2. Buka issue baru menggunakan template **Bug Report**
3. Sertakan langkah reproduksi, pesan error, dan informasi environment

### Mengusulkan Fitur
1. Buka issue baru menggunakan template **Feature Request**
2. Jelaskan fitur yang diinginkan dan alasan kebutuhannya
3. Diskusikan pendekatan implementasi sebelum membuat PR

### Membuat Pull Request

1. **Fork** repository ini
2. Buat branch baru dari `main`:
   ```bash
   git checkout -b fitur/nama-fitur
   ```
3. Lakukan perubahan sesuai panduan kode di bawah
4. Commit dengan pesan yang deskriptif:
   ```bash
   git commit -m "feat: tambah deteksi zona ketiga"
   ```
5. Push ke fork kamu dan buat Pull Request ke branch `main`

## Panduan Kode

### Python (`server_ai/`)
- Gunakan Python 3.9+
- Ikuti [PEP 8](https://peps.python.org/pep-0008/) untuk style guide
- Tambahkan docstring pada setiap fungsi publik
- Jalankan sebelum commit:
  ```bash
  pip install flake8
  flake8 server_ai/
  ```

### Arduino / C++ (`edge_node/`)
- Gunakan indentasi 2 spasi (konvensi Arduino)
- Tambahkan komentar untuk setiap fungsi utama
- Uji sketch di hardware fisik sebelum PR

## Setup Development

```bash
# Clone repo
git clone https://github.com/<username>/indoor-monitoring.git
cd indoor-monitoring

# Setup Python environment
cd server_ai
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # Linux/Mac
pip install -r requirements.txt

# Unduh model YOLOv8
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# Pindahkan ke folder weights/
```

## Konvensi Commit

Format: `<type>: <deskripsi singkat>`

| Type | Digunakan untuk |
|------|----------------|
| `feat` | Fitur baru |
| `fix` | Perbaikan bug |
| `docs` | Perubahan dokumentasi |
| `refactor` | Refactoring kode |
| `test` | Menambah/mengubah test |
| `chore` | Pemeliharaan (dependency update, dll.) |
