# Brainstorming Sistem Prediksi Stok dengan ARIMA

## 1. Problem Statement

### Masalah Utama
Admin pembelian saat ini kesulitan menentukan jumlah stok yang harus dipesan untuk bulan depan. Kondisi ini menyebabkan:
- **Overstock**: Menumpuk barang yang tidak laku, modal tertahan
- **Stockout**: Kehilangan penjualan karena barang habis
- **Keputusan subjektif**: Bergantung pada "feeling" atau perkiraan manual yang tidak akurat

### Target Pengguna
- Admin pembelian/procurement
- Manager inventory
- Business owner yang mengelola stok

### Nilai yang Diharapkan
Sistem yang dapat memprediksi kebutuhan stok secara data-driven berdasarkan pola penjualan historis, sehingga keputusan pembelian lebih akurat dan terukur.

---

## 2. Core Features MVP

### A. Autentikasi & Manajemen User
**Tujuan**: Keamanan dan tracking siapa yang menggunakan sistem

**Sub-fitur**:
- Login/Logout
- Manajemen akun (ubah password0
- Role sederhana: Admin (bisa semua) dan Manajer (hanya lihat prediksi)

---

### B. Dashboard Overview
**Tujuan**: Memberikan gambaran cepat kondisi stok dan performa prediksi

**Komponen**:
- **Summary Cards**: 
  - Total produk yang dipantau
  - Akurasi rata-rata prediksi bulan lalu (vs aktual)
  - Produk yang butuh perhatian (prediksi tinggi atau rendah drastis)
  
- **Grafik Ringkasan**:
  - Tren penjualan 6 bulan terakhir (aggregate semua produk)
  - Perbandingan prediksi vs aktual bulan lalu

- **Alert/Notifikasi**:
  - Model yang sudah lama tidak di-update

---

### C. Upload & Parse Data Penjualan
**Tujuan**: Input data historis dari sistem POS untuk dianalisis

**Alur Kerja**:
1. **Upload File Excel**
   - Format yang diharapkan: kolom (Tanggal, Kode Produk, Nama Produk, Jumlah Terjual)
   - Validasi format otomatis
   
2. **Preview Data**
   - Tampilkan 10-20 baris pertama untuk verifikasi
   - Deteksi otomatis kolom yang dibutuhkan
   
3. **Konfirmasi & Import**
   - Pilihan: "Tambah data baru"
   - Simpan ke database tabel `penjualan`

**Validasi Penting**:
- Cek data duplikat (tanggal + produk yang sama)
- Cek format tanggal
- Cek jumlah terjual (harus angka positif)

---

### D. Prediksi Penjualan
**Tujuan**: Generate prediksi untuk bulan depan per produk

**Alur Kerja**:
1. **Pilih Produk**
   - Dropdown atau search produk
   - Atau "Prediksi Semua Produk" (batch processing)

2. **Setting Parameter**:
   - Jumlah bulan yang ingin diprediksi (default: 1 bulan)

3. **Jalankan Prediksi**
   - Sistem load model ARIMA yang sudah ada
   - Proses prediksi
   - Tampilkan hasil

**Output yang Ditampilkan**:
- **Prediksi angka**: "Prediksi penjualan bulan depan: 150 unit"
- **Confidence interval**: Rentang (misalnya 130-170 unit)
- **Visualisasi grafik**: 
  - Data historis 6-12 bulan
  - Garis prediksi bulan depan
  - Shaded area untuk confidence interval
- **Rekomendasi**: "Disarankan order 160 unit (prediksi + buffer 10%)"

**Simpan Hasil**:
- Log prediksi ke tabel `hasil_prediksi` (produk, tanggal_prediksi, nilai_prediksi, confidence_interval)

---

### E. Latih Ulang Model (Retrain)
**Tujuan**: Update model dengan data penjualan terbaru agar prediksi lebih akurat

**Alur Kerja**:
1. **Trigger Manual**
   - Tombol "Latih Ulang Model" di halaman prediksi untuk all products

2. **Proses Training**
   - Ambil semua data dari tabel `penjualan` untuk produk tersebut
   - Jalankan ARIMA fitting dengan parameter optimal (auto ARIMA)
   - Progress bar/loading indicator

3. **Evaluasi Model**
   - Hitung metrik: MAE, RMSE, MAPE
   - Bandingkan dengan model lama
   - Jika lebih baik → save sebagai `model_v2.pkl`
   - Jika lebih buruk → tetap pakai model lama, beri warning

4. **Notifikasi**
   - "Model berhasil diperbarui. Akurasi meningkat dari 85% menjadi 89%"
   - Atau "Model tidak diperbarui. Performa tidak lebih baik dari model sebelumnya"

**Logging**:
- Catat setiap training: tanggal, produk, metrik performa, status (sukses/gagal)

---

### F. Riwayat & Evaluasi Prediksi
**Tujuan**: Tracking akurasi prediksi untuk continuous improvement

**Komponen**:
1. **Tabel Riwayat Prediksi**
   - Kolom: Produk, Tanggal Prediksi, Nilai Prediksi, Nilai Aktual, Selisih, Akurasi (%)
   - Filter by produk, rentang tanggal

2. **Grafik Performa**
   - Plot prediksi vs aktual untuk lihat pola error
   - Tren akurasi over time

**Use Case**:
- Admin bisa evaluasi: "Prediksi bulan Januari meleset 20%, kenapa?"
- Data ini juga bisa untuk improve model (feature engineering)

---

## 3. Arsitektur Aplikasi

### A. Tech Stack

**Backend**:
- **Framework**: Python Flask atau FastAPI
  - Alasan: Ekosistem Python kuat untuk machine learning (scikit-learn, statsmodels untuk ARIMA)
  - Flask: Lebih simple untuk MVP
  - FastAPI: Lebih modern, auto-documentation
  
- **Database**: PostgreSQL
  - Relasional database cocok untuk data terstruktur (penjualan, user, prediksi)
  
- **ML Libraries**: 
  - `statsmodels` atau `pmdarima` untuk ARIMA
  - `pandas` untuk data manipulation
  - `joblib` atau `pickle` untuk save/load model

**Frontend**:
- **Framework**: Next.Js
  - Untuk UI interaktif (upload file, real-time chart update)
  
- **UI Library**: Tailwind CSS atau Material-UI
  - Percepat development dengan komponen siap pakai
  
- **Charting**: Chart.js atau Recharts
  - Untuk visualisasi grafik time series

---

### B. Database Schema (Simplified)

```sql
-- Tabel: users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user', -- 'admin' or 'user'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tabel: penjualan
CREATE TABLE penjualan (
    id SERIAL PRIMARY KEY,
    tanggal DATE NOT NULL,
    kode_produk VARCHAR(50) NOT NULL,
    nama_produk VARCHAR(255) NOT NULL,
    jumlah_terjual DECIMAL(10,2) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tanggal, kode_produk)
);

-- Tabel: models
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    kode_produk VARCHAR(50) NOT NULL,
    file_path VARCHAR(255), -- lokasi file .pkl
    version INT DEFAULT 1,
    mae DECIMAL(10,4),
    rmse DECIMAL(10,4),
    mape DECIMAL(10,4),
    trained_at TIMESTAMP DEFAULT NOW()
);

-- Tabel: hasil_prediksi
CREATE TABLE hasil_prediksi (
    id SERIAL PRIMARY KEY,
    kode_produk VARCHAR(50) NOT NULL,
    tanggal_prediksi DATE NOT NULL, -- untuk bulan mana
    nilai_prediksi DECIMAL(10,2),
    confidence_lower DECIMAL(10,2),
    confidence_upper DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tabel: training_logs
CREATE TABLE training_logs (
    id SERIAL PRIMARY KEY,
    kode_produk VARCHAR(50) NOT NULL,
    status VARCHAR(20), -- 'success', 'failed'
    mae_before DECIMAL(10,4),
    mae_after DECIMAL(10,4),
    mape_before DECIMAL(10,4),
    mape_after DECIMAL(10,4),
    trained_at TIMESTAMP DEFAULT NOW()
);
```

---

### C. Alur Kerja Sistem (Flow)

#### Flow 1: Upload Data Pertama Kali
1. User login
2. Upload file Excel penjualan historis (minimal 12-24 bulan untuk ARIMA)
3. Sistem parse dan simpan ke tabel `penjualan`
4. Sistem otomatis latih model untuk setiap produk
5. Model tersimpan sebagai `model_{kode_produk}_v1.pkl`

#### Flow 2: Prediksi Rutin
1. Admin buka halaman "Prediksi"
2. Pilih produk atau "Prediksi Semua"
3. Klik "Jalankan Prediksi"
4. Sistem load model terbaru dari tabel `models`
5. Hasil ditampilkan + disimpan ke `hasil_prediksi`
6. Admin lihat rekomendasi order

#### Flow 3: Update Berkala
1. Setiap bulan, admin upload data penjualan bulan lalu
2. Data baru ditambahkan ke tabel `penjualan`
3. Admin klik "Latih Ulang Model" (bisa untuk 1 produk atau all)
4. Sistem re-train ARIMA dengan data terbaru
5. Jika akurasi lebih baik → save sebagai versi baru
6. Admin jalankan prediksi lagi dengan model terbaru

---

## 5. Error Handling
- Upload file salah format → beri contoh template
- Model gagal converge → fallback ke simple moving average
- Data terlalu sedikit → warning ke user

---

## 5. Roadmap Development

### Phase 1: MVP (2-4 minggu)
- Setup project & database
- Autentikasi basic
- Upload & parse Excel
- Training model ARIMA 
- Prediksi & tampilkan hasil
- UI Dasar

### Phase 2: Enhancement (2-3 minggu)
- Multi-produk support
- Dashboard dengan visualisasi
- Riwayat prediksi
- Evaluasi akurasi

### Phase 3: Optimization (ongoing)
- Auto-retraining scheduler
- Improve UI/UX
- Export hasil prediksi ke Excel
- Notifikasi email/WhatsApp
- Parameter tuning otomatis

---

### Kriteria Sukses MVP:
- Sistem bisa prediksi minimal 5 produk berbeda
- User bisa prediksi dalam 15 detik
- Model bisa di-retrain dengan data baru dalam < 5 menit
