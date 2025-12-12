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

# Salin library dari build
COPY --from=build /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Salin file Streamlit
COPY praktikum_streamlit.py /app/praktikum_streamlit.py

# Konfigurasi
ENV PORT=8501
EXPOSE 8501

# Jalankan Streamlit
CMD ["streamlit", "run", "praktikum_streamlit.py", "--server.port=8501", "--server.address=0.0.0.0"]
