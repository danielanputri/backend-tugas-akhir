# Menggunakan image slim. Ini adalah best-practice untuk project Machine Learning di Python.
# Image slim sudah memiliki pre-compiled wheels yang dibutuhkan numpy/pandas dkk, 
# sedangkan image alpine sering gagal/sangat memakan RAM dan waktu saat install.
FROM python:3.10-slim

# Optimasi Environment Variable untuk VPS RAM Kecil
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # MALLOC_ARENA_MAX=2 sangat penting untuk VPS 1GB RAM. 
    # Mencegah memory fragmentation pada glibc yang sering bikin aplikasi Python rakus RAM over-time.
    MALLOC_ARENA_MAX=2

WORKDIR /app

# Install dependency sistem untuk build beberapa package (jika dibutuhkan)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install package python dengan flag --no-cache-dir untuk menghemat ratusan MB space pada docker image
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Hapus dependencies build yang sudah tidak terpakai untuk memperkecil size image akhir
RUN apt-get purge -y --auto-remove build-essential && \
    apt-get clean

# Security: Buat user non-root agar jika container jebol, server VPS tetap aman
RUN adduser --disabled-password --gecos "" appuser

# Copy seluruh source code
COPY . .

# Buat folder yang menyimpan state/file dan berikan akses ke appuser
RUN mkdir -p /app/data/uploads /app/app/ml_models && \
    chown -R appuser:appuser /app

# Gunakan non-root user
USER appuser

EXPOSE 8000

# Untuk VPS 1 Core, --workers WAJIB di set ke 1. 
# Jika lebih, Uvicorn akan memakan RAM 2-3x lipat dan membuat VPS 1GB RAM sering mati/OOM (Out Of Memory)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
