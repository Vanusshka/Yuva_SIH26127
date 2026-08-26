# UrbanEye AI — Backend Dockerfile
# Suitable for Railway, Render, Google Cloud Run, or any Docker host.
# Uses Python 3.12 slim (good wheel support for torch/ultralytics/easyocr).

FROM python:3.12-slim

# Install system dependencies required by OpenCV and EasyOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1-mesa-glx \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# torch CPU build — explicit index so pip gets the right wheel fast
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/input data/output data/processed data/raw/traffic_images \
    data/raw/traffic_videos data/raw/license_plates data/metadata models

# Copy metadata files
COPY data/metadata/ data/metadata/

# Seed the database on startup (handled by app itself via init_db())

# Expose port (Railway/Render use $PORT environment variable)
ENV PORT=8000
EXPOSE $PORT

# Start the server
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
