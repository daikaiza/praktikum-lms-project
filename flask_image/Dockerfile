# ==========================
# Stage 1: Build dependencies
# ==========================
FROM python:3.10 AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================
# Stage 2: Runtime
# ==========================
FROM python:3.10-slim
WORKDIR /app

# Salin dependensi yang sudah terinstal
COPY --from=build /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Salin file aplikasi
COPY praktikum_api.py /app/praktikum_api.py

# Konfigurasi
ENV PORT=5000
EXPOSE 5000

# Jalankan Flask app
CMD ["python", "praktikum_api.py"]
