## 1. Persiapan Awal

Install Python (versi 3.9+) dan Docker di sistem Anda.

## 2. Setup Lingkungan Virtual (Virtual Environment)

Buka terminal di dalam folder proyek, lalu jalankan perintah berikut untuk membuat dan mengaktifkan virtual environment:

```bash
# Membuat virtual environment
python3 -m venv .venv

# Mengaktifkan virtual environment (Linux/macOS)
source .venv/bin/activate

# Jika menggunakan Windows:
# .venv\Scripts\activate
```

## 3. Install Dependencies

Setelah virtual environment aktif (ditandai dengan awalan `(.venv)` di terminal), install semua pustaka yang dibutuhkan:

```bash
pip install -r requirements.txt
```

## 4. Konfigurasi Database

Aplikasi membutuhkan database PostgreSQL. Jalankan PostgreSQL menggunakan Docker dari file konfigurasi yang sudah tersedia.

```bash
# Menjalankan PostgreSQL di background
docker compose up -d
```

Pastikan file konfigurasi `.env` sudah ada. Jika belum, salin dari `.env.example`:

```bash
cp .env.example .env
```

## 5. Inisialisasi Database dan Seeder

Jalankan script inisialisasi untuk membuat semua tabel yang dibutuhkan ke dalam database:

```bash
python3 init_db.py

python3 seed_users.py
```

## 6. Menjalankan Server Aplikasi

Jalankan server FastAPI menggunakan `uvicorn`:

```bash
uvicorn app.main:app --reload
```

Aplikasi sekarang dapat diakses secara lokal.
- API Endpoint: http://127.0.0.1:8000
- Dokumentasi API (Swagger UI): http://127.0.0.1:8000/docs
- Dokumentasi API (ReDoc): http://127.0.0.1:8000/redoc

## 7. Mematikan Aplikasi

- Untuk mematikan server FastAPI, tekan `CTRL+C` di terminal tempat `uvicorn` berjalan.
- Untuk keluar dari virtual environment, ketik `deactivate`.
- Untuk mematikan database PostgreSQL, ketik `docker compose down`.
